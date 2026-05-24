# StickWords Stage 4 Minimum Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first LAN sync loop so the M5Stick can fetch real review cards from the PC and upload ratings back to `data/vocab.csv`.

**Architecture:** Add small JSON device endpoints to the existing standard-library WSGI server, reusing `StickWordsService`, scheduler, and review-event processing. Add private firmware config through `secrets.h`, then add Wi-Fi/HTTP sync to the current single-file firmware while preserving the existing review UI and sample-card fallback.

**Tech Stack:** Python standard library WSGI/JSON/unittest, existing StickWords service modules, PlatformIO Arduino framework, M5StickCPlus, ESP32 WiFi, HTTPClient.

---

## File Map

- Modify `src/stickwords/service.py`: add device task serialization and review upload processing.
- Modify `src/stickwords/web.py`: add JSON body parsing and `/api/device/tasks` / `/api/device/reviews` routes.
- Modify `tests/test_web.py`: cover the two device endpoints.
- Modify `tests/test_firmware_project.py`: cover private config, Wi-Fi/HTTP includes, synced storage, and pending-review upload markers.
- Modify `.gitignore`: ignore `firmware/include/secrets.h`.
- Create `firmware/include/secrets.example.h`: safe template for local Wi-Fi and PC server URL.
- Modify `firmware/src/main.cpp`: add Wi-Fi connect, task fetch, minimal JSON extraction, synced card storage, pending review upload, and sync status pages.
- Modify `docs/dev_log.md` and `docs/handoff.md`: record Stage 4 status, commands, and limitations.

## Task 1: PC Device API

**Files:**
- Modify: `src/stickwords/service.py`
- Modify: `src/stickwords/web.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write failing web tests for task download and review upload**

Append these tests inside `WebTests` in `tests/test_web.py`:

```python
    def test_get_device_tasks_returns_due_cards_json(self):
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            word = service.add_word("abandon", "give up", "Do not abandon your plan.")
            app = create_app(service)

            status, headers, body = call_app(app, "GET", "/api/device/tasks")

            payload = json.loads(body)
            self.assertEqual(status, "200 OK")
            self.assertEqual(headers["Content-Type"], "application/json; charset=utf-8")
            self.assertEqual(payload["generated_at"], "2026-05-24T12:00:00Z")
            self.assertEqual(
                payload["tasks"],
                [
                    {
                        "id": word.id,
                        "word": "abandon",
                        "meaning": "give up",
                        "example": "Do not abandon your plan.",
                    }
                ],
            )

    def test_get_device_tasks_respects_limit(self):
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            service.add_word("abandon", "give up", "Do not abandon your plan.")
            service.add_word("benefit", "good effect", "Daily review has a benefit.")
            app = create_app(service)

            status, headers, body = call_app(
                app,
                "GET",
                "/api/device/tasks",
                query_string="limit=1",
            )

            payload = json.loads(body)
            self.assertEqual(status, "200 OK")
            self.assertEqual(len(payload["tasks"]), 1)

    def test_post_device_reviews_applies_rating_and_is_idempotent(self):
        now = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            word = service.add_word("abandon", "give up", "Do not abandon your plan.")
            app = create_app(service)
            body = json.dumps(
                {
                    "device_id": "m5stick-c-plus",
                    "reviews": [
                        {
                            "word_id": word.id,
                            "rating": "good",
                            "reviewed_at": "2026-05-24T12:03:00Z",
                            "event_id": "m5stick-c-plus-20260524T120300-w-000001",
                        }
                    ],
                }
            )

            first_status, _, first_body = call_app(
                app,
                "POST",
                "/api/device/reviews",
                body,
                content_type="application/json",
            )
            second_status, _, second_body = call_app(
                app,
                "POST",
                "/api/device/reviews",
                body,
                content_type="application/json",
            )

            self.assertEqual(first_status, "200 OK")
            self.assertEqual(json.loads(first_body)["accepted"], 1)
            self.assertEqual(second_status, "200 OK")
            self.assertEqual(json.loads(second_body)["skipped_duplicate"], 1)
            reviewed = service.load_words()[0]
            self.assertEqual(reviewed.review_count, 1)
            self.assertEqual(reviewed.status, "review")

    def test_post_device_reviews_reports_invalid_rows(self):
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir)
            app = create_app(service)
            body = json.dumps(
                {
                    "device_id": "m5stick-c-plus",
                    "reviews": [
                        {
                            "word_id": "missing",
                            "rating": "good",
                            "reviewed_at": "2026-05-24T12:03:00Z",
                            "event_id": "missing-event",
                        },
                        {
                            "word_id": "",
                            "rating": "great",
                            "reviewed_at": "bad-date",
                            "event_id": "",
                        },
                    ],
                }
            )

            status, _, response_body = call_app(
                app,
                "POST",
                "/api/device/reviews",
                body,
                content_type="application/json",
            )

            payload = json.loads(response_body)
            self.assertEqual(status, "200 OK")
            self.assertEqual(payload["accepted"], 0)
            self.assertEqual(payload["failed"], 2)
            self.assertTrue(payload["errors"])
