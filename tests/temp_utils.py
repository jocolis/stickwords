from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from shutil import rmtree
from typing import Iterator
from uuid import uuid4


@contextmanager
def workspace_temp_dir() -> Iterator[Path]:
    base = Path(__file__).resolve().parents[1] / ".test-tmp"
    base.mkdir(exist_ok=True)
    temp_dir = base / f"case-{uuid4().hex}"
    temp_dir.mkdir()
    try:
        yield temp_dir
    finally:
        rmtree(temp_dir, ignore_errors=True)
