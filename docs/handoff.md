# StickWords Handoff

## Current Status

Stage 2 PC web management page is implemented and tested.
Stage 3A M5Stick hardware check firmware is implemented and validated on the real device.
Stage 3B review UI prototype is implemented.
Stage 3C-1 left/right landscape auto-rotation is implemented and validated on the real device.
Stage 3C-2 rating-page double-shake `good` is implemented and ready for real-device validation.

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

Current Stage 3C expected boot log: `StickWords Stage 3C boot`.
Manually validate the review flow and rating-page double-shake `good` before moving to the next stage.

Note: PlatformIO auto-detected COM1 on this PC, but the M5Stick appeared as COM5. Use COM5 explicitly unless the device list changes.

## How To Test

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected result: all 55 tests pass.

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
  - word, meaning, example, rating, and done pages
  - meaning and example pages both use the same content paging path for long text
  - compact review layout without the old title, page counter, or button-hint footer
  - larger word, meaning, example, rating, and done-page text
  - Button A short press advances pages or cycles rating
  - Button A long press submits rating
  - Button B returns to previous page or re-rates previous card
  - in-memory rating overwrite logs
- Stage 3C-1 left/right landscape auto-rotation:
  - reuses M5Stick IMU accelerometer readings
  - switches between landscape rotations 1 and 3 after a stable 500 ms orientation signal
  - redraws the current review page without changing review progress
  - logs orientation changes to serial
  - real-device direction mapping was confirmed correct
- Stage 3C-2 rating-page double-shake `good`:
  - detects two acceleration peaks within a short window only on the rating page
  - sets the selected rating to `good` and submits immediately
  - keeps Button B re-rate behavior available on the next word page
  - logs `Shake good word=...` to serial

## Known Limits

- Stage 3B still uses built-in fake cards.
- Stage 3B ratings are stored only in RAM and disappear after reboot.
- Firmware does not implement tilt scoring yet.
- Double-shake `good` is not yet validated on the real device and may need threshold tuning.
- Auto-rotation currently depends on hand-held tilt. If the device is perfectly flat and only yaw-rotated 180 degrees, the accelerometer cannot distinguish left/right orientation.
- Firmware does not implement Wi-Fi sync yet.
- No sync API yet.
- No USB configuration yet.
- No multi-deck support yet.
- No multipart file upload yet.
- Tests use `.test-tmp/` inside the repository because this Windows sandbox can reject Python writes to `TemporaryDirectory()` paths.

## Next Stage

Validate Stage 3C-2 on the real M5Stick C Plus. If double-shake is too sensitive or too hard to trigger, tune `kShakeThreshold`, `kShakeReleaseThreshold`, `kShakeWindowMs`, and `kShakeCooldownMs`.