```

Also extend `call_app()` in `tests/test_web.py` to accept a query string:

```python
def call_app(
    app,
    method="GET",
    path="/admin",
    body="",
    content_type="application/x-www-form-urlencoded",
    query_string="",
):
    ...
    environ = {
        ...
        "QUERY_STRING": query_string,
        ...
    }
```

- [ ] **Step 2: Run the focused web tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_web -v
```

Expected: FAIL because `/api/device/tasks`, `/api/device/reviews`, and the service helpers do not exist yet.

- [ ] **Step 3: Add service helpers**

In `src/stickwords/service.py`, add imports:

```python
from .models import format_dt, parse_dt, RATING_FORGOT, RATING_HARD, RATING_GOOD
from .reviews import ReviewEvent, ReviewEventStore, process_review_events
```

Then add methods to `StickWordsService`:

```python
    def device_tasks_payload(self, limit: int = 20) -> dict:
        limit = max(0, min(limit, 50))
        tasks = self.get_today_tasks(max_due=limit, max_new=limit)
        return {
            "generated_at": format_dt(self.now()),
            "tasks": [
                {
                    "id": word.id,
                    "word": word.word,
                    "meaning": word.meaning,
                    "example": word.example,
                }
                for word in tasks[:limit]
            ],
        }

    def process_device_reviews(self, payload: dict) -> dict:
        raw_reviews = payload.get("reviews")
        if not isinstance(raw_reviews, list):
            raise ValueError("reviews must be a list")

        events: list[ReviewEvent] = []
        failed = 0
        errors: list[str] = []
        valid_ratings = {RATING_FORGOT, RATING_HARD, RATING_GOOD}

        for index, raw in enumerate(raw_reviews):
            if not isinstance(raw, dict):
                failed += 1
                errors.append(f"reviews[{index}] must be an object")
                continue
            try:
                word_id = str(raw.get("word_id", "")).strip()
                rating = str(raw.get("rating", "")).strip()
                event_id = str(raw.get("event_id", "")).strip()
                reviewed_at = parse_dt(str(raw.get("reviewed_at", "")).strip())
                if word_id == "":
                    raise ValueError("word_id is required")
                if event_id == "":
                    raise ValueError("event_id is required")
                if rating not in valid_ratings:
                    raise ValueError(f"invalid rating: {rating}")
                if reviewed_at is None:
                    raise ValueError("reviewed_at is required")
                events.append(
                    ReviewEvent(
                        review_event_id=event_id,
                        word_id=word_id,
                        rating=rating,
                        reviewed_at=reviewed_at,
                    )
                )
            except ValueError as exc:
                failed += 1
                errors.append(f"reviews[{index}]: {exc}")

        result = process_review_events(
            words=self.load_words(),
            events=events,
            event_store=ReviewEventStore(self.data_dir / "review_events.csv"),
        )
        self.save_words(result.words)

        return {
            "accepted": result.applied,
            "skipped_duplicate": result.skipped_duplicate,
            "failed": failed + result.failed,
            "errors": errors + result.errors,
        }
```

- [ ] **Step 4: Add JSON routes**

In `src/stickwords/web.py`, add a JSON reader:

```python
def _read_json(environ: dict) -> dict:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length).decode("utf-8")
    if body.strip() == "":
        raise ValueError("JSON body is required")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("JSON body must be an object")
    return parsed
```

Inside `create_app()`, add before admin POST routes:

```python
            if method == "GET" and path == "/api/device/tasks":
                raw_limit = (query.get("limit") or ["20"])[0]
                try:
                    limit = int(raw_limit)
                except ValueError as exc:
                    raise ValueError("limit must be an integer") from exc
                body = json.dumps(
                    service.device_tasks_payload(limit),
                    ensure_ascii=False,
                )
                return _response(
                    start_response,
                    "200 OK",
                    body,
                    "application/json; charset=utf-8",
                )

            if method == "POST" and path == "/api/device/reviews":
                body = json.dumps(
                    service.process_device_reviews(_read_json(environ)),
                    ensure_ascii=False,
                )
                return _response(
                    start_response,
                    "200 OK",
                    body,
                    "application/json; charset=utf-8",
                )
```

Extend the `except` tuple to include JSON decode errors:

```python
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
```

- [ ] **Step 5: Run focused and full tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_web -v
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit PC API**

Run:

```powershell
git add src/stickwords/service.py src/stickwords/web.py tests/test_web.py
git commit -m "Add Stage 4 device sync API"
```

## Task 2: Firmware Private Config Guardrails

**Files:**
- Modify: `.gitignore`
- Create: `firmware/include/secrets.example.h`
- Modify: `tests/test_firmware_project.py`

- [ ] **Step 1: Write failing firmware config tests**

Add this test to `tests/test_firmware_project.py`:

```python
    def test_stage4_private_firmware_config_is_template_only(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        example = ROOT / "firmware" / "include" / "secrets.example.h"

        self.assertIn("firmware/include/secrets.h", ignore)
        self.assertTrue(example.exists())
        text = example.read_text(encoding="utf-8")
        self.assertIn("STICKWORDS_WIFI_SSID", text)
        self.assertIn("STICKWORDS_WIFI_PASSWORD", text)
        self.assertIn("STICKWORDS_SERVER_URL", text)
        self.assertIn("your-2.4ghz-wifi-name", text)
        self.assertFalse((ROOT / "firmware" / "include" / "secrets.h").exists())
```

- [ ] **Step 2: Run focused firmware tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: FAIL because `.gitignore` and `secrets.example.h` have not been updated.

- [ ] **Step 3: Add config template and ignore local secret**

Append to `.gitignore`:

```text
firmware/include/secrets.h
```

Create `firmware/include/secrets.example.h`:

```cpp
#pragma once

#define STICKWORDS_WIFI_SSID "your-2.4ghz-wifi-name"
#define STICKWORDS_WIFI_PASSWORD "your-wifi-password"
#define STICKWORDS_SERVER_URL "http://192.168.1.100:8000"
```

- [ ] **Step 4: Run tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit config guardrails**

Run:

```powershell
git add .gitignore firmware/include/secrets.example.h tests/test_firmware_project.py
git commit -m "Add Stage 4 firmware secrets template"
```

## Task 3: Firmware Sync Data Model And Source Markers

**Files:**
- Modify: `firmware/src/main.cpp`
- Modify: `tests/test_firmware_project.py`

- [ ] **Step 1: Write failing firmware sync source test**

Add this test to `tests/test_firmware_project.py`:

```python
    def test_stage4_firmware_has_wifi_http_sync_storage(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("#include <WiFi.h>", source)
        self.assertIn("#include <HTTPClient.h>", source)
        self.assertIn('#include "secrets.h"', source)
        self.assertIn("constexpr size_t kMaxSyncedCards", source)
        self.assertIn("constexpr size_t kMaxPendingReviews", source)
        self.assertIn("struct DeviceCard", source)
        self.assertIn("struct PendingReview", source)
        self.assertIn("DeviceCard syncedCards[kMaxSyncedCards]", source)
        self.assertIn("PendingReview pendingReviews[kMaxPendingReviews]", source)
        self.assertIn("connectWifi()", source)
        self.assertIn("fetchDeviceTasks()", source)
        self.assertIn("uploadPendingReviews()", source)
        self.assertIn("STICKWORDS_SERVER_URL", source)
        self.assertIn("WiFi...", source)
        self.assertIn("Sync failed", source)
```

- [ ] **Step 2: Run focused firmware tests and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: FAIL because firmware has no Wi-Fi or sync storage.

- [ ] **Step 3: Add firmware includes, limits, structs, and active-card helpers**

Modify `firmware/src/main.cpp`:

```cpp
#include <HTTPClient.h>
#include <WiFi.h>
#include "secrets.h"
```

Add limits and structs:

