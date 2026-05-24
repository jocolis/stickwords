#!/usr/bin/env python3
"""Quickly add an example-backed word to StickWords.

Usage:
    python scripts/quick_add.py
    python scripts/quick_add.py --example "A sentence with a new word."
    python scripts/quick_add.py --data-dir data
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stickwords.service import StickWordsService  # noqa: E402


DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"

COBUILD_PROMPT = """You are a professional English lexicographer writing in the Collins COBUILD style.

Write a definition for the word "{word}" based on this example sentence:

"{example}"

Collins COBUILD style rules:
- Write the definition as a complete, natural English sentence, never just synonyms or short phrases
- The sentence should begin with a structure like "If you describe something as ...", "When you ...", "A ... is ...", etc.
- Only define the specific sense of the word used in the example sentence
- The tone should be clear and explanatory, as if a teacher explaining to a student
- Write in plain, natural English

Output only the definition sentence, with no prefix, label, or explanation."""

_tk = None
_ttk = None
_messagebox = None
_TclError = None


def add_or_update(
    data_dir: Path | str,
    word: str,
    meaning: str,
    example: str,
    clock: Callable[[], datetime] | None = None,
):
    service = StickWordsService(data_dir, clock=clock) if clock else StickWordsService(data_dir)
    return service.add_or_update_word(word, meaning, example)


def call_deepseek(word: str, example: str, api_key: str) -> str:
    prompt = COBUILD_PROMPT.format(word=word, example=example)
    body = json.dumps(
        {
            "model": DEEPSEEK_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a professional English lexicographer skilled in "
                        "Collins COBUILD style definitions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 300,
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        DEEPSEEK_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()


def _init_tk() -> None:
    global _tk, _ttk, _messagebox, _TclError
    if _tk is not None:
        return
    try:
        import tkinter as _tk  # type: ignore[no-redef]
        from tkinter import TclError as _TclError  # type: ignore[no-redef]
        from tkinter import messagebox as _messagebox  # type: ignore[no-redef]
        from tkinter import ttk as _ttk  # type: ignore[no-redef]
    except ImportError:
        sys.exit("Tkinter is not available. On Windows, the standard Python installer includes it.")


class QuickAddApp:
    FONT_BOLD = ("Segoe UI", 10, "bold")
    FONT_ENTRY = ("Segoe UI", 12)
    FONT_TEXT = ("Segoe UI", 11)

    def __init__(self, data_dir: Path, initial_example: str = ""):
        _init_tk()
        self.data_dir = data_dir
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()

        self.root = _tk.Tk()
        self.root.title("StickWords Quick Add")
        self.root.geometry("520x440")
        self.root.minsize(400, 320)
        self.root.resizable(True, True)
        self.root.attributes("-topmost", True)
        self.root.bind("<Escape>", lambda _event: self.root.destroy())

        style = _ttk.Style()
        style.theme_use("clam")

        _ttk.Label(self.root, text="Example", font=self.FONT_BOLD).pack(
            anchor="w", padx=12, pady=(12, 0)
        )
        self.example_text = _tk.Text(
            self.root, height=3, width=58, wrap="word", font=self.FONT_TEXT
        )
        self.example_text.pack(fill="x", padx=12, pady=(2, 0))
        self.example_text.bind("<Double-Button-1>", self._on_example_double_click)
        if initial_example:
            self.example_text.insert("1.0", initial_example)

        _ttk.Label(self.root, text="Word", font=self.FONT_BOLD).pack(
            anchor="w", padx=12, pady=(12, 0)
        )
        self.word_entry = _ttk.Entry(self.root, font=self.FONT_ENTRY)
        self.word_entry.pack(fill="x", padx=12, pady=(2, 0))
        self.word_entry.focus_set()
        self.word_entry.bind("<Return>", lambda _event: self._on_generate())

        _ttk.Label(self.root, text="Meaning", font=self.FONT_BOLD).pack(
            anchor="w", padx=12, pady=(12, 0)
        )
        self.meaning_text = _tk.Text(
            self.root, height=4, width=58, wrap="word", font=self.FONT_TEXT
        )
        self.meaning_text.pack(fill="x", padx=12, pady=(2, 0))

        buttons = _ttk.Frame(self.root)
        buttons.pack(fill="x", padx=12, pady=(12, 0))
        self.generate_button = _ttk.Button(
            buttons, text="Generate Meaning", command=self._on_generate
        )
        self.generate_button.pack(side="left", padx=(0, 8))
        self.add_button = _ttk.Button(buttons, text="Add To StickWords", command=self._on_add)
        self.add_button.pack(side="left")

        self.status_label = _ttk.Label(self.root, text="", foreground="gray")
        self.status_label.pack(anchor="w", padx=12, pady=(8, 12))
        if not self.api_key:
            self.status_label.config(
                text="DEEPSEEK_API_KEY is not set. Enter meaning manually.",
                foreground="orange",
            )

    def _on_example_double_click(self, event) -> None:
        index = self.example_text.index(f"@{event.x},{event.y}")
        start = self.example_text.index(f"{index} wordstart")
        end = self.example_text.index(f"{index} wordend")
        word = self.example_text.get(start, end).strip()
        while word and not word[0].isalpha():
            word = word[1:]
        while word and not word[-1].isalpha():
            word = word[:-1]
        if not word:
            return
        self.word_entry.delete(0, "end")
        self.word_entry.insert(0, word)
        self._on_generate()

    def _on_generate(self) -> None:
        word = self.word_entry.get().strip()
        example = self.example_text.get("1.0", "end-1c").strip()
        if not word:
            _messagebox.showwarning("Missing word", "Enter a word first.")
            return
        if not example:
            _messagebox.showwarning("Missing example", "Enter or paste an example first.")
            return
        if word.casefold() not in example.casefold():
            ok = _messagebox.askyesno(
                "Word not found",
                f"'{word}' was not found in the example.\n\nContinue anyway?",
            )
            if not ok:
                self.word_entry.focus_set()
                return
        if not self.api_key:
            _messagebox.showwarning(
                "No API key",
                "DEEPSEEK_API_KEY is not set. Enter meaning manually.",
            )
            return

        self.status_label.config(text="Calling DeepSeek...", foreground="blue")
        self.generate_button.config(state="disabled")
        self.root.update()
        try:
            definition = call_deepseek(word, example, self.api_key)
            self.meaning_text.delete("1.0", "end")
            self.meaning_text.insert("1.0", definition)
            self.status_label.config(text="Meaning generated. You can edit it.", foreground="green")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self.status_label.config(text=f"API error ({exc.code})", foreground="red")
            _messagebox.showerror("API error", body[:400])
        except OSError as exc:
            self.status_label.config(text="Network error", foreground="red")
            _messagebox.showerror("Network error", str(exc))
        finally:
            self.generate_button.config(state="normal")

    def _on_add(self) -> None:
        word = self.word_entry.get().strip()
        meaning = self.meaning_text.get("1.0", "end-1c").strip()
        example = self.example_text.get("1.0", "end-1c").strip()
        if not word:
            _messagebox.showwarning("Missing word", "Enter a word.")
            return
        if not meaning:
            _messagebox.showwarning("Missing meaning", "Enter or generate a meaning.")
            return
        if not example:
            _messagebox.showwarning("Missing example", "Enter an example.")
            return
        try:
            action, saved = add_or_update(self.data_dir, word, meaning, example)
            self.status_label.config(text=f"{action}: {saved.word}", foreground="green")
            self.root.destroy()
        except OSError as exc:
            _messagebox.showerror("Save failed", str(exc))

    def run(self) -> None:
        self.root.mainloop()


def _read_clipboard() -> str:
    _init_tk()
    try:
        temp = _tk.Tk()
        temp.withdraw()
        text = temp.clipboard_get()
        temp.destroy()
        return text
    except (_TclError, Exception):
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="StickWords Quick Add")
    parser.add_argument("--example", default="", help="Example text. Defaults to clipboard.")
    parser.add_argument("--data-dir", default=str(ROOT / "data"), help="StickWords data directory.")
    args = parser.parse_args()

    example = args.example.strip() or _read_clipboard()
    QuickAddApp(Path(args.data_dir), initial_example=example).run()


if __name__ == "__main__":
    main()
