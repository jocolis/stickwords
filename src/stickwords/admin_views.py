from __future__ import annotations

from html import escape
from typing import Iterable, Mapping

from .models import Word, format_dt


def render_admin_page(
    status: Mapping[str, int],
    words: Iterable[Word],
    message: str = "",
    server_url: str = "http://localhost:8000",
) -> str:
    stats_html = "\n".join(_render_stat(label, status.get(key, 0)) for label, key in _stat_items(status))
    message_html = ""
    if message:
        message_html = f'<p class="message">{_html(message)}</p>'

    rows_html = "\n".join(_render_word_row(word) for word in words)
    if not rows_html:
        rows_html = '<tr><td colspan="7">No words yet.</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>StickWords Admin</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; line-height: 1.4; }}
    header {{ margin-bottom: 1.5rem; }}
    section {{ margin: 1.5rem 0; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f5f5f5; }}
    input, textarea {{ display: block; margin: 0.25rem 0 0.5rem; max-width: 32rem; width: 100%; }}
    textarea {{ min-height: 4rem; }}
    button {{ margin-top: 0.25rem; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 0.75rem; padding: 0; list-style: none; }}
    .stats li {{ border: 1px solid #ddd; padding: 0.75rem; min-width: 8rem; }}
    .stat-value {{ display: block; font-size: 1.5rem; font-weight: bold; }}
    .message {{ background: #eef8ee; border: 1px solid #b9dfb9; padding: 0.75rem; }}
    .server-url {{ font-family: monospace; }}
  </style>
</head>
<body>
  <header>
    <h1>StickWords</h1>
    <p>M5Stick server URL: <span class="server-url">{_html(server_url)}</span></p>
    {message_html}
  </header>

  <section aria-labelledby="status-heading">
    <h2 id="status-heading">Status</h2>
    <ul class="stats">
{stats_html}
    </ul>
  </section>

  <section aria-labelledby="add-word-heading">
    <h2 id="add-word-heading">Add Word</h2>
    <form method="post" action="/admin/add-word">
      <label>Word <input name="word" required></label>
      <label>Meaning <input name="meaning" required></label>
      <label>Example <textarea name="example" required></textarea></label>
      <button type="submit">Add Word</button>
    </form>
  </section>

  <section aria-labelledby="import-csv-heading">
    <h2 id="import-csv-heading">Import CSV</h2>
    <form method="post" action="/admin/import">
      <label>CSV Text <textarea name="csv_text" required>word,meaning,example
</textarea></label>
      <button type="submit">Import CSV</button>
    </form>
  </section>

  <section aria-labelledby="words-heading">
    <h2 id="words-heading">Words table</h2>
    <table>
      <thead>
        <tr>
          <th>Word</th>
          <th>Meaning</th>
          <th>Example</th>
          <th>Status</th>
          <th>Due Date</th>
          <th>Edit</th>
          <th>Suspend</th>
        </tr>
      </thead>
      <tbody>
{rows_html}
      </tbody>
    </table>
  </section>
</body>
</html>"""


def _stat_items(status: Mapping[str, int]) -> list[tuple[str, str]]:
    items = [
        ("Total Words", "total_words"),
        ("New Words", "new_words"),
    ]
    if "learning_words" in status:
        items.append(("Learning Words", "learning_words"))
    items.extend(
        [
            ("Review Words", "review_words"),
            ("Suspended Words", "suspended_words"),
            ("Due Today", "due_today"),
        ]
    )
    return items


def _render_stat(label: str, value: int) -> str:
    return f'      <li><span class="stat-value">{_html(str(value))}</span>{_html(label)}</li>'


def _render_word_row(word: Word) -> str:
    word_id = _html(word.id)
    return f"""        <tr>
          <td>{_html(word.word)}</td>
          <td>{_html(word.meaning)}</td>
          <td>{_html(word.example)}</td>
          <td>{_html(word.status)}</td>
          <td>{_html(format_dt(word.due_at))}</td>
          <td>
            <form method="post" action="/admin/edit-word">
              <input type="hidden" name="word_id" value="{word_id}">
              <label>Meaning <input name="meaning" value="{_html(word.meaning)}" required></label>
              <label>Example <textarea name="example" required>{_html(word.example)}</textarea></label>
              <button type="submit">Save</button>
            </form>
          </td>
          <td>
            <form method="post" action="/admin/suspend-word">
              <input type="hidden" name="word_id" value="{word_id}">
              <button type="submit">Suspend</button>
            </form>
          </td>
        </tr>"""


def _html(value: str) -> str:
    return escape(value, quote=True)