```cpp
constexpr size_t kMaxSyncedCards = 20;
constexpr size_t kMaxPendingReviews = 20;
constexpr size_t kMaxWordIdLength = 24;
constexpr size_t kMaxWordLength = 32;
constexpr size_t kMaxMeaningLength = 192;
constexpr size_t kMaxExampleLength = 256;

struct DeviceCard {
  char id[kMaxWordIdLength];
  char word[kMaxWordLength];
  char meaning[kMaxMeaningLength];
  char example[kMaxExampleLength];
};

struct PendingReview {
  char wordId[kMaxWordIdLength];
  Rating rating;
  uint32_t reviewedAtMs;
  bool uploaded;
};
```

Add storage:

```cpp
DeviceCard syncedCards[kMaxSyncedCards] = {};
PendingReview pendingReviews[kMaxPendingReviews] = {};
size_t syncedCardCount = 0;
size_t pendingReviewCount = 0;
```

Add helpers and migrate read sites from `kCards[currentCardIndex]` to `currentCard()`:

```cpp
size_t activeCardCount() {
  return syncedCardCount > 0 ? syncedCardCount : kCardCount;
}

const char* currentWordId() {
  return syncedCardCount > 0 ? syncedCards[currentCardIndex].id : kCards[currentCardIndex].word;
}

Card currentCard() {
  if (syncedCardCount == 0) {
    return kCards[currentCardIndex];
  }
  return {
      syncedCards[currentCardIndex].word,
      syncedCards[currentCardIndex].meaning,
      syncedCards[currentCardIndex].example,
  };
}
```

Replace all `kCardCount` progress checks with `activeCardCount()` where they refer to current review session length.

- [ ] **Step 4: Add stub sync functions that compile**

Add temporary stubs:

```cpp
void drawStatusMessage(const char* line1, const char* line2 = "") {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setCursor(8, 36);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println(line1);
  if (line2[0] != '\0') {
    M5.Lcd.println(line2);
  }
}

bool connectWifi() {
  drawStatusMessage("WiFi...");
  Serial.printf("WiFi connecting ssid=%s\n", STICKWORDS_WIFI_SSID);
  return false;
}

bool fetchDeviceTasks() {
  drawStatusMessage("Sync failed", "using samples");
  Serial.printf("Sync failed url=%s\n", STICKWORDS_SERVER_URL);
  return false;
}

bool uploadPendingReviews() {
  return false;
}
```

Call after screen setup in `setup()`:

```cpp
  if (connectWifi()) {
    fetchDeviceTasks();
  }
```

Call after storing a review in `submitRating()`:

```cpp
  uploadPendingReviews();
```

- [ ] **Step 5: Run tests and PlatformIO build**

Before building firmware, the developer must create local `firmware/include/secrets.h` from the example.
Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
$env:Path = "$env:USERPROFILE\.platformio\penv\Scripts;$env:Path"; pio run
```

Expected: focused tests pass and firmware builds.

- [ ] **Step 6: Commit firmware sync scaffolding**

Run:

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Add Stage 4 firmware sync scaffolding"
```

## Task 4: Firmware HTTP Fetch And Upload

**Files:**
- Modify: `firmware/src/main.cpp`
- Modify: `tests/test_firmware_project.py`

- [ ] **Step 1: Strengthen firmware source test for real HTTP operations**

Extend `test_stage4_firmware_has_wifi_http_sync_storage` with:

```python
        self.assertIn("HTTPClient http", source)
        self.assertIn('/api/device/tasks?limit=', source)
        self.assertIn('/api/device/reviews', source)
        self.assertIn("http.GET()", source)
        self.assertIn("http.POST(", source)
        self.assertIn("parseDeviceTasksJson(", source)
        self.assertIn("buildPendingReviewsJson(", source)
        self.assertIn("markPendingReviewsUploaded()", source)
```

- [ ] **Step 2: Run focused test and verify failure**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: FAIL because HTTP functions are still stubs.

- [ ] **Step 3: Implement Wi-Fi connection**

Replace `connectWifi()` with:

```cpp
bool connectWifi() {
  drawStatusMessage("WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(STICKWORDS_WIFI_SSID, STICKWORDS_WIFI_PASSWORD);

  const uint32_t startedAt = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < 12000) {
    delay(250);
    M5.update();
  }

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi failed");
    drawStatusMessage("WiFi failed", "using samples");
    return false;
  }

  Serial.print("WiFi connected ip=");
  Serial.println(WiFi.localIP());
  return true;
}
```

