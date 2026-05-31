# StickWords Stage 6 LVGL Clock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an LVGL clock page to the current `M5Stick` firmware, based on the Figma Make export, without adopting Stage 5E idle behavior from `M5Stick-v2`.

**Architecture:** Switch firmware to M5Unified and add LVGL 8.3. LVGL owns only `Page::Clock`; all review, status, setup, sync, and offline scheduling behavior stays on the current code path.

**Tech Stack:** PlatformIO Arduino, ESP32, M5Unified, LVGL 8.3, existing Python `unittest` source-level firmware tests.

---

## Files And Responsibilities

- `firmware/platformio.ini`: replace M5StickCPlus dependency with M5Unified and add LVGL.
- `firmware/include/lv_conf.h`: LVGL configuration and font enablement.
- `firmware/src/main.cpp`: M5Unified API migration, LVGL initialization, LVGL clock UI, clock-only LVGL ticking.
- `tests/test_firmware_project.py`: source tests for Stage 6 dependencies, LVGL clock behavior, and Stage 5E exclusion.
- `docs/dev_log.md`: record Stage 6 implementation and validation.
- `docs/handoff.md`: update current capabilities, build instructions, manual validation procedure.

---

## Task 1: Stage 6 Source Tests

**Files:**
- Modify: `tests/test_firmware_project.py`

- [ ] **Step 1: Write failing tests**

Add these tests to `FirmwareProjectTests`:

```python
    def test_stage6_platformio_uses_m5unified_and_lvgl(self):
        config = (ROOT / "firmware" / "platformio.ini").read_text(encoding="utf-8")
        lv_conf = ROOT / "firmware" / "include" / "lv_conf.h"

        self.assertIn("m5stack/M5Unified", config)
        self.assertIn("lvgl/lvgl@^8.3.11", config)
        self.assertNotIn("m5stack/M5StickCPlus", config)
        self.assertTrue(lv_conf.exists())
        text = lv_conf.read_text(encoding="utf-8")
        self.assertIn("#define LV_FONT_MONTSERRAT_12 1", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_14 1", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_18 1", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_24 1", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_48 1", text)

    def test_stage6_clock_page_uses_lvgl_without_stage5e_idle(self):
        source = firmware_source()
        setup_body = firmware_function_body(source, "setup")
        loop_body = firmware_function_body(source, "loop")
        render_body = firmware_function_body(source, "render")
        flush_body = firmware_function_body(source, "lvglFlushCb")
        clock_body = firmware_function_body(source, "drawClockPage")

        self.assertIn("#include <M5Unified.h>", source)
        self.assertIn("#include <lvgl.h>", source)
        self.assertNotIn("#include <M5StickCPlus.h>", source)
        self.assertIn("lv_disp_draw_buf_t lvDrawBuf", source)
        self.assertIn("lv_color_t lvBuf1[240 * 16]", source)
        self.assertIn("lv_color_t lvBuf2[240 * 16]", source)
        self.assertIn("void lvglFlushCb(", source)
        self.assertIn("M5.Display.setSwapBytes(true)", flush_body)
        self.assertIn("lv_disp_flush_ready", flush_body)
        self.assertIn("createClockUI()", source)
        self.assertIn("updateClockUI()", source)
        self.assertIn("lv_font_montserrat_48", source)
        self.assertIn("lv_arc_create", source)
        self.assertIn("lv_label_create", source)
        self.assertIn("DUE", source)
        self.assertIn("lv_init()", setup_body)
        self.assertIn("lv_disp_drv_register", setup_body)
        self.assertIn("if (currentPage == Page::Clock)", loop_body)
        self.assertIn("lv_timer_handler()", loop_body)
        self.assertIn("drawClockPage()", render_body)
        self.assertIn("updateClockUI()", clock_body)
        self.assertIn("constexpr uint32_t kIdlePowerOffMs = 180000", source)
        self.assertNotIn("kIdleClockReturnMs", source)
```

- [ ] **Step 2: Run focused tests and confirm RED**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage6_platformio_uses_m5unified_and_lvgl tests.test_firmware_project.FirmwareProjectTests.test_stage6_clock_page_uses_lvgl_without_stage5e_idle -v
```

Expected: FAIL because the current firmware still uses M5StickCPlus and has no LVGL.

- [ ] **Step 3: Commit tests**

```powershell
git add tests/test_firmware_project.py
git commit -m "Test Stage 6 LVGL clock migration"
```

---

## Task 2: Dependencies And LVGL Config

**Files:**
- Modify: `firmware/platformio.ini`
- Create: `firmware/include/lv_conf.h`

- [ ] **Step 1: Update PlatformIO dependencies**

Replace the dependency block in `firmware/platformio.ini` with:

```ini
lib_deps =
    m5stack/M5Unified
    lvgl/lvgl@^8.3.11
