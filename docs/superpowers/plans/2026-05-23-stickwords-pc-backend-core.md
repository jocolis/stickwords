# StickWords PC Backend Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first independently testable PC backend core for StickWords: CSV persistence, CSV import, spaced-repetition scheduling, today-task selection, and idempotent review-event processing.

**Architecture:** Implement a small Python package under `src/stickwords` with focused modules: models, CSV storage, importer, scheduler, and review processing. This phase intentionally avoids HTTP, web UI, USB, and M5Stick firmware so the data rules can be verified locally before integration.

**Tech Stack:** Python 3 standard library, `dataclasses`, `csv`, `datetime`, `tempfile`, `unittest`.

---

## Scope

This plan implements only roadmap stage 1:

- `data/vocab.csv` read/write.
- CSV batch import.
- Duplicate `word` import updates `meaning` and `example` while preserving review progress.
- Lightweight SM-2 review rules for `forgot`, `hard`, and `good`.
- Today-task generation with due cards first and new cards after.
- Idempotent `review_event_id` handling.

This plan does not implement:

- `app.py`.
- `/admin` web UI.
- HTTP API.
- USB configuration.
- M5Stick firmware.

## File Structure

Create these files:

```text
pyproject.toml
src/stickwords/__init__.py
src/stickwords/models.py
src/stickwords/storage.py
src/stickwords/importer.py
src/stickwords/scheduler.py
src/stickwords/reviews.py
tests/test_models.py
tests/test_storage.py
tests/test_importer.py
tests/test_scheduler.py
tests/test_reviews.py
```

Responsibilities:

- `models.py`: shared dataclasses, constants, datetime parsing/formatting, and row conversion.
- `storage.py`: CSV file creation, loading, saving, and atomic-ish replacement writes.
- `importer.py`: user CSV import rules.
- `scheduler.py`: spaced-repetition updates and today-task selection.
- `reviews.py`: idempotent review-event storage and batch processing.
- `tests/`: behavior-level tests for each module.

## Task 1: Project Scaffold And Data Models

**Files:**
- Create: `pyproject.toml`
- Create: `src/stickwords/__init__.py`
- Create: `src/stickwords/models.py`
- Test: `tests/test_models.py`

- [ ] **Step 1: Write the failing model tests**

Create `tests/test_models.py`:

```python
import unittest
from datetime import datetime, timezone

from stickwords.models import (
    RATING_FORGOT,
    RATING_GOOD,
    RATING_HARD,
    STATUS_NEW,
    VOCAB_FIELDS,
    Word,
    format_dt,
    parse_dt,
)


class ModelTests(unittest.TestCase):
    def test_word_defaults_match_design(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )

        self.assertEqual(word.id, "w-1")
        self.assertEqual(word.word, "abandon")
        self.assertEqual(word.meaning, "放弃")
        self.assertEqual(word.example, "Do not abandon your plan.")
        self.assertEqual(word.status, STATUS_NEW)
        self.assertEqual(word.added_at, now)
        self.assertEqual(word.due_at, now)
        self.assertIsNone(word.last_reviewed_at)
        self.assertEqual(word.review_count, 0)
        self.assertEqual(word.ease, 2.5)
        self.assertEqual(word.interval_days, 0)
        self.assertEqual(word.lapses, 0)
        self.assertEqual(word.updated_at, now)

    def test_word_round_trip_csv_row(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )

        row = word.to_row()
        restored = Word.from_row(row)

        self.assertEqual(list(row.keys()), VOCAB_FIELDS)
        self.assertEqual(restored, word)

    def test_datetime_format_is_stable_utc_iso(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        value = format_dt(now)

        self.assertEqual(value, "2026-05-23T10:00:00Z")
        self.assertEqual(parse_dt(value), now)

    def test_supported_ratings_are_explicit(self):
        self.assertEqual(RATING_FORGOT, "forgot")
        self.assertEqual(RATING_HARD, "hard")
        self.assertEqual(RATING_GOOD, "good")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
python -m unittest tests.test_models -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stickwords'`.

- [ ] **Step 3: Add package configuration**

Create `pyproject.toml`:

