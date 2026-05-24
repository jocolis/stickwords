import unittest
from datetime import datetime, timedelta, timezone

from stickwords.importer import import_words
from stickwords.models import STATUS_REVIEW, Word
from tests.temp_utils import workspace_temp_dir


class ImporterTests(unittest.TestCase):
    def test_import_new_words_from_simple_csv(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "import.csv"
            path.write_text(
                "word,meaning,example\n"
                "abandon,give up,Do not abandon your plan.\n"
                "benefit,advantage,This change has a clear benefit.\n",
                encoding="utf-8",
            )

            result = import_words(existing=[], import_path=path, now=now)

        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.errors, [])
        self.assertEqual([word.word for word in result.words], ["abandon", "benefit"])
        self.assertEqual(result.words[0].id, "w-000001")
        self.assertEqual(result.words[1].id, "w-000002")

    def test_duplicate_word_updates_content_but_preserves_review_state(self):
        added_at = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        reviewed_at = datetime(2026, 5, 22, 10, 0, tzinfo=timezone.utc)
        now = datetime(2026, 5, 23, 18, 0, tzinfo=timezone(timedelta(hours=8)))
        expected_now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        existing = Word.new_word(
            word_id="w-000001",
            word="Abandon",
            meaning="old meaning",
            example="Old example.",
            now=added_at,
        )
        existing.status = STATUS_REVIEW
        existing.last_reviewed_at = reviewed_at
        existing.review_count = 4
        existing.ease = 2.2
        existing.interval_days = 3
        existing.lapses = 1
        existing.due_at = added_at + timedelta(days=7)

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "import.csv"
            path.write_text(
                "word,meaning,example\n"
                "abandon,give up,Do not abandon your plan.\n",
                encoding="utf-8",
            )

            result = import_words(existing=[existing], import_path=path, now=now)

        updated = result.words[0]
        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(updated.id, "w-000001")
        self.assertEqual(updated.word, "abandon")
        self.assertEqual(updated.meaning, "give up")
        self.assertEqual(updated.example, "Do not abandon your plan.")
        self.assertEqual(updated.status, STATUS_REVIEW)
        self.assertEqual(updated.added_at, added_at)
        self.assertEqual(updated.last_reviewed_at, reviewed_at)
        self.assertEqual(updated.due_at, added_at + timedelta(days=7))
        self.assertEqual(updated.review_count, 4)
        self.assertEqual(updated.ease, 2.2)
        self.assertEqual(updated.interval_days, 3)
        self.assertEqual(updated.lapses, 1)
        self.assertEqual(updated.updated_at, expected_now)

    def test_duplicate_words_inside_import_are_reported_and_last_row_wins(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "import.csv"
            path.write_text(
                "word,meaning,example\n"
                "abandon,first,First example.\n"
                "benefit,advantage,A clear benefit.\n"
                "abandon,second,Second example.\n",
                encoding="utf-8",
            )

            result = import_words(existing=[], import_path=path, now=now)

        by_word = {word.word: word for word in result.words}
        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(result.duplicate_rows, 1)
        self.assertEqual(by_word["abandon"].meaning, "second")
        self.assertEqual(by_word["abandon"].example, "Second example.")
        self.assertEqual(by_word["abandon"].id, "w-000001")
        self.assertEqual(by_word["benefit"].id, "w-000002")

    def test_blank_word_rows_fail_without_stopping_import(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "import.csv"
            path.write_text(
                "word,meaning,example\n"
                ",empty row,No word.\n"
                "benefit,advantage,This change has a clear benefit.\n",
                encoding="utf-8",
            )

            result = import_words(existing=[], import_path=path, now=now)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.errors, ["row 2: word is required"])
        self.assertEqual(result.words[0].word, "benefit")
        self.assertEqual(result.words[0].id, "w-000001")

    def test_missing_required_column_raises_value_error(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "import.csv"
            path.write_text(
                "word,meaning\n"
                "abandon,give up\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "import CSV missing required column: example",
            ):
                import_words(existing=[], import_path=path, now=now)


if __name__ == "__main__":
    unittest.main()
