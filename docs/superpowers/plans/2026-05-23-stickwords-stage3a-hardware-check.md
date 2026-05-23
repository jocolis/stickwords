# StickWords Stage 3A Hardware Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the first PlatformIO firmware project for M5Stick C Plus and verify screen, serial, Button A, Button B, and IMU hardware access.

**Architecture:** Add a small `firmware/` PlatformIO project alongside the existing PC backend. The firmware is a standalone Arduino-style `main.cpp` that uses `M5StickCPlus`, fixed landscape display, serial logs, button polling, and IMU acceleration reads. PC-side tests verify the firmware project files and documentation; real device behavior is verified manually with PlatformIO commands.

**Tech Stack:** PlatformIO, Espressif 32 platform, Arduino framework, `m5stack/M5StickCPlus`, C++, Python `unittest`, Windows PowerShell.

---

## Scope

This plan implements Stage 3A only.

It creates:

```text
firmware/platformio.ini
firmware/src/main.cpp
tests/test_firmware_project.py
docs/stage3a_platformio_quickstart.md
```

It modifies:

```text
.gitignore
docs/dev_log.md
docs/handoff.md
```

It does not implement Wi-Fi, HTTP sync, vocabulary cards, review screens, tilt rating, double-shake rating, auto-rotation, local cache, power-loss recovery, or USB configuration.

## File Responsibilities

- `firmware/platformio.ini`: PlatformIO environment for M5Stick C Plus hardware check.
- `firmware/src/main.cpp`: Minimal hardware check firmware.
- `tests/test_firmware_project.py`: Repository-level checks for the firmware project files.
- `docs/stage3a_platformio_quickstart.md`: Beginner-friendly PlatformIO run/upload/monitor guide.
- `.gitignore`: Ignore PlatformIO build artifacts.
- `docs/dev_log.md`: Record Stage 3A implementation work.
- `docs/handoff.md`: Update current status, firmware commands, and known limits.

## Task 1: PlatformIO Project Skeleton