- [ ] **Step 4: Implement bounded JSON extraction for known response shape**

Add helper functions:

```cpp
void copyBounded(char* dest, size_t destSize, const String& value) {
  if (destSize == 0) {
    return;
  }
  value.substring(0, destSize - 1).toCharArray(dest, destSize);
}

String jsonStringValue(const String& object, const char* key) {
  const String marker = String("\"") + key + "\":";
  int markerIndex = object.indexOf(marker);
  if (markerIndex < 0) {
    return "";
  }
  int start = object.indexOf('"', markerIndex + marker.length());
  if (start < 0) {
    return "";
  }
  int end = object.indexOf('"', start + 1);
  if (end < 0) {
    return "";
  }
  return object.substring(start + 1, end);
}

bool parseDeviceTasksJson(const String& body) {
  syncedCardCount = 0;
  int arrayStart = body.indexOf("\"tasks\"");
  arrayStart = body.indexOf('[', arrayStart);
  int arrayEnd = body.indexOf(']', arrayStart);
  if (arrayStart < 0 || arrayEnd < 0) {
    return false;
  }

  int cursor = arrayStart;
  while (syncedCardCount < kMaxSyncedCards) {
    int objectStart = body.indexOf('{', cursor);
    if (objectStart < 0 || objectStart > arrayEnd) {
      break;
    }
    int objectEnd = body.indexOf('}', objectStart);
    if (objectEnd < 0 || objectEnd > arrayEnd) {
      break;
    }
    String object = body.substring(objectStart, objectEnd + 1);
    DeviceCard& card = syncedCards[syncedCardCount];
    copyBounded(card.id, sizeof(card.id), jsonStringValue(object, "id"));
    copyBounded(card.word, sizeof(card.word), jsonStringValue(object, "word"));
    copyBounded(card.meaning, sizeof(card.meaning), jsonStringValue(object, "meaning"));
    copyBounded(card.example, sizeof(card.example), jsonStringValue(object, "example"));
    if (card.id[0] != '\0' && card.word[0] != '\0') {
      syncedCardCount += 1;
    }
    cursor = objectEnd + 1;
  }

  return true;
}
```

- [ ] **Step 5: Implement task fetch**

Replace `fetchDeviceTasks()`:

```cpp
bool fetchDeviceTasks() {
  drawStatusMessage("Sync...");
  HTTPClient http;
  const String url = String(STICKWORDS_SERVER_URL) + "/api/device/tasks?limit=20";
  Serial.println("GET " + url);
  http.begin(url);
  const int status = http.GET();
  if (status != 200) {
    Serial.printf("Sync failed status=%d\n", status);
    http.end();
    drawStatusMessage("Sync failed", "using samples");
    return false;
  }

  const String body = http.getString();
  http.end();
  if (!parseDeviceTasksJson(body)) {
    Serial.println("Sync parse failed");
    drawStatusMessage("Sync failed", "using samples");
    return false;
  }

  if (syncedCardCount == 0) {
    Serial.println("No due cards");
    drawStatusMessage("No due cards");
    return true;
  }

  Serial.printf("Synced cards=%u\n", static_cast<unsigned>(syncedCardCount));
  resetReviewSet();
  return true;
}
```

- [ ] **Step 6: Implement pending review queue and upload**

Add helper functions:

```cpp
void queuePendingReview(const char* wordId, Rating rating) {
  if (pendingReviewCount >= kMaxPendingReviews) {
    Serial.println("Pending review queue full");
    return;
  }
  PendingReview& pending = pendingReviews[pendingReviewCount++];
  copyBounded(pending.wordId, sizeof(pending.wordId), String(wordId));
  pending.rating = rating;
  pending.reviewedAtMs = millis();
  pending.uploaded = false;
}

String buildPendingReviewsJson() {
  String body = "{\"device_id\":\"m5stick-c-plus\",\"reviews\":[";
  bool first = true;
  for (size_t i = 0; i < pendingReviewCount; ++i) {
    PendingReview& pending = pendingReviews[i];
    if (pending.uploaded) {
      continue;
    }
    if (!first) {
      body += ",";
    }
    first = false;
    const String eventId = String("m5stick-c-plus-") + String(pending.reviewedAtMs) + "-" + pending.wordId;
    body += "{\"word_id\":\"";
    body += pending.wordId;
    body += "\",\"rating\":\"";
    body += ratingName(pending.rating);
    body += "\",\"reviewed_at\":\"2026-05-24T00:00:00Z\",\"event_id\":\"";
    body += eventId;
    body += "\"}";
  }
  body += "]}";
  return body;
}

void markPendingReviewsUploaded() {
  pendingReviewCount = 0;
}
```

