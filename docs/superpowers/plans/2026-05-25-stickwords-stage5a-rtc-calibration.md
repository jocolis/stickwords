# StickWords Stage 5A RTC Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set and read the M5Stick C Plus BM8563 RTC from the backend `generated_at` timestamp and make the behavior visible in serial logs.

**Architecture:** Keep the existing single-file firmware structure for this milestone. Add small bounded timestamp parsing helpers, RTC validity checks, RTC logging, and a sync-success hook in `firmware/src/main.cpp`; update source tests and docs without changing the backend API.

**Tech Stack:** PlatformIO, Arduino framework, M5StickCPlus `M5.Rtc`, Python `unittest`, existing StickWords backend API.

---

## File Structure

- Modify `tests/test_firmware_project.py`: add source-level firmware tests for RTC parsing, validation, boot logging, and sync calibration hook.
- Modify `firmware/src/main.cpp`: add `RtcTimestamp` helper struct, ISO UTC parser, RTC read/write/log helpers, boot-time RTC logging, and post-sync RTC calibration.
- Modify `docs/handoff.md`: add Stage 5A behavior and real-device validation steps.
- Modify `docs/dev_log.md`: record Stage 5A implementation and verification.

No backend file changes are required because `/api/device/tasks` already returns `generated_at`.

---

### Task 1: Add Failing RTC Firmware Test

**Files:**
- Modify: `tests/test_firmware_project.py`

- [ ] **Step 1: Add the failing source test**

Add this test after `test_stage4_review_timestamp_uses_generated_at_or_fallback`:

```python
    def test_stage5a_firmware_sets_and_logs_bm8563_rtc_from_generated_at(self):
        source = firmware_source()
        setup_body = firmware_function_body(source, "setup")
        fetch_body = firmware_function_body(source, "fetchDeviceTasks")
        parse_body = firmware_function_body(source, "parseUtcTimestamp")
        valid_body = firmware_function_body(source, "isValidRtcTimestamp")
        set_body = firmware_function_body(source, "setRtcFromGeneratedAt")
        log_body = firmware_function_body(source, "logRtcNow")

        self.assertIn("struct RtcTimestamp", source)
        self.assertIn("parseUtcTimestamp(", source)
        self.assertIn("isValidRtcTimestamp(", source)
        self.assertIn("readRtcTimestamp(", source)
        self.assertIn("logRtcNow()", source)
        self.assertIn("setRtcFromGeneratedAt(", source)
        self.assertIn("RTC_TimeTypeDef", source)
        self.assertIn("RTC_DateTypeDef", source)
        self.assertIn("M5.Rtc.GetTime", source)
        self.assertIn("M5.Rtc.GetDate", source)
        self.assertIn("M5.Rtc.SetTime", source)
        self.assertIn("M5.Rtc.SetDate", source)

        self.assertIn("value.length() != 20", parse_body)
        self.assertIn("value[4] != '-'", parse_body)
        self.assertIn("value[10] != 'T'", parse_body)
        self.assertIn("value[19] != 'Z'", parse_body)
        self.assertIn("timestamp.year >= 2024", valid_body)
        self.assertIn("timestamp.month >= 1", valid_body)
        self.assertIn("timestamp.month <= 12", valid_body)
        self.assertIn("timestamp.hour <= 23", valid_body)
        self.assertIn("timestamp.minute <= 59", valid_body)
        self.assertIn("timestamp.second <= 59", valid_body)
        self.assertIn("RTC now=", log_body)
        self.assertIn("valid=1", log_body)
        self.assertIn("RTC now=invalid valid=0", log_body)
        self.assertIn("RTC set=", set_body)
        self.assertIn("RTC set skipped: invalid generated_at", set_body)
        self.assertIn("logRtcNow()", setup_body)
        self.assertIn("setRtcFromGeneratedAt(serverGeneratedAt)", fetch_body)
```