**Files:**
- Create: `firmware/platformio.ini`
- Create: `firmware/src/main.cpp`
- Create: `tests/test_firmware_project.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add failing firmware project tests**

Create `tests/test_firmware_project.py`:

```python
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FirmwareProjectTests(unittest.TestCase):
    def test_platformio_config_targets_m5stick_c_plus_check(self):
        config = (ROOT / "firmware" / "platformio.ini").read_text(encoding="utf-8")

        self.assertIn("[env:m5stick-c]", config)
        self.assertIn("platform = espressif32", config)
        self.assertIn("board = m5stick-c", config)
        self.assertIn("framework = arduino", config)
        self.assertIn("monitor_speed = 115200", config)
        self.assertIn("m5stack/M5StickCPlus", config)

    def test_firmware_source_contains_stage3a_hardware_checks(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("#include <M5StickCPlus.h>", source)
        self.assertIn("StickWords Stage 3A boot", source)
        self.assertIn("Button A pressed", source)
        self.assertIn("Button B pressed", source)
        self.assertIn("getAccelData", source)
        self.assertIn("setRotation(1)", source)

    def test_platformio_build_output_is_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("firmware/.pio/", ignore)
        self.assertIn("firmware/.vscode/.browse.c_cpp.db*", ignore)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run firmware project tests to verify they fail**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: FAIL with `FileNotFoundError` for `firmware/platformio.ini`.

- [ ] **Step 3: Create `firmware/platformio.ini`**

Create `firmware/platformio.ini`:

```ini
[env:m5stick-c]
platform = espressif32
board = m5stick-c
framework = arduino
monitor_speed = 115200
lib_deps =
    m5stack/M5StickCPlus
```

- [ ] **Step 4: Create placeholder `firmware/src/main.cpp`**

Create `firmware/src/main.cpp`:

```cpp
#include <M5StickCPlus.h>

void setup() {
  M5.begin();
  M5.Lcd.setRotation(1);
  Serial.begin(115200);
  Serial.println("StickWords Stage 3A boot");
}

void loop() {
  M5.update();

  float ax = 0.0F;
  float ay = 0.0F;
  float az = 0.0F;
  M5.IMU.getAccelData(&ax, &ay, &az);

  if (M5.BtnA.wasPressed()) {
    Serial.println("Button A pressed");
  }

  if (M5.BtnB.wasPressed()) {
    Serial.println("Button B pressed");
  }

  delay(100);
}
```

- [ ] **Step 5: Update `.gitignore` for PlatformIO artifacts**

Append these lines to `.gitignore`:

```gitignore
firmware/.pio/
firmware/.vscode/.browse.c_cpp.db*
firmware/.vscode/c_cpp_properties.json
firmware/.vscode/launch.json
firmware/.vscode/ipch/
```

- [ ] **Step 6: Run firmware project tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: PASS, 3 tests.

- [ ] **Step 7: Commit**

Run:

```powershell
git add .gitignore firmware/platformio.ini firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Add Stage 3A firmware skeleton"
```

## Task 2: Hardware Check Firmware UI And Logs

**Files:**
- Modify: `firmware/src/main.cpp`
- Test: `tests/test_firmware_project.py`

- [ ] **Step 1: Replace placeholder firmware with full Stage 3A hardware check**

Replace `firmware/src/main.cpp` with:

```cpp
#include <M5StickCPlus.h>

namespace {

constexpr uint32_t kScreenRefreshMs = 250;
constexpr uint32_t kSerialImuMs = 1000;

bool buttonAState = false;
bool buttonBState = false;
float accelX = 0.0F;
float accelY = 0.0F;
float accelZ = 0.0F;
uint32_t lastScreenRefresh = 0;
uint32_t lastSerialImu = 0;

void drawStatusScreen() {
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setCursor(8, 8);
  M5.Lcd.setTextColor(WHITE, BLACK);
  M5.Lcd.setTextSize(2);
  M5.Lcd.println("StickWords");

  M5.Lcd.setTextSize(1);
  M5.Lcd.println("Stage 3A Hardware Check");
  M5.Lcd.println();

  M5.Lcd.printf("Button A: %s\n", buttonAState ? "pressed" : "released");
  M5.Lcd.printf("Button B: %s\n", buttonBState ? "pressed" : "released");
  M5.Lcd.println();
  M5.Lcd.printf("ax: %.2f\n", accelX);
  M5.Lcd.printf("ay: %.2f\n", accelY);
  M5.Lcd.printf("az: %.2f\n", accelZ);
}

void readImu() {
  M5.IMU.getAccelData(&accelX, &accelY, &accelZ);
}

void logButtonTransitions() {
  if (M5.BtnA.wasPressed()) {
    Serial.println("Button A pressed");
  }
  if (M5.BtnA.wasReleased()) {
    Serial.println("Button A released");
  }

  if (M5.BtnB.wasPressed()) {
    Serial.println("Button B pressed");
  }
  if (M5.BtnB.wasReleased()) {
    Serial.println("Button B released");
  }
}

void logImuPeriodically(uint32_t now) {
  if (now - lastSerialImu < kSerialImuMs) {
    return;
  }

  lastSerialImu = now;
  Serial.printf("IMU ax=%.2f ay=%.2f az=%.2f\n", accelX, accelY, accelZ);
}

void refreshScreenPeriodically(uint32_t now) {
  if (now - lastScreenRefresh < kScreenRefreshMs) {
    return;
  }

  lastScreenRefresh = now;
  drawStatusScreen();
}

}  // namespace

void setup() {
  M5.begin();
  Serial.begin(115200);
  delay(200);

  M5.Lcd.setRotation(1);
  M5.Lcd.setTextFont(1);
  M5.Lcd.setTextDatum(TL_DATUM);

  Serial.println("StickWords Stage 3A boot");
  readImu();
  drawStatusScreen();
}

void loop() {
  M5.update();

  buttonAState = M5.BtnA.isPressed();
  buttonBState = M5.BtnB.isPressed();
  readImu();

  const uint32_t now = millis();
  logButtonTransitions();
  logImuPeriodically(now);
  refreshScreenPeriodically(now);

  delay(20);
}
```

- [ ] **Step 2: Strengthen firmware source tests**

Update `tests/test_firmware_project.py` so `test_firmware_source_contains_stage3a_hardware_checks` is:

```python
    def test_firmware_source_contains_stage3a_hardware_checks(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("#include <M5StickCPlus.h>", source)
        self.assertIn("StickWords Stage 3A boot", source)
        self.assertIn("Stage 3A Hardware Check", source)
        self.assertIn("Button A pressed", source)
        self.assertIn("Button A released", source)
        self.assertIn("Button B pressed", source)
        self.assertIn("Button B released", source)
        self.assertIn("M5.BtnA.isPressed()", source)
        self.assertIn("M5.BtnB.isPressed()", source)
        self.assertIn("M5.IMU.getAccelData", source)
        self.assertIn("M5.Lcd.setRotation(1)", source)
        self.assertIn("Serial.printf(\"IMU ax=", source)
```

- [ ] **Step 3: Run firmware project tests**

Run:

```powershell
$env:PYTHONPATH='src'; python -m unittest tests.test_firmware_project -v
```

Expected: PASS.

- [ ] **Step 4: Run repository Python tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 51 tests after Task 2.

- [ ] **Step 5: Run PlatformIO build if `pio` is available**

Run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
```

Expected when PlatformIO is installed and network/dependencies are available: SUCCESS.

If `pio` is not available in this shell, record that firmware build was not run from Codex and continue. The user can run the same command from VSCode PlatformIO Terminal.

If dependency download fails because of network restrictions, rerun with escalated network permission if available. If it still fails, record the exact error and do not claim firmware build success.

- [ ] **Step 6: Commit**

Run:

```powershell
git add firmware/src/main.cpp tests/test_firmware_project.py
git commit -m "Implement Stage 3A hardware check firmware"
```

## Task 3: User Quickstart And Handoff Docs

**Files:**
- Create: `docs/stage3a_platformio_quickstart.md`
- Modify: `docs/dev_log.md`
- Modify: `docs/handoff.md`

- [ ] **Step 1: Create PlatformIO quickstart guide**

Create `docs/stage3a_platformio_quickstart.md`:

```markdown
# Stage 3A PlatformIO Quickstart

This guide is for the first StickWords M5Stick C Plus hardware check.

## What This Stage Verifies

- PlatformIO can build the firmware.
- The firmware can be uploaded to the M5Stick C Plus.
- The serial monitor shows logs.
- The screen shows a landscape status page.
- Button A and Button B are detected.
- IMU acceleration values change when the device moves.

This stage does not include Wi-Fi, vocabulary sync, or the review flow.

## Open The Firmware Project

In VSCode:

1. Open the repository folder:

   ```text
   C:\Users\ASUS\Documents\M5Stick
   ```

2. Open this file:

   ```text
   firmware\platformio.ini
   ```

3. Wait for PlatformIO to finish loading the project.

## Build

From a PlatformIO terminal:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
```

Expected result:

```text
SUCCESS
```

Meaning: the firmware can compile.

## Upload

Connect the M5Stick C Plus by USB, then run:

```powershell
pio run --target upload
```

Expected result:

```text
SUCCESS
```

Meaning: the firmware was written to the device.

If upload fails, check:

- The USB cable supports data, not only charging.
- The device is powered on.
- No other serial monitor is using the port.
- PlatformIO selected the correct port.

## Serial Monitor

Run:

```powershell
pio device monitor
```

Expected boot log:

```text
StickWords Stage 3A boot
```

Expected interaction logs:

```text
Button A pressed
Button A released
Button B pressed
Button B released
IMU ax=... ay=... az=...
```

To exit the monitor, press:

```text
Ctrl+C
```

If that does not close it, try:

```text
Ctrl+]
```

## Device Screen Check

The screen should show:

```text
StickWords
Stage 3A Hardware Check
Button A: ...
Button B: ...
ax: ...
ay: ...
az: ...
```

Press Button A and Button B. The displayed state should change.

Move or tilt the device. The acceleration values should change.

## What To Report Back

After testing, report:

- Whether `pio run` succeeded.
- Whether `pio run --target upload` succeeded.
- Whether `pio device monitor` showed boot logs.
- Whether Button A and Button B logs appeared.
- Whether IMU values changed when moving the device.
- Any exact error text if something failed.
```

