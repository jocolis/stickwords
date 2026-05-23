from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping


STATUS_NEW = "new"
STATUS_LEARNING = "learning"
STATUS_REVIEW = "review"
STATUS_SUSPENDED = "suspended"

RATING_FORGOT = "forgot"
RATING_HARD = "hard"
RATING_GOOD = "good"

VOCAB_FIELDS = [
    "id",
    "word",
    "meaning",
    "example",
    "status",
    "added_at",
    "last_reviewed_at",
    "due_at",
    "review_count",
    "ease",
    "interval_days",
    "lapses",
    "updated_at",
]


def normalize_dt(value: datetime) -> datetime:
    """Return a timezone-aware UTC datetime with second precision."""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc).replace(microsecond=0)


def format_dt(value: datetime | None) -> str:
    if value is None:
        return ""

    return normalize_dt(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_dt(value: str) -> datetime | None:
    if value == "":
        return None

    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"

    return normalize_dt(datetime.fromisoformat(value))


@dataclass
class Word:
    id: str
    word: str
    meaning: str
    example: str
    status: str
    added_at: datetime
    last_reviewed_at: datetime | None
    due_at: datetime
    review_count: int
    ease: float
    interval_days: int
    lapses: int
    updated_at: datetime

    @classmethod
    def new_word(
        cls,
        word_id: str,
        word: str,
        meaning: str,
        example: str,
        now: datetime,
    ) -> Word:
        now = normalize_dt(now)
        return cls(
            id=word_id,
            word=word.strip(),
            meaning=meaning.strip(),
            example=example.strip(),
            status=STATUS_NEW,
            added_at=now,
            last_reviewed_at=None,
            due_at=now,
            review_count=0,
            ease=2.5,
            interval_days=0,
            lapses=0,
            updated_at=now,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, str]) -> Word:
        last_reviewed_at = parse_dt(row["last_reviewed_at"])
        if last_reviewed_at is not None and not isinstance(last_reviewed_at, datetime):
            raise ValueError("last_reviewed_at must be a datetime or blank")

        return cls(
            id=row["id"],
            word=row["word"],
            meaning=row["meaning"],
            example=row["example"],
            status=row["status"],
            added_at=_require_dt(row["added_at"], "added_at"),
            last_reviewed_at=last_reviewed_at,
            due_at=_require_dt(row["due_at"], "due_at"),
            review_count=int(row["review_count"]),
            ease=float(row["ease"]),
            interval_days=int(row["interval_days"]),
            lapses=int(row["lapses"]),
            updated_at=_require_dt(row["updated_at"], "updated_at"),
        )

    def to_row(self) -> dict[str, str]:
        return {
            "id": self.id,
            "word": self.word,
            "meaning": self.meaning,
            "example": self.example,
            "status": self.status,
            "added_at": format_dt(self.added_at),
            "last_reviewed_at": format_dt(self.last_reviewed_at),
            "due_at": format_dt(self.due_at),
            "review_count": str(self.review_count),
            "ease": f"{self.ease:.2f}",
            "interval_days": str(self.interval_days),
            "lapses": str(self.lapses),
            "updated_at": format_dt(self.updated_at),
        }


def _require_dt(value: str, field_name: str) -> datetime:
    parsed = parse_dt(value)
    if parsed is None:
        raise ValueError(f"{field_name} must not be blank")

    return parsed
