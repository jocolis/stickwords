# Stage 3A PlatformIO Quickstart

This guide is for the first StickWords M5Stick C Plus hardware check.

Important environment note: the current Codex shell cannot find `pio`, so real firmware build, upload, and serial monitor checks need to be run in VSCode PlatformIO Terminal or another environment where PlatformIO CLI is available.

## What This Stage Verifies

- PlatformIO can build the firmware.
- The firmware can be uploaded to the M5Stick C Plus.
- The serial monitor shows logs.
- The device screen shows a fixed landscape status page.
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

On this PC, PlatformIO once auto-detected COM1, but the M5Stick was actually COM5. If upload fails with `No serial data received`, list devices and specify the M5Stick port:

```powershell
pio device list
pio run --target upload --upload-port COM5
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

If the device is on COM5, run:

```powershell
pio device monitor --port COM5
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
