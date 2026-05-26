# StickWords Offline Due Scheduling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let M5Stick review a cached 7-day due package plus a small new-card reserve while offline, using RTC time and uploadable review events.

**Architecture:** Extend the existing PC device payload with scheduling metadata and an `offline.cards` package, then teach firmware to cache and select due cards from that package. In a second milestone, change firmware pending reviews from per-word replacement to append-only events and apply the same simplified scheduler locally after offline ratings.

**Tech Stack:** Python standard-library WSGI backend, `unittest`, Arduino/C++ firmware for M5StickCPlus, ESP32 `Preferences`, PlatformIO.

---

## Files And Responsibilities

- `src/stickwords/scheduler.py`: add a reusable offline-package selector beside the current today-task selector.
- `src/stickwords/service.py`: serialize immediate tasks and offline cards with the same scheduling fields.
- `src/stickwords/reviews.py`: process multiple review events in chronological order before updating `vocab.csv`.
- `tests/test_scheduler.py`: cover offline due/new package selection.
- `tests/test_web.py`: cover the extended `/api/device/tasks` payload and multi-event upload behavior.
- `tests/test_reviews.py`: cover timestamp-ordered event replay for the same word.
- `firmware/src/main.cpp`: extend card storage, parse/cache offline fields, select offline due cards, append pending events, and perform local scheduling.
- `tests/test_firmware_project.py`: source-level firmware tests for the staged firmware behavior.
- `docs/dev_log.md` and `docs/handoff.md`: record implementation, test commands, and manual M5Stick validation steps.

---

## Task 1: PC Offline Package Selection

**Files:**
- Modify: `src/stickwords/scheduler.py`
- Modify: `tests/test_scheduler.py`

- [ ] **Step 1: Write the failing scheduler test**

Append this test to `tests/test_scheduler.py`:

```python
    def test_get_offline_package_returns_7_day_due_then_new_reserve(self):
        now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)

        due_soon = Word.new_word("w-1", "alpha", "first", "Alpha example.", now)
        due_soon.status = STATUS_REVIEW
        due_soon.due_at = now + timedelta(days=2)

        due_now = Word.new_word("w-2", "beta", "second", "Beta example.", now)
        due_now.status = STATUS_REVIEW
        due_now.due_at = now - timedelta(minutes=5)

        future = Word.new_word("w-3", "gamma", "third", "Gamma example.", now)
        future.status = STATUS_REVIEW
        future.due_at = now + timedelta(days=8)

        new_later = Word.new_word("w-4", "delta", "fourth", "Delta example.", now + timedelta(minutes=1))
        new_earlier = Word.new_word("w-5", "epsilon", "fifth", "Epsilon example.", now)

        suspended = Word.new_word("w-6", "zeta", "sixth", "Zeta example.", now)
        suspended.status = STATUS_SUSPENDED
        suspended.due_at = now

        package = get_offline_package(
            [new_later, suspended, due_soon, future, new_earlier, due_now],
            now,
            horizon_days=7,
            max_due=20,
            max_new=20,
        )

        self.assertEqual([word.id for word in package], ["w-2", "w-1", "w-5", "w-4"])
```

Also update the import at the top of `tests/test_scheduler.py`:

```python
from stickwords.scheduler import apply_review, get_offline_package, get_today_tasks
```

- [ ] **Step 2: Run the focused test and confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_scheduler.SchedulerTests.test_get_offline_package_returns_7_day_due_then_new_reserve -v
```

Expected: FAIL with `cannot import name 'get_offline_package'`.

- [ ] **Step 3: Implement `get_offline_package`**

Add this function to `src/stickwords/scheduler.py` after `get_today_tasks`:

```python
def get_offline_package(
    words: list[Word],
    now: datetime,
    horizon_days: int = 7,
    max_due: int = 20,
    max_new: int = 20,
) -> list[Word]:
    now = normalize_dt(now)
    horizon = now + timedelta(days=horizon_days)
    eligible_words = [word for word in words if word.status != STATUS_SUSPENDED]

    due_words = [
        word
        for word in eligible_words
        if word.status != STATUS_NEW and normalize_dt(word.due_at) <= horizon
    ]
    due_words.sort(key=lambda word: (normalize_dt(word.due_at), word.word.casefold()))

    new_words = [word for word in eligible_words if word.status == STATUS_NEW]
    new_words.sort(key=lambda word: (normalize_dt(word.added_at), word.word.casefold()))

    return due_words[:max_due] + new_words[:max_new]
```

- [ ] **Step 4: Run scheduler tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_scheduler -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```powershell
git add src/stickwords/scheduler.py tests/test_scheduler.py
git commit -m "Add offline package scheduler"
```

---

## Task 2: PC Device Payload With Scheduling Metadata

**Files:**
- Modify: `src/stickwords/service.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write the failing web payload test**

Update `test_get_device_tasks_returns_due_cards_json` in `tests/test_web.py` so the expected task includes scheduling fields and the response includes `offline.cards`:

```python
            self.assertEqual(
                payload["tasks"],
                [
                    {
                        "id": word.id,
                        "word": "abandon",
                        "meaning": "give up",
                        "example": "Do not abandon your plan.",
                        "status": "new",
                        "due_at": "2026-05-24T12:00:00Z",
                        "review_count": 0,
                        "ease": 2.5,
                        "interval_days": 0,
                        "lapses": 0,
                    }
                ],
            )
            self.assertEqual(payload["offline"]["horizon_days"], 7)
            self.assertEqual(payload["offline"]["max_new"], 20)
            self.assertEqual(payload["offline"]["cards"], payload["tasks"])
```

Add this new test to `tests/test_web.py` near the other device-task tests:

```python
    def test_get_device_tasks_includes_future_due_offline_package(self):
        now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            due_now = service.add_word("alpha", "first", "Alpha example.")
            due_future = service.add_word("beta", "second", "Beta example.")
            too_late = service.add_word("gamma", "third", "Gamma example.")
            suspended = service.add_word("delta", "fourth", "Delta example.")

            words = service.load_words()
            by_id = {word.id: word for word in words}
            by_id[due_now.id].status = "review"
            by_id[due_now.id].due_at = now
            by_id[due_future.id].status = "review"
            by_id[due_future.id].due_at = now + timedelta(days=7)
            by_id[too_late.id].status = "review"
            by_id[too_late.id].due_at = now + timedelta(days=8)
            by_id[suspended.id].status = "suspended"
            service.save_words(words)

            app = create_app(service)
            status, _, body = call_app(app, "GET", "/api/device/tasks", query_string="limit=1")

            payload = json.loads(body)
            self.assertEqual(status, "200 OK")
            self.assertEqual([card["id"] for card in payload["tasks"]], [due_now.id])
            self.assertEqual(
                [card["id"] for card in payload["offline"]["cards"]],
                [due_now.id, due_future.id],
            )
```

Also ensure `timedelta` is imported:

```python
from datetime import datetime, timedelta, timezone
```

- [ ] **Step 2: Run the focused web tests and confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_web.WebTests.test_get_device_tasks_returns_due_cards_json tests.test_web.WebTests.test_get_device_tasks_includes_future_due_offline_package -v
```

Expected: FAIL because scheduling fields and `offline` are missing.

- [ ] **Step 3: Implement serialization helpers in service**

Update the scheduler import in `src/stickwords/service.py`:

```python
from .scheduler import (
    get_offline_package as schedule_offline_package,
    get_today_tasks as schedule_today_tasks,
)
```

Add this private helper inside `StickWordsService` before `device_tasks_payload`:

```python
    def _device_card_payload(self, word: Word) -> dict:
        return {
            "id": word.id,
            "word": word.word,
            "meaning": word.meaning,
            "example": word.example,
            "status": word.status,
            "due_at": format_dt(word.due_at),
            "review_count": word.review_count,
            "ease": word.ease,
            "interval_days": word.interval_days,
            "lapses": word.lapses,
        }
```

Replace `device_tasks_payload` with:

```python
    def device_tasks_payload(self, limit: int = 20) -> dict:
        limit = max(0, min(limit, 50))
        now = self.now()
        words = self.load_words()
        tasks = schedule_today_tasks(words, now, max_due=limit, max_new=limit)
        offline_cards = schedule_offline_package(
            words,
            now,
            horizon_days=7,
            max_due=20,
            max_new=20,
        )
        return {
            "generated_at": format_dt(now),
            "tasks": [self._device_card_payload(word) for word in tasks[:limit]],
            "offline": {
                "horizon_days": 7,
                "max_new": 20,
                "cards": [self._device_card_payload(word) for word in offline_cards],
            },
        }
```

- [ ] **Step 4: Run web tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_web -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 2**

```powershell
git add src/stickwords/service.py tests/test_web.py
git commit -m "Add offline cards to device payload"
```

---

## Task 3: PC Review Event Ordering

**Files:**
- Modify: `src/stickwords/reviews.py`
- Modify: `tests/test_reviews.py`
- Modify: `tests/test_web.py`

- [ ] **Step 1: Write failing review-order tests**

Add this test to `tests/test_reviews.py`:

```python
    def test_process_review_events_replays_same_word_by_reviewed_at(self):
        now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
        word = Word.new_word("w-1", "abandon", "give up", "Do not abandon it.", now)
        later = ReviewEvent(
            review_event_id="device-1-2-w-1",
            word_id="w-1",
            rating=RATING_GOOD,
            reviewed_at=datetime(2026, 5, 26, 8, 10, tzinfo=timezone.utc),
        )
        earlier = ReviewEvent(
            review_event_id="device-1-1-w-1",
            word_id="w-1",
            rating=RATING_GOOD,
            reviewed_at=datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc),
        )

        with workspace_temp_dir() as temp_dir:
            event_store = ReviewEventStore(temp_dir / "review_events.csv")
            result = process_review_events(
                words=[word],
                events=[later, earlier],
                event_store=event_store,
            )

            self.assertEqual(result.applied, 2)
            self.assertEqual(result.words[0].review_count, 2)
            self.assertEqual(result.words[0].last_reviewed_at, later.reviewed_at)
