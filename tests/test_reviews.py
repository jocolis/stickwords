import unittest
from datetime import datetime, timezone

from stickwords.models import RATING_GOOD, Word
from stickwords.reviews import ReviewEvent, ReviewEventStore, process_review_events
from tests.temp_utils import workspace_temp_dir


class ReviewEventTests(unittest.TestCase):
    def test_process_review_event_updates_word_once(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )
        event = ReviewEvent(
            review_event_id="device-1-20260523T100000-w-1",
            word_id="w-1",
            rating=RATING_GOOD,
            reviewed_at=now,
        )

        with workspace_temp_dir() as temp_dir:
            event_store = ReviewEventStore(temp_dir / "review_events.csv")
            result = process_review_events(
                words=[word],
                events=[event, event],
                event_store=event_store,
            )

            self.assertEqual(result.applied, 1)
            self.assertEqual(result.skipped_duplicate, 1)
            self.assertEqual(result.failed, 0)
            self.assertEqual(result.words[0].review_count, 1)
            self.assertEqual(event_store.load_ids(), {event.review_event_id})

    def test_unknown_word_event_is_failed_and_not_recorded(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        event = ReviewEvent(
            review_event_id="device-1-20260523T100000-w-missing",
            word_id="w-missing",
            rating=RATING_GOOD,
            reviewed_at=now,
        )

        with workspace_temp_dir() as temp_dir:
            event_store = ReviewEventStore(temp_dir / "review_events.csv")
            result = process_review_events(
                words=[],
                events=[event],
                event_store=event_store,
            )

            self.assertEqual(result.applied, 0)
            self.assertEqual(result.skipped_duplicate, 0)
            self.assertEqual(result.failed, 1)
            self.assertEqual(result.errors, ["unknown word_id: w-missing"])
            self.assertEqual(event_store.load_ids(), set())

    def test_event_store_appends_multiple_events_without_mid_file_bom(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        first = ReviewEvent(
            review_event_id="device-1-20260523T100000-w-1",
            word_id="w-1",
            rating=RATING_GOOD,
            reviewed_at=now,
        )
        second = ReviewEvent(
            review_event_id="device-1-20260523T100100-w-2",
            word_id="w-2",
            rating=RATING_GOOD,
            reviewed_at=now,
        )

        with workspace_temp_dir() as temp_dir:
            event_store = ReviewEventStore(temp_dir / "review_events.csv")
            event_store.append(first)
            event_store.append(second)

            self.assertEqual(
                event_store.load_ids(),
                {first.review_event_id, second.review_event_id},
            )

    def test_process_review_events_replays_same_word_by_reviewed_at(self):
        now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
        word = Word.new_word("w-1", "abandon", "give up", "Do not abandon it.", now)
        later = ReviewEvent(
            review_event_id="device-1-2-w-1",
            word_id="w-1",
            rating=RATING_GOOD,
            reviewed_at=datetime(2026, 5, 26, 8, 10, tzinfo=timezone.utc),
        )
        earlier = ReviewEvent(
            review_event_id="device-1-1-w-1",
            word_id="w-1",
            rating=RATING_GOOD,
            reviewed_at=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
        )

        with workspace_temp_dir() as temp_dir:
            event_store = ReviewEventStore(temp_dir / "review_events.csv")
            result = process_review_events(
                words=[word],
                events=[later, earlier],
                event_store=event_store,
            )

            self.assertEqual(result.applied, 2)
            self.assertEqual(result.words[0].review_count, 2)
            self.assertEqual(result.words[0].last_reviewed_at, later.reviewed_at)


if __name__ == "__main__":
    unittest.main()
