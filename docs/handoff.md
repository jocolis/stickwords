# StickWords Handoff

## Current Status

Stage 4 minimum PC-to-M5Stick sync is implemented and ready for real-device validation.

Completed milestones:

- Stage 1 PC backend core.
- Stage 2 PC web management page.
- Stage 3A M5Stick hardware check, validated on the real device.
- Stage 3B local review UI prototype.
- Stage 3C-1 left/right landscape auto-rotation, validated on the real device.
- Stage 3C-2 rating-page double-shake `good`, validated on the real device.
- Stage 4 PC device sync API and firmware HTTP sync path.

## How To Run The PC Backend

```powershell
cd C:\Users\ASUS\Documents\M5Stick
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

Then open `http://localhost:8000/admin`.

On Windows, you can also double-click `start_stickwords.bat`.

The admin page displays the suggested `STICKWORDS_SERVER_URL` for the M5Stick.
When opened from `localhost`, the server tries to show a LAN IPv4 URL such as `http://192.168.x.x:8000` instead of `localhost`.

## How To Configure Firmware Sync

Create a private local secrets file from the committed template:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
Copy-Item include\secrets.example.h include\secrets.h
```

Edit `firmware\include\secrets.h`:

```cpp
#define STICKWORDS_WIFI_SSID "your-2.4ghz-wifi-name"
#define STICKWORDS_WIFI_PASSWORD "your-wifi-password"
#define STICKWORDS_SERVER_URL "http://192.168.x.x:8000"
```

Use the PC's LAN IPv4 address in `STICKWORDS_SERVER_URL`, not `localhost`, because `localhost` on the M5Stick means the M5Stick itself.

`firmware\include\secrets.h` is intentionally ignored by Git. Do not commit real Wi-Fi credentials.

## How To Build, Upload, And Monitor Firmware

Open a PlatformIO terminal, then run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
pio run --target upload --upload-port COM5
pio device monitor --port COM5
```

Current Stage 4 expected boot log: `StickWords Stage 4 boot`.

Note: PlatformIO previously auto-detected COM1 on this PC, but the M5Stick appeared as COM5. Use COM5 explicitly unless the device list changes.

## How To Test

```powershell
cd C:\Users\ASUS\Documents\M5Stick
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected result: all 73 tests pass.

Firmware build:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
```

Expected result: PlatformIO build succeeds.

## What Works

- CSV vocab loading and saving.
- CSV import with duplicate-word update rules and duplicate-row reporting.
- Lightweight SM-2 review updates.
- Today-task generation.
- Idempotent review-event processing.
- PC web admin page:
  - `/admin`
  - add, edit, and suspend words
  - CSV import by file picker or textarea text fallback
  - `/api/status` JSON status endpoint
  - suggested M5Stick LAN server URL when opened from localhost
  - Windows launcher through `start_stickwords.bat`
- Device sync API:
  - `GET /api/device/tasks?limit=20`
  - `POST /api/device/reviews`
  - bounded review-event processing with accepted-count response
- Firmware review UI:
  - word, meaning pages, example pages, rating page, and done page
  - long meaning and example content can page forward through the single review flow
  - content pages use a larger per-page text budget to reduce unnecessary page turns
  - compact layout without the old title, page counter, or footer hints
  - Button A short press advances pages or cycles rating
  - Button A long press submits rating
  - Button B returns to previous page or re-rates the previous card from the next word page
- Firmware orientation and gesture input:
  - left/right landscape auto-rotation using IMU readings
  - rating-page double-shake submits `good`
- Firmware HTTP sync:
  - connects to 2.4 GHz Wi-Fi using `secrets.h`
  - fetches due cards from the PC backend at boot
  - falls back to built-in sample cards when Wi-Fi or sync fails
  - queues review results in RAM
  - posts queued reviews to the PC backend after rating submission
  - keeps pending reviews when upload fails or the server response is not accepted

## Known Limits

- Stage 4 uses a manually configured LAN URL; there is no automatic PC discovery yet.
- The M5Stick must be on the same reachable LAN as the PC backend.
- Windows firewall may block inbound access to port 8000 until allowed.
- Firmware sync currently uses plain HTTP without authentication.
- Pending firmware reviews are stored in RAM and are lost on reboot or power loss before upload.
- Review correction after a successful upload is sent as a fresh review event; the PC backend accepts idempotent event IDs but does not yet merge correction semantics across different event IDs.
- Firmware JSON parsing is deliberately small and bounded for the known PC API shape, not a general JSON parser.
- No USB configuration UI yet.
- No multi-deck support yet.
- No multipart file upload yet.
- Tests use `.test-tmp/` inside the repository because this Windows sandbox can reject Python writes to `TemporaryDirectory()` paths.

## Next Stage

Run Stage 4 on the real M5Stick C Plus:

1. Start the PC backend with `--host 0.0.0.0`.
2. Confirm the PC LAN IPv4 address with `ipconfig`.
3. Put that address into `firmware\include\secrets.h`.
4. Build and upload firmware with PlatformIO.
5. Watch serial logs for Wi-Fi connection, `GET /api/device/tasks`, and `POST /api/device/reviews`.
6. Complete one review on the M5Stick and confirm `data\vocab.csv` updates through the PC admin page.