```

Add this web-level test to `tests/test_web.py`:

```python
    def test_post_device_reviews_replays_multiple_same_word_events(self):
        now = datetime(2026, 5, 26, 8, 0, tzinfo=timezone.utc)
        with workspace_temp_dir() as temp_dir:
            service = StickWordsService(temp_dir, clock=lambda: now)
            word = service.add_word("abandon", "give up", "Do not abandon it.")
            app = create_app(service)
            body = json.dumps(
                {
                    "device_id": "m5stick-c-plus",
                    "reviews": [
                        {
                            "word_id": word.id,
                            "rating": "good",
                            "reviewed_at": "2026-05-26T08:10:00Z",
                            "event_id": "m5stick-c-plus-test-2",
                        },
                        {
                            "word_id": word.id,
                            "rating": "forgot",
                            "reviewed_at": "2026-05-26T08:00:00Z",
                            "event_id": "m5stick-c-plus-test-1",
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

            reviewed = service.load_words()[0]
            self.assertEqual(status, "200 OK")
            self.assertEqual(json.loads(response_body)["accepted"], 2)
            self.assertEqual(reviewed.review_count, 2)
            self.assertEqual(reviewed.last_reviewed_at, datetime(2026, 5, 26, 8, 10, tzinfo=timezone.utc))
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_reviews.ReviewEventTests.test_process_review_events_replays_same_word_by_reviewed_at tests.test_web.WebTests.test_post_device_reviews_replays_multiple_same_word_events -v
```

Expected: FAIL because events are applied in input order.

- [ ] **Step 3: Sort normalized events before applying**

In `src/stickwords/reviews.py`, replace the start of the loop logic in `process_review_events` with this pattern:

```python
    normalized_events = [
        ReviewEvent(
            review_event_id=raw_event.review_event_id,
            word_id=raw_event.word_id,
            rating=raw_event.rating,
            reviewed_at=normalize_dt(raw_event.reviewed_at),
        )
        for raw_event in events
    ]
    normalized_events.sort(key=lambda event: (event.reviewed_at, event.review_event_id))

    for event in normalized_events:
        if event.review_event_id in processed_ids:
            skipped_duplicate += 1
            continue
```

Remove the old per-loop `event = ReviewEvent(...)` block so each event is normalized once.

- [ ] **Step 4: Run review and web tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_reviews tests.test_web -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

```powershell
git add src/stickwords/reviews.py tests/test_reviews.py tests/test_web.py
git commit -m "Replay device review events by time"
```

---

## Task 4: Firmware Offline Cache Payload Fields

**Files:**
- Modify: `firmware/src/main.cpp`
- Modify: `tests/test_firmware_project.py`

- [ ] **Step 1: Write failing firmware source test for card metadata**

Add this test to `tests/test_firmware_project.py`:

```python
    def test_stage5d_firmware_parses_and_caches_offline_card_metadata(self):
        source = firmware_source()
        parse_body = firmware_function_body(source, "parseDeviceTasksJson")
        save_body = firmware_function_body(source, "saveCachedTasks")
        load_body = firmware_function_body(source, "loadCachedTasks")

        self.assertIn("constexpr size_t kMaxImmediateCards = 20", source)
        self.assertIn("constexpr size_t kMaxOfflineCards = 40", source)
        self.assertIn("char status", source)
        self.assertIn("char dueAt", source)
        self.assertIn("uint16_t reviewCount", source)
        self.assertIn("float ease", source)
        self.assertIn("int16_t intervalDays", source)
        self.assertIn("uint16_t lapses", source)
        self.assertIn("\"offline\"", parse_body)
        self.assertIn("\"cards\"", parse_body)
        self.assertIn("jsonStringValue(object, \"status\")", parse_body)
        self.assertIn("jsonStringValue(object, \"due_at\")", parse_body)
        self.assertIn("jsonIntValue(object, \"review_count\"", parse_body)
        self.assertIn("jsonFloatValue(object, \"ease\"", parse_body)
        self.assertIn("jsonIntValue(object, \"interval_days\"", parse_body)
        self.assertIn("jsonIntValue(object, \"lapses\"", parse_body)
        self.assertIn("offlineCardCount", source)
        self.assertIn("offlineCards", source)
        self.assertIn("storage.putUInt(\"offline_count\"", save_body)
        self.assertIn("storage.putBytes(\"offline\"", save_body)
        self.assertIn("storage.getUInt(\"offline_count\"", load_body)
        self.assertIn("storage.getBytes(\"offline\"", load_body)
```

- [ ] **Step 2: Run focused test and confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage5d_firmware_parses_and_caches_offline_card_metadata -v
```

Expected: FAIL because firmware does not have offline metadata fields yet.

- [ ] **Step 3: Add firmware fields and cache arrays**

In `firmware/src/main.cpp`, replace the existing max card constant:

```cpp
constexpr size_t kMaxSyncedCards = 20;
```

with:

```cpp
constexpr size_t kMaxImmediateCards = 20;
constexpr size_t kMaxOfflineCards = 40;
constexpr size_t kMaxSyncedCards = kMaxImmediateCards;
```

Extend `DeviceCard`:

```cpp
struct DeviceCard {
  char id[kMaxWordIdLength];
  char word[kMaxWordLength];
  char meaning[kMaxMeaningLength];
  char example[kMaxExampleLength];
  char status[12];
  char dueAt[kMaxTimestampLength];
  uint16_t reviewCount;
  float ease;
  int16_t intervalDays;
  uint16_t lapses;
};
```

Add globals near `syncedCards`:

```cpp
DeviceCard offlineCards[kMaxOfflineCards] = {};
size_t offlineCardCount = 0;
```

- [ ] **Step 4: Add numeric JSON helpers**

Add helpers near `jsonStringValue`:

```cpp
int jsonIntValue(const String& object, const char* key, int fallback = 0) {
  const String marker = String("\"") + key + "\":";
  const int markerIndex = object.indexOf(marker);
  if (markerIndex < 0) {
    return fallback;
  }
  int cursor = markerIndex + marker.length();
  while (cursor < object.length() && (object[cursor] == ' ' || object[cursor] == '\t')) {
    cursor += 1;
  }
  int sign = 1;
  if (cursor < object.length() && object[cursor] == '-') {
    sign = -1;
    cursor += 1;
  }
  int value = 0;
  bool hasDigit = false;
  while (cursor < object.length() && object[cursor] >= '0' && object[cursor] <= '9') {
    hasDigit = true;
    value = value * 10 + (object[cursor] - '0');
    cursor += 1;
  }
  return hasDigit ? value * sign : fallback;
}

float jsonFloatValue(const String& object, const char* key, float fallback = 0.0F) {
  const String marker = String("\"") + key + "\":";
  const int markerIndex = object.indexOf(marker);
  if (markerIndex < 0) {
    return fallback;
  }
  int cursor = markerIndex + marker.length();
  while (cursor < object.length() && (object[cursor] == ' ' || object[cursor] == '\t')) {
    cursor += 1;
  }
  return object.substring(cursor).toFloat();
}
```

- [ ] **Step 5: Parse both immediate tasks and offline cards**

Refactor the parsing loop into a helper:

```cpp
size_t parseCardArrayJson(const String& body, const char* arrayKey, DeviceCard* cards, size_t maxCards) {
  size_t count = 0;
  int arrayStart = body.indexOf(String("\"") + arrayKey + "\"");
  arrayStart = body.indexOf('[', arrayStart);
  if (arrayStart < 0) {
    return 0;
  }
  const int arrayEnd = findJsonArrayEnd(body, arrayStart);
  if (arrayEnd < 0) {
    return 0;
  }

  int cursor = arrayStart;
  while (count < maxCards) {
    const int objectStart = body.indexOf('{', cursor);
    if (objectStart < 0 || objectStart > arrayEnd) {
      break;
    }
    const int objectEnd = findJsonObjectEnd(body, objectStart, arrayEnd);
    if (objectEnd < 0 || objectEnd > arrayEnd) {
      break;
    }

    const String object = body.substring(objectStart, objectEnd + 1);
    DeviceCard& card = cards[count];
    copyBounded(card.id, sizeof(card.id), jsonStringValue(object, "id"));
    copyBounded(card.word, sizeof(card.word), jsonStringValue(object, "word"));
    copyBounded(card.meaning, sizeof(card.meaning), jsonStringValue(object, "meaning"));
    copyBounded(card.example, sizeof(card.example), jsonStringValue(object, "example"));
    copyBounded(card.status, sizeof(card.status), jsonStringValue(object, "status"));
    copyBounded(card.dueAt, sizeof(card.dueAt), jsonStringValue(object, "due_at"));
    card.reviewCount = static_cast<uint16_t>(jsonIntValue(object, "review_count", 0));
    card.ease = jsonFloatValue(object, "ease", 2.5F);
    card.intervalDays = static_cast<int16_t>(jsonIntValue(object, "interval_days", 0));
    card.lapses = static_cast<uint16_t>(jsonIntValue(object, "lapses", 0));
    if (card.id[0] != '\0' && card.word[0] != '\0') {
      count += 1;
    }
    cursor = objectEnd + 1;
  }
  return count;
}
```

Replace `parseDeviceTasksJson` body with:

```cpp
bool parseDeviceTasksJson(const String& body) {
  syncedCardCount = 0;
  offlineCardCount = 0;
  copyBounded(serverGeneratedAt, sizeof(serverGeneratedAt), jsonStringValue(body, "generated_at"));
  syncedCardCount = parseCardArrayJson(body, "tasks", syncedCards, kMaxImmediateCards);
  const int offlineStart = body.indexOf("\"offline\"");
  if (offlineStart >= 0) {
    const String offlineBody = body.substring(offlineStart);
    offlineCardCount = parseCardArrayJson(offlineBody, "cards", offlineCards, kMaxOfflineCards);
  }
  if (offlineCardCount == 0 && syncedCardCount > 0) {
    for (size_t i = 0; i < syncedCardCount && i < kMaxOfflineCards; ++i) {
      offlineCards[i] = syncedCards[i];
      offlineCardCount += 1;
    }
  }
  return body.indexOf("\"tasks\"") >= 0;
}
```

- [ ] **Step 6: Persist offline cache**

In `saveCachedTasks`, add:

```cpp
  storage.putUInt("offline_count", static_cast<uint32_t>(offlineCardCount));
  storage.putBytes("offline", offlineCards, sizeof(DeviceCard) * offlineCardCount);
```

In `loadCachedTasks`, read both immediate and offline arrays. Use this exact pattern after reading `cards`:

```cpp
  uint32_t storedOfflineCount = storage.getUInt("offline_count", 0);
  if (storedOfflineCount > kMaxOfflineCards) {
    storedOfflineCount = kMaxOfflineCards;
  }
  const size_t expectedOfflineBytes = sizeof(DeviceCard) * storedOfflineCount;
  const size_t readOfflineBytes = storedOfflineCount == 0
                                      ? 0
                                      : storage.getBytes("offline", offlineCards, expectedOfflineBytes);
```

After the existing read validation, add:

```cpp
  if (storedOfflineCount > 0 && readOfflineBytes != expectedOfflineBytes) {
    return false;
  }
  offlineCardCount = storedOfflineCount;
  if (offlineCardCount == 0) {
    for (size_t i = 0; i < syncedCardCount && i < kMaxOfflineCards; ++i) {
      offlineCards[i] = syncedCards[i];
      offlineCardCount += 1;
    }
  }
```

In `clearCachedTasks`, remove:

```cpp
  storage.remove("offline_count");
  storage.remove("offline");
```

- [ ] **Step 7: Run firmware source tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 4**

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Cache offline card metadata on device"
```

---

## Task 5: Firmware Offline Due Selection

**Files:**
- Modify: `firmware/src/main.cpp`
- Modify: `tests/test_firmware_project.py`

- [ ] **Step 1: Write failing firmware source test for offline selection**

Add this test to `tests/test_firmware_project.py`:

```python
    def test_stage5d_firmware_selects_cached_due_cards_using_rtc(self):
        source = firmware_source()
        select_body = firmware_function_body(source, "selectOfflineDueCards")
        setup_body = firmware_function_body(source, "setup")

        self.assertIn("bool selectOfflineDueCards()", source)
        self.assertIn("readRtcTimestamp()", select_body)
        self.assertIn("isValidRtcTimestamp(now)", select_body)
        self.assertIn("isCardDue(card, now)", select_body)
        self.assertIn('std::strcmp(card.status, "new")', select_body)
        self.assertIn("offlineCards", select_body)
        self.assertIn("syncedCards[syncedCardCount++] = card", select_body)
        self.assertIn("selectOfflineDueCards()", setup_body)
        self.assertIn('setStatusPage("RTC invalid", "sync needed")', select_body)
```

- [ ] **Step 2: Run focused test and confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage5d_firmware_selects_cached_due_cards_using_rtc -v
```

Expected: FAIL because selection helpers do not exist.

- [ ] **Step 3: Add timestamp comparison helpers**

Add these helpers after `formatRtcTimestamp`:

```cpp
int compareRtcTimestamp(const RtcTimestamp& left, const RtcTimestamp& right) {
  if (left.year != right.year) return left.year < right.year ? -1 : 1;
  if (left.month != right.month) return left.month < right.month ? -1 : 1;
  if (left.date != right.date) return left.date < right.date ? -1 : 1;
  if (left.hour != right.hour) return left.hour < right.hour ? -1 : 1;
  if (left.minute != right.minute) return left.minute < right.minute ? -1 : 1;
  if (left.second != right.second) return left.second < right.second ? -1 : 1;
  return 0;
}

bool isCardDue(const DeviceCard& card, const RtcTimestamp& now) {
  if (card.dueAt[0] == '\0') {
    return false;
  }
  RtcTimestamp due = {};
  if (!parseUtcTimestamp(String(card.dueAt), &due)) {
    return false;
  }
  return compareRtcTimestamp(due, now) <= 0;
}
```

- [ ] **Step 4: Add offline selection helper**

Add:

```cpp
bool selectOfflineDueCards() {
  syncedCardCount = 0;
  const RtcTimestamp now = readRtcTimestamp();
  if (!isValidRtcTimestamp(now)) {
    setStatusPage("RTC invalid", "sync needed");
    drawStatusMessage("RTC invalid", "sync needed");
    return false;
  }

  for (size_t i = 0; i < offlineCardCount && syncedCardCount < kMaxImmediateCards; ++i) {
    const DeviceCard& card = offlineCards[i];
    if (std::strcmp(card.status, "new") != 0 && isCardDue(card, now)) {
      syncedCards[syncedCardCount++] = card;
    }
  }

  for (size_t i = 0; i < offlineCardCount && syncedCardCount < kMaxImmediateCards; ++i) {
    const DeviceCard& card = offlineCards[i];
    if (std::strcmp(card.status, "new") == 0) {
      syncedCards[syncedCardCount++] = card;
    }
  }

  if (syncedCardCount == 0) {
    setStatusPage("No due cards");
    drawStatusMessage("No due cards");
    return false;
  }

  resetReviewSet();
  Serial.printf("Selected offline cards=%u\n", static_cast<unsigned>(syncedCardCount));
  return true;
}
```

- [ ] **Step 5: Use selection on sync failure**

In `setup`, replace:

```cpp
  } else if (loadCachedTasks()) {
    Serial.println("Using cached tasks after WiFi failure");
  }
```

with:

```cpp
  } else if (loadCachedTasks()) {
    Serial.println("Using cached tasks after WiFi failure");
    selectOfflineDueCards();
  }
```

In `fetchDeviceTasks`, when `loadCachedTasks()` succeeds after HTTP or parse failure, call `selectOfflineDueCards()` before returning true:

```cpp
    if (loadCachedTasks()) {
      Serial.println("Using cached tasks after sync failure");
      selectOfflineDueCards();
      return true;
    }
```

and:

```cpp
    if (loadCachedTasks()) {
      Serial.println("Using cached tasks after parse failure");
      selectOfflineDueCards();
      return true;
    }
```

- [ ] **Step 6: Run firmware tests and build**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
cd firmware
C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run
cd ..
```

Expected: tests PASS and PlatformIO SUCCESS.

- [ ] **Step 7: Commit Task 5**

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Select offline due cards from RTC"
```

---

## Task 6: Firmware Append-Only Pending Events

**Files:**
- Modify: `firmware/src/main.cpp`
- Modify: `tests/test_firmware_project.py`

- [x] **Step 1: Update Python firmware queue model tests**

In `tests/test_firmware_project.py`, change `PendingReviewQueue.queue` to append every review instead of replacing same-word reviews:

```python
    def queue(self, word_id, rating, reviewed_at="2026-05-26T08:00:00Z"):
        self.sequence += 1
        self.items.append({
            "wordId": word_id,
            "rating": rating,
            "reviewedAt": reviewed_at,
            "sequence": self.sequence,
            "uploaded": False,
        })
```

Update `build_json` in the same class:

```python
    def build_json(self, boot_nonce, generated_at=""):
        reviews = []
        for item in self.items:
            if item["uploaded"]:
                continue
            event_id = (
                f"m5stick-c-plus-{boot_nonce:x}-{item['sequence']}-"
                f"{item['wordId']}"
            )
            reviews.append({
                "word_id": item["wordId"],
                "rating": item["rating"],
                "reviewed_at": item["reviewedAt"],
                "event_id": event_id,
            })
        return json.dumps({"device_id": "m5stick-c-plus", "reviews": reviews})
```

Replace the old same-pending-word replacement test with:

```python
    def test_stage5d_pending_reviews_append_multiple_events_per_word(self):
        source = firmware_source()
        queue_body = firmware_function_body(source, "queuePendingReview")
        reviews_body = firmware_function_body(source, "buildPendingReviewsJson")

        self.assertNotIn("replace pending review word=", queue_body)
        self.assertIn("PendingReview& pending = pendingReviews[pendingReviewCount++]", queue_body)
        self.assertIn("currentReviewTimestamp()", queue_body)
        self.assertIn("pending.reviewedAt", queue_body)
        self.assertIn("pending.reviewedAt", reviews_body)

        queue = PendingReviewQueue()
        queue.queue("w-1", "forgot", "2026-05-26T08:00:00Z")
        queue.queue("w-1", "good", "2026-05-26T08:10:00Z")
        body = json.loads(queue.build_json(0x1234))
        self.assertEqual(len(body["reviews"]), 2)
        self.assertEqual([review["rating"] for review in body["reviews"]], ["forgot", "good"])
        self.assertEqual(
            [review["reviewed_at"] for review in body["reviews"]],
            ["2026-05-26T08:00:00Z", "2026-05-26T08:10:00Z"],
        )
```

- [x] **Step 2: Run focused test and confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage5d_pending_reviews_append_multiple_events_per_word -v
```

Expected: FAIL because `queuePendingReview` still replaces pending reviews per word and stores only milliseconds.

- [x] **Step 3: Change pending review struct**

In `firmware/src/main.cpp`, replace:

```cpp
  uint32_t reviewedAtMs;
```

with:

```cpp
  char reviewedAt[kMaxTimestampLength];
```

- [x] **Step 4: Make `queuePendingReview` append events**

Replace `queuePendingReview` with:

```cpp
void queuePendingReview(const char* wordId, Rating rating) {
  if (pendingReviewCount >= kMaxPendingReviews) {
    Serial.println("Pending review queue full");
    setStatusPage("Pending full", "sync needed");
    drawStatusMessage("Pending full", "sync needed");
    return;
  }

  PendingReview& pending = pendingReviews[pendingReviewCount++];
  copyBounded(pending.wordId, sizeof(pending.wordId), String(wordId));
  pending.rating = rating;
  copyBounded(pending.reviewedAt, sizeof(pending.reviewedAt), currentReviewTimestamp());
  pending.sequence = ++reviewSequence;
  pending.uploaded = false;
  savePendingReviews();
}
```

- [x] **Step 5: Use each event timestamp in upload JSON**

In `buildPendingReviewsJson`, replace:

```cpp
    body += currentReviewTimestamp();
```

with:

```cpp
    body += pending.reviewedAt;
```

- [x] **Step 6: Run firmware tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: PASS after updating any older tests that explicitly expected same-word replacement.

- [x] **Step 7: Commit Task 6**

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Append pending review events on device"
```

---

## Task 7: Firmware Local Offline Scheduling

**Files:**
- Modify: `firmware/src/main.cpp`
- Modify: `tests/test_firmware_project.py`

- [x] **Step 1: Write failing source test for local scheduling**

Add this test to `tests/test_firmware_project.py`:

```python
    def test_stage5d_firmware_updates_cached_schedule_after_rating(self):
        source = firmware_source()
        apply_body = firmware_function_body(source, "applyLocalReview")
        submit_body = firmware_function_body(source, "submitRating")

        self.assertIn("void applyLocalReview(DeviceCard& card, Rating rating", source)
        self.assertIn("card.reviewCount += 1", apply_body)
        self.assertIn('copyBounded(card.status, sizeof(card.status), "learning")', apply_body)
        self.assertIn('copyBounded(card.status, sizeof(card.status), "review")', apply_body)
        self.assertIn("card.lapses += 1", apply_body)
        self.assertIn("card.ease = maxFloat(1.3F, card.ease - 0.2F)", apply_body)
        self.assertIn("card.ease = minFloat(3.0F, card.ease + 0.05F)", apply_body)
        self.assertIn("addMinutesToTimestamp", apply_body)
        self.assertIn("addDaysToTimestamp", apply_body)
        self.assertIn("applyLocalReview(syncedCards[currentCardIndex], selectedRating", submit_body)
        self.assertIn("saveCachedTasks()", submit_body)
```

- [x] **Step 2: Run focused test and confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage5d_firmware_updates_cached_schedule_after_rating -v
```

Expected: FAIL because local scheduling helpers do not exist.

- [x] **Step 3: Add small math helpers**

Add after `ratingName`:

```cpp
float minFloat(float left, float right) {
  return left < right ? left : right;
}

float maxFloat(float left, float right) {
  return left > right ? left : right;
}
```

- [x] **Step 4: Add timestamp add helpers**

Add simple UTC timestamp add helpers near other RTC helpers:

```cpp
void addMinutesToTimestamp(RtcTimestamp* timestamp, uint16_t minutes) {
  timestamp->minute += minutes;
  while (timestamp->minute >= 60) {
    timestamp->minute -= 60;
    timestamp->hour += 1;
  }
  while (timestamp->hour >= 24) {
    timestamp->hour -= 24;
    timestamp->date += 1;
    const uint8_t monthDays = daysInMonth(timestamp->year, timestamp->month);
    if (timestamp->date <= monthDays) {
      continue;
    }
    timestamp->date = 1;
    timestamp->month += 1;
    if (timestamp->month <= 12) {
      continue;
    }
    timestamp->month = 1;
    timestamp->year += 1;
  }
}

void addDaysToTimestamp(RtcTimestamp* timestamp, uint16_t days) {
  for (uint16_t i = 0; i < days; ++i) {
    addMinutesToTimestamp(timestamp, 24 * 60);
  }
}
```

- [x] **Step 5: Apply scheduler locally**

Add:

```cpp
void applyLocalReview(DeviceCard& card, Rating rating, const RtcTimestamp& reviewedAt) {
  card.reviewCount += 1;
  RtcTimestamp due = reviewedAt;

  if (rating == Rating::Forgot) {
    copyBounded(card.status, sizeof(card.status), "learning");
    card.lapses += 1;
    card.ease = maxFloat(1.3F, card.ease - 0.2F);
    card.intervalDays = 0;
    addMinutesToTimestamp(&due, 10);
  } else if (rating == Rating::Hard) {
    copyBounded(card.status, sizeof(card.status), "review");
    card.ease = maxFloat(1.3F, card.ease - 0.05F);
    card.intervalDays = static_cast<int16_t>(std::max(1.0F, roundf(card.intervalDays * 1.2F)));
    addDaysToTimestamp(&due, static_cast<uint16_t>(card.intervalDays));
  } else {
    copyBounded(card.status, sizeof(card.status), "review");
    card.ease = minFloat(3.0F, card.ease + 0.05F);
    if (card.intervalDays == 0) {
      card.intervalDays = 1;
    } else {
      card.intervalDays = static_cast<int16_t>(std::max(1.0F, roundf(card.intervalDays * card.ease)));
    }
    addDaysToTimestamp(&due, static_cast<uint16_t>(card.intervalDays));
  }

  copyBounded(card.dueAt, sizeof(card.dueAt), formatRtcTimestamp(due) + "Z");
}
```

- [x] **Step 6: Call scheduler after rating**

In `submitRating`, after `queuePendingReview(currentWordId(), selectedRating);`, add:

```cpp
  const RtcTimestamp reviewedAt = readRtcTimestamp();
  if (isValidRtcTimestamp(reviewedAt)) {
    applyLocalReview(syncedCards[currentCardIndex], selectedRating, reviewedAt);
    for (size_t i = 0; i < offlineCardCount; ++i) {
      if (std::strcmp(offlineCards[i].id, syncedCards[currentCardIndex].id) == 0) {
        offlineCards[i] = syncedCards[currentCardIndex];
        break;
      }
    }
    saveCachedTasks();
  }
```

- [x] **Step 7: Run firmware tests and PlatformIO build**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
cd firmware
C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run
cd ..
```

Expected: PASS and SUCCESS.

- [x] **Step 8: Commit Task 7**

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Update offline schedule after device reviews"
```

---

## Task 8: Documentation, Full Verification, And Manual Test Script

**Files:**
- Modify: `docs/dev_log.md`
- Modify: `docs/handoff.md`

- [ ] **Step 1: Update development log**

Append this entry to `docs/dev_log.md`:

```markdown
## 2026-05-26 Stage 5D: RTC-backed offline due scheduling

完成内容：
- PC `/api/device/tasks` 返回即时任务和 7 天离线复习包。
- 离线包包含最多 20 个 due 复习词和最多 20 个 new 词。
- M5Stick 缓存离线包，并在 Wi-Fi/backend 不可用时用 RTC 筛选已到期卡片。
- M5Stick pending reviews 改为 append-only 事件队列，允许同一词离线期间多次复习并上传多条事件。
- M5Stick 离线评分后本地更新缓存卡的排期状态，支持同一词再次到期。

验证结果：
- Python 全量测试通过：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- PlatformIO 固件编译通过：
  `C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run`

真机验证建议：
- 在线同步一次，确认串口显示 cached/offline cards。
- 关闭 PC 后端或断开 Wi-Fi，重启 M5Stick，确认可以从缓存筛选 due cards。
- 使用 `forgot` 离线复习一张卡，等待 10 分钟后确认它再次出现。
- 恢复 Wi-Fi/backend，确认多条 pending reviews 上传成功。
```

- [ ] **Step 2: Update handoff**

In `docs/handoff.md`, add completed milestone:

```markdown
- Stage 5D RTC-backed offline due scheduling.
```

Add firmware capability bullets:

```markdown
  - caches a 7-day offline due package plus a small new-card reserve
  - selects offline due cards from the cached package using BM8563 RTC time
  - updates cached scheduling metadata after offline ratings
  - uploads append-only review events after Wi-Fi returns
```

Replace the known-limit line that says cached fallback does not compute future due cards offline with:

```markdown
- Firmware offline scheduling is limited to the most recently synced offline package; it does not cache the full PC vocabulary.
```

- [ ] **Step 3: Run full verification**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
cd firmware
C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run
cd ..
git diff --check
git status --short
```

Expected:

- All Python tests PASS.
- PlatformIO reports SUCCESS.
- `git diff --check` has no errors.
- `git status --short` shows only the intended docs if not yet committed.

- [ ] **Step 4: Commit docs**

```powershell
git add docs/dev_log.md docs/handoff.md
git commit -m "Document offline due scheduling"
```

---

## Self-Review

Spec coverage:

- PC offline payload: Task 1 and Task 2.
- 7-day due plus 20 new selection: Task 1 and Task 2.
- Firmware cache metadata and larger cache: Task 4.
- Offline RTC due selection: Task 5.
- Multiple events for the same word: Task 3 and Task 6.
- Local offline scheduling after rating: Task 7.
- Conflict and recovery basics: Task 3, Task 6, Task 8.
- Docs and manual validation: Task 8.

Placeholder scan:

- The plan uses concrete code snippets, exact file paths, and exact verification commands.

Type consistency:

- PC JSON uses snake_case fields: `due_at`, `review_count`, `interval_days`.
- Firmware struct uses C++ field names: `dueAt`, `reviewCount`, `intervalDays`.
- Pending upload JSON remains the existing API shape: `word_id`, `rating`, `reviewed_at`, `event_id`.
