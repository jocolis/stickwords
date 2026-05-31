# StickWords Device Setup Portal Design

## Goal

Make M5Stick Wi-Fi and PC server configuration editable at runtime, without editing `firmware/include/secrets.h` and reflashing firmware for normal network changes.

The first product version uses a temporary M5Stick access point and a small browser setup page.

## Current Problem

The firmware currently reads:

- `STICKWORDS_WIFI_SSID`
- `STICKWORDS_WIFI_PASSWORD`
- `STICKWORDS_SERVER_URL`

from `firmware/include/secrets.h` at compile time. This works for development, but changing Wi-Fi or the PC LAN IP requires editing the file and uploading firmware again.

## Entry Point

The confirmed manual entry point is:

- Hold Button B while powering on or resetting the M5Stick.
- The device enters setup mode and shows a setup status screen.

The firmware should also enter setup mode automatically when no saved runtime configuration exists.

If a saved configuration exists but Wi-Fi connection fails during normal boot, the firmware should keep the current behavior: show failure state and use cached cards if possible. It should not force setup mode on every temporary network failure.

## Setup Mode Behavior

In setup mode, the M5Stick starts a temporary Wi-Fi access point:

```text
StickWords-Setup
```

The screen displays:

```text
Setup mode
WiFi: StickWords-Setup
Open: 192.168.4.1
```

A phone or PC connects to `StickWords-Setup` and opens:

```text
http://192.168.4.1
```

The M5Stick serves a small HTML form with these fields:

- Wi-Fi SSID
- Wi-Fi password
- StickWords server URL, for example `http://192.168.x.x:8000`

After submit, the firmware validates and saves the configuration to ESP32 flash, shows `Saved, restarting`, then restarts.

## Runtime Configuration Storage

Runtime configuration is stored with ESP32 `Preferences`, using the existing `stickwords` namespace unless implementation finds a strong reason to split namespaces.

Suggested keys:

- `cfg_ssid`
- `cfg_pass`
- `cfg_server`

The already implemented cached cards and pending reviews remain in the same persistent store and must not be cleared by saving network configuration.

## Normal Boot Flow

The normal boot flow becomes:

1. Initialize M5Stick, IMU, serial, display, and orientation.
2. If Button B is held, enter setup mode.
3. Load pending reviews.
4. Load runtime network configuration from flash.
5. If no runtime config exists, enter setup mode.
6. Connect to Wi-Fi using runtime config.
7. If connected, upload pending reviews and fetch due cards using runtime server URL.
8. If Wi-Fi or sync fails, use the existing cached-card fallback.

The compile-time `secrets.h` can remain as a development fallback for now, but the product path is runtime configuration.

## Validation Rules

- SSID must not be empty.
- Password can be empty.
- Server URL must start with `http://`.
- Server URL should be stored without a trailing slash if one is provided, so existing API path joining stays consistent.
- Invalid form submissions show an error page and do not overwrite the previous saved config.

## Error Handling

- If access point startup fails, show `Setup failed` and log the failure over serial.
- If submitted config is invalid, keep setup mode active.
- If saved config later cannot connect, do not erase it automatically.
- User can always hold Button B at boot to re-enter setup mode and overwrite saved config.

## Security And Scope

This is a local convenience feature, not a hardened provisioning system.

First version intentionally does not include:

- HTTPS.
- Setup password.
- Captive portal DNS redirect.
- Wi-Fi network scanning.
- PC auto-discovery.
- Multiple profiles.

The setup AP should only run while the user intentionally enters setup mode or when the device has no config.

## Testing

Firmware source tests should verify:

- `WebServer` support is included.
- `WiFi.softAP` is used for setup mode.
- There are functions for loading, saving, and validating runtime config.
- `connectWifi()` no longer hardcodes `STICKWORDS_WIFI_SSID` and `STICKWORDS_WIFI_PASSWORD`.
- task and review URLs use a runtime server URL instead of hardcoded `STICKWORDS_SERVER_URL`.
- setup mode can be triggered from `setup()` when Button B is held or no config exists.

Manual real-device validation:

1. Upload firmware.
2. Hold Button B while rebooting.
3. Confirm the screen shows setup mode.
4. Connect a PC or phone to `StickWords-Setup`.
5. Open `http://192.168.4.1`.
6. Save Wi-Fi and server settings.
7. Confirm the device restarts and syncs with the PC backend.
8. Reboot normally and confirm it uses saved config without editing `secrets.h`.

## Documentation Updates

Update handoff and dev log after implementation:

- Replace the current `secrets.h`-first instructions with setup portal instructions.
- Keep `secrets.example.h` documented as a developer fallback.
- Record the real-device setup validation logs.
