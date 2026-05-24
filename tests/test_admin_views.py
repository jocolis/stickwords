import unittest
from datetime import datetime, timezone

from stickwords.admin_views import render_admin_page
from stickwords.models import Word


class AdminViewTests(unittest.TestCase):
    def test_render_admin_page_contains_core_sections(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-000001",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )

        html = render_admin_page(
            status={
                "total_words": 1,
                "new_words": 1,
                "review_words": 0,
                "suspended_words": 0,
                "due_today": 1,
            },
            words=[word],
            message="Imported 1 word",
            server_url="http://192.168.1.10:8000",
        )

        self.assertIn("<title>StickWords Admin</title>", html)
        self.assertIn("StickWords", html)
        self.assertIn("Total Words", html)
        self.assertIn("Add Word", html)
        self.assertIn("Import CSV", html)
        self.assertIn("Imported 1 word", html)
        self.assertIn("http://192.168.1.10:8000", html)
        self.assertIn("abandon", html)

    def test_render_admin_page_escapes_user_content(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-000001",
            word="<script>alert(1)</script>",
            meaning="<b>bad</b>",
            example="Use <tag> safely.",
            now=now,
        )

        html = render_admin_page(
            status={
                "total_words": 1,
                "new_words": 1,
                "review_words": 0,
                "suspended_words": 0,
                "due_today": 1,
            },
            words=[word],
            message="<ok>",
            server_url="http://localhost:8000",
        )

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;bad&lt;/b&gt;", html)
        self.assertIn("&lt;ok&gt;", html)

    def test_import_csv_form_supports_file_upload_and_text_fallback(self):
        html = render_admin_page(
            status={
                "total_words": 0,
                "new_words": 0,
                "review_words": 0,
                "suspended_words": 0,
                "due_today": 0,
            },
            words=[],
        )

        self.assertIn('action="/admin/import"', html)
        self.assertIn('enctype="multipart/form-data"', html)
        self.assertIn('type="file"', html)
        self.assertIn('name="csv_file"', html)
        self.assertIn('accept=".csv,text/csv"', html)
        self.assertIn('name="csv_text"', html)

    def test_words_table_has_search_and_no_inline_edit_column(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-000001",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )

        html = render_admin_page(
            status={
                "total_words": 1,
                "new_words": 1,
                "review_words": 0,
                "suspended_words": 0,
                "due_today": 1,
            },
            words=[word],
        )

        self.assertIn('id="word-search"', html)
        self.assertIn('placeholder="Search words"', html)
        self.assertIn('data-search-text="abandon 放弃 do not abandon your plan. new"', html)
        self.assertIn("addEventListener('input'", html)
        self.assertNotIn("<th>Edit</th>", html)
        self.assertNotIn('action="/admin/edit-word"', html)
        self.assertNotIn("<button type=\"submit\">Save</button>", html)
        self.assertIn("<th>Suspend</th>", html)


if __name__ == "__main__":
    unittest.main()