```

- [ ] **Step 2: Add LVGL config**

Create `firmware/include/lv_conf.h`:

```c
#pragma once

#define LV_COLOR_DEPTH 16
#define LV_MEM_CUSTOM 0
#define LV_MEM_SIZE (16U * 1024U)
#define LV_USE_LOG 0
#define LV_USE_ASSERT_NULL 0
#define LV_USE_ASSERT_MALLOC 0
#define LV_USE_ASSERT_STYLE 0
#define LV_USE_ASSERT_MEM_INTEGRITY 0
#define LV_USE_ASSERT_OBJ 0
#define LV_USE_PERF_MONITOR 0
#define LV_USE_MEM_MONITOR 0
#define LV_FONT_MONTSERRAT_12 1
#define LV_FONT_MONTSERRAT_14 1
#define LV_FONT_MONTSERRAT_18 1
#define LV_FONT_MONTSERRAT_24 1
#define LV_FONT_MONTSERRAT_48 1
#define LV_FONT_DEFAULT &lv_font_montserrat_14
```

- [ ] **Step 3: Run dependency test**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage6_platformio_uses_m5unified_and_lvgl -v
```

Expected: PASS.

- [ ] **Step 4: Commit dependencies**

```powershell
git add firmware/platformio.ini firmware/include/lv_conf.h
git commit -m "Add M5Unified and LVGL dependencies"
```

---

## Task 3: M5Unified API Migration

**Files:**
- Modify: `firmware/src/main.cpp`

- [ ] **Step 1: Replace include and display API**

Replace:

```cpp
#include <M5StickCPlus.h>
```

with:

```cpp
#include <M5Unified.h>
```

Replace all `M5.Lcd.` calls with `M5.Display.`. Keep existing drawing behavior otherwise unchanged.

- [ ] **Step 2: Replace setup initialization**

Replace the beginning of `setup()`:

```cpp
  M5.begin();
  M5.Imu.Init();
  Serial.begin(115200);
  delay(200);
```

with:

```cpp
  auto cfg = M5.config();
  cfg.serial_baudrate = 115200;
  cfg.internal_imu = true;
  cfg.clear_display = true;
  M5.begin(cfg);
  delay(200);
```

- [ ] **Step 3: Update Button A long-press API casing if needed**

If PlatformIO reports `wasReleasefor` is missing, replace:

```cpp
M5.BtnA.wasReleasefor(kButtonLongPressMs)
```

with:

```cpp
M5.BtnA.wasReleaseFor(kButtonLongPressMs)
```

- [ ] **Step 4: Run firmware tests and build**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run
```

Expected: source tests may still fail for LVGL clock details until Task 4, but PlatformIO should compile the M5Unified migration once API casing is correct.

---

## Task 4: LVGL Clock UI

**Files:**
- Modify: `firmware/src/main.cpp`

- [ ] **Step 1: Add LVGL include and globals**

Add:

```cpp
#include <lvgl.h>
```

Add globals near the existing UI globals:

```cpp
static lv_disp_draw_buf_t lvDrawBuf;
static lv_color_t lvBuf1[240 * 16];
static lv_color_t lvBuf2[240 * 16];
static lv_disp_drv_t lvDispDrv;