```toml
[project]
name = "stickwords"
version = "0.1.0"
description = "M5Stick C Plus vocabulary review system using spaced repetition"
requires-python = ">=3.11"

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]
```

Create `src/stickwords/__init__.py`:

```python
"""StickWords PC backend core."""
```

- [ ] **Step 4: Implement models**

Create `src/stickwords/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

STATUS_NEW = "new"
STATUS_LEARNING = "learning"
STATUS_REVIEW = "review"
STATUS_SUSPENDED = "suspended"

RATING_FORGOT = "forgot"
RATING_HARD = "hard"
RATING_GOOD = "good"

VOCAB_FIELDS = [
    "id",
    "word",
    "meaning",
    "example",
    "status",
    "added_at",
    "last_reviewed_at",
    "due_at",
    "review_count",
    "ease",
    "interval_days",
    "lapses",
    "updated_at",
]


def normalize_dt(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def format_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    normalized = normalize_dt(value)
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value).astimezone(timezone.utc)


@dataclass
class Word:
    id: str
    word: str
    meaning: str
    example: str
    status: str
    added_at: datetime
    last_reviewed_at: datetime | None
    due_at: datetime
    review_count: int
    ease: float
    interval_days: int
    lapses: int
    updated_at: datetime

    @classmethod
    def new_word(
        cls,
        *,
        word_id: str,
        word: str,
        meaning: str,
        example: str,
        now: datetime,
    ) -> "Word":
        now = normalize_dt(now)
        return cls(
            id=word_id,
            word=word.strip(),
            meaning=meaning.strip(),
            example=example.strip(),
            status=STATUS_NEW,
            added_at=now,
            last_reviewed_at=None,
            due_at=now,
            review_count=0,
            ease=2.5,
            interval_days=0,
            lapses=0,
            updated_at=now,
        )

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "Word":
        added_at = parse_dt(row["added_at"])
        due_at = parse_dt(row["due_at"])
        updated_at = parse_dt(row["updated_at"])
        if added_at is None or due_at is None or updated_at is None:
            raise ValueError("added_at, due_at, and updated_at are required")
        return cls(
            id=row["id"],
            word=row["word"],
            meaning=row["meaning"],
            example=row["example"],
            status=row["status"],
            added_at=added_at,
            last_reviewed_at=parse_dt(row["last_reviewed_at"]),
            due_at=due_at,
            review_count=int(row["review_count"]),
            ease=float(row["ease"]),
            interval_days=int(row["interval_days"]),
            lapses=int(row["lapses"]),
            updated_at=updated_at,
        )

    def to_row(self) -> dict[str, str]:
        return {
            "id": self.id,
            "word": self.word,
            "meaning": self.meaning,
            "example": self.example,
            "status": self.status,
            "added_at": format_dt(self.added_at),
            "last_reviewed_at": format_dt(self.last_reviewed_at),
            "due_at": format_dt(self.due_at),
            "review_count": str(self.review_count),
            "ease": f"{self.ease:.2f}",
            "interval_days": str(self.interval_days),
            "lapses": str(self.lapses),
            "updated_at": format_dt(self.updated_at),
        }
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_models -v
```

Expected: PASS, 4 tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add pyproject.toml src/stickwords/__init__.py src/stickwords/models.py tests/test_models.py
git commit -m "Add StickWords backend models"
```

## Task 2: CSV Vocab Store

**Files:**
- Create: `src/stickwords/storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write failing storage tests**

Create `tests/test_storage.py`:

```python
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from stickwords.models import VOCAB_FIELDS, Word
from stickwords.storage import VocabStore


class VocabStoreTests(unittest.TestCase):
    def test_load_missing_file_returns_empty_list(self):
        with TemporaryDirectory() as temp_dir:
            store = VocabStore(Path(temp_dir) / "vocab.csv")

            self.assertEqual(store.load(), [])

    def test_save_creates_parent_directory_and_header(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "data" / "vocab.csv"
            store = VocabStore(path)
            store.save([word])

            content = path.read_text(encoding="utf-8-sig").splitlines()
            self.assertEqual(content[0], ",".join(VOCAB_FIELDS))
            self.assertEqual(store.load(), [word])

    def test_load_rejects_missing_required_columns(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "vocab.csv"
            path.write_text("word,meaning,example\nabandon,放弃,x\n", encoding="utf-8")
            store = VocabStore(path)

            with self.assertRaisesRegex(ValueError, "missing required columns"):
                store.load()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_storage -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stickwords.storage'`.

