import io
import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlencode

from stickwords.service import StickWordsService
from stickwords.web import create_app
from tests.temp_utils import workspace_temp_dir


def call_app(
    app,
    method="GET",
    path="/admin",
    body="",
    content_type="application/x-www-form-urlencoded",
    query_string="",
):
    body_bytes = body.encode("utf-8")
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "CONTENT_LENGTH": str(len(body_bytes)),
        "CONTENT_TYPE": content_type,
        "wsgi.input": io.BytesIO(body_bytes),
        "SERVER_NAME": "127.0.0.1",
        "SERVER_PORT": "8000",
        "wsgi.url_scheme": "http",
    }
    response_body = b"".join(app(environ, start_response)).decode("utf-8")
    return captured["status"], captured["headers"], response_body


class WebTests(unittest.TestCase):
    def test_app_module_imports(self):
        import app

        self.assertTrue(callable(app.main))

    def test_get_admin_returns_html(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            service.add_word("abandon", "放弃", "Do not abandon your plan.")
            app = create_app(service)

            status, headers, body = call_app(app, "GET", "/admin")

            self.assertEqual(status, "200 OK")
            self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
            self.assertIn("StickWords", body)
            self.assertIn("abandon", body)

    def test_post_add_word_redirects_and_persists(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            app = create_app(service)
            form = urlencode(
                {
                    "word": "benefit",
                    "meaning": "好处",
                    "example": "A clear benefit.",
                }
            )

            status, headers, body = call_app(app, "POST", "/admin/words", form)

            self.assertEqual(status, "303 See Other")
            self.assertEqual(headers["Location"], "/admin?message=Added+benefit")
            self.assertEqual(service.load_words()[0].word, "benefit")
            self.assertEqual(body, "")

    def test_post_add_word_blank_form_returns_400_without_persisting(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service)
            form = urlencode({"word": "  ", "meaning": "  ", "example": "  "})

            status, headers, body = call_app(app, "POST", "/admin/words", form)

            self.assertEqual(status, "400 Bad Request")
            self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
            self.assertEqual(body, "word is required")
            self.assertEqual(service.load_words(), [])

    def test_post_add_word_empty_body_returns_400_without_persisting(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service)

            status, headers, body = call_app(app, "POST", "/admin/words", "")

            self.assertEqual(status, "400 Bad Request")
            self.assertEqual(body, "word is required")
            self.assertEqual(service.load_words(), [])

    def test_post_edit_word_updates_existing_word(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            word = service.add_word("abandon", "old", "Old example.")
            app = create_app(service)
            form = urlencode(
                {
                    "id": word.id,
                    "meaning": "fangqi",
                    "example": "Do not abandon your plan.",
                }
            )

            status, headers, body = call_app(app, "POST", "/admin/words/edit", form)

            edited = service.load_words()[0]
            self.assertEqual(status, "303 See Other")
            self.assertEqual(headers["Location"], "/admin?message=Saved")
            self.assertEqual(edited.meaning, "fangqi")
            self.assertEqual(edited.example, "Do not abandon your plan.")
            self.assertEqual(body, "")

    def test_post_suspend_word_marks_existing_word_suspended(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            word = service.add_word("abandon", "fangqi", "Do not abandon your plan.")
            app = create_app(service)
            form = urlencode({"id": word.id})

            status, headers, body = call_app(app, "POST", "/admin/words/suspend", form)

            self.assertEqual(status, "303 See Other")
            self.assertEqual(headers["Location"], "/admin?message=Suspended")
            self.assertEqual(service.load_words()[0].status, "suspended")
            self.assertEqual(body, "")

    def test_post_edit_missing_id_returns_400(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            service.add_word("abandon", "fangqi", "Do not abandon your plan.")
            app = create_app(service)
            form = urlencode(
                {
                    "id": " ",
                    "meaning": "updated",
                    "example": "Updated example.",
                }
            )

            status, headers, body = call_app(app, "POST", "/admin/words/edit", form)

            self.assertEqual(status, "400 Bad Request")
            self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
            self.assertEqual(body, "id is required")

    def test_post_suspend_missing_id_returns_400(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            word = service.add_word("abandon", "fangqi", "Do not abandon your plan.")
            app = create_app(service)

            status, headers, body = call_app(app, "POST", "/admin/words/suspend", "")

            self.assertEqual(status, "400 Bad Request")
            self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
            self.assertEqual(body, "id is required")
            loaded = service.load_words()[0]
            self.assertEqual(loaded.id, word.id)
            self.assertEqual(loaded.status, "new")

    def test_api_status_returns_json(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            service.add_word("abandon", "放弃", "Do not abandon your plan.")
            app = create_app(service)

            status, headers, body = call_app(app, "GET", "/api/status")

            self.assertEqual(status, "200 OK")
            self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
            self.assertEqual(json.loads(body)["total_words"], 1)

    def test_get_device_tasks_returns_due_cards_json(self):
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            word = service.add_word("abandon", "give up", "Do not abandon your plan.")
            app = create_app(service)

            status, headers, body = call_app(app, "GET", "/api/device/tasks")

            payload = json.loads(body)
            self.assertEqual(status, "200 OK")
            self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
            self.assertEqual(payload["generated_at"], "2026-05-24T12:00:00Z")
            self.assertEqual(
                payload["tasks"],
                [
                    {
                        "id": word.id,
                        "word": "abandon",
                        "meaning": "give up",
                        "example": "Do not abandon your plan.",
                    }
                ],
            )

    def test_get_device_tasks_respects_limit(self):
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            service.add_word("abandon", "give up", "Do not abandon your plan.")
            service.add_word("benefit", "good effect", "Daily review has a benefit.")
            app = create_app(service)

            status, headers, body = call_app(
                app,
                "GET",
                "/api/device/tasks",
                query_string="limit=1",
            )

            payload = json.loads(body)
            self.assertEqual(status, "200 OK")
            self.assertEqual(len(payload["tasks"]), 1)

    def test_post_device_reviews_applies_rating_and_is_idempotent(self):
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            word = service.add_word("abandon", "give up", "Do not abandon your plan.")
            app = create_app(service)
            body = json.dumps(
                {
                    "device_id": "m5stick-c-plus",
                    "reviews": [
                        {
                            "word_id": word.id,
                            "rating": "good",
                            "reviewed_at": "2026-05-24T12:03:00Z",
                            "event_id": "m5stick-c-plus-20260524T120300-w-000001",
                        }
                    ],
                }
            )

            first_status, _, first_body = call_app(
                app,
                "POST",
                "/api/device/reviews",
                body,
                content_type="application/json",
            )
            second_status, _, second_body = call_app(
                app,
                "POST",
                "/api/device/reviews",
                body,
                content_type="application/json",
            )

            self.assertEqual(first_status, "200 OK")
            self.assertEqual(json.loads(first_body)["accepted"], 1)
            self.assertEqual(second_status, "200 OK")
            self.assertEqual(json.loads(second_body)["skipped_duplicate"], 1)
            reviewed = service.load_words()[0]
            self.assertEqual(reviewed.review_count, 1)
            self.assertEqual(reviewed.status, "review")

    def test_post_device_reviews_reports_invalid_rows(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service)
            body = json.dumps(
                {
                    "device_id": "m5stick-c-plus",
                    "reviews": [
                        {
                            "word_id": "missing",
                            "rating": "good",
                            "reviewed_at": "2026-05-24T12:03:00Z",
                            "event_id": "missing-event",
                        },
                        {
                            "word_id": "",
                            "rating": "great",
                            "reviewed_at": "bad-date",
                            "event_id": "",
                        },
                    ],
                }
            )

            status, _, response_body = call_app(
                app,
                "POST",
                "/api/device/reviews",
                body,
                content_type="application/json",
            )

            payload = json.loads(response_body)
            self.assertEqual(status, "200 OK")
            self.assertEqual(payload["accepted"], 0)
            self.assertEqual(payload["failed"], 2)
            self.assertTrue(payload["errors"])

    def test_post_import_csv_text_redirects_and_persists(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            app = create_app(service)
            form = urlencode(
                {
                    "csv_text": (
                        "word,meaning,example\n"
                        "abandon,fangqi,Do not abandon your plan.\n"
                        "benefit,haochu,A clear benefit.\n"
                    )
                }
            )

            status, headers, body = call_app(app, "POST", "/admin/import", form)

            self.assertEqual(status, "303 See Other")
            self.assertEqual(
                headers["Location"],
                "/admin?message=Imported+created%3D2+updated%3D0+failed%3D0",
            )
            self.assertEqual(
                [word.word for word in service.load_words()],
                ["abandon", "benefit"],
            )
            self.assertEqual(body, "")

    def test_post_blank_import_returns_400_without_creating_words(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service)
            form = urlencode({"csv_text": "  "})

            status, headers, body = call_app(app, "POST", "/admin/import", form)

            self.assertEqual(status, "400 Bad Request")
            self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
            self.assertEqual(body, "csv_text is required")
            self.assertEqual(service.load_words(), [])

    def test_unknown_route_returns_404(self):
        with workspace_temp_dir() as temp_dir:
            app = create_app(StickWordsService(temp_dir))

            status, headers, body = call_app(app, "GET", "/missing")

            self.assertEqual(status, "404 Not Found")
            self.assertIn("Not Found", body)


if __name__ == "__main__":
    unittest.main()
