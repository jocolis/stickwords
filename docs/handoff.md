# StickWords Handoff

## Current Status

Stage 2 PC web management page is implemented and tested.
Stage 3A M5Stick hardware check firmware is prepared for PlatformIO validation.

## How To Run

```powershell
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

Then open `http://localhost:8000/admin`.

On Windows, you can also double-click `start_stickwords.bat`.

## How To Run Firmware Hardware Check

Open a PlatformIO terminal, then run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
pio run --target upload
pio device monitor
```

See `docs/stage3a_platformio_quickstart.md` for beginner-friendly steps and expected output.

## How To Test

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected result: all 51 tests pass.

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
- Stage 3A firmware skeleton:
  - PlatformIO project under `firmware/`
  - fixed landscape status screen
  - serial boot log
  - Button A/Button B detection
  - IMU acceleration readout

## Known Limits

- Stage 3A requires real-device manual validation with PlatformIO.
- Firmware does not implement review UI yet.
- Firmware does not implement Wi-Fi sync yet.
- No sync API yet.
- No USB configuration yet.
- No multi-deck support yet.
- No multipart file upload yet.
- Tests use `.test-tmp/` inside the repository because this Windows sandbox can reject Python writes to `TemporaryDirectory()` paths.

## Next Stage

Validate Stage 3A on the real M5Stick C Plus. After it passes, build Stage 3B: minimum review UI prototype with fake local cards.
