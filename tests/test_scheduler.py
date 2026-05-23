import unittest
from datetime import datetime, timedelta, timezone

from stickwords.models import (
    RATING_FORGOT,
    RATING_GOOD,
    RATING_HARD,
    STATUS_LEARNING,
    STATUS_NEW,
    STATUS_REVIEW,
    STATUS_SUSPENDED,
    Word,
)
from stickwords.scheduler import apply_review, get_today_tasks


class SchedulerTests(unittest.TestCase):
    def test_forgot_moves_card_to_learning_soon(self):
        added_at = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        reviewed_at = datetime(
            2026,
            5,
            23,
            18,
            0,
            tzinfo=timezone(timedelta(hours=8)),
        )
        expected_reviewed_at = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="give up",
            example="Do not abandon your plan.",
            now=added_at,
        )
        word.status = STATUS_REVIEW
        word.review_count = 2
        word.lapses = 1
        word.ease = 1.4
        word.interval_days = 3

        reviewed = apply_review(word, rating=RATING_FORGOT, reviewed_at=reviewed_at)

        self.assertIsNot(reviewed, word)
        self.assertEqual(word.review_count, 2)
        self.assertEqual(word.lapses, 1)
        self.assertEqual(reviewed.status, STATUS_LEARNING)
        self.assertEqual(reviewed.review_count, 3)
        self.assertEqual(reviewed.lapses, 2)
        self.assertEqual(reviewed.ease, 1.3)
        self.assertEqual(reviewed.interval_days, 0)
        self.assertEqual(reviewed.last_reviewed_at, expected_reviewed_at)
        self.assertEqual(reviewed.updated_at, expected_reviewed_at)
        self.assertEqual(reviewed.due_at, expected_reviewed_at + timedelta(minutes=10))

    def test_hard_keeps_short_interval(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="give up",
            example="Do not abandon your plan.",
            now=now,
        )
        word.interval_days = 3
        word.ease = 1.32

        reviewed = apply_review(word, rating=RATING_HARD, reviewed_at=now)

        self.assertEqual(word.review_count, 0)
        self.assertEqual(word.ease, 1.32)
        self.assertEqual(reviewed.status, STATUS_REVIEW)
        self.assertEqual(reviewed.review_count, 1)
        self.assertEqual(reviewed.ease, 1.3)
        self.assertEqual(reviewed.interval_days, 4)
        self.assertEqual(reviewed.last_reviewed_at, now)
        self.assertEqual(reviewed.updated_at, now)
        self.assertEqual(reviewed.due_at, now + timedelta(days=4))

    def test_good_grows_interval(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        new_word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="give up",
            example="Do not abandon your plan.",
            now=now,
        )
        new_word.ease = 2.98
        review_word = Word.new_word(
            word_id="w-2",
            word="benefit",
            meaning="advantage",
            example="This change has a clear benefit.",
            now=now,
        )
        review_word.interval_days = 2
        review_word.ease = 2.5

        reviewed_new = apply_review(new_word, rating=RATING_GOOD, reviewed_at=now)
        reviewed_existing = apply_review(review_word, rating=RATING_GOOD, reviewed_at=now)

        self.assertEqual(new_word.review_count, 0)
        self.assertEqual(reviewed_new.status, STATUS_REVIEW)
        self.assertEqual(reviewed_new.review_count, 1)
        self.assertEqual(reviewed_new.ease, 3.0)
        self.assertEqual(reviewed_new.interval_days, 1)
        self.assertEqual(reviewed_new.last_reviewed_at, now)
        self.assertEqual(reviewed_new.updated_at, now)
        self.assertEqual(reviewed_new.due_at, now + timedelta(days=1))
        self.assertEqual(reviewed_existing.status, STATUS_REVIEW)
        self.assertEqual(reviewed_existing.review_count, 1)
        self.assertEqual(reviewed_existing.ease, 2.55)
        self.assertEqual(reviewed_existing.interval_days, 5)
        self.assertEqual(reviewed_existing.due_at, now + timedelta(days=5))

    def test_get_today_tasks_returns_due_then_new_and_skips_suspended(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        due_beta = Word.new_word(
            word_id="w-1",
            word="beta",
            meaning="second",
            example="Beta comes second.",
            now=now - timedelta(days=5),
        )
        due_beta.status = STATUS_REVIEW
        due_beta.due_at = now - timedelta(days=1)
        due_alpha = Word.new_word(
            word_id="w-2",
            word="Alpha",
            meaning="first",
            example="Alpha comes first.",
            now=now - timedelta(days=4),
        )
        due_alpha.status = STATUS_REVIEW
        due_alpha.due_at = now - timedelta(days=1)
        future_review = Word.new_word(
            word_id="w-3",
            word="future",
            meaning="later",
            example="Future work waits.",
            now=now - timedelta(days=3),
        )
        future_review.status = STATUS_REVIEW
        future_review.due_at = now + timedelta(days=1)
        new_later = Word.new_word(
            word_id="w-4",
            word="delta",
            meaning="change",
            example="Delta means change.",
            now=now - timedelta(hours=1),
        )
        new_earlier = Word.new_word(
            word_id="w-5",
            word="charlie",
            meaning="name",
            example="Charlie is next.",
            now=now - timedelta(hours=2),
        )
        suspended = Word.new_word(
            word_id="w-6",
            word="cancel",
            meaning="stop",
            example="Cancel the task.",
            now=now - timedelta(days=6),
        )
        suspended.status = STATUS_SUSPENDED
        suspended.due_at = now - timedelta(days=2)

        tasks = get_today_tasks(
            [new_later, suspended, due_beta, future_review, new_earlier, due_alpha],
            now=now,
            max_due=20,
            max_new=5,
        )

        self.assertEqual(
            [word.status for word in tasks],
            [STATUS_REVIEW, STATUS_REVIEW, STATUS_NEW, STATUS_NEW],
        )
        self.assertEqual([word.id for word in tasks], ["w-2", "w-1", "w-5", "w-4"])


if __name__ == "__main__":
    unittest.main()
