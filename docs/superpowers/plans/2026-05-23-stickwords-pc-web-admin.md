# StickWords PC Web Admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first PC-side StickWords web management console and Windows launch entrypoint.

**Architecture:** Keep the web layer small and dependency-free by using Python standard-library WSGI. Add a service layer over the existing CSV/import/scheduler/review core, a pure HTML rendering layer, a WSGI app/router, and a Windows batch launcher that starts `app.py` and opens `/admin`.

**Tech Stack:** Python 3 standard library, `wsgiref.simple_server`, `urllib.parse`, `html`, `unittest`, Windows batch.

---

## Scope

This plan implements roadmap stage 2:

- `app.py` starts a local PC backend server.
- `/admin` displays a management console.
- The web page can add words, edit meaning/example, suspend words, paste-import CSV, and view basic status.
- `/api/status` returns JSON status for later M5Stick integration.
- `start_stickwords.bat` starts the server and opens `http://localhost:8000/admin`.

This plan does not implement:

- M5Stick firmware.
- Wi-Fi sync endpoints for device tasks/reviews.
- USB serial configuration.
- User accounts.
- Multi-deck support.
- File-upload multipart CSV import. Stage 2 uses textarea CSV paste to keep the first web console simple and testable.

## File Structure

Create these files:

```text
app.py
start_stickwords.bat
src/stickwords/service.py
src/stickwords/admin_views.py
src/stickwords/web.py
tests/test_service.py
tests/test_admin_views.py
tests/test_web.py
```

Modify these files:

```text
docs/dev_log.md
docs/handoff.md
```

Responsibilities:

- `service.py`: business operations for the PC app: stats, add/edit/suspend, import CSV text, today tasks, recent words.
- `admin_views.py`: pure HTML string rendering with escaping.
- `web.py`: WSGI routing, form parsing, redirects, JSON response, and server runner.
- `app.py`: command-line entrypoint for the PC backend server.
- `start_stickwords.bat`: Windows-friendly double-click launcher.
- `tests/test_service.py`: service behavior against temporary workspace data.
- `tests/test_admin_views.py`: HTML escaping and expected page sections.
- `tests/test_web.py`: WSGI route behavior without opening a real socket.

## Task 1: Service Layer

**Files:**
- Create: `src/stickwords/service.py`
- Test: `tests/test_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_service.py`:

```python
import unittest
from datetime import datetime, timezone

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
```

- [ ] **Step 2: Run service tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_service -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stickwords.service'`.

- [ ] **Step 3: Implement service layer**

