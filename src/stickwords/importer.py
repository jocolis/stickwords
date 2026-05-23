from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import Word, normalize_dt


@dataclass
class ImportResult:
    words: list[Word]
    created: int
    updated: int
    failed: int
    errors: list[str]


def _next_word_id(existing: list[Word], created_count: int) -> str:
    max_number = 0
    for word in existing:
        prefix, separator, suffix = word.id.partition("-")
        if prefix == "w" and separator == "-" and suffix.isdigit():
            max_number = max(max_number, int(suffix))

    return f"w-{max_number + created_count + 1:06d}"


def import_words(
    existing: list[Word],
    import_path: Path | str,
    now: datetime,
) -> ImportResult:
    now = normalize_dt(now)
    path = Path(import_path)
    words = list(existing)
    by_word = {word.word.casefold(): word for word in words}
    created = 0
    updated = 0
    failed = 0
    errors: list[str] = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        fieldnames = reader.fieldnames or []
        for required in ("word", "meaning", "example"):
            if required not in fieldnames:
                raise ValueError(f"import CSV missing required column: {required}")

        for row_number, row in enumerate(reader, start=2):
            word_text = (row.get("word") or "").strip()
            meaning = (row.get("meaning") or "").strip()
            example = (row.get("example") or "").strip()

            if word_text == "":
                failed += 1
                errors.append(f"row {row_number}: word is required")
                continue

            key = word_text.casefold()
            if key in by_word:
                word = by_word[key]
                word.word = word_text
                word.meaning = meaning
                word.example = example
                word.updated_at = now
                updated += 1
                continue

            word = Word.new_word(
                word_id=_next_word_id(existing, created),
                word=word_text,
                meaning=meaning,
                example=example,
                now=now,
            )
            words.append(word)
            by_word[key] = word
            created += 1

    return ImportResult(
        words=words,
        created=created,
        updated=updated,
        failed=failed,
        errors=errors,
    )
