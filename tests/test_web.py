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
):
    body_bytes = body.encode("utf-8")
    captured = {}

    def start_response(status, headers):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": "",
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

    def test_unknown_route_returns_404(self):
        with workspace_temp_dir() as temp_dir:
            app = create_app(StickWordsService(temp_dir))

            status, headers, body = call_app(app, "GET", "/missing")

            self.assertEqual(status, "404 Not Found")
            self.assertIn("Not Found", body)


if __name__ == "__main__":
    unittest.main()