Create `src/stickwords/service.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

from .importer import ImportResult, import_words
from .models import STATUS_NEW, STATUS_REVIEW, STATUS_SUSPENDED, Word, normalize_dt
from .scheduler import get_today_tasks
from .storage import VocabStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class StickWordsService:
    data_dir: Path | str
    clock: object = utc_now

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.vocab_store = VocabStore(self.data_dir / "vocab.csv")

    def now(self) -> datetime:
        return normalize_dt(self.clock())

    def load_words(self) -> list[Word]:
        return self.vocab_store.load()

    def save_words(self, words: list[Word]) -> None:
        self.vocab_store.save(words)

    def next_word_id(self, words: list[Word]) -> str:
        max_number = 0
        for word in words:
            if word.id.startswith("w-") and word.id[2:].isdigit():
                max_number = max(max_number, int(word.id[2:]))
        return f"w-{max_number + 1:06d}"

    def add_word(self, word: str, meaning: str, example: str) -> Word:
        words = self.load_words()
        new_word = Word.new_word(
            word_id=self.next_word_id(words),
            word=word,
            meaning=meaning,
            example=example,
            now=self.now(),
        )
        words.append(new_word)
        self.save_words(words)
        return new_word

    def edit_word(self, word_id: str, *, meaning: str, example: str) -> Word:
        words = self.load_words()
        now = self.now()
        for word in words:
            if word.id == word_id:
                word.meaning = meaning.strip()
                word.example = example.strip()
                word.updated_at = now
                self.save_words(words)
                return word
        raise KeyError(f"unknown word_id: {word_id}")

    def suspend_word(self, word_id: str) -> Word:
        words = self.load_words()
        now = self.now()
        for word in words:
            if word.id == word_id:
                word.status = STATUS_SUSPENDED
                word.updated_at = now
                self.save_words(words)
                return word
        raise KeyError(f"unknown word_id: {word_id}")

    def import_csv_text(self, csv_text: str) -> ImportResult:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", newline="", delete=False, dir=self.data_dir) as file:
            file.write(csv_text)
            import_path = Path(file.name)
        try:
            result = import_words(
                existing=self.load_words(),
                import_path=import_path,
                now=self.now(),
            )
            self.save_words(result.words)
            return result
        finally:
            import_path.unlink(missing_ok=True)

    def get_today_tasks(self, *, max_due: int = 20, max_new: int = 5) -> list[Word]:
        return get_today_tasks(self.load_words(), self.now(), max_due, max_new)

    def get_status(self) -> dict[str, int]:
        words = self.load_words()
        due_today = len(self.get_today_tasks())
        return {
            "total_words": len(words),
            "new_words": sum(1 for word in words if word.status == STATUS_NEW),
            "review_words": sum(1 for word in words if word.status == STATUS_REVIEW),
            "suspended_words": sum(1 for word in words if word.status == STATUS_SUSPENDED),
            "due_today": due_today,
        }

    def recent_words(self, limit: int = 50) -> list[Word]:
        words = self.load_words()
        words.sort(key=lambda word: (word.updated_at, word.word.casefold()), reverse=True)
        return words[:limit]
```

- [ ] **Step 4: Run service tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_service -v
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Run all tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/stickwords/service.py tests/test_service.py
git commit -m "Add web admin service layer"
```

## Task 2: Admin HTML Rendering

**Files:**
- Create: `src/stickwords/admin_views.py`
- Test: `tests/test_admin_views.py`

- [ ] **Step 1: Write failing view tests**

Create `tests/test_admin_views.py`:

```python
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run view tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_admin_views -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stickwords.admin_views'`.

- [ ] **Step 3: Implement HTML rendering**

Create `src/stickwords/admin_views.py`:

