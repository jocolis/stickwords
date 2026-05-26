import io
import json
import unittest
from datetime import datetime, timedelta, timezone
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
    http_host="localhost:8000",
):
    if isinstance(body, bytes):
        body_bytes = body
    else:
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
        "HTTP_HOST": http_host,
        "wsgi.url_scheme": "http",
    }
    response_body = b"".join(app(environ, start_response)).decode("utf-8")
    return captured["status"], captured["headers"], response_body


def multipart_body(fields=None, files=None, boundary="----stickwords-test"):
    fields = fields or {}
    files = files or {}
    chunks = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, file_info in files.items():
        filename, content, content_type = file_info
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\n'
                ).encode("utf-8"),
                f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
                content.encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


class WebTests(unittest.TestCase):
    def test_app_module_imports(self):
        import app

        self.assertTrue(callable(app.main))

    def test_server_uses_threaded_wsgi_server(self):
        import stickwords.web as web

        self.assertTrue(issubclass(web.ThreadedWSGIServer, web.ThreadingMixIn))
        self.assertTrue(issubclass(web.ThreadedWSGIServer, web.WSGIServer))
        self.assertTrue(web.ThreadedWSGIServer.daemon_threads)

    def test_windows_launcher_restarts_stale_port_8000_backend(self):
        root = __import__("pathlib").Path(__file__).resolve().parents[1]
        batch = (root / "start_stickwords.bat").read_text(encoding="utf-8")
        launcher = (root / "scripts" / "start_stickwords.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("scripts\\start_stickwords.ps1", batch)
        self.assertIn("netstat -ano", launcher)
        self.assertIn(":8000", launcher)
        self.assertIn("LISTENING", launcher)
        self.assertIn("Stop-Process", launcher)
        self.assertIn("app.py", launcher)
        self.assertIn("--host", launcher)
        self.assertIn("0.0.0.0", launcher)
        self.assertIn("http://localhost:8000/admin", launcher)

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

    def test_get_admin_prefers_lan_server_url_for_m5stick(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service, lan_host_lookup=lambda: "192.168.1.23")

            status, _, body = call_app(
                app,
                "GET",
                "/admin",
                http_host="localhost:8000",
            )

            self.assertEqual(status, "200 OK")
            self.assertIn("http://192.168.1.23:8000", body)
            self.assertNotIn("http://localhost:8000", body)

    def test_get_admin_keeps_explicit_lan_host(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service, lan_host_lookup=lambda: "192.168.1.23")

            status, _, body = call_app(
                app,
                "GET",
                "/admin",
                http_host="192.168.1.99:8000",
            )

            self.assertEqual(status, "200 OK")
            self.assertIn("http://192.168.1.99:8000", body)
            self.assertNotIn("http://192.168.1.23:8000", body)

    def test_get_admin_falls_back_to_localhost_when_lan_lookup_fails(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service, lan_host_lookup=lambda: "")

            status, _, body = call_app(
                app,
                "GET",
                "/admin",
                http_host="localhost:8000",
            )

            self.assertEqual(status, "200 OK")
            self.assertIn("http://localhost:8000", body)

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
                        "status": "new",
                        "due_at": "2026-05-24T12:00:00Z",
                        "review_count": 0,
                        "ease": 2.5,
                        "interval_days": 0,
                        "lapses": 0,
                    }
                ],
            )
            self.assertEqual(payload["offline"]["horizon_days"], 7)
            self.assertEqual(payload["offline"]["max_new"], 20)
            self.assertEqual(payload["offline"]["cards"], payload["tasks"])

    def test_get_device_tasks_includes_future_due_offline_package(self):
        now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            due_now = service.add_word("alpha", "first", "Alpha example.")
            due_future = service.add_word("beta", "second", "Beta example.")
            too_late = service.add_word("gamma", "third", "Gamma example.")
            suspended = service.add_word("delta", "fourth", "Delta example.")

            words = service.load_words()
            by_id = {word.id: word for word in words}
            by_id[due_now.id].status = "review"
            by_id[due_now.id].due_at = now
            by_id[due_future.id].status = "review"
            by_id[due_future.id].due_at = now + timedelta(days=7)
            by_id[too_late.id].status = "review"
            by_id[too_late.id].due_at = now + timedelta(days=8)
            by_id[suspended.id].status = "suspended"
            service.save_words(words)

            app = create_app(service)
            status, _, body = call_app(app, "GET", "/api/device/tasks", query_string="limit=1")

            payload = json.loads(body)
            self.assertEqual(status, "200 OK")
            self.assertEqual([card["id"] for card in payload["tasks"]], [due_now.id])
            self.assertEqual(
                [card["id"] for card in payload["offline"]["cards"]],
                [due_now.id, due_future.id],
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

    def test_post_import_csv_file_redirects_and_persists(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            app = create_app(service)
            body, content_type = multipart_body(
                fields={"csv_text": ""},
                files={
                    "csv_file": (
                        "words.csv",
                        (
                            "word,meaning,example\n"
                            "abandon,fangqi,Do not abandon your plan.\n"
                            "benefit,haochu,A clear benefit.\n"
                        ),
                        "text/csv",
                    )
                },
            )

            status, headers, response_body = call_app(
                app,
                "POST",
                "/admin/import",
                body,
                content_type=content_type,
            )

            self.assertEqual(status, "303 See Other")
            self.assertEqual(
                headers["Location"],
                "/admin?message=Imported+created%3D2+updated%3D0+failed%3D0",
            )
            self.assertEqual(
                [word.word for word in service.load_words()],
                ["abandon", "benefit"],
            )
            self.assertEqual(response_body, "")

    def test_post_import_reports_duplicate_rows_in_redirect_message(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            app = create_app(service)
            form = urlencode(
                {
                    "csv_text": (
                        "word,meaning,example\n"
                        "abandon,first,First example.\n"
                        "abandon,second,Second example.\n"
                    )
                }
            )

            status, headers, _ = call_app(app, "POST", "/admin/import", form)

            self.assertEqual(status, "303 See Other")
            self.assertEqual(
                headers["Location"],
                (
                    "/admin?message=Imported+created%3D1+updated%3D1+"
                    "failed%3D0+duplicate_rows%3D1"
                ),
            )
            loaded = service.load_words()
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].meaning, "second")

    def test_post_blank_import_returns_400_without_creating_words(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service)
            form = urlencode({"csv_text": "  "})

            status, headers, body = call_app(app, "POST", "/admin/import", form)

            self.assertEqual(status, "400 Bad Request")
            self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
            self.assertEqual(body, "csv_text or csv_file is required")
            self.assertEqual(service.load_words(), [])

    def test_unknown_route_returns_404(self):
        with workspace_temp_dir() as temp_dir:
            app = create_app(StickWordsService(temp_dir))

            status, headers, body = call_app(app, "GET", "/missing")

            self.assertEqual(status, "404 Not Found")
            self.assertIn("Not Found", body)


if __name__ == "__main__":
    unittest.main()
