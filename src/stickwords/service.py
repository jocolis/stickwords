from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from .importer import ImportResult, import_words
from .models import (
    STATUS_NEW,
    STATUS_REVIEW,
    STATUS_SUSPENDED,
    Word,
    normalize_dt,
)
from .scheduler import get_today_tasks as schedule_today_tasks
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

    def get_status(self) -> dict[str, int]:
        words = self.load_words()
        return {
            "total_words": len(words),
            "new_words": sum(1 for word in words if word.status == STATUS_NEW),
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