- [ ] **Step 2: Run the focused test and verify red**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage5a_firmware_sets_and_logs_bm8563_rtc_from_generated_at -v
```

Expected: FAIL because `parseUtcTimestamp`, `RtcTimestamp`, and RTC helper functions do not exist yet.

- [ ] **Step 3: Commit is not needed for red test alone**

Do not commit after the red test. Continue to Task 2 and commit the green implementation with its test.

---

### Task 2: Implement RTC Parsing, Logging, And Calibration

**Files:**
- Modify: `firmware/src/main.cpp`
- Test: `tests/test_firmware_project.py`

- [ ] **Step 1: Add RTC timestamp struct**

In `firmware/src/main.cpp`, after `struct RuntimeConfig`, add:

```cpp
struct RtcTimestamp {
  uint16_t year;
  uint8_t month;
  uint8_t date;
  uint8_t hour;
  uint8_t minute;
  uint8_t second;
  uint8_t weekDay;
};
```

- [ ] **Step 2: Add timestamp helper functions**

Add these helpers near `currentReviewTimestamp()` or before it:

```cpp
int twoDigitsAt(const String& value, int index) {
  if (index + 1 >= value.length() ||
      value[index] < '0' || value[index] > '9' ||
      value[index + 1] < '0' || value[index + 1] > '9') {
    return -1;
  }
  return (value[index] - '0') * 10 + (value[index + 1] - '0');
}

bool parseUtcTimestamp(const String& value, RtcTimestamp* timestamp) {
  if (timestamp == nullptr || value.length() != 20 ||
      value[4] != '-' || value[7] != '-' || value[10] != 'T' ||
      value[13] != ':' || value[16] != ':' || value[19] != 'Z') {
    return false;
  }
  const int yearHigh = twoDigitsAt(value, 0);
  const int yearLow = twoDigitsAt(value, 2);
  const int month = twoDigitsAt(value, 5);
  const int date = twoDigitsAt(value, 8);
  const int hour = twoDigitsAt(value, 11);
  const int minute = twoDigitsAt(value, 14);
  const int second = twoDigitsAt(value, 17);
  if (yearHigh < 0 || yearLow < 0 || month < 0 || date < 0 ||
      hour < 0 || minute < 0 || second < 0) {
    return false;
  }
  timestamp->year = static_cast<uint16_t>(yearHigh * 100 + yearLow);
  timestamp->month = static_cast<uint8_t>(month);
  timestamp->date = static_cast<uint8_t>(date);
  timestamp->hour = static_cast<uint8_t>(hour);
  timestamp->minute = static_cast<uint8_t>(minute);
  timestamp->second = static_cast<uint8_t>(second);
  timestamp->weekDay = 0;
  return isValidRtcTimestamp(*timestamp);
}
```

- [ ] **Step 3: Add RTC validity and formatting helpers**

Add:

```cpp
bool isValidRtcTimestamp(const RtcTimestamp& timestamp) {
  return timestamp.year >= 2024 &&
         timestamp.month >= 1 && timestamp.month <= 12 &&
         timestamp.date >= 1 && timestamp.date <= 31 &&
         timestamp.hour <= 23 &&
         timestamp.minute <= 59 &&
         timestamp.second <= 59;
}

String formatRtcTimestamp(const RtcTimestamp& timestamp) {
  char buffer[25];
  std::snprintf(
      buffer,
      sizeof(buffer),
      "%04u-%02u-%02uT%02u:%02u:%02uZ",
      static_cast<unsigned>(timestamp.year),
      static_cast<unsigned>(timestamp.month),
      static_cast<unsigned>(timestamp.date),
      static_cast<unsigned>(timestamp.hour),
      static_cast<unsigned>(timestamp.minute),
      static_cast<unsigned>(timestamp.second));
  return String(buffer);
}
```

If `std::snprintf` needs an include, add `#include <cstdio>`.

- [ ] **Step 4: Add RTC read/write/log helpers**

Add:

```cpp
RtcTimestamp readRtcTimestamp() {
  RTC_TimeTypeDef time = {};
  RTC_DateTypeDef date = {};
  M5.Rtc.GetTime(&time);
  M5.Rtc.GetDate(&date);
  return {
      date.Year,
      date.Month,
      date.Date,
      time.Hours,
      time.Minutes,
      time.Seconds,
      date.WeekDay,
  };
}

void logRtcNow() {
  const RtcTimestamp timestamp = readRtcTimestamp();
  if (!isValidRtcTimestamp(timestamp)) {
    Serial.println("RTC now=invalid valid=0");
    return;
  }
  Serial.println("RTC now=" + formatRtcTimestamp(timestamp) + " valid=1");
}

void setRtcFromGeneratedAt(const char* generatedAt) {
  RtcTimestamp timestamp = {};
  if (!parseUtcTimestamp(String(generatedAt), &timestamp)) {
    Serial.println("RTC set skipped: invalid generated_at");
    return;
  }

  RTC_TimeTypeDef time = {
      timestamp.hour,
      timestamp.minute,
      timestamp.second,
  };
  RTC_DateTypeDef date = {
      timestamp.weekDay,
      timestamp.month,
      timestamp.date,
      timestamp.year,
  };
  M5.Rtc.SetDate(&date);
  M5.Rtc.SetTime(&time);
  Serial.println("RTC set=" + formatRtcTimestamp(timestamp));
  logRtcNow();
}
```

