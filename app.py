from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent
SRC_DIR = REPO_ROOT / "src"

for path in (REPO_ROOT, SRC_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from stickwords.web import run_server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args()

    run_server(host=args.host, port=args.port, data_dir=args.data_dir)


if __name__ == "__main__":
    main()