- [ ] **Step 3: Implement storage**

Create `src/stickwords/storage.py`:

```python
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
                raise ValueError(f"vocab CSV missing required columns: {', '.join(missing)}")
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_storage -v
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Run model and storage tests together**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_models tests.test_storage -v
```

Expected: PASS, 7 tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/stickwords/storage.py tests/test_storage.py
git commit -m "Add vocab CSV storage"
```

## Task 3: CSV Import Rules

**Files:**
- Create: `src/stickwords/importer.py`
- Test: `tests/test_importer.py`

- [ ] **Step 1: Write failing importer tests**

Create `tests/test_importer.py`:

```python
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from stickwords.importer import import_words
from stickwords.models import STATUS_REVIEW, Word


class ImporterTests(unittest.TestCase):
    def test_import_new_words_from_simple_csv(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "import.csv"
            path.write_text(
                "word,meaning,example\n"
                "abandon,放弃,Do not abandon your plan.\n"
                "benefit,好处,This change has a clear benefit.\n",
                encoding="utf-8",
            )

            result = import_words(existing=[], import_path=path, now=now)

        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.failed, 0)
        self.assertEqual([word.word for word in result.words], ["abandon", "benefit"])
        self.assertEqual(result.words[0].id, "w-000001")
        self.assertEqual(result.words[1].id, "w-000002")

    def test_duplicate_word_updates_content_but_preserves_review_state(self):
        added_at = datetime(2026, 5, 20, 10, 0, tzinfo=timezone.utc)
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        existing = Word.new_word(
            word_id="w-000001",
            word="abandon",
            meaning="旧释义",
            example="Old example.",
            now=added_at,
        )
        existing.status = STATUS_REVIEW
        existing.review_count = 4
        existing.ease = 2.2
        existing.interval_days = 3
        existing.lapses = 1
        existing.due_at = now + timedelta(days=3)

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "import.csv"
            path.write_text(
                "word,meaning,example\n"
                "abandon,放弃,Do not abandon your plan.\n",
                encoding="utf-8",
            )

            result = import_words(existing=[existing], import_path=path, now=now)

        updated = result.words[0]
        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.failed, 0)
        self.assertEqual(updated.id, "w-000001")
        self.assertEqual(updated.meaning, "放弃")
        self.assertEqual(updated.example, "Do not abandon your plan.")
        self.assertEqual(updated.status, STATUS_REVIEW)
        self.assertEqual(updated.review_count, 4)
        self.assertEqual(updated.ease, 2.2)
        self.assertEqual(updated.interval_days, 3)
        self.assertEqual(updated.lapses, 1)
        self.assertEqual(updated.added_at, added_at)
        self.assertEqual(updated.updated_at, now)

    def test_blank_word_rows_fail_without_stopping_import(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "import.csv"
            path.write_text(
                "word,meaning,example\n"
                ",空行,No word.\n"
                "benefit,好处,This change has a clear benefit.\n",
                encoding="utf-8",
            )

            result = import_words(existing=[], import_path=path, now=now)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.errors, ["row 2: word is required"])
        self.assertEqual(result.words[0].word, "benefit")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_importer -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stickwords.importer'`.

- [ ] **Step 3: Implement importer**

Create `src/stickwords/importer.py`:

```python
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
        if word.id.startswith("w-") and word.id[2:].isdigit():
            max_number = max(max_number, int(word.id[2:]))
    return f"w-{max_number + created_count + 1:06d}"


def import_words(*, existing: list[Word], import_path: Path | str, now: datetime) -> ImportResult:
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
            raw_word = (row.get("word") or "").strip()
            meaning = (row.get("meaning") or "").strip()
            example = (row.get("example") or "").strip()

            if not raw_word:
                failed += 1
                errors.append(f"row {row_number}: word is required")
                continue

            key = raw_word.casefold()
            if key in by_word:
                word = by_word[key]
                word.word = raw_word
                word.meaning = meaning
                word.example = example
                word.updated_at = now
                updated += 1
                continue

            word = Word.new_word(
                word_id=_next_word_id(words, created),
                word=raw_word,
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_importer -v
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Run all current tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 10 tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/stickwords/importer.py tests/test_importer.py
git commit -m "Add vocab CSV import rules"
```

## Task 4: Lightweight SM-2 Review Updates

**Files:**
- Create: `src/stickwords/scheduler.py`
- Test: `tests/test_scheduler.py`

- [ ] **Step 1: Write failing review-rule tests**

Create `tests/test_scheduler.py`:

```python
import unittest
from datetime import datetime, timedelta, timezone

from stickwords.models import (
    RATING_FORGOT,
    RATING_GOOD,
    RATING_HARD,
    STATUS_LEARNING,
    STATUS_NEW,
    STATUS_REVIEW,
    STATUS_SUSPENDED,
    Word,
)
from stickwords.scheduler import apply_review, get_today_tasks


class SchedulerTests(unittest.TestCase):
    def test_forgot_moves_card_to_learning_soon(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )

        reviewed = apply_review(word, rating=RATING_FORGOT, reviewed_at=now)

        self.assertEqual(reviewed.status, STATUS_LEARNING)
        self.assertEqual(reviewed.review_count, 1)
        self.assertEqual(reviewed.lapses, 1)
        self.assertEqual(reviewed.ease, 2.3)
        self.assertEqual(reviewed.interval_days, 0)
        self.assertEqual(reviewed.last_reviewed_at, now)
        self.assertEqual(reviewed.due_at, now + timedelta(minutes=10))

    def test_hard_keeps_short_interval(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )
        word.interval_days = 3
        word.ease = 2.0

        reviewed = apply_review(word, rating=RATING_HARD, reviewed_at=now)

        self.assertEqual(reviewed.status, STATUS_REVIEW)
        self.assertEqual(reviewed.review_count, 1)
        self.assertEqual(reviewed.ease, 1.95)
        self.assertEqual(reviewed.interval_days, 4)
        self.assertEqual(reviewed.due_at, now + timedelta(days=4))

    def test_good_grows_interval_with_ease(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )
        word.interval_days = 2
        word.ease = 2.5

        reviewed = apply_review(word, rating=RATING_GOOD, reviewed_at=now)

        self.assertEqual(reviewed.status, STATUS_REVIEW)
        self.assertEqual(reviewed.review_count, 1)
        self.assertEqual(reviewed.ease, 2.55)
        self.assertEqual(reviewed.interval_days, 5)
        self.assertEqual(reviewed.due_at, now + timedelta(days=5))

    def test_get_today_tasks_returns_due_then_new_and_skips_suspended(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        overdue = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now - timedelta(days=3),
        )
        overdue.status = STATUS_REVIEW
        overdue.due_at = now - timedelta(days=2)

        new_word = Word.new_word(
            word_id="w-2",
            word="benefit",
            meaning="好处",
            example="This change has a clear benefit.",
            now=now,
        )

        suspended = Word.new_word(
            word_id="w-3",
            word="cancel",
            meaning="取消",
            example="Cancel the task.",
            now=now - timedelta(days=5),
        )
        suspended.status = STATUS_SUSPENDED
        suspended.due_at = now - timedelta(days=4)

        tasks = get_today_tasks(
            [new_word, suspended, overdue],
            now=now,
            max_due=20,
            max_new=5,
        )

        self.assertEqual([word.id for word in tasks], ["w-1", "w-2"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_scheduler -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stickwords.scheduler'`.

- [ ] **Step 3: Implement scheduler**

Create `src/stickwords/scheduler.py`:

