# StickWords Handoff

## Current Status

Stage 1 PC backend core is implemented and tested.

## How To Test

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected result: all 24 tests pass.

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

## Known Limits

- No web UI yet.
- No HTTP API yet.
- No USB configuration yet.
- No M5Stick firmware yet.
- Tests use `.test-tmp/` inside the repository because this Windows sandbox can reject Python writes to `TemporaryDirectory()` paths.

## Next Stage

Build stage 2: PC web management page and `start_stickwords.bat`.
