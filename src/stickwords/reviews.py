from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Word, format_dt, normalize_dt, parse_dt
from .scheduler import apply_review

REVIEW_EVENT_FIELDS = ["review_event_id", "word_id", "rating", "reviewed_at"]


@dataclass(frozen=True)
class ReviewEvent:
    review_event_id: str
    word_id: str
    rating: str
    reviewed_at: datetime

    def to_row(self) -> dict[str, str]:
        return {
            "review_event_id": self.review_event_id,
            "word_id": self.word_id,
            "rating": self.rating,
            "reviewed_at": format_dt(self.reviewed_at),
        }

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "ReviewEvent":
        reviewed_at = parse_dt(row["reviewed_at"])
        if reviewed_at is None:
            raise ValueError("reviewed_at is required")
        return cls(
            review_event_id=row["review_event_id"],
            word_id=row["word_id"],
            rating=row["rating"],
            reviewed_at=reviewed_at,
        )


@dataclass
class ReviewProcessResult:
    words: list[Word]
    applied: int
    skipped_duplicate: int
    failed: int
    errors: list[str]


class ReviewEventStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return {
                row["review_event_id"]
                for row in reader
                if row.get("review_event_id")
            }

    def append(self, event: ReviewEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.path.exists()
        with self.path.open("a", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=REVIEW_EVENT_FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow(event.to_row())


def process_review_events(
    *,
    words: list[Word],
    events: list[ReviewEvent],
    event_store: ReviewEventStore,
) -> ReviewProcessResult:
    by_id = {word.id: word for word in words}
    processed_ids = event_store.load_ids()
    applied = 0
    skipped_duplicate = 0
    failed = 0
    errors: list[str] = []

    normalized_events = [
        ReviewEvent(
            review_event_id=raw_event.review_event_id,
            word_id=raw_event.word_id,
            rating=raw_event.rating,
            reviewed_at=normalize_dt(raw_event.reviewed_at),
        )
        for raw_event in events
    ]
    normalized_events.sort(key=lambda event: (event.reviewed_at, event.review_event_id))

    for event in normalized_events:
        if event.review_event_id in processed_ids:
            skipped_duplicate += 1
            continue

        if event.word_id not in by_id:
            failed += 1
            errors.append(f"unknown word_id: {event.word_id}")
            continue

        updated = apply_review(
            by_id[event.word_id],
            event.rating,
            event.reviewed_at,
        )
        by_id[event.word_id] = updated
        processed_ids.add(event.review_event_id)
        event_store.append(event)
        applied += 1

    updated_words = [by_id[word.id] for word in words]
    return ReviewProcessResult(
        words=updated_words,
        applied=applied,
        skipped_duplicate=skipped_duplicate,
        failed=failed,
        errors=errors,
    )