```python
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta

from .models import (
    RATING_FORGOT,
    RATING_GOOD,
    RATING_HARD,
    STATUS_LEARNING,
    STATUS_NEW,
    STATUS_REVIEW,
    STATUS_SUSPENDED,
    Word,
    normalize_dt,
)


def apply_review(word: Word, *, rating: str, reviewed_at: datetime) -> Word:
    reviewed_at = normalize_dt(reviewed_at)
    updated = deepcopy(word)
    updated.review_count += 1
    updated.last_reviewed_at = reviewed_at
    updated.updated_at = reviewed_at

    if rating == RATING_FORGOT:
        updated.lapses += 1
        updated.ease = round(max(1.3, updated.ease - 0.2), 2)
        updated.interval_days = 0
        updated.due_at = reviewed_at + timedelta(minutes=10)
        updated.status = STATUS_LEARNING
        return updated

    if rating == RATING_HARD:
        updated.ease = round(max(1.3, updated.ease - 0.05), 2)
        updated.interval_days = max(1, round(updated.interval_days * 1.2))
        updated.due_at = reviewed_at + timedelta(days=updated.interval_days)
        updated.status = STATUS_REVIEW
        return updated

    if rating == RATING_GOOD:
        updated.ease = round(min(3.0, updated.ease + 0.05), 2)
        if updated.interval_days == 0:
            updated.interval_days = 1
        else:
            updated.interval_days = max(1, round(updated.interval_days * updated.ease))
        updated.due_at = reviewed_at + timedelta(days=updated.interval_days)
        updated.status = STATUS_REVIEW
        return updated

    raise ValueError(f"unsupported rating: {rating}")


def get_today_tasks(
    words: list[Word],
    *,
    now: datetime,
    max_due: int = 20,
    max_new: int = 5,
) -> list[Word]:
    now = normalize_dt(now)
    eligible = [word for word in words if word.status != STATUS_SUSPENDED]
    due_words = [
        word
        for word in eligible
        if word.status != STATUS_NEW and word.due_at <= now
    ]
    due_words.sort(key=lambda word: (word.due_at, word.word.casefold()))

    new_words = [word for word in eligible if word.status == STATUS_NEW]
    new_words.sort(key=lambda word: (word.added_at, word.word.casefold()))

    return due_words[:max_due] + new_words[:max_new]
```

- [ ] **Step 4: Run scheduler tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_scheduler -v
```

Expected: PASS, 4 tests.

- [ ] **Step 5: Run all current tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 14 tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/stickwords/scheduler.py tests/test_scheduler.py
git commit -m "Add spaced repetition scheduler"
```

## Task 5: Idempotent Review Event Processing

**Files:**
- Create: `src/stickwords/reviews.py`
- Test: `tests/test_reviews.py`

- [ ] **Step 1: Write failing review-event tests**

Create `tests/test_reviews.py`:

```python
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from stickwords.models import RATING_GOOD, Word
from stickwords.reviews import ReviewEvent, ReviewEventStore, process_review_events


class ReviewEventTests(unittest.TestCase):
    def test_process_review_event_updates_word_once(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        word = Word.new_word(
            word_id="w-1",
            word="abandon",
            meaning="放弃",
            example="Do not abandon your plan.",
            now=now,
        )
        event = ReviewEvent(
            review_event_id="device-1-20260523T100000-w-1",
            word_id="w-1",
            rating=RATING_GOOD,
            reviewed_at=now,
        )

        with TemporaryDirectory() as temp_dir:
            event_store = ReviewEventStore(Path(temp_dir) / "review_events.csv")
            result = process_review_events(
                words=[word],
                events=[event, event],
                event_store=event_store,
            )

            self.assertEqual(result.applied, 1)
            self.assertEqual(result.skipped_duplicate, 1)
            self.assertEqual(result.failed, 0)
            self.assertEqual(result.words[0].review_count, 1)
            self.assertEqual(event_store.load_ids(), {event.review_event_id})

    def test_unknown_word_event_is_failed_and_not_recorded(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)
        event = ReviewEvent(
            review_event_id="device-1-20260523T100000-w-missing",
            word_id="w-missing",
            rating=RATING_GOOD,
            reviewed_at=now,
        )

        with TemporaryDirectory() as temp_dir:
            event_store = ReviewEventStore(Path(temp_dir) / "review_events.csv")
            result = process_review_events(
                words=[],
                events=[event],
                event_store=event_store,
            )

            self.assertEqual(result.applied, 0)
            self.assertEqual(result.skipped_duplicate, 0)
            self.assertEqual(result.failed, 1)
            self.assertEqual(result.errors, ["unknown word_id: w-missing"])
            self.assertEqual(event_store.load_ids(), set())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_reviews -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'stickwords.reviews'`.

