import unittest
from dataclasses import fields
from datetime import datetime, timedelta, timezone

from stickwords.models import (
    RATING_FORGOT,
    RATING_GOOD,
    RATING_HARD,
    STATUS_LEARNING,
    STATUS_NEW,
    STATUS_REVIEW,
    STATUS_SUSPENDED,
    VOCAB_FIELDS,
    Word,
    format_dt,
    normalize_dt,
    parse_dt,
)

REQUIRED_VOCAB_FIELDS = [
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


class ModelTests(unittest.TestCase):
    def test_word_defaults_match_design(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        word = Word.new_word(
            word_id="w-1",
            word="  abandon  ",
            meaning="  放弃  ",
            example="  Do not abandon your plan.  ",
            now=now,
        )

        self.assertEqual(word.id, "w-1")
        self.assertEqual(word.word, "abandon")
        self.assertEqual(word.meaning, "放弃")
        self.assertEqual(word.example, "Do not abandon your plan.")
        self.assertEqual(word.status, STATUS_NEW)
        self.assertEqual(word.added_at, now)
        self.assertEqual(word.due_at, now)
        self.assertIsNone(word.last_reviewed_at)
        self.assertEqual(word.review_count, 0)
        self.assertEqual(word.ease, 2.5)
        self.assertEqual(word.interval_days, 0)
        self.assertEqual(word.lapses, 0)
        self.assertEqual(word.updated_at, now)

    def test_word_round_trip_csv_row(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        reviewed_at = datetime(2026, 5, 24, 8, 30, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )
        word.last_reviewed_at = reviewed_at

        row = word.to_row()
        restored = Word.from_row(row)

        self.assertEqual(VOCAB_FIELDS, REQUIRED_VOCAB_FIELDS)
        self.assertEqual([field.name for field in fields(Word)], REQUIRED_VOCAB_FIELDS)
        self.assertEqual(list(row.keys()), VOCAB_FIELDS)
        self.assertEqual(row["last_reviewed_at"], "2026-05-24T08:30:00Z")
        self.assertEqual(row["ease"], "2.50")
        self.assertEqual(restored, word)

    def test_datetime_format_is_stable_utc_iso(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        value = format_dt(now)

        self.assertEqual(value, "2026-05-23T10:00:00Z")
        self.assertEqual(parse_dt(value), now)
        self.assertEqual(format_dt(None), "")
        self.assertIsNone(parse_dt(""))
        self.assertIsNone(parse_dt("   "))

    def test_normalize_dt_handles_naive_and_non_utc_values(self):
        naive = datetime(2026, 5, 23, 10, 0)
        non_utc = datetime(
            2026,
            5,
            23,
            18,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        )

        self.assertEqual(
            normalize_dt(naive),
            datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            normalize_dt(non_utc),
            datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc),
        )

    def test_supported_statuses_are_explicit(self):
        self.assertEqual(STATUS_NEW, "new")
        self.assertEqual(STATUS_LEARNING, "learning")
        self.assertEqual(STATUS_REVIEW, "review")
        self.assertEqual(STATUS_SUSPENDED, "suspended")

    def test_supported_ratings_are_explicit(self):
        self.assertEqual(RATING_FORGOT, "forgot")
        self.assertEqual(RATING_HARD, "hard")
        self.assertEqual(RATING_GOOD, "good")


if __name__ == "__main__":
    unittest.main()