lv_obj_t* clockScr = nullptr;
lv_obj_t* clockTime = nullptr;
lv_obj_t* clockDayLabel = nullptr;
lv_obj_t* clockDateLabel = nullptr;
lv_obj_t* clockDueBg = nullptr;
lv_obj_t* clockDueText = nullptr;
lv_obj_t* clockBatArc = nullptr;
lv_obj_t* clockBatLabel = nullptr;
lv_obj_t* clockCheckMark = nullptr;
lv_obj_t* clockCheckCircle = nullptr;
```

- [ ] **Step 2: Add LVGL flush callback**

Add:

```cpp
void lvglFlushCb(lv_disp_drv_t* disp, const lv_area_t* area, lv_color_t* pixels) {
  const uint32_t w = area->x2 - area->x1 + 1;
  const uint32_t h = area->y2 - area->y1 + 1;
  M5.Display.startWrite();
  M5.Display.setSwapBytes(true);
  M5.Display.setAddrWindow(area->x1, area->y1, w, h);
  M5.Display.pushPixels(reinterpret_cast<uint16_t*>(pixels), w * h);
  M5.Display.endWrite();
  lv_disp_flush_ready(disp);
}
```

- [ ] **Step 3: Add clock object creation**

Add a `createClockUI()` helper that creates:

- black `clockScr`
- green circular checkmark at `(10, 6)`, size `14x14`
- red DUE pill top-right, size about `58x22`
- white time label using `lv_font_montserrat_48`
- red weekday and white day label using `lv_font_montserrat_24`
- battery arc at right-center, `56x56`, with centered percentage label

Use LVGL labels and arc objects; do not use raw `M5.Display` drawing for the clock page.

- [ ] **Step 4: Add clock update helper**

Add `updateClockUI()`:

- create UI if missing
- if RTC invalid, show `RTC invalid` and `Sync needed`
- set `clockTime` to `HH:MM`
- compute weekday from date
- set due text to `DUE%zu`
- read battery with `M5.Power.getBatteryLevel()`, clamp to `0..100`
- update arc value and color

- [ ] **Step 5: Replace `drawClockPage()`**

Replace current raw drawing implementation with:

```cpp
void drawClockPage() {
  updateClockUI();
}
```

- [ ] **Step 6: Initialize LVGL in setup**

After `M5.begin(cfg); delay(200);`, add:

```cpp
  lv_init();
  lv_disp_draw_buf_init(&lvDrawBuf, lvBuf1, lvBuf2, 240 * 16);
  lv_disp_drv_init(&lvDispDrv);
  lvDispDrv.hor_res = 240;
  lvDispDrv.ver_res = 135;
  lvDispDrv.flush_cb = lvglFlushCb;
  lvDispDrv.draw_buf = &lvDrawBuf;
  lv_disp_drv_register(&lvDispDrv);
  lv_obj_set_style_bg_color(lv_scr_act(), lv_color_black(), 0);
  createClockUI();
  updateClockUI();
```

- [ ] **Step 7: Tick LVGL only on clock page**

In `loop()`, immediately after `M5.update();`, add:

```cpp
  if (currentPage == Page::Clock) {
    lv_timer_handler();
  }
```

Keep current `updateClockPage(now)` and 3-minute idle flow.

- [ ] **Step 8: Run focused Stage 6 test**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project.FirmwareProjectTests.test_stage6_clock_page_uses_lvgl_without_stage5e_idle -v
```

Expected: PASS.

---

## Task 5: Verification And Documentation

**Files:**
- Modify: `docs/dev_log.md`
- Modify: `docs/handoff.md`

- [ ] **Step 1: Run full verification**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
C:\Users\ASUS\.platformio\penv\Scripts\pio.exe run
git diff --check
```

Expected:

- all Python tests pass
- PlatformIO reports SUCCESS
- `git diff --check` has no whitespace errors

- [ ] **Step 2: Update docs**

Append to `docs/dev_log.md`:

```markdown
## 2026-05-31 Stage 6: LVGL clock page on current baseline

Completed:
- Migrated firmware dependency from M5StickCPlus to M5Unified.
- Added LVGL 8.3 and `lv_conf.h`.
- Implemented the clock page with LVGL widgets based on the Figma Make export.
- Kept review/status/setup pages on the existing display path.
- Preserved the current 3-minute idle power-off behavior; Stage 5E two-stage idle was intentionally not adopted.

Verification:
- Python tests passed.
- PlatformIO firmware build passed.
```

Update `docs/handoff.md`:

- add Stage 6 to completed milestones
- update firmware build notes to mention M5Unified + LVGL
- add Stage 6 manual validation steps

- [ ] **Step 3: Commit implementation**

```powershell
git add firmware/platformio.ini firmware/include/lv_conf.h firmware/src/main.cpp tests/test_firmware_project.py docs/dev_log.md docs/handoff.md
git commit -m "Implement Stage 6 LVGL clock page"
```

---

## Self-Review

Spec coverage:

- Current folder remains baseline: Task 1-5 modify only current `M5Stick`.
- Figma Make export is design source: Task 4 implements the exported clock layout.
- LVGL only owns Clock page: Task 4 keeps other render paths intact.
- Stage 5E excluded: Task 1 asserts no `kIdleClockReturnMs`, Task 4 keeps current idle flow.
- v2 pitfalls addressed: Task 4 uses `setSwapBytes(true)`, explicit LVGL screen creation, clock-only ticking; Task 3 handles M5Unified API casing.

Placeholder scan:

- No `TODO` or `TBD` placeholders are required for implementation.

Type consistency:

- Existing firmware names are preserved: `drawClockPage`, `showClockPage`, `updateClockPage`, `activeCardCount`, `formatRtcTime`, `toClockDisplayTimestamp`.
