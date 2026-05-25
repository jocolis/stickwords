# StickWords Handoff

## Current Status

Stage 4 minimum PC-to-M5Stick sync is implemented and validated on the real M5Stick C Plus.
Quick Add helper scripts are available for adding example-backed words from the PC.

Completed milestones:

- Stage 1 PC backend core.
- Stage 2 PC web management page.
- Stage 3A M5Stick hardware check, validated on the real device.
- Stage 3B local review UI prototype.
- Stage 3C-1 left/right landscape auto-rotation, validated on the real device.
- Stage 3C-2 rating-page double-shake `good`, validated on the real device.
- Stage 4 PC device sync API, firmware HTTP sync path, cached task fallback, pending-review recovery, device setup portal, and captive portal setup assist.
- Stage 5A RTC calibration from backend sync time.

## How To Run The PC Backend

```powershell
cd C:\Users\ASUS\Documents\M5Stick
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

Then open `http://localhost:8000/admin`.

On Windows, you can also double-click `start_stickwords.bat`.
The launcher stops any existing process listening on port `8000`, then starts the current backend and opens `/admin`.

The admin page displays the suggested `STICKWORDS_SERVER_URL` for the M5Stick.
When opened from `localhost`, the server tries to show a LAN IPv4 URL such as `http://192.168.x.x:8000` instead of `localhost`.

## How To Configure M5Stick Wi-Fi And Server URL

The normal path is the M5Stick setup portal:

1. Upload firmware once.
2. Hold Button B while rebooting the M5Stick.
3. Connect a PC or phone to the `StickWords-Setup` Wi-Fi network.
4. Most phones should automatically open the setup/login page. If not, open `http://192.168.4.1` manually.
5. Enter the 2.4 GHz Wi-Fi SSID, password, and StickWords server URL shown on the PC admin page.
6. Save and wait for the M5Stick to restart.

The setup screen shows:

```text
Setup mode
WiFi: StickWords-Setup
Open: 192.168.4.1
```

The admin page displays the suggested StickWords server URL. Use the PC's LAN IPv4 address, not `localhost`, because `localhost` on the M5Stick means the M5Stick itself.

`firmware\include\secrets.h` remains a developer fallback and must not contain committed real credentials.

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

Expected result: all tests pass.

Firmware build:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
```

Expected result: PlatformIO build succeeds.

## How To Use Quick Add

Quick Add is a small PC-side helper for adding a word from a selected sentence.
It writes to the same `data\vocab.csv` through `StickWordsService`, so duplicate words update the existing row while preserving review progress.

Optional AI definition generation uses DeepSeek:

```powershell
$env:DEEPSEEK_API_KEY='your-api-key'
```

Manual meaning entry still works without an API key.

Run directly:

```powershell
cd C:\Users\ASUS\Documents\M5Stick
python scripts\quick_add.py --example "This change has a clear benefit."
```

On Windows, you can also run `scripts\setup_quick_add_hotkey.ps1` once to create a desktop shortcut with `Ctrl+Alt+W`.
The intended daily workflow is: copy a sentence in Obsidian or Chrome, press `Ctrl+Alt+W`, double-click or type the target word, generate or enter the meaning, then add it to StickWords.

## What Works

- CSV vocab loading and saving.
- CSV import with duplicate-word update rules and duplicate-row reporting.
- Quick Add helper for clipboard/example-backed word entry, with optional DeepSeek definition generation.
- Lightweight SM-2 review updates.
- Today-task generation.
- Idempotent review-event processing.
- PC web admin page:
  - `/admin`
  - add, edit, and suspend words
  - CSV import by file picker or textarea text fallback
  - `/api/status` JSON status endpoint
  - suggested M5Stick LAN server URL when opened from localhost
  - searchable words table without inline edit controls
  - threaded local WSGI server to avoid one stuck request blocking sync
  - Windows launcher through `start_stickwords.bat`
- Device sync API:
  - `GET /api/device/tasks?limit=20`
  - `POST /api/device/reviews`
  - bounded review-event processing with accepted-count response
- Firmware review UI:
  - word, meaning pages, example pages, rating page, and done page
  - long meaning and example content can page forward through the single review flow
  - content pages wrap and paginate at English word boundaries where possible
  - compact layout without the old title, page counter, or footer hints
  - Button A short press advances pages or cycles rating
  - Button A long press submits rating
  - Button B returns to previous page or re-rates the previous card from the next word page
- Firmware orientation and gesture input:
  - left/right landscape auto-rotation using IMU readings
  - rating-page double-shake submits `good`
- Firmware HTTP sync:
  - stores Wi-Fi and server URL settings in ESP32 flash
  - provides a `StickWords-Setup` temporary hotspot and `http://192.168.4.1` setup page
  - uses captive DNS and common phone captive-portal probe redirects during setup mode
  - enters setup mode when Button B is held at boot or when no runtime config exists
  - connects to 2.4 GHz Wi-Fi using runtime config, with `secrets.h` kept as a developer fallback
  - fetches due cards from the PC backend at boot
  - sets the BM8563 RTC from the backend `generated_at` timestamp after successful sync
  - logs RTC status at boot and after calibration with `RTC now=... valid=1` or `RTC now=invalid valid=0`
  - shows a UTC+8 clock page after normal boot while keeping RTC/sync timestamps internally in UTC
  - short-press Button A on the clock page to enter the review/status flow
  - shows an explicit status page when Wi-Fi fails, sync fails, or there are no due cards
  - caches the most recently synced due-card batch in ESP32 flash
  - loads cached due cards when Wi-Fi or sync fails
  - queues review results and persists the pending queue in ESP32 flash
  - posts queued reviews to the PC backend after rating submission
  - keeps pending reviews when upload fails or the server response is not accepted
  - uploads persisted pending reviews on the next successful Wi-Fi boot

