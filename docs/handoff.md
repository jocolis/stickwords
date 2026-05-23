# StickWords Handoff

## Current Status

Stage 2 PC web management page is implemented and tested.

## How To Run

```powershell
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

Then open `http://localhost:8000/admin`.

On Windows, you can also double-click `start_stickwords.bat`.

## How To Test

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected result: all 48 tests pass.

## What Works

- CSV vocab loading and saving.
- CSV import with duplicate-word update rules.
- Lightweight SM-2 review updates.
- Today-task generation.
- Idempotent review-event processing.
- Stage 1 integration path:
  - import words
  - save vocab
  - load vocab
  - generate today's tasks
  - process a review event
  - save and reload updated review state
- Stage 2 web management page:
  - `/admin` PC web admin page
  - add, edit, and suspend words
  - textarea CSV import
  - `/api/status` JSON status endpoint
  - Windows launcher through `start_stickwords.bat`

## Known Limits

- No M5Stick firmware yet.
- No sync API yet.
- No USB configuration yet.
- No multi-deck support yet.
- No multipart file upload yet.
- Tests use `.test-tmp/` inside the repository because this Windows sandbox can reject Python writes to `TemporaryDirectory()` paths.

## Next Stage

Stage 3 M5Stick UI prototype.
