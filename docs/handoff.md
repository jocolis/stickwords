# StickWords Handoff

## Current Status

Stage 2 PC web management page is implemented and tested.
Stage 3A M5Stick hardware check firmware is implemented and validated on the real device.
Stage 3B review UI prototype is implemented and ready for real-device validation.

## How To Run

```powershell
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

Then open `http://localhost:8000/admin`.

On Windows, you can also double-click `start_stickwords.bat`.

## How To Run Current Firmware

Open a PlatformIO terminal, then run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
pio run --target upload --upload-port COM5
pio device monitor --port COM5
```

Current Stage 3B expected boot log: `StickWords Stage 3B boot`.
Manually validate the review flow before moving to the next stage.

Note: PlatformIO auto-detected COM1 on this PC, but the M5Stick appeared as COM5. Use COM5 explicitly unless the device list changes.

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
- Stage 3A hardware validation history:
  - real-device build, upload, serial monitor, Button A/B, and IMU checks passed earlier on COM5
  - current firmware has since moved to Stage 3B and no longer exposes IMU readout
- Stage 3B review UI prototype:
  - three built-in fake cards
  - word, summary, full example, rating, and done pages
  - Button A short press advances pages or cycles rating
  - Button A long press submits rating
  - Button B returns to previous page or re-rates previous card
  - in-memory rating overwrite logs

## Known Limits

- Stage 3B still uses built-in fake cards.
- Stage 3B ratings are stored only in RAM and disappear after reboot.
- Firmware does not implement tilt scoring yet.
- Firmware does not implement double-shake `good` yet.
- Firmware does not implement Wi-Fi sync yet.
- No sync API yet.
- No USB configuration yet.
- No multi-deck support yet.
- No multipart file upload yet.
- Tests use `.test-tmp/` inside the repository because this Windows sandbox can reject Python writes to `TemporaryDirectory()` paths.

## Next Stage

Validate Stage 3B on the real M5Stick C Plus. After it passes, build Stage 3C: add tilt rating, double-shake `good`, and left/right hand auto-rotation one at a time.
