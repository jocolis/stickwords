from __future__ import annotations

import csv
from pathlib import Path

from .models import VOCAB_FIELDS, Word


class VocabStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load(self) -> list[Word]:
        if not self.path.exists():
            return []

        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            fieldnames = reader.fieldnames or []
            missing = [field for field in VOCAB_FIELDS if field not in fieldnames]
            if missing:
                raise ValueError(
                    f"vocab CSV missing required columns: {', '.join(missing)}"
                )
            return [Word.from_row(row) for row in reader]

    def save(self, words: list[Word]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")

        with temp_path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=VOCAB_FIELDS)
            writer.writeheader()
            for word in words:
                writer.writerow(word.to_row())

        temp_path.replace(self.path)