```python
from __future__ import annotations

from html import escape

from .models import Word, format_dt


def _input(name: str, value: str = "", input_type: str = "text") -> str:
    return f'<input type="{input_type}" name="{escape(name)}" value="{escape(value)}">'


def _word_row(word: Word) -> str:
    return f"""
    <tr>
      <td>{escape(word.word)}</td>
      <td>{escape(word.meaning)}</td>
      <td>{escape(word.example)}</td>
      <td>{escape(word.status)}</td>
      <td>{escape(format_dt(word.due_at))}</td>
      <td>
        <form method="post" action="/admin/words/edit">
          <input type="hidden" name="id" value="{escape(word.id)}">
          {_input("meaning", word.meaning)}
          {_input("example", word.example)}
          <button type="submit">Save</button>
        </form>
        <form method="post" action="/admin/words/suspend">
          <input type="hidden" name="id" value="{escape(word.id)}">
          <button type="submit">Suspend</button>
        </form>
      </td>
    </tr>
    """


def render_admin_page(
    *,
    status: dict[str, int],
    words: list[Word],
    message: str = "",
    server_url: str = "http://localhost:8000",
) -> str:
    rows = "\n".join(_word_row(word) for word in words)
    message_html = f'<p class="message">{escape(message)}</p>' if message else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>StickWords Admin</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; max-width: 1200px; }}
    header {{ display: flex; justify-content: space-between; gap: 16px; align-items: baseline; }}
    section {{ margin-top: 24px; }}
    .stats {{ display: grid; grid-template-columns: repeat(5, minmax(120px, 1fr)); gap: 8px; }}
    .stat {{ border: 1px solid #ddd; padding: 12px; }}
    label {{ display: block; margin-top: 8px; }}
    input, textarea {{ width: 100%; box-sizing: border-box; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; vertical-align: top; }}
    button {{ margin-top: 8px; }}
    .message {{ padding: 8px; background: #eef7ee; border: 1px solid #b8dfb8; }}
  </style>
</head>
<body>
  <header>
    <h1>StickWords</h1>
    <p>M5Stick server URL: <code>{escape(server_url)}</code></p>
  </header>
  {message_html}
  <section class="stats" aria-label="Status">
    <div class="stat"><strong>Total Words</strong><br>{status["total_words"]}</div>
    <div class="stat"><strong>New</strong><br>{status["new_words"]}</div>
    <div class="stat"><strong>Review</strong><br>{status["review_words"]}</div>
    <div class="stat"><strong>Suspended</strong><br>{status["suspended_words"]}</div>
    <div class="stat"><strong>Due Today</strong><br>{status["due_today"]}</div>
  </section>
  <section>
    <h2>Add Word</h2>
    <form method="post" action="/admin/words">
      <label>Word {_input("word")}</label>
      <label>Meaning {_input("meaning")}</label>
      <label>Example <textarea name="example" rows="3"></textarea></label>
      <button type="submit">Add</button>
    </form>
  </section>
  <section>
    <h2>Import CSV</h2>
    <form method="post" action="/admin/import">
      <textarea name="csv_text" rows="8">word,meaning,example
</textarea>
      <button type="submit">Import</button>
    </form>
  </section>
  <section>
    <h2>Words</h2>
    <table>
      <thead><tr><th>Word</th><th>Meaning</th><th>Example</th><th>Status</th><th>Due</th><th>Actions</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </section>
</body>
</html>"""
```

- [ ] **Step 4: Run view tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_admin_views -v
```

Expected: PASS, 2 tests.

- [ ] **Step 5: Run all tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/stickwords/admin_views.py tests/test_admin_views.py
git commit -m "Add admin HTML rendering"
```

## Task 3: WSGI Admin Routes

**Files:**
- Create: `src/stickwords/web.py`
- Test: `tests/test_web.py`

- [ ] **Step 1: Write failing WSGI tests**

Create `tests/test_web.py`:

```python
import io
import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlencode

from stickwords.service import StickWordsService
from stickwords.web import create_app
from tests.temp_utils import workspace_temp_dir


def call_app(app, method="GET", path="/admin", body="", content_type="application/x-www-form-urlencoded"):
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
            form = urlencode({"word": "benefit", "meaning": "好处", "example": "A clear benefit."})

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

    def test_unknown_route_returns_404(self):
        with workspace_temp_dir() as temp_dir:
            app = create_app(StickWordsService(temp_dir))

            status, headers, body = call_app(app, "GET", "/missing")

            self.assertEqual(status, "404 Not Found")
            self.assertIn("Not Found", body)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run WSGI tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_web -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stickwords.web'`.

- [ ] **Step 3: Implement WSGI app**

