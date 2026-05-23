import unittest
from datetime import datetime, timezone

from stickwords.models import (
    RATING_FORGOT,
    RATING_GOOD,
    RATING_HARD,
    STATUS_NEW,
    VOCAB_FIELDS,
    Word,
    format_dt,
    parse_dt,
)


class ModelTests(unittest.TestCase):
    def test_word_defaults_match_design(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
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
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )

        row = word.to_row()
        restored = Word.from_row(row)

        self.assertEqual(list(row.keys()), VOCAB_FIELDS)
        self.assertEqual(restored, word)

    def test_datetime_format_is_stable_utc_iso(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        value = format_dt(now)

        self.assertEqual(value, "2026-05-23T10:00:00Z")
        self.assertEqual(parse_dt(value), now)

    def test_supported_ratings_are_explicit(self):
        self.assertEqual(RATING_FORGOT, "forgot")
        self.assertEqual(RATING_HARD, "hard")
        self.assertEqual(RATING_GOOD, "good")


if __name__ == "__main__":
    unittest.main()
