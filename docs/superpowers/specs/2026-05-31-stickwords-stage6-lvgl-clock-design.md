# StickWords Stage 6 LVGL Clock Design

## Goal

Implement Stage 6 in the current `C:\Users\ASUS\Documents\M5Stick` project: migrate only the M5Stick clock page to LVGL while keeping the existing review flow, sync behavior, offline scheduling, and 3-minute idle power-off strategy intact.

`C:\Users\ASUS\Documents\M5Stick-v2` is an exploration reference only. Its bug history is useful, but its implementation details and Stage 5E two-stage idle behavior are not the product baseline.

## Design Source

The visual source is the Figma Make export in:

`C:\Users\ASUS\Downloads\M5stick界面设计`

The export README points to the original Figma Make file:

`https://www.figma.com/design/FWvmwHMzR3Yk6lGzdd0zyx/M5stick界面设计`

I attempted to use the Figma plugin against the file key, but the available screenshot tool reported that Make files are not supported. Therefore the implementation will treat the exported React source, especially `src/app/App.tsx`, as the local design source of truth.

## Scope

In scope:

- Switch firmware from `M5StickCPlus` to `M5Unified` if needed for reliable LVGL display and power APIs.
- Add LVGL 8.3 and `firmware/include/lv_conf.h`.
- Use LVGL only for `Page::Clock`.
- Keep all non-clock pages rendered with the existing immediate-mode display code.
- Render a 240x135 clock page based on the Figma Make export:
  - black screen with a subtle dark color atmosphere where feasible
  - green sync checkmark at top-left
  - red `DUE n` pill at top-right
  - large white `HH:MM` time on the left
  - red weekday plus white day number below the time
  - battery arc ring on the right with percentage text inside
- Preserve Button A behavior from the current baseline: short-press on clock enters the review/status flow.
- Preserve Button B behavior from the current baseline: no new clock-page action.
- Preserve the current 3-minute idle power-off behavior.
- Preserve setup portal, Wi-Fi sync, RTC calibration, cached offline scheduling, and pending review upload behavior.

Out of scope:

- Stage 5E two-stage idle behavior: 1 minute return to clock and 2 minutes power-off from clock.
- Migrating review/status/setup pages to LVGL.
- Chinese font rendering improvements.
- Automatic server discovery.
- Full gradient or blur effects from the web mockup if they are too expensive for the M5Stick display path.

## Architecture

LVGL will be initialized in `setup()` after `M5.begin(...)` and before the first clock render. A small partial draw buffer is enough for 240x135.

The firmware will keep the existing `Page` state machine. `render()` will continue to dispatch by page. On `Page::Clock`, `drawClockPage()` will create/update LVGL objects and run through the LVGL flush callback. Other pages will render through the existing M5 display calls.

The LVGL flush callback must use the correct display byte order for the ST7789 panel. Based on the v2 exploration, `setSwapBytes(true)` is required in the LVGL flush path to prevent red/blue color inversion.

When leaving the clock page for non-LVGL pages, the regular renderer must still fully clear and redraw the display. The design should avoid LVGL objects intercepting button behavior; button polling remains in the existing `loop()` using M5 button APIs.

## Data Mapping

- Time: RTC value converted through the existing UTC+8 display helper.
- Due count: `activeCardCount()`.
- Sync checkmark: always shown for this first Stage 6 pass once the clock page is available. Later we can make this reflect last sync state.
- Weekday/date: computed from the displayed calendar date, because RTC weekday may be unreliable.
- Battery: read from M5Unified power API and clamp to `0..100`.
- Battery color:
  - green above 50
  - yellow/orange above 20
  - red at 20 or below

## Known Pitfalls From Exploration

Avoid these v2 issues while implementing:

- Use the correct M5Unified button API casing (`wasReleaseFor` if required by M5Unified).
- Explicitly load the LVGL screen to avoid a white or inactive first screen.
- Set display byte order in the LVGL flush callback to avoid BGR565 color mistakes.
- Do not let LVGL timing interfere with Button A. Idle/power-off checks should compare against a fresh `millis()` value if LVGL handling consumes measurable time.
- Keep LVGL ticking and screen updates limited to `Page::Clock` to avoid overhead on review pages.

## Testing

Firmware source tests should assert:

- `platformio.ini` uses `M5Unified` and `lvgl/lvgl@^8.3.11`.
- `firmware/include/lv_conf.h` exists and enables the needed Montserrat fonts.
- `main.cpp` includes `M5Unified.h` and `lvgl.h`.
- LVGL display buffers and flush callback exist.
- The flush callback uses `setSwapBytes(true)`.
- Clock UI uses LVGL labels/arc and Montserrat 48 for the large time.
- `loop()` runs `lv_timer_handler()` only on `Page::Clock`.
- The current baseline idle behavior remains `kIdlePowerOffMs = 180000`; Stage 5E's `kIdleClockReturnMs` must not appear.
- `submitRating()` still does not call `uploadPendingReviews()`.

Manual validation on M5Stick:

1. Build and upload firmware.
2. Boot with Wi-Fi available.
3. Confirm the LVGL clock page appears with the Figma-derived layout.
4. Confirm colors are correct, especially red DUE badge and green battery/checkmark.
5. Press Button A on the clock page and confirm it enters the existing review/status flow.
6. Confirm review pages still render normally.
7. Leave the device idle and confirm the current 3-minute power-off behavior remains.
