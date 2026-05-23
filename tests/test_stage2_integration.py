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


class Stage2IntegrationTests(unittest.TestCase):
    def test_web_admin_add_import_status_flow_persists_expected_words(self):
        fixed_now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: fixed_now)
            app = create_app(service)

            add_form = urlencode(
                {
                    "word": "abandon",
                    "meaning": "放弃",
                    "example": "Do not abandon your plan.",
                }
            )
            add_status, add_headers, add_body = call_app(
                app,
                method="POST",
                path="/admin/words",
                body=add_form,
            )

            import_form = urlencode(
                {
                    "csv_text": (
                        "word,meaning,example\n"
                        "benefit,好处,A clear benefit.\n"
                    )
                }
            )
            import_status, import_headers, import_body = call_app(
                app,
                method="POST",
                path="/admin/import",
                body=import_form,
            )

            status, headers, body = call_app(app, method="GET", path="/api/status")

            self.assertEqual(add_status, "303 See Other")
            self.assertEqual(add_headers["Location"], "/admin?message=Added+abandon")
            self.assertEqual(add_body, "")
            self.assertEqual(import_status, "303 See Other")
            self.assertEqual(
                import_headers["Location"],
                "/admin?message=Imported+created%3D1+updated%3D0+failed%3D0",
            )
            self.assertEqual(import_body, "")
            self.assertEqual(status, "200 OK")
            self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
            self.assertEqual(json.loads(body)["total_words"], 2)
            self.assertEqual(
                [word.word for word in service.load_words()],
                ["abandon", "benefit"],
            )


if __name__ == "__main__":
    unittest.main()