In `submitRating()`, after assigning `result.rating`, call:

```cpp
  queuePendingReview(currentWordId(), selectedRating);
```

Replace `uploadPendingReviews()`:

```cpp
bool uploadPendingReviews() {
  if (pendingReviewCount == 0 || WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  const String url = String(STICKWORDS_SERVER_URL) + "/api/device/reviews";
  const String body = buildPendingReviewsJson();
  Serial.println("POST " + url);
  http.begin(url);
  http.addHeader("Content-Type", "application/json");
  const int status = http.POST(body);
  const String response = http.getString();
  http.end();

  if (status != 200) {
    Serial.printf("Review upload failed status=%d\n", status);
    return false;
  }

  Serial.println("Review upload response=" + response);
  markPendingReviewsUploaded();
  return true;
}
```

- [ ] **Step 7: Run tests and build**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
$env:Path = "$env:USERPROFILE\.platformio\penv\Scripts;$env:Path"; pio run
```

Expected: all tests pass and firmware builds.

- [ ] **Step 8: Commit firmware HTTP sync**

Run:

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Add Stage 4 firmware HTTP sync"
```

## Task 5: Documentation And Manual Validation Checklist

**Files:**
- Modify: `docs/dev_log.md`
- Modify: `docs/handoff.md`

- [ ] **Step 1: Update docs**

Append a Stage 4 entry to `docs/dev_log.md` with:

- PC API endpoints implemented.
- Firmware private config and Wi-Fi sync implemented.
- Current test count.
- Firmware build status.
- Manual validation steps still needed.

Update `docs/handoff.md` with:

- `firmware/include/secrets.h` setup instructions.
- `python app.py --host 0.0.0.0 --port 8000 --data-dir data`.
- `/api/device/tasks` and `/api/device/reviews` summary.
- Current expected test count.
- Known limits: no automatic discovery, no HTTPS/auth, no offline persistent queue.

- [ ] **Step 2: Run final verification**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
$env:Path = "$env:USERPROFILE\.platformio\penv\Scripts;$env:Path"; pio run
git status --short
```

Expected: all tests pass, firmware build succeeds, and only doc files are modified before the docs commit.

- [ ] **Step 3: Commit docs**

Run:

```powershell
git add docs/dev_log.md docs/handoff.md
git commit -m "Document Stage 4 sync workflow"
```

## Manual Real-Device Validation

After implementation, validate with the user:

1. Start PC server:

```powershell
cd C:\Users\ASUS\Documents\M5Stick
python app.py --host 0.0.0.0 --port 8000 --data-dir data
```

2. Confirm PC LAN IP:

```powershell
ipconfig
```

3. Create local `firmware/include/secrets.h`:

```cpp
#pragma once

#define STICKWORDS_WIFI_SSID "actual-2.4ghz-ssid"
#define STICKWORDS_WIFI_PASSWORD "actual-password"
#define STICKWORDS_SERVER_URL "http://PC_LAN_IP:8000"
```

4. Add at least one due word through `http://localhost:8000/admin`.

5. Build and upload:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run --target upload --upload-port COM5
pio device monitor --port COM5
```

6. Expected serial evidence:

```text
WiFi connected ip=...
GET http://.../api/device/tasks?limit=20
Synced cards=...
POST http://.../api/device/reviews
Review upload response=...
```

7. Expected behavior:

- M5Stick shows a real word from `data/vocab.csv`.
- A Button A long-press rating or double-shake `good` uploads to PC.
- `data/vocab.csv` changes review state after upload.

## Self-Review Notes

- Spec coverage: PC tasks endpoint, review endpoint, private secrets config, Wi-Fi/HTTP firmware sync, failure fallback, tests, and manual validation all have tasks.
- Placeholder scan: no placeholder instructions are left; every task has concrete files, commands, and expected outcomes.
- Type consistency: PC uses `event_id` in JSON and maps it to `ReviewEvent.review_event_id`; firmware uses `PendingReview.wordId` and the existing `Rating` enum.
