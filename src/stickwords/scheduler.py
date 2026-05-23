from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

from .models import (
    RATING_FORGOT,
    RATING_GOOD,
    RATING_HARD,
    STATUS_LEARNING,
    STATUS_NEW,
    STATUS_REVIEW,
    STATUS_SUSPENDED,
    Word,
    normalize_dt,
)


def apply_review(word: Word, rating: str, reviewed_at: datetime) -> Word:
    reviewed_at = normalize_dt(reviewed_at)
    updated = deepcopy(word)
    updated.review_count += 1
    updated.last_reviewed_at = reviewed_at
    updated.updated_at = reviewed_at

    if rating == RATING_FORGOT:
        updated.status = STATUS_LEARNING
        updated.lapses += 1
        updated.ease = round(max(1.3, updated.ease - 0.2), 2)
        updated.interval_days = 0
        updated.due_at = reviewed_at + timedelta(minutes=10)
        return updated

    if rating == RATING_HARD:
        updated.status = STATUS_REVIEW
        updated.ease = round(max(1.3, updated.ease - 0.05), 2)
        updated.interval_days = max(1, round(updated.interval_days * 1.2))
        updated.due_at = reviewed_at + timedelta(days=updated.interval_days)
        return updated

    if rating == RATING_GOOD:
        updated.status = STATUS_REVIEW
        updated.ease = round(min(3.0, updated.ease + 0.05), 2)
        if updated.interval_days == 0:
            updated.interval_days = 1
        else:
            updated.interval_days = max(1, round(updated.interval_days * updated.ease))
        updated.due_at = reviewed_at + timedelta(days=updated.interval_days)
        return updated

    raise ValueError(f"unsupported rating: {rating}")


def get_today_tasks(
    words: list[Word],
    now: datetime,
    max_due: int = 20,
    max_new: int = 5,
) -> list[Word]:
    now = normalize_dt(now)
    eligible_words = [word for word in words if word.status != STATUS_SUSPENDED]

    due_words = [
        word
        for word in eligible_words
        if word.status != STATUS_NEW and normalize_dt(word.due_at) <= now
    ]
    due_words.sort(key=lambda word: (normalize_dt(word.due_at), word.word.casefold()))

    new_words = [word for word in eligible_words if word.status == STATUS_NEW]
    new_words.sort(key=lambda word: (normalize_dt(word.added_at), word.word.casefold()))

    return due_words[:max_due] + new_words[:max_new]
