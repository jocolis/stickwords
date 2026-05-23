import unittest
from datetime import datetime, timezone

from stickwords.models import VOCAB_FIELDS, Word
from stickwords.storage import VocabStore
from tests.temp_utils import workspace_temp_dir


class VocabStoreTests(unittest.TestCase):
    def test_load_missing_file_returns_empty_list(self):
        with workspace_temp_dir() as temp_dir:
            store = VocabStore(temp_dir / "vocab.csv")

            self.assertEqual(store.load(), [])

    def test_save_creates_parent_directory_and_header(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )

        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "data" / "vocab.csv"
            store = VocabStore(path)
            store.save([word])

            content = path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(content[0], ",".join(VOCAB_FIELDS))
            self.assertEqual(store.load(), [word])

    def test_load_rejects_missing_required_columns(self):
        with workspace_temp_dir() as temp_dir:
            path = temp_dir / "vocab.csv"
            path.write_text("word,meaning,example\nabandon,放弃,x\n", encoding="utf-8")
            store = VocabStore(path)

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                store.load()


if __name__ == "__main__":
    unittest.main()
