# StickWords Stage 4 Minimum Sync Design

## Goal

Stage 4 builds the first real sync loop between the PC backend and the M5Stick C Plus.
The target is small and testable: the M5Stick can fetch due review cards from the PC, use the existing review UI, and send completed ratings back to the PC.

## Current Context

The PC backend already stores words in `data/vocab.csv`, schedules due cards, and applies review ratings.
The web server is a standard-library WSGI app in `src/stickwords/web.py`.
The firmware currently uses three built-in cards and already has the review flow, content paging, left/right landscape auto-rotation, and double-shake `good` on the rating page.

## Scope

Stage 4 includes:

- PC JSON endpoint for device tasks.
- PC JSON endpoint for device review uploads.
- Firmware private network configuration through `firmware/include/secrets.h`.
- Firmware example config through `firmware/include/secrets.example.h`.
- Firmware Wi-Fi connection and HTTP sync using the configured PC server URL.
- Replacing the built-in card list with synced cards after a successful sync.
- Uploading ratings from the current review session.
- Clear serial logs and simple on-screen failure states for troubleshooting.

Stage 4 does not include:

- Automatic PC discovery.
- Captive-portal Wi-Fi setup.
- USB configuration.
- HTTPS or authentication.
- Offline persistent storage on the M5Stick.
- Multi-deck support.
- Large vocabulary paging beyond a small task batch.

## Network Assumption

The user confirmed the Wi-Fi is 2.4GHz.
The M5Stick and PC are expected to be on the same LAN.
The PC server remains started with:

```powershell
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

The M5Stick uses a configured LAN URL such as:

```cpp
#define STICKWORDS_SERVER_URL "http://192.168.1.100:8000"
```

## Private Firmware Configuration

Add `firmware/include/secrets.example.h` to git:

```cpp
#pragma once

#define STICKWORDS_WIFI_SSID "your-2.4ghz-wifi-name"
#define STICKWORDS_WIFI_PASSWORD "your-wifi-password"
#define STICKWORDS_SERVER_URL "http://192.168.1.100:8000"
```

The user copies it to `firmware/include/secrets.h` and edits local values.
`firmware/include/secrets.h` must be ignored by git.
The firmware includes only `secrets.h`; build errors should clearly tell the user to create it if missing.

## PC API

### `GET /api/device/tasks`

Returns due cards as JSON.
Initial query parameters:

- `limit`: optional integer, default `20`, maximum `50`.

Response:

```json
{
  "generated_at": "2026-05-24T12:00:00+00:00",
  "tasks": [
    {
      "id": "w-000001",
      "word": "abandon",
      "meaning": "give up",
      "example": "Do not abandon your plan when practice gets hard."
    }
  ]
}
```

The endpoint should omit suspended words because it uses the existing scheduler.
If there are no due cards, return `200 OK` with an empty `tasks` array.

### `POST /api/device/reviews`

Accepts completed ratings from the M5Stick.
Request:

```json
{
  "device_id": "m5stick-c-plus",
  "reviews": [
    {
      "word_id": "w-000001",
      "rating": "good",
      "reviewed_at": "2026-05-24T12:03:00+00:00",
      "event_id": "m5stick-c-plus-20260524T120300-w-000001"
    }
  ]
}
```

Response:

```json
{
  "accepted": 1,
  "failed": 0,
  "errors": []
}
```

Ratings use the existing values: `forgot`, `hard`, and `good`.
The PC should process each review idempotently through the existing review-event path.
Unknown words or invalid ratings should be reported in `errors` without crashing the server.

## Firmware Sync Flow

For the first implementation, sync can be triggered at startup after Wi-Fi connects.
If startup sync succeeds:

1. Fetch `/api/device/tasks`.
2. Parse the JSON response.
3. Copy up to a fixed maximum number of cards into firmware memory.
4. Start the existing review UI with the synced cards.

If startup sync fails:

1. Show a short sync failure message on screen.
2. Print the HTTP or Wi-Fi error to serial.
3. Fall back to the existing built-in sample cards so UI testing remains possible.

After each rating submission:

1. Store a pending review in RAM.
2. Attempt to upload pending reviews to `/api/device/reviews`.
3. If upload succeeds, clear those pending reviews.
4. If upload fails, keep them in RAM for another attempt while power remains on.

Stage 4 does not need to survive power loss on the M5Stick. PC-side CSV data remains durable.

## Firmware Data Limits

Use fixed-size arrays to keep memory behavior predictable:

- Maximum synced cards: 20.
- Maximum word length: 31 characters plus null terminator.
- Maximum meaning length: 191 characters plus null terminator.
- Maximum example length: 255 characters plus null terminator.
- Maximum pending reviews: 20.

Long PC fields should be truncated safely on the M5Stick.
The PC keeps the full source text in `vocab.csv`.

## UI Impact

The existing review UI should remain the main experience.
Stage 4 adds only minimal sync states:

- `WiFi...`
- `Sync...`
- `Sync failed`
- `No due cards`

Button behavior inside the review flow remains unchanged:

- Button A advances pages or cycles rating.
- Button A long press submits rating.
- Button B returns or re-rates previous card.
- Double-shake on rating page submits `good`.

## Testing

PC tests should cover:

- `/api/device/tasks` returns scheduled cards as JSON.
- `/api/device/tasks` supports an optional limit.
- `/api/device/reviews` accepts valid ratings and updates word review state.
- `/api/device/reviews` reports invalid rows without server failure.

Firmware source tests should cover:

- `secrets.example.h` exists and defines the required macros.
- `secrets.h` is ignored by git.
- Firmware includes Wi-Fi and HTTP client support.
- Firmware has fixed-size synced card storage.
- Firmware has pending review upload code.

Manual real-device validation should cover:

- PC server reachable from another LAN device by IP.
- M5Stick connects to Wi-Fi.
- M5Stick fetches tasks from the PC.
- Review flow shows real words from `data/vocab.csv`.
- Ratings upload back to the PC and change future scheduling.

## Risks

- Windows firewall may block inbound LAN access to port `8000`.
- The PC LAN IP can change. The user may need to update `STICKWORDS_SERVER_URL`.
- The first JSON parser approach must be small enough for the firmware and reliable enough for the known response shape.
- Wi-Fi credentials must never be committed.

## Success Criteria

Stage 4 is complete when:

- PC tests pass.
- Firmware builds with a local `secrets.h`.
- The M5Stick can fetch at least one real card from `data/vocab.csv`.
- A `good`, `hard`, or `forgot` rating from the M5Stick changes the PC CSV review state.
- The private Wi-Fi config remains untracked.
