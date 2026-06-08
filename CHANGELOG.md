# Changelog

## v0.1.0 - 2026-06-09

Initial public release snapshot for StickWords.

### Added

- PC backend with CSV vocabulary storage in `data/vocab.csv`.
- Web admin page for adding, importing, searching, and suspending words.
- Optional PC Quick Add helper with manual entry and DeepSeek-powered definition generation.
- M5Stick C Plus firmware built with PlatformIO and Arduino.
- M5Stick setup portal for 2.4 GHz Wi-Fi and PC server URL configuration.
- Wi-Fi sync API for downloading review cards and uploading review events.
- Local pending-review queue for interrupted or offline review sessions.
- Offline fallback using cached due cards and RTC-backed scheduling.
- BM8563 RTC calibration from backend sync timestamps.
- LVGL clock page with live time, due count, battery arc, sync-success indicator, rotation support, and 7-minute idle power-off.
- LVGL review pages for word, meaning, example, rating, and review-complete states.
- Button A/Button B review flow, previous-card re-rating, and double-shake `good` rating.
- English word-boundary pagination for meaning and example pages.

### Changed

- Expanded the ESP32 app partition to leave headroom for LVGL UI work.
- Normalized smart punctuation in device payloads so curly quotes and long dashes do not show as missing glyph boxes.
- Increased word-page font sizes while keeping very long words smaller to reduce clipping.
- Kept generated Host Grotesk font experiments out of the public release path after real-device black-screen issues.

### Known Limits

- Firmware uses plain HTTP on the local network.
- M5Stick and PC must be on the same reachable LAN.
- Setup portal has no password and should only be enabled intentionally on trusted networks.
- Chinese rendering on the M5Stick is not implemented in this release.
- Automatic PC/backend discovery is not implemented; users still copy the LAN server URL from the PC admin page.
- Offline review is limited to the cached review package, not the full vocabulary database.
- No multi-deck or multi-user support.