- [ ] **Step 2: Append Stage 3A log to `docs/dev_log.md`**

Append:

```markdown
## 2026-05-23 阶段 3A：M5Stick 硬件连通验证

完成内容：

- 设计 M5Stick C Plus 的第一版 PlatformIO 固件工程。
- 第一版范围限定为屏幕、串口、Button A、Button B 和 IMU 验证。
- 明确 Stage 3A 不实现 Wi-Fi、同步、复习流程、双摇评分和断电恢复。
- 增加 PlatformIO 新手操作说明，便于编译、上传和查看串口日志。

测试结果：

- 仓库级 Python 测试继续使用：
  `$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v`
- 固件需要在 `firmware/` 下运行：
  `pio run`
  `pio run --target upload`
  `pio device monitor`

遇到的问题：

- `M5StickCPlus` 专用库更适合第一版连通验证，但上游仓库提示新项目可考虑 M5Unified/M5GFX。
- Codex 环境不一定能直接访问 PlatformIO 依赖下载或真实 USB 设备。

解决方式：

- Stage 3A 先用 `M5StickCPlus`，如果编译或硬件行为出现兼容问题，再切换到 M5Unified。
- 把真实硬件验证拆成明确的人工检查项：编译、上传、串口、按键、IMU。

下一步：

- 在真实 M5Stick C Plus 上执行 Stage 3A 验证。
- 验证通过后进入 Stage 3B：使用假数据实现最小复习 UI 状态机。
```