## Known Limits

- Stage 4 uses a manually configured LAN URL through the setup portal; automatic PC/backend discovery is a future improvement.
- The M5Stick must be on the same reachable LAN as the PC backend.
- Windows firewall may block inbound access to port 8000 until allowed.
- Firmware sync currently uses plain HTTP without authentication.
- Firmware cached-task fallback only reuses the last synced due-card batch. It does not compute future due cards offline.
- Firmware now sets and logs the M5StickC Plus BM8563 RTC from backend sync time, but it does not yet use RTC time for offline due-card scheduling.
- Review correction after a successful upload is sent as a fresh review event; the PC backend accepts idempotent event IDs but does not yet merge correction semantics across different event IDs.
- Firmware JSON parsing is deliberately small and bounded for the known PC API shape, not a general JSON parser.
- Setup portal has no password; only enable it intentionally by holding Button B or when no config exists.
- Captive portal auto-open is best-effort and depends on phone OS/browser behavior. If it does not pop up automatically, open `http://192.168.4.1` manually.
- No multi-deck support yet.
- Quick Add requires PC-side Python/Tkinter and does not run on the M5Stick itself.
- DeepSeek generation requires `DEEPSEEK_API_KEY`; without it, the helper is manual-entry only.
- Tests use `.test-tmp/` inside the repository because this Windows sandbox can reject Python writes to `TemporaryDirectory()` paths.

## Future Improvements

- Automatic PC/backend discovery, for example via mDNS, UDP broadcast, or a setup-page helper that can provide the current LAN server URL without manual copying.
- RTC-backed offline due-card scheduling: set the BM8563 RTC from the PC/backend during sync, persist enough scheduling metadata on the device, and use the RTC to decide whether cached future cards are due when Wi-Fi is unavailable.

## Real-Device Validation Notes

On the real M5Stick C Plus, Stage 4 was validated with these serial-log signals:

- Wi-Fi connected at `192.168.5.172`.
- PC backend was reachable at `http://192.168.5.105:8000`.
- When the backend was unreachable, firmware logged `Sync failed status=-1`, then loaded `Loaded cached cards=1` and continued with cached review cards.
- After an offline review and reboot, firmware logged `Loaded pending reviews=1`, proving the pending queue survived power loss/restart.
- After the backend became reachable again, firmware posted to `/api/device/reviews` and received `{"accepted": 1, "skipped_duplicate": 0, "failed": 0, "errors": []}`.
- On the next reboot, firmware logged `Loaded pending reviews=0`, proving the uploaded pending review was cleared.

Stage 5A RTC validation procedure:

1. Start the PC backend.
2. Boot M5Stick with Wi-Fi available.
3. Confirm serial shows `RTC set=...` and `RTC now=... valid=1`.
4. Power off M5Stick.
5. Wait 1 to 2 minutes.
6. Boot again and confirm `RTC now=... valid=1` moved forward.

## Next Stage

Choose the next product milestone:

1. Improve M5Stick Chinese rendering.
2. Add easier Wi-Fi/server configuration instead of editing `secrets.h`.
3. Improve offline-review semantics beyond the last cached due-card batch.
4. Prepare the GitHub publication path: README, screenshots, license, and repository hygiene.
