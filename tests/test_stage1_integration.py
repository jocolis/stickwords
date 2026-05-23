import unittest
from datetime import datetime, timezone

from stickwords.importer import import_words
from stickwords.models import RATING_GOOD
from stickwords.reviews import ReviewEvent, ReviewEventStore, process_review_events
from stickwords.scheduler import get_today_tasks
from stickwords.storage import VocabStore
from tests.temp_utils import workspace_temp_dir


class Stage1IntegrationTests(unittest.TestCase):
    def test_import_save_load_task_review_save_load(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with workspace_temp_dir() as temp_dir:
            import_path = temp_dir / "words.csv"
            import_path.write_text(
                "word,meaning,example\n"
                "abandon,放弃,Do not abandon your plan.\n",
                encoding="utf-8",
            )

            import_result = import_words(existing=[], import_path=import_path, now=now)
            vocab_store = VocabStore(temp_dir / "data" / "vocab.csv")
            vocab_store.save(import_result.words)
            loaded_words = vocab_store.load()

            tasks = get_today_tasks(loaded_words, now)
            self.assertEqual([word.word for word in tasks], ["abandon"])

            event_store = ReviewEventStore(temp_dir / "data" / "review_events.csv")
            event = ReviewEvent(
                review_event_id="device-1-20260523T100000-w-000001",
                word_id=tasks[0].id,
                rating=RATING_GOOD,
                reviewed_at=now,
            )
            review_result = process_review_events(
                words=loaded_words,
                events=[event],
                event_store=event_store,
            )
            vocab_store.save(review_result.words)
            reloaded_words = vocab_store.load()

        self.assertEqual(reloaded_words[0].review_count, 1)
        self.assertEqual(reloaded_words[0].interval_days, 1)
        self.assertEqual(reloaded_words[0].status, "review")


if __name__ == "__main__":
    unittest.main()
