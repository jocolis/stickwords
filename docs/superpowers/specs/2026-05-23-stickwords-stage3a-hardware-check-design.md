# StickWords Stage 3A Hardware Check Design

## Goal

Stage 3A verifies the M5Stick C Plus firmware development chain before adding review workflow, sync, or persistence.

The goal is to prove that this project can:

- Build a PlatformIO firmware project.
- Upload firmware to the M5Stick C Plus.
- Print serial logs.
- Draw a simple horizontal screen.
- Detect Button A and Button B.
- Read IMU acceleration values.

This stage is intentionally small. It is a hardware and toolchain check, not the first review app implementation.

## Scope

Stage 3A will create the first firmware project:

```text
firmware/
  platformio.ini
  src/
    main.cpp
```

The firmware will use:

```ini
[env:m5stick-c]
platform = espressif32
board = m5stick-c
framework = arduino
monitor_speed = 115200
lib_deps =
    m5stack/M5StickCPlus
```

The first firmware will:

- Initialize the M5Stick C Plus with the M5StickCPlus Arduino library.
- Set the display to a fixed horizontal orientation.
- Show a simple status screen:
  - `StickWords`
  - `Stage 3A Hardware Check`
  - Button A state
  - Button B state
  - IMU acceleration values
- Print startup, button, and IMU logs to the serial monitor.
- Update the screen periodically without needing PC backend data.

## Out Of Scope

Stage 3A will not implement:

- Wi-Fi.
- HTTP sync.
- PC backend API calls.
- Real vocabulary cards.
- Review flow screens.
- Rating logic.
- Double-shake `good` submission.
- Left/right tilt scoring.
- Left-hand/right-hand auto-rotation.
- Local session cache.
- Power-loss recovery.
- USB configuration protocol.

These features remain in later stages after the hardware chain is proven.

## Library Choice

Stage 3A will use the `M5StickCPlus` library because it is direct and easy to understand for the first hardware check.

Known note: the M5Stack GitHub repository for `M5StickC-Plus` currently points new projects toward M5Unified/M5GFX. For this project, using `M5StickCPlus` is acceptable for Stage 3A because the goal is quick hardware verification. If build or compatibility problems appear, the next design revision can switch the firmware base to M5Unified.

## User Workflow

The user will use VSCode with the PlatformIO extension installed.

Main commands:

```powershell
cd C:\Users\ASUS\Documents\M5Stick\firmware
pio run
pio run --target upload
pio device monitor
```

Meaning:

- `pio run`: compile the firmware.
- `pio run --target upload`: upload the firmware to the M5Stick C Plus.
- `pio device monitor`: open serial logs.

The project should also be usable through the PlatformIO buttons in VSCode:

- Build
- Upload
- Monitor

## Expected Device Behavior

After upload, the M5Stick C Plus should:

- Display the StickWords Stage 3A status page in landscape orientation.
- Show live Button A and Button B state changes.
- Show changing IMU acceleration values when the device is moved.
- Print readable logs at `115200` baud.

Example serial log shape:

```text
StickWords Stage 3A boot
Button A pressed
Button A released
Button B pressed
IMU ax=0.01 ay=-0.98 az=0.05
```

Exact IMU values are not fixed. The check is that values change when the device moves and stay readable in the serial monitor.

## Error Handling And Debugging

Stage 3A debugging will be split by failure point:

```text
Build fails:
  Check PlatformIO installation, board id, framework, and library dependency.

Upload fails:
  Check USB cable, serial driver, device port, and whether the device needs manual boot/reset handling.

Monitor has no output:
  Check baud rate, selected serial port, and whether firmware reached setup().

Buttons do not respond:
  Check M5.update() usage and Button A/Button B API behavior.

IMU does not respond:
  Check IMU initialization result and library compatibility.
```

No later-stage feature should be added until the Stage 3A checks are usable.

## Test And Verification

Automated PC tests will not cover firmware behavior in Stage 3A.

Verification is manual and evidence-based:

1. `pio run` exits successfully.
2. `pio run --target upload` exits successfully.
3. `pio device monitor` shows boot logs.
4. Pressing Button A changes serial logs and screen state.
5. Pressing Button B changes serial logs and screen state.
6. Moving or tilting the device changes IMU values.

Repository-level Python tests should still pass after adding firmware files:

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'; $env:PYTHONPATH='src'; python -m unittest discover -s tests -v
```

## Next Stage

After Stage 3A passes on the real device, Stage 3B should add the minimum review UI state machine with fake local cards:

```text
word page -> meaning + example summary -> full example -> rating page
```

Tilt rating, double-shake `good`, auto-rotation, sync, and power-loss recovery should remain separate follow-up milestones.