- [ ] **Step 5: Wire boot logging and sync calibration**

In `setup()`, after the existing orientation serial log, add:

```cpp
  logRtcNow();
```

In `fetchDeviceTasks()`, after successful `parseDeviceTasksJson(body)` and before `tasksFetchedAtMs = millis();`, add:

```cpp
  setRtcFromGeneratedAt(serverGeneratedAt);
```

- [ ] **Step 6: Run the focused test and verify green**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage5a_firmware_sets_and_logs_bm8563_rtc_from_generated_at -v
```

Expected: PASS.

- [ ] **Step 7: Run all firmware source tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: PASS.

- [ ] **Step 8: Commit implementation**

Run:

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Calibrate M5Stick RTC from sync time"
```

---

### Task 3: Update Handoff And Development Log

**Files:**
- Modify: `docs/handoff.md`
- Modify: `docs/dev_log.md`

- [ ] **Step 1: Update handoff current status**

In `docs/handoff.md`, update completed milestones to include Stage 5A RTC calibration, and replace the RTC known-limit line with wording that says the firmware now sets and logs RTC but does not yet use it for offline due-card scheduling.

Add this validation note under real-device validation notes:

```markdown
Stage 5A RTC validation procedure:

1. Start the PC backend.
2. Boot M5Stick with Wi-Fi available.
3. Confirm serial shows `RTC set=...` and `RTC now=... valid=1`.
4. Power off M5Stick.
5. Wait 1 to 2 minutes.
6. Boot again and confirm `RTC now=... valid=1` moved forward.
```

- [ ] **Step 2: Append dev log entry**

Append:

```markdown
## 2026-05-25 Stage 5A: RTC calibration

完成内容：
- 使用 PC 后端 `/api/device/tasks` 返回的 `generated_at` 校准 M5Stick C Plus BM8563 RTC。
- 开机时读取 RTC 并打印 `RTC now=... valid=1` 或 `RTC now=invalid valid=0`。
- 同步成功后打印 `RTC set=...` 并读回当前 RTC。
- 本阶段不改变复习调度逻辑，也不实现离线 due-card 选择。

测试结果：
- RTC 固件源码测试通过：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage5a_firmware_sets_and_logs_bm8563_rtc_from_generated_at -v`
- 固件源码测试通过：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v`

下一步：
- 上传固件到真机，执行 RTC 断电保持验证。
```

- [ ] **Step 3: Run diff check**

Run:

```powershell
git diff --check
```

Expected: exit code 0, only possible CRLF warnings.

- [ ] **Step 4: Commit docs**

Run:

```powershell
git add docs/handoff.md docs/dev_log.md
git commit -m "Document RTC calibration validation"
```

---

### Task 4: Full Verification

**Files:**
- Verify entire repository and firmware build.

- [ ] **Step 1: Run all tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Build firmware**

Run:

```powershell
& 'C:\Users\ASUS\.platformio\penv\Scripts\pio.exe' run
```

from:

```powershell
C:\Users\ASUS\Documents\M5Stick\firmware
```

Expected: PlatformIO build succeeds and dependency graph includes `M5StickCPlus`.

- [ ] **Step 3: Check whitespace and git status**

Run:

```powershell
git diff --check
git status --short
```

Expected: no whitespace errors; status clean after commits.

---

## Self-Review

- Spec coverage: plan covers timestamp parsing, RTC write/read/logging, boot log, post-sync calibration, docs, and validation. Offline scheduling and auto power-off are excluded as specified.
- Placeholder scan: no unfinished placeholder items or ambiguous "handle later" instructions.
- Type consistency: plan uses `RtcTimestamp`, `RTC_TimeTypeDef`, `RTC_DateTypeDef`, `parseUtcTimestamp`, `isValidRtcTimestamp`, `readRtcTimestamp`, `logRtcNow`, and `setRtcFromGeneratedAt` consistently.
