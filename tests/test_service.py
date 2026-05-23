import unittest
from datetime import datetime, timezone

from stickwords.models import STATUS_LEARNING
from stickwords.service import StickWordsService
from tests.temp_utils import workspace_temp_dir


class StickWordsServiceTests(unittest.TestCase):
    def test_add_word_persists_and_updates_status(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)

            word = service.add_word(
                word=" abandon ",
                meaning=" 放弃 ",
                example=" Do not abandon your plan. ",
            )
            status = service.get_status()

            self.assertEqual(word.id, "w-000001")
            self.assertEqual(word.word, "abandon")
            self.assertEqual(status["total_words"], 1)
            self.assertEqual(status["new_words"], 1)
            self.assertEqual(status["due_today"], 1)
            self.assertEqual(service.load_words()[0].meaning, "放弃")

    def test_edit_and_suspend_word(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            word = service.add_word("abandon", "old", "Old example.")

            edited = service.edit_word(
                word.id,
                meaning="放弃",
                example="Do not abandon your plan.",
            )
            suspended = service.suspend_word(word.id)

            self.assertEqual(edited.meaning, "放弃")
            self.assertEqual(edited.example, "Do not abandon your plan.")
            self.assertEqual(suspended.status, "suspended")
            self.assertEqual(service.get_status()["suspended_words"], 1)

    def test_status_counts_learning_words(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            service.add_word("abandon", "old", "Old example.")
            words = service.load_words()
            words[0].status = STATUS_LEARNING
            service.save_words(words)

            self.assertEqual(service.get_status()["learning_words"], 1)

    def test_recent_words_orders_by_updated_at_then_word_and_limits(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            service.add_word("apple", "苹果", "An apple.")
            service.add_word("zebra", "斑马", "A zebra.")
            service.add_word("benefit", "好处", "A benefit.")
            words = service.load_words()
            words[0].updated_at = datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc)
            words[1].updated_at = datetime(2026, 5, 23, 9, 0, tzinfo=timezone.utc)
            words[2].updated_at = datetime(2026, 5, 23, 11, 0, tzinfo=timezone.utc)
            service.save_words(words)

            recent = service.recent_words(limit=2)

            self.assertEqual([word.word for word in recent], ["benefit", "zebra"])

    def test_import_csv_text_updates_duplicate_and_preserves_progress(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            original = service.add_word("abandon", "old", "Old example.")
            words = service.load_words()
            words[0].review_count = 3
            service.save_words(words)

            result = service.import_csv_text(
                "word,meaning,example\n"
                "abandon,放弃,Do not abandon your plan.\n"
                "benefit,好处,This change has a clear benefit.\n"
            )

            words = service.load_words()
            by_word = {word.word: word for word in words}
            self.assertEqual(result.created, 1)
            self.assertEqual(result.updated, 1)
            self.assertEqual(by_word["abandon"].id, original.id)
            self.assertEqual(by_word["abandon"].review_count, 3)
            self.assertEqual(by_word["abandon"].meaning, "放弃")
            self.assertEqual(by_word["benefit"].id, "w-000002")

    def test_import_csv_text_failure_preserves_words_and_removes_temp_file(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            original = service.add_word("abandon", "old", "Old example.")

            with self.assertRaisesRegex(
                ValueError, "import CSV missing required column: example"
            ):
                service.import_csv_text("word,meaning\nbenefit,好处\n")

            words = service.load_words()
            self.assertEqual(len(words), 1)
            self.assertEqual(words[0].id, original.id)
            self.assertEqual(words[0].meaning, "old")
            self.assertEqual(list(temp_dir.glob("import-*.csv")), [])

    def test_unknown_word_operations_raise_key_error(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)

            with self.assertRaisesRegex(KeyError, "unknown word_id: missing"):
                service.edit_word("missing", meaning="x", example="y")

            with self.assertRaisesRegex(KeyError, "unknown word_id: missing"):
                service.suspend_word("missing")


if __name__ == "__main__":
    unittest.main()
