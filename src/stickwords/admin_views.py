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
    stats_html = "\n".join(
        _render_stat(label, status.get(key, 0)) for label, key in _stat_items(status)
    )
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
    :root {{
      color-scheme: light;
      --bg: #f4f6f8;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #64748b;
      --line: #d8dee8;
      --line-soft: #edf1f5;
      --accent: #2563eb;
      --accent-dark: #1d4ed8;
      --success-bg: #ecfdf3;
      --success-line: #a7f3c4;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", Arial, sans-serif;
      line-height: 1.45;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 28px 24px 40px;
    }}
    header {{
      margin-bottom: 20px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 2rem;
      font-weight: 700;
    }}
    h2 {{
      margin: 0 0 16px;
      font-size: 1.05rem;
      font-weight: 650;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      margin: 16px 0;
      padding: 18px;
      box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      background: var(--panel);
    }}
    th, td {{
      border-bottom: 1px solid var(--line-soft);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #f8fafc;
      color: #475569;
      font-size: 0.82rem;
      font-weight: 650;
      text-transform: uppercase;
    }}
    input, textarea {{
      display: block;
      margin: 6px 0 12px;
      max-width: 36rem;
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 9px 10px;
      font: inherit;
      background: #fff;
    }}
    input[type="file"] {{
      padding: 8px;
      background: #f8fafc;
    }}
    textarea {{
      min-height: 5rem;
      resize: vertical;
    }}
    button {{
      border: 0;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      cursor: pointer;
      font: inherit;
      font-weight: 650;
      padding: 9px 14px;
    }}
    button:hover {{
      background: var(--accent-dark);
    }}
    label {{
      color: #334155;
      font-weight: 600;
    }}
    .subtitle {{
      color: var(--muted);
      margin: 0;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
      gap: 12px;
      padding: 0;
      list-style: none;
      margin: 0;
    }}
    .stats li {{
      border: 1px solid var(--line-soft);
      border-radius: 8px;
      padding: 14px;
      background: #fbfcfe;
    }}
    .stat-value {{
      display: block;
      font-size: 1.65rem;
      font-weight: 750;
      line-height: 1.1;
    }}
    .message {{
      background: var(--success-bg);
      border: 1px solid var(--success-line);
      border-radius: 8px;
      padding: 10px 12px;
    }}
    .server-url {{
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      font-family: Consolas, "Segoe UI Mono", monospace;
      padding: 3px 6px;
    }}
    .form-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px 24px;
      align-items: start;
    }}
    .table-wrap {{
      overflow-x: auto;
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>StickWords</h1>
    <p class="subtitle">M5Stick server URL: <span class="server-url">{_html(server_url)}</span></p>
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
      <div class="form-grid">
        <label>Word <input name="word" required></label>
        <label>Meaning <input name="meaning" required></label>
        <label>Example <textarea name="example" required></textarea></label>
      </div>
      <button type="submit">Add Word</button>
    </form>
  </section>

  <section aria-labelledby="import-csv-heading">
    <h2 id="import-csv-heading">Import CSV</h2>
    <form method="post" action="/admin/import" enctype="multipart/form-data">
      <div class="form-grid">
        <label>Choose CSV File <input type="file" name="csv_file" accept=".csv,text/csv"></label>
        <label>CSV Text <textarea name="csv_text">word,meaning,example
</textarea></label>
      </div>
      <button type="submit">Import CSV</button>
    </form>
  </section>

  <section aria-labelledby="words-heading">
    <h2 id="words-heading">Words table</h2>
    <div class="table-wrap">
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
    </div>
  </section>
</main>
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