- [ ] **Step 3: Implement review-event processing**

Create `src/stickwords/reviews.py`:

```python
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .models import format_dt, normalize_dt, parse_dt
from .models import Word
from .scheduler import apply_review

REVIEW_EVENT_FIELDS = ["review_event_id", "word_id", "rating", "reviewed_at"]


@dataclass(frozen=True)
class ReviewEvent:
    review_event_id: str
    word_id: str
    rating: str
    reviewed_at: datetime

    def to_row(self) -> dict[str, str]:
        return {
            "review_event_id": self.review_event_id,
            "word_id": self.word_id,
            "rating": self.rating,
            "reviewed_at": format_dt(self.reviewed_at),
        }

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "ReviewEvent":
        reviewed_at = parse_dt(row["reviewed_at"])
        if reviewed_at is None:
            raise ValueError("reviewed_at is required")
        return cls(
            review_event_id=row["review_event_id"],
            word_id=row["word_id"],
            rating=row["rating"],
            reviewed_at=reviewed_at,
        )


@dataclass
class ReviewProcessResult:
    words: list[Word]
    applied: int
    skipped_duplicate: int
    failed: int
    errors: list[str]


class ReviewEventStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    def load_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        with self.path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            return {
                row["review_event_id"]
                for row in reader
                if row.get("review_event_id")
            }

    def append(self, event: ReviewEvent) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.path.exists()
        with self.path.open("a", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=REVIEW_EVENT_FIELDS)
            if not exists:
                writer.writeheader()
            writer.writerow(event.to_row())


def process_review_events(
    *,
    words: list[Word],
    events: list[ReviewEvent],
    event_store: ReviewEventStore,
) -> ReviewProcessResult:
    by_id = {word.id: word for word in words}
    processed_ids = event_store.load_ids()
    applied = 0
    skipped_duplicate = 0
    failed = 0
    errors: list[str] = []

    for raw_event in events:
        event = ReviewEvent(
            review_event_id=raw_event.review_event_id,
            word_id=raw_event.word_id,
            rating=raw_event.rating,
            reviewed_at=normalize_dt(raw_event.reviewed_at),
        )
        if event.review_event_id in processed_ids:
            skipped_duplicate += 1
            continue

        if event.word_id not in by_id:
            failed += 1
            errors.append(f"unknown word_id: {event.word_id}")
            continue

        updated = apply_review(
            by_id[event.word_id],
            rating=event.rating,
            reviewed_at=event.reviewed_at,
        )
        by_id[event.word_id] = updated
        processed_ids.add(event.review_event_id)
        event_store.append(event)
        applied += 1

    updated_words = [by_id[word.id] for word in words]
    return ReviewProcessResult(
        words=updated_words,
        applied=applied,
        skipped_duplicate=skipped_duplicate,
        failed=failed,
        errors=errors,
    )
```

- [ ] **Step 4: Run review tests to verify they pass**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_reviews -v
```

Expected: PASS, 2 tests.

- [ ] **Step 5: Run all backend-core tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 16 tests.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/stickwords/reviews.py tests/test_reviews.py
git commit -m "Add idempotent review processing"
```

## Task 6: Stage 1 Integration Smoke Test And Docs

**Files:**
- Modify: `docs/dev_log.md`
- Create: `tests/test_stage1_integration.py`

- [ ] **Step 1: Write integration test**

Create `tests/test_stage1_integration.py`:

```python
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from stickwords.importer import import_words
from stickwords.models import RATING_GOOD
from stickwords.reviews import ReviewEvent, ReviewEventStore, process_review_events
from stickwords.scheduler import get_today_tasks
from stickwords.storage import VocabStore


class Stage1IntegrationTests(unittest.TestCase):
    def test_import_save_load_task_review_save_load(self):
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            import_path = temp_path / "words.csv"
            import_path.write_text(
                "word,meaning,example\n"
                "abandon,放弃,Do not abandon your plan.\n",
                encoding="utf-8",
            )

            import_result = import_words(existing=[], import_path=import_path, now=now)
            vocab_store = VocabStore(temp_path / "data" / "vocab.csv")
            vocab_store.save(import_result.words)
            loaded_words = vocab_store.load()

            tasks = get_today_tasks(loaded_words, now=now)
            self.assertEqual([word.word for word in tasks], ["abandon"])

            event_store = ReviewEventStore(temp_path / "data" / "review_events.csv")
            event = ReviewEvent(
                review_event_id="device-1-20260523T100000-w-000001",
                word_id=tasks[0].id,
                rating=RATING_GOOD,
                reviewed_at=now,
            )
            review_result = process_review_events(
                words=loaded_words,
                events=[event],
                event_store=event_store,
            )
            vocab_store.save(review_result.words)
            reloaded_words = vocab_store.load()

        self.assertEqual(reloaded_words[0].review_count, 1)
        self.assertEqual(reloaded_words[0].interval_days, 1)
        self.assertEqual(reloaded_words[0].status, "review")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run full test suite**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 17 tests.

- [ ] **Step 3: Update development log**

Append this entry to `docs/dev_log.md`:

````markdown
## 2026-05-23 阶段 1：PC 后端核心

完成内容：

- 实现 StickWords PC 后端核心 Python 包。
- 实现 CSV 词库读写。
- 实现 CSV 批量导入和重复单词更新规则。
- 实现轻量 SM-2 复习算法。
- 实现今日任务生成。
- 实现 `review_event_id` 幂等处理。
- 增加阶段 1 集成测试。

测试结果：

- `$env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 预期通过 17 个测试。

遇到的问题：

- 阶段 1 暂不处理网页、HTTP、USB 和 M5Stick 固件，避免范围扩散。

解决方式：

- 把 PC 后端核心拆成可独立测试的纯 Python 模块。

下一步：

- 进入阶段 2：PC 网页管理页和 `start_stickwords.bat`。
````

- [ ] **Step 4: Commit**

Run:

```powershell
git add tests/test_stage1_integration.py docs/dev_log.md
git commit -m "Add backend core integration coverage"
```

## Final Verification

- [ ] **Step 1: Run all tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 17 tests.

- [ ] **Step 2: Check git status**

Run:

```powershell
git status --short
```

Expected: no output.

- [ ] **Step 3: Record final status in handoff**

Create or update `docs/handoff.md` with:

````markdown
# StickWords Handoff

## Current Status

Stage 1 PC backend core is implemented and tested.

## How To Test

```powershell
$env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected result: all 17 tests pass.

## What Works

- CSV vocab loading and saving.
- CSV import with duplicate-word update rules.
- Lightweight SM-2 review updates.
- Today-task generation.
- Idempotent review-event processing.

## Known Limits

- No web UI yet.
- No HTTP API yet.
- No USB configuration yet.
- No M5Stick firmware yet.

## Next Stage

Build stage 2: PC web management page and `start_stickwords.bat`.
````

- [ ] **Step 4: Commit handoff**

Run:

```powershell
git add docs/handoff.md
git commit -m "Document backend core handoff"
```

## Self-Review

Spec coverage:

- CSV read/write: Task 2.
- CSV import: Task 3.
- Duplicate import preserving review state: Task 3.
- Lightweight SM-2 rules: Task 4.
- Today task generation: Task 4.
- `review_event_id` idempotency: Task 5.
- Stage documentation: Task 6 and final verification.

Vague-step scan:

- The plan contains no vague markers and no open-ended implementation steps.

Type consistency:

- `Word`, `ReviewEvent`, `VocabStore`, `ReviewEventStore`, `apply_review`, `get_today_tasks`, `import_words`, and `process_review_events` are defined before use in later tasks.
- Rating names use `forgot`, `hard`, and `good` consistently.
- Status names use `new`, `learning`, `review`, and `suspended` consistently.