Create `src/stickwords/web.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, quote_plus
from wsgiref.simple_server import make_server

from .admin_views import render_admin_page
from .service import StickWordsService


def _read_form(environ: dict) -> dict[str, str]:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    raw = environ["wsgi.input"].read(length).decode("utf-8")
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[0] for key, values in parsed.items()}


def _response(start_response, status: str, body: str, content_type: str = "text/plain; charset=utf-8"):
    start_response(status, [("Content-Type", content_type)])
    return [body.encode("utf-8")]


def _redirect(start_response, location: str):
    start_response("303 See Other", [("Location", location), ("Content-Type", "text/plain; charset=utf-8")])
    return [b""]


def _server_url(environ: dict) -> str:
    scheme = environ.get("wsgi.url_scheme", "http")
    host = environ.get("HTTP_HOST") or f'{environ.get("SERVER_NAME", "127.0.0.1")}:{environ.get("SERVER_PORT", "8000")}'
    return f"{scheme}://{host}"


def create_app(service: StickWordsService):
    def app(environ, start_response):
        method = environ.get("REQUEST_METHOD", "GET").upper()
        path = environ.get("PATH_INFO", "/")
        query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)

        try:
            if method == "GET" and path in ("/", "/admin"):
                html = render_admin_page(
                    status=service.get_status(),
                    words=service.recent_words(),
                    message=(query.get("message") or [""])[0],
                    server_url=_server_url(environ),
                )
                return _response(start_response, "200 OK", html, "text/html; charset=utf-8")

            if method == "GET" and path == "/api/status":
                body = json.dumps(service.get_status(), ensure_ascii=False)
                return _response(start_response, "200 OK", body, "application/json; charset=utf-8")

            if method == "POST" and path == "/admin/words":
                form = _read_form(environ)
                word = service.add_word(
                    form.get("word", ""),
                    form.get("meaning", ""),
                    form.get("example", ""),
                )
                return _redirect(start_response, f"/admin?message=Added+{quote_plus(word.word)}")

            if method == "POST" and path == "/admin/words/edit":
                form = _read_form(environ)
                service.edit_word(
                    form.get("id", ""),
                    meaning=form.get("meaning", ""),
                    example=form.get("example", ""),
                )
                return _redirect(start_response, "/admin?message=Saved")

            if method == "POST" and path == "/admin/words/suspend":
                form = _read_form(environ)
                service.suspend_word(form.get("id", ""))
                return _redirect(start_response, "/admin?message=Suspended")

            if method == "POST" and path == "/admin/import":
                form = _read_form(environ)
                result = service.import_csv_text(form.get("csv_text", ""))
                message = f"Imported created={result.created} updated={result.updated} failed={result.failed}"
                return _redirect(start_response, f"/admin?message={quote_plus(message)}")

        except (KeyError, ValueError) as exc:
            return _response(start_response, "400 Bad Request", str(exc))

        return _response(start_response, "404 Not Found", "Not Found")

    return app


def run_server(*, host: str = "0.0.0.0", port: int = 8000, data_dir: str | Path = "data") -> None:
    service = StickWordsService(data_dir)
    app = create_app(service)
    with make_server(host, port, app) as server:
        print(f"StickWords admin: http://localhost:{port}/admin")
        server.serve_forever()
```

- [ ] **Step 4: Run WSGI tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_web -v
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Run all tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/stickwords/web.py tests/test_web.py
git commit -m "Add web admin routes"
```

## Task 4: App Entrypoint And Windows Launcher

**Files:**
- Create: `app.py`
- Create: `start_stickwords.bat`
- Test: `tests/test_web.py`

- [ ] **Step 1: Add entrypoint test**

Append this test to `tests/test_web.py`:

```python
    def test_app_module_imports(self):
        import app

        self.assertTrue(callable(app.main))
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_web.WebTests.test_app_module_imports -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'app'`.

- [ ] **Step 3: Implement `app.py`**

Create `app.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from stickwords.web import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the StickWords PC admin server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port, data_dir=args.data_dir)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Create Windows launcher**

Create `start_stickwords.bat`:

```bat
@echo off
setlocal
cd /d "%~dp0"
start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 1; Start-Process 'http://localhost:8000/admin'"
python app.py --host 0.0.0.0 --port 8000 --data-dir data
endlocal
```

- [ ] **Step 5: Run tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add app.py start_stickwords.bat tests/test_web.py
git commit -m "Add StickWords app launcher"
```

## Task 5: Stage 2 Integration Test And Documentation

**Files:**
- Create: `tests/test_stage2_integration.py`
- Modify: `docs/dev_log.md`
- Modify: `docs/handoff.md`

- [ ] **Step 1: Write integration test**

Create `tests/test_stage2_integration.py`:

```python
import io
import json
import unittest
from datetime import datetime, timezone
from urllib.parse import urlencode