- [ ] **Step 3: Update `docs/handoff.md` current status and commands**

Update `docs/handoff.md` so:

Current status becomes:

```markdown
Stage 2 PC web management page is implemented and tested.
Stage 3A M5Stick hardware check firmware is prepared for PlatformIO validation.
```

Add a firmware section after `How To Run`:

````markdown
## How To Run Firmware Hardware Check

Open a PlatformIO terminal, then run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
pio run --target upload
pio device monitor
```

See `docs/stage3a_platformio_quickstart.md` for beginner-friendly steps and expected output.
````

Update `What Works` by adding:

```markdown
- Stage 3A firmware skeleton:
  - PlatformIO project under `firmware/`
  - fixed landscape status screen
  - serial boot log
  - Button A/Button B detection
  - IMU acceleration readout
```

Update `Known Limits` to include:

```markdown
- Stage 3A requires real-device manual validation with PlatformIO.
- Firmware does not implement review UI yet.
- Firmware does not implement Wi-Fi sync yet.
```

Update `Next Stage` to:

```markdown
Validate Stage 3A on the real M5Stick C Plus. After it passes, build Stage 3B: minimum review UI prototype with fake local cards.
```

- [ ] **Step 4: Run repository Python tests**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 51 tests after Task 3.

- [ ] **Step 5: Commit**

Run:

```powershell
git add docs/stage3a_platformio_quickstart.md docs/dev_log.md docs/handoff.md
git commit -m "Document Stage 3A PlatformIO workflow"
```

## Task 4: Final Verification And Manual Hardware Checklist

**Files:**
- Modify: `docs/handoff.md` only if verification findings need to be recorded.

- [ ] **Step 1: Run full Python test suite**

Run:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

Expected: PASS, 51 tests.

- [ ] **Step 2: Run PlatformIO build from `firmware/` if possible**

Run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
```

Expected when PlatformIO and dependency downloads are available: SUCCESS.

If it cannot be run in this environment, record the exact reason in the final response. Do not claim firmware build success without this command passing.

- [ ] **Step 3: Check git status**

Run:

```powershell
git status --short
```

Expected: no output.

- [ ] **Step 4: Give the user the real-device checklist**

Tell the user to run:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
pio run --target upload
pio device monitor
```

Ask them to report:

```text
1. Did pio run show SUCCESS?
2. Did upload show SUCCESS?
3. Did the screen show StickWords / Stage 3A Hardware Check?
4. Did Button A logs appear?
5. Did Button B logs appear?
6. Did IMU ax/ay/az values change when moving the device?
```

## Self-Review

Spec coverage:

- PlatformIO firmware project: Tasks 1 and 2.
- Uploadable firmware source: Task 2.
- Serial logs: Task 2.
- Landscape screen: Task 2.
- Button A/Button B detection: Task 2.
- IMU acceleration reads: Task 2.
- Beginner PlatformIO operation guide: Task 3.
- Manual verification checklist: Task 4.
- Python test continuity: Tasks 1, 2, 3, and 4.

Out-of-scope protection:

- No Wi-Fi code.
- No HTTP code.
- No vocabulary data.
- No review UI state machine.
- No tilt scoring or double-shake scoring.
- No auto-rotation.
- No local cache or power-loss recovery.

Type and API consistency:

- Firmware uses `M5.begin()`, `M5.update()`, `M5.BtnA`, `M5.BtnB`, `M5.IMU.getAccelData`, and `M5.Lcd`.
- Serial speed is consistently `115200` in `platformio.ini`, firmware, and docs.
- PlatformIO project path is consistently `C:\Users\ASUS\Documents\M5Stick\firmware`.
