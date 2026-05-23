from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, quote_plus
from wsgiref.simple_server import make_server

from .admin_views import render_admin_page
from .service import StickWordsService


def _read_form(environ: dict) -> dict[str, str]:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length).decode("utf-8")
    parsed = parse_qs(body, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def _response(
    start_response,
    status: str,
    body: str,
    content_type: str = "text/plain; charset=utf-8",
):
    start_response(status, [("Content-Type", content_type)])
    return [body.encode("utf-8")]


def _redirect(start_response, location: str):
    start_response("303 See Other", [("Location", location)])
    return [b""]


def _server_url(environ: dict) -> str:
    scheme = environ.get("wsgi.url_scheme") or "http"
    host = environ.get("HTTP_HOST")
    if not host:
        host = f'{environ.get("SERVER_NAME", "127.0.0.1")}:{environ.get("SERVER_PORT", "8000")}'

    return f"{scheme}://{host}"


def create_app(service: StickWordsService):
    def app(environ, start_response):
        method = (environ.get("REQUEST_METHOD") or "GET").upper()
        path = environ.get("PATH_INFO") or "/"
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)

        try:
            if method == "GET" and path in ("/", "/admin"):
                body = render_admin_page(
                    status=service.get_status(),
                    words=service.recent_words(),
                    message=(query.get("message") or [""])[0],
                    server_url=_server_url(environ),
                )
                return _response(
                    start_response,
                    "200 OK",
                    body,
                    "text/html; charset=utf-8",
                )

            if method == "GET" and path == "/api/status":
                body = json.dumps(service.get_status(), ensure_ascii=False)
                return _response(
                    start_response,
                    "200 OK",
                    body,
                    "application/json; charset=utf-8",
                )

            if method == "POST" and path in ("/admin/words", "/admin/add-word"):
                form = _read_form(environ)
                word = service.add_word(
                    form.get("word", ""),
                    form.get("meaning", ""),
                    form.get("example", ""),
                )
                return _redirect(
                    start_response,
                    f"/admin?message=Added+{quote_plus(word.word)}",
                )

            if method == "POST" and path in (
                "/admin/words/edit",
                "/admin/edit-word",
            ):
                form = _read_form(environ)
                service.edit_word(
                    _word_id(form),
                    meaning=form.get("meaning", ""),
                    example=form.get("example", ""),
                )
                return _redirect(start_response, "/admin?message=Saved")

            if method == "POST" and path in (
                "/admin/words/suspend",
                "/admin/suspend-word",
            ):
                form = _read_form(environ)
                service.suspend_word(_word_id(form))
                return _redirect(start_response, "/admin?message=Suspended")

            if method == "POST" and path in ("/admin/import", "/admin/import-csv"):
                form = _read_form(environ)
                result = service.import_csv_text(
                    form.get("csv_text", form.get("csv_file", ""))
                )
                message = (
                    f"Imported created={result.created} "
                    f"updated={result.updated} failed={result.failed}"
                )
                return _redirect(
                    start_response,
                    f"/admin?message={quote_plus(message)}",
                )

        except (KeyError, ValueError) as exc:
            return _response(start_response, "400 Bad Request", str(exc))

        return _response(start_response, "404 Not Found", "Not Found")

    return app


def _word_id(form: dict[str, str]) -> str:
    return form.get("id") or form.get("word_id", "")


def run_server(
    host: str = "0.0.0.0",
    port: int = 8000,
    data_dir: str | Path = "data",
) -> None:
    service = StickWordsService(data_dir)
    app = create_app(service)
    with make_server(host, port, app) as server:
        print(f"StickWords admin: http://localhost:{port}/admin")
        server.serve_forever()
