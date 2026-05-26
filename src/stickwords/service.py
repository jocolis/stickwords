from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .importer import ImportResult, import_words
from .models import (
    RATING_FORGOT,
    RATING_GOOD,
    RATING_HARD,
    STATUS_LEARNING,
    STATUS_NEW,
    STATUS_REVIEW,
    STATUS_SUSPENDED,
    Word,
    format_dt,
    normalize_dt,
    parse_dt,
)
from .reviews import ReviewEvent, ReviewEventStore, process_review_events
from .scheduler import (
    get_offline_package as schedule_offline_package,
    get_today_tasks as schedule_today_tasks,
)
from .storage import VocabStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StickWordsService:
    data_dir: Path | str
    clock: Callable[[], datetime] = utc_now

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.vocab_store = VocabStore(self.data_dir / "vocab.csv")

    def now(self) -> datetime:
        return normalize_dt(self.clock())

    def load_words(self) -> list[Word]:
        return self.vocab_store.load()

    def save_words(self, words: list[Word]) -> None:
        self.vocab_store.save(words)

    def next_word_id(self, words: list[Word]) -> str:
        max_number = 0
        for word in words:
            prefix, separator, suffix = word.id.partition("-")
            if prefix == "w" and separator == "-" and suffix.isdigit():
                max_number = max(max_number, int(suffix))

        return f"w-{max_number + 1:06d}"

    def add_word(self, word: str, meaning: str, example: str) -> Word:
        words = self.load_words()
        new_word = Word.new_word(
            word_id=self.next_word_id(words),
            word=word,
            meaning=meaning,
            example=example,
            now=self.now(),
        )
        words.append(new_word)
        self.save_words(words)
        return new_word

    def add_or_update_word(
        self,
        word: str,
        meaning: str,
        example: str,
    ) -> tuple[str, Word]:
        words = self.load_words()
        now = self.now()
        key = word.strip().casefold()
        for existing in words:
            if existing.word.casefold() == key:
                existing.word = word.strip()
                existing.meaning = meaning.strip()
                existing.example = example.strip()
                existing.updated_at = now
                self.save_words(words)
                return "updated", existing

        new_word = Word.new_word(
            word_id=self.next_word_id(words),
            word=word,
            meaning=meaning,
            example=example,
            now=now,
        )
        words.append(new_word)
        self.save_words(words)
        return "created", new_word

    def edit_word(self, word_id: str, *, meaning: str, example: str) -> Word:
        words = self.load_words()
        now = self.now()
        for word in words:
            if word.id == word_id:
                word.meaning = meaning.strip()
                word.example = example.strip()
                word.updated_at = now
                self.save_words(words)
                return word

        raise KeyError(f"unknown word_id: {word_id}")

    def suspend_word(self, word_id: str) -> Word:
        words = self.load_words()
        now = self.now()
        for word in words:
            if word.id == word_id:
                word.status = STATUS_SUSPENDED
                word.updated_at = now
                self.save_words(words)
                return word

        raise KeyError(f"unknown word_id: {word_id}")

    def import_csv_text(self, csv_text: str) -> ImportResult:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.data_dir / f"import-{uuid4().hex}.csv"
        try:
            temp_path.write_text(csv_text, encoding="utf-8-sig", newline="")
            result = import_words(self.load_words(), temp_path, self.now())
            self.save_words(result.words)
            return result
        finally:
            temp_path.unlink(missing_ok=True)

    def get_today_tasks(self, max_due: int = 20, max_new: int = 5) -> list[Word]:
        return schedule_today_tasks(
            self.load_words(),
            self.now(),
            max_due=max_due,
            max_new=max_new,
        )

    def _device_card_payload(self, word: Word) -> dict:
        return {
            "id": word.id,
            "word": word.word,
            "meaning": word.meaning,
            "example": word.example,
            "status": word.status,
            "due_at": format_dt(word.due_at),
            "review_count": word.review_count,
            "ease": word.ease,
            "interval_days": word.interval_days,
            "lapses": word.lapses,
        }

    def device_tasks_payload(self, limit: int = 20) -> dict:
        limit = max(0, min(limit, 50))
        now = self.now()
        words = self.load_words()
        tasks = schedule_today_tasks(words, now, max_due=limit, max_new=limit)
        offline_cards = schedule_offline_package(
            words,
            now,
            horizon_days=7,
            max_due=20,
            max_new=20,
        )
        return {
            "generated_at": format_dt(now),
            "tasks": [self._device_card_payload(word) for word in tasks[:limit]],
            "offline": {
                "horizon_days": 7,
                "max_new": 20,
                "cards": [self._device_card_payload(word) for word in offline_cards],
            },
        }

    def process_device_reviews(self, payload: dict) -> dict:
        raw_reviews = payload.get("reviews")
        if not isinstance(raw_reviews, list):
            raise ValueError("reviews must be a list")

        events: list[ReviewEvent] = []
        failed = 0
        errors: list[str] = []
        valid_ratings = {RATING_FORGOT, RATING_HARD, RATING_GOOD}

        for index, raw in enumerate(raw_reviews):
            if not isinstance(raw, dict):
                failed += 1
                errors.append(f"reviews[{index}] must be an object")
                continue

            try:
                word_id = str(raw.get("word_id", "")).strip()
                rating = str(raw.get("rating", "")).strip()
                event_id = str(raw.get("event_id", "")).strip()
                reviewed_at = parse_dt(str(raw.get("reviewed_at", "")).strip())
                if word_id == "":
                    raise ValueError("word_id is required")
                if event_id == "":
                    raise ValueError("event_id is required")
                if rating not in valid_ratings:
                    raise ValueError(f"invalid rating: {rating}")
                if reviewed_at is None:
                    raise ValueError("reviewed_at is required")

                events.append(
                    ReviewEvent(
                        review_event_id=event_id,
                        word_id=word_id,
                        rating=rating,
                        reviewed_at=reviewed_at,
                    )
                )
            except ValueError as exc:
                failed += 1
                errors.append(f"reviews[{index}]: {exc}")

        result = process_review_events(
            words=self.load_words(),
            events=events,
            event_store=ReviewEventStore(self.data_dir / "review_events.csv"),
        )
        self.save_words(result.words)

        return {
            "accepted": result.applied,
            "skipped_duplicate": result.skipped_duplicate,
            "failed": failed + result.failed,
            "errors": errors + result.errors,
        }

    def get_status(self) -> dict[str, int]:
        words = self.load_words()
        return {
            "total_words": len(words),
            "new_words": sum(1 for word in words if word.status == STATUS_NEW),
            "learning_words": sum(
                1 for word in words if word.status == STATUS_LEARNING
            ),
            "review_words": sum(1 for word in words if word.status == STATUS_REVIEW),
            "suspended_words": sum(
                1 for word in words if word.status == STATUS_SUSPENDED
            ),
            "due_today": len(self.get_today_tasks()),
        }

    def recent_words(self, limit: int = 50) -> list[Word]:
        words = self.load_words()
        words.sort(
            key=lambda word: (normalize_dt(word.updated_at), word.word.casefold()),
            reverse=True,
        )
        return words[:limit]