from stickwords.service import StickWordsService
from stickwords.web import create_app
from tests.temp_utils import workspace_temp_dir


def call_app(app, method="GET", path="/admin", body=""):
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
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
        "wsgi.input": io.BytesIO(body_bytes),
        "SERVER_NAME": "localhost",
        "SERVER_PORT": "8000",
        "wsgi.url_scheme": "http",
    }
    response_body = b"".join(app(environ, start_response)).decode("utf-8")
    return captured["status"], captured["headers"], response_body


class Stage2IntegrationTests(unittest.TestCase):
    def test_web_admin_add_import_status_flow(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            app = create_app(service)

            add_form = urlencode({
                "word": "abandon",
                "meaning": "放弃",
                "example": "Do not abandon your plan.",
            })
            add_status, _, _ = call_app(app, "POST", "/admin/words", add_form)

            import_form = urlencode({
                "csv_text": "word,meaning,example\nbenefit,好处,This change has a clear benefit.\n"
            })
            import_status, _, _ = call_app(app, "POST", "/admin/import", import_form)

            status, headers, body = call_app(app, "GET", "/api/status")

            self.assertEqual(add_status, "303 See Other")
            self.assertEqual(import_status, "303 See Other")
            self.assertEqual(status, "200 OK")
            self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
            self.assertEqual(json.loads(body)["total_words"], 2)
            self.assertEqual([word.word for word in service.load_words()], ["abandon", "benefit"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run full test suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 3: Update development log**

Append to `docs/dev_log.md`:

````markdown
## 2026-05-23 阶段 2：PC 网页管理页

完成内容：

- 增加 StickWords 服务层，统一网页操作和 CSV 核心逻辑。
- 增加 `/admin` 网页管理页。
- 支持添加、编辑、停用单词。
- 支持通过 textarea 粘贴 CSV 批量导入。
- 增加 `/api/status` JSON 状态接口。
- 增加 `app.py` 和 `start_stickwords.bat` 启动入口。

测试结果：

- `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`

遇到的问题：

- 第一版避免引入 Flask/FastAPI，降低安装依赖和环境配置成本。
- 文件上传的 multipart 解析会增加复杂度。

解决方式：

- 使用 Python 标准库 WSGI。
- CSV 批量导入第一版采用 textarea 粘贴 CSV 文本。

下一步：

- 进入阶段 3：M5Stick UI 原型。
````

- [ ] **Step 4: Update handoff**

Update `docs/handoff.md` current status to include:

````markdown
Stage 2 PC web management page is implemented and tested.

## How To Run

```powershell
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

Then open:

```text
http://localhost:8000/admin
```

On Windows, double-click:

```text
start_stickwords.bat
```
````

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_stage2_integration.py docs/dev_log.md docs/handoff.md
git commit -m "Document web admin handoff"
```

## Final Verification

- [ ] **Step 1: Run all tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 2: Check git status**

Run:

```powershell
git status --short
```

Expected: no output.

## Self-Review

Spec coverage:

- Web management page: Tasks 2 and 3.
- Add/edit/suspend words: Tasks 1 and 3.
- CSV batch import: Tasks 1 and 3, using textarea CSV paste.
- Status view and JSON status: Tasks 1, 2, 3.
- `app.py`: Task 4.
- `start_stickwords.bat`: Task 4.
- Stage documentation: Task 5.

Vague-step scan:

- The plan contains no vague markers and no open-ended implementation steps.

Type consistency:

- `StickWordsService`, `render_admin_page`, `create_app`, and `run_server` are defined before use in later tasks.
- Route paths are consistent: `/admin`, `/admin/words`, `/admin/words/edit`, `/admin/words/suspend`, `/admin/import`, `/api/status`.
- The test helper `workspace_temp_dir` already exists from stage 1.
