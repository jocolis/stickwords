from pathlib import Path
import json
import re
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
FIRMWARE_MAIN = ROOT / "firmware" / "src" / "main.cpp"


def firmware_source():
    return FIRMWARE_MAIN.read_text(encoding="utf-8")


def firmware_function_body(source, function_name):
    match = re.search(rf"\b{re.escape(function_name)}\s*\([^)]*\)\s*\{{", source)
    if match is None:
        raise AssertionError(f"Missing firmware function {function_name}")

    cursor = match.end()
    depth = 1
    while cursor < len(source) and depth > 0:
        char = source[cursor]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        cursor += 1
    if depth != 0:
        raise AssertionError(f"Could not parse firmware function {function_name}")
    return source[match.end(): cursor - 1]


def parse_json_string_at(source, quote_index):
    value = ""
    escaped = False
    for current in source[quote_index + 1:]:
        if escaped:
            if current == "n":
                value += "\n"
            elif current == "r":
                value += "\r"
            elif current == "t":
                value += "\t"
            else:
                value += current
            escaped = False
            continue
        if current == "\\":
            escaped = True
            continue
        if current == '"':
            return value
        value += current
    return ""


def json_string_value(object_text, key):
    marker = f'"{key}":'
    marker_index = object_text.find(marker)
    if marker_index < 0:
        return ""
    start = object_text.find('"', marker_index + len(marker))
    if start < 0:
        return ""
    return parse_json_string_at(object_text, start)


def find_json_array_end(body, array_start):
    in_string = False
    escaped = False
    depth = 0
    for index in range(array_start, len(body)):
        current = body[index]
        if in_string:
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == '"':
                in_string = False
            continue
        if current == '"':
            in_string = True
        elif current == "[":
            depth += 1
        elif current == "]":
            depth -= 1
            if depth == 0:
                return index
    return -1


def find_json_object_end(body, object_start, limit):
    in_string = False
    escaped = False
    depth = 0
    for index in range(object_start, min(limit, len(body) - 1) + 1):
        current = body[index]
        if in_string:
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == '"':
                in_string = False
            continue
        if current == '"':
            in_string = True
        elif current == "{":
            depth += 1
        elif current == "}":
            depth -= 1
            if depth == 0:
                return index
    return -1


def parse_device_tasks_json(body):
    server_generated_at = json_string_value(body, "generated_at")
    array_start = body.find('"tasks"')
    array_start = body.find("[", array_start)
    if array_start < 0:
        return False, server_generated_at, []
    array_end = find_json_array_end(body, array_start)
    if array_end < 0:
        return False, server_generated_at, []

    cards = []
    cursor = array_start
    while len(cards) < 20:
        object_start = body.find("{", cursor)
        if object_start < 0 or object_start > array_end:
            break
        object_end = find_json_object_end(body, object_start, array_end)
        if object_end < 0 or object_end > array_end:
            break

        object_text = body[object_start: object_end + 1]
        card = {
            "id": json_string_value(object_text, "id"),
            "word": json_string_value(object_text, "word"),
            "meaning": json_string_value(object_text, "meaning"),
            "example": json_string_value(object_text, "example"),
        }
        if card["id"] and card["word"]:
            cards.append(card)
        cursor = object_end + 1
    return True, server_generated_at, cards


def compact_json_markers(body):
    compact = ""
    in_string = False
    escaped = False
    for current in body:
        if in_string:
            compact += current
            if escaped:
                escaped = False
            elif current == "\\":
                escaped = True
            elif current == '"':
                in_string = False
            continue
        if current == '"':
            in_string = True
            compact += current
        elif current not in " \n\r\t":
            compact += current
    return compact


def json_int_value(compact_body, key):
    marker = f'"{key}":'
    marker_index = compact_body.find(marker)
    if marker_index < 0:
        return -1
    cursor = marker_index + len(marker)
    end = cursor
    while end < len(compact_body) and compact_body[end].isdigit():
        end += 1
    if end == cursor:
        return -1
    return int(compact_body[cursor:end])


def upload_response_accepted(response, attempted_reviews):
    compact = compact_json_markers(response)
    if '"failed":0' not in compact:
        return False
    accepted = json_int_value(compact, "accepted")
    skipped = json_int_value(compact, "skipped_duplicate")
    if accepted < 0 or skipped < 0:
        return False
    return accepted + skipped >= attempted_reviews


def firmware_source_uses_calendar_rtc_validation():
    source = firmware_source()
    return (
        "isLeapYear(" in source and
        "daysInMonth(" in source and
        "timestamp.date <= daysInMonth" in source
    )


def firmware_rtc_days_in_month(year, month):
    if not firmware_source_uses_calendar_rtc_validation():
        return 31
    if month == 2:
        if year % 400 == 0 or (year % 4 == 0 and year % 100 != 0):
            return 29
        return 28
    if month in (4, 6, 9, 11):
        return 30
    return 31


def firmware_parse_utc_timestamp(value):
    if len(value) != 20:
        return None
    if (
        value[4] != "-" or value[7] != "-" or value[10] != "T" or
        value[13] != ":" or value[16] != ":" or value[19] != "Z"
    ):
        return None

    numeric_slices = (
        value[0:2], value[2:4], value[5:7], value[8:10],
        value[11:13], value[14:16], value[17:19],
    )
    if any(not part.isdigit() for part in numeric_slices):
        return None

    year = int(value[0:2]) * 100 + int(value[2:4])
    month = int(value[5:7])
    date = int(value[8:10])
    hour = int(value[11:13])
    minute = int(value[14:16])
    second = int(value[17:19])
    if year < 2024 or month < 1 or month > 12:
        return None
    if date < 1 or date > firmware_rtc_days_in_month(year, month):
        return None
    if hour > 23 or minute > 59 or second > 59:
        return None
    return {
        "year": year,
        "month": month,
        "date": date,
        "hour": hour,
        "minute": minute,
        "second": second,
        "weekDay": 0,
    }


def firmware_clock_display_timestamp(timestamp):
    display = dict(timestamp)
    display["hour"] += 8
    while display["hour"] >= 24:
        display["hour"] -= 24
        display["date"] += 1
        month_days = firmware_rtc_days_in_month(display["year"], display["month"])
        if display["date"] <= month_days:
            continue
        display["date"] = 1
        display["month"] += 1
        if display["month"] <= 12:
            continue
        display["month"] = 1
        display["year"] += 1
    return display


class PendingReviewQueue:
    def __init__(self):
        self.items = []
        self.sequence = 0

    def queue(self, word_id, rating, reviewed_at="1970-01-01T00:00:00Z"):
        self.sequence += 1
        self.items.append({
            "wordId": word_id,
            "rating": rating,
            "reviewedAt": reviewed_at,
            "sequence": self.sequence,
            "uploaded": False,
        })

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


class FirmwareProjectTests(unittest.TestCase):
    def test_platformio_config_targets_m5stick_c_plus_check(self):
        config = (ROOT / "firmware" / "platformio.ini").read_text(encoding="utf-8")

        self.assertIn("[env:m5stick-c]", config)
        self.assertIn("platform = espressif32", config)
        self.assertIn("board = m5stick-c", config)
        self.assertIn("framework = arduino", config)
        self.assertIn("monitor_speed = 115200", config)

    def test_firmware_source_contains_stage3b_review_ui(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("StickWords Stage 4 boot", source)
        self.assertIn("enum class Page", source)
        self.assertIn("Word", source)
        self.assertIn("Meaning", source)
        self.assertIn("Example", source)
        self.assertIn("Rating", source)
        self.assertIn("Status", source)
        self.assertIn("Done", source)
        self.assertIn("struct Card", source)
        self.assertIn("struct ReviewResult", source)
        self.assertIn("forgot", source)
        self.assertIn("hard", source)
        self.assertIn("good", source)
        self.assertIn("handleButtonAShortPress", source)
        self.assertIn("handleButtonALongPress", source)
        self.assertIn("handleButtonBShortPress", source)
        self.assertIn("submitRating", source)
        self.assertIn("tryReRatePrevious", source)
        self.assertIn("Review saved word=", source)
        self.assertIn("Review overwritten word=", source)
        self.assertIn("M5.Display.setRotation(currentRotation)", source)
        self.assertIn("cfg.internal_imu = true", source)
        self.assertIn("M5.Imu.getAccel", source)

    def test_stage6_platformio_uses_m5unified_and_lvgl(self):
        config = (ROOT / "firmware" / "platformio.ini").read_text(encoding="utf-8")
        lv_conf = ROOT / "firmware" / "include" / "lv_conf.h"

        self.assertIn("m5stack/M5Unified", config)
        self.assertIn("lvgl/lvgl@^8.3.11", config)
        self.assertIn("-D LV_CONF_INCLUDE_SIMPLE", config)
        self.assertNotIn("m5stack/M5StickCPlus", config)
        self.assertTrue(lv_conf.exists())
        text = lv_conf.read_text(encoding="utf-8")
        self.assertIn("#define LV_CONF_H", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_12 1", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_14 1", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_18 1", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_24 1", text)
        self.assertIn("#define LV_FONT_MONTSERRAT_48 1", text)
        self.assertIn("#define LV_USE_ARC 1", text)
        self.assertIn("#define LV_USE_LABEL 1", text)
        self.assertIn("#define LV_USE_BAR 0", text)
        self.assertIn("#define LV_USE_BTN 0", text)
        self.assertIn("#define LV_USE_ANIMIMG 0", text)
        self.assertIn("#define LV_USE_CALENDAR 0", text)
        self.assertIn("#define LV_USE_CALENDAR_HEADER_ARROW 0", text)
        self.assertIn("#define LV_USE_CHART 0", text)
        self.assertIn("#define LV_USE_FRAGMENT 0", text)
        self.assertIn("#define LV_USE_GRIDNAV 0", text)
        self.assertIn("#define LV_USE_IMGFONT 0", text)
        self.assertIn("#define LV_USE_MSG 0", text)
        self.assertIn("#define LV_USE_SNAPSHOT 0", text)
        self.assertIn("#define LV_USE_THEME_DEFAULT 0", text)
        self.assertIn("#define LV_USE_FLEX 0", text)
        self.assertIn("#define LV_USE_GRID 0", text)
        self.assertIn("#define LV_USE_GIF 0", text)
        self.assertIn("#define LV_USE_PNG 0", text)
        self.assertIn("#define LV_USE_QRCODE 0", text)

    def test_stage6_clock_page_uses_lvgl_without_stage5e_idle(self):
        source = firmware_source()
        setup_body = firmware_function_body(source, "setup")
        loop_body = firmware_function_body(source, "loop")
        render_body = firmware_function_body(source, "render")
        flush_body = firmware_function_body(source, "lvglFlushCb")
        clock_body = firmware_function_body(source, "drawClockPage")

        self.assertIn("#include <M5Unified.h>", source)
        self.assertIn("#include <src/core/lv_refr.h>", source)
        self.assertIn("#include <src/widgets/lv_arc.h>", source)
        self.assertIn("#include <src/widgets/lv_label.h>", source)
        self.assertNotIn("#include <lvgl.h>", source)
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
        self.assertIn("clockColonOpacity", source)
        self.assertIn("constexpr uint32_t kClockRefreshMs = 50", source)
        self.assertIn("constexpr uint32_t kClockColonPulseMs = 2000", source)
        self.assertIn("constexpr lv_opa_t kClockColonMinOpacity = 0", source)
        self.assertIn("constexpr lv_opa_t kClockColonMaxOpacity = 255", source)
        self.assertIn("DUE", source)
        self.assertIn("lv_init()", setup_body)
        self.assertIn("lv_disp_drv_register", setup_body)
        self.assertIn("if (currentPage == Page::Clock)", loop_body)
        self.assertIn("lv_timer_handler()", loop_body)
        self.assertIn("drawClockPage()", render_body)
        self.assertIn("updateClockUI()", clock_body)
        self.assertIn("constexpr uint32_t kIdlePowerOffMs = 420000", source)
        self.assertIn("constexpr uint32_t kClockIdlePowerOffMs = 420000", source)
        self.assertNotIn("kIdleClockReturnMs", source)

    def test_stage6_clock_render_does_not_clear_m5gfx_before_lvgl_refresh(self):
        source = firmware_source()
        render_body = firmware_function_body(source, "render")

        self.assertIn("if (currentPage == Page::Clock)", render_body)
        self.assertIn("drawClockPage()", render_body)
        self.assertIn("lv_obj_invalidate(clockScr)", source)
        self.assertIn("lv_refr_now(nullptr)", source)
        self.assertIn("lv_obj_set_style_bg_opa(clockScr, LV_OPA_COVER, 0)", source)
        self.assertIn("lv_obj_remove_style_all(clockCheckCircle)", source)
        self.assertIn("lv_obj_set_style_bg_opa(clockCheckCircle, LV_OPA_TRANSP, 0)", source)
        self.assertIn("lv_obj_set_style_border_color(clockCheckCircle, lv_color_hex(0x22C55E), 0)", source)
        self.assertIn("lv_obj_set_style_border_width(clockCheckCircle, 2, 0)", source)
        self.assertIn("lv_obj_set_style_text_color(clockCheckMark, lv_color_hex(0x22C55E), 0)", source)
        self.assertIn("lv_obj_set_style_bg_opa(clockDueBg, LV_OPA_COVER, 0)", source)
        self.assertIn("lv_obj_set_style_text_opa(clockColon", source)
        self.assertIn("lv_obj_set_pos(clockColon, 74, 34)", source)
        self.assertIn("lv_obj_set_pos(clockColonBold, 75, 34)", source)
        self.assertIn("lv_obj_set_pos(clockMinute, 95, 34)", source)
        self.assertIn("lv_obj_set_pos(clockMinuteBold, 96, 34)", source)
        self.assertIn("lv_obj_set_pos(clockTimeBold, 11, 34)", source)
        self.assertIn("lv_obj_set_pos(clockDayLabelBold, 11, 90)", source)
        self.assertIn("lv_obj_set_style_text_opa(clockColonBold, colonOpacity, 0)", source)
        self.assertIn("lv_obj_align_to(clockBatLabel, clockBatArc, LV_ALIGN_CENTER, 0, 0)", source)
        self.assertIn("lv_obj_align(clockBatArc, LV_ALIGN_RIGHT_MID, -12, 8)", source)
        self.assertIn("lv_obj_center(clockDueText)", source)
        self.assertIn("lv_obj_set_size(clockDueBg, 70, 22)", source)
        self.assertIn('"DUE %u"', source)
        self.assertNotIn("lv_obj_del(clockScr)", source)
        self.assertLess(
            render_body.index("if (currentPage == Page::Clock)"),
            render_body.index("M5.Display.fillScreen(BLACK)"),
        )

    def test_stage4_firmware_does_not_fallback_to_sample_cards(self):
        source = firmware_source()
        active_body = firmware_function_body(source, "activeCardCount")
        current_body = firmware_function_body(source, "currentCard")
        fetch_body = firmware_function_body(source, "fetchDeviceTasks")
        wifi_body = firmware_function_body(source, "connectWifi")

        self.assertNotIn("kCards[]", source)
        self.assertNotIn("using samples", source)
        self.assertNotIn("abandon", source)
        self.assertNotIn("benefit", source)
        self.assertNotIn("curious", source)
        self.assertNotIn("syncedCardCount == 0", active_body)
        self.assertNotIn("syncedCardCount == 0", current_body)
        self.assertIn("return syncedCardCount", active_body)
        self.assertIn("syncedCards[currentCardIndex].word", current_body)
        self.assertNotIn("kCards", current_body)
        self.assertIn("setStatusPage(", fetch_body)
        self.assertIn('drawStatusMessage("Sync failed", "check server")', fetch_body)
        self.assertIn('drawStatusMessage("WiFi failed", "check network")', wifi_body)
        self.assertIn("setStatusPage(", wifi_body)

    def test_stage3b_screen_removes_old_headers_and_button_hints(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertNotIn('M5.Lcd.println("StickWords")', source)
        self.assertNotIn("A: next", source)
        self.assertNotIn("A: full example", source)
        self.assertNotIn("A: rating", source)
        self.assertNotIn("A: change", source)
        self.assertNotIn("A: restart", source)
        self.assertNotIn("B: back", source)
        self.assertNotIn("B: re-rate", source)
        self.assertNotIn("Hold A: save", source)
        self.assertIn("StickWords Stage 4 boot", source)

    def test_stage3b_uses_single_flow_content_paging(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("size_t contentPageStart", source)
        self.assertIn("findNextContentPageStart(", source)
        self.assertIn("findPreviousContentPageStart(", source)
        self.assertIn("drawWrappedContentPage(", source)
        self.assertIn("hasMoreContentPage(", source)
        self.assertIn("Page::Meaning", source)
        self.assertIn("Page::Example", source)
        self.assertNotIn("MeaningSummary", source)
        self.assertNotIn("FullExample", source)
        self.assertNotIn("M5.Lcd.println(card.word);", source)
        self.assertNotIn('M5.Lcd.print("ex: ");', source)

    def test_content_pages_use_most_of_landscape_screen(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("constexpr int16_t kContentMaxY", source)
        self.assertIn("size_t nextTokenEnd(", source)
        self.assertIn("size_t findNextContentPageStart(", source)
        self.assertIn("size_t findPreviousContentPageStart(", source)
        self.assertIn("void drawWrappedContentPage(", source)
        self.assertNotIn("kContentPageChars", source)

    def test_content_pages_wrap_at_word_boundaries(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")
        draw_body = firmware_function_body(source, "drawWrappedContentPage")
        next_body = firmware_function_body(source, "findNextContentPageStart")

        self.assertIn("tokenEnd = nextTokenEnd", draw_body)
        self.assertIn("textWidthSlice(text, tokenStart, tokenEnd)", draw_body)
        self.assertIn("cursorX != kContentX", draw_body)
        self.assertIn("cursorY + kContentLineHeight > kContentMaxY", draw_body)
        self.assertIn("lastDrawnEnd", draw_body)
        self.assertIn("findNextContentPageStart", draw_body)
        self.assertIn("skipBreakChars(text, start)", next_body)
        self.assertIn("nextTokenEnd(text, index)", next_body)
        self.assertIn("lastFitEnd", next_body)

    def test_stage3c_uses_stable_imu_landscape_auto_rotation(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("constexpr float kOrientationThreshold", source)
        self.assertIn("constexpr uint32_t kOrientationStableMs", source)
        self.assertIn("uint8_t currentRotation = 1", source)
        self.assertIn("uint8_t pendingRotation = 1", source)
        self.assertIn("void readImu()", source)
        self.assertIn("uint8_t detectLandscapeRotation()", source)
        self.assertIn("void updateAutoRotation(uint32_t now)", source)
        self.assertIn("M5.Display.setRotation(currentRotation)", source)
        self.assertIn('Serial.printf("Orientation rotation=%u', source)
        self.assertIn("needsRender = true", source)

    def test_stage3c_rating_page_supports_double_shake_good(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("constexpr float kShakeThreshold", source)
        self.assertIn("constexpr uint32_t kShakeWindowMs", source)
        self.assertIn("constexpr uint32_t kShakeCooldownMs", source)
        self.assertIn("uint8_t shakeCount", source)
        self.assertIn("float accelMagnitude()", source)
        self.assertIn("void resetShakeDetection()", source)
        self.assertIn("void updateShakeGood(uint32_t now)", source)
        self.assertIn("currentPage != Page::Rating", source)
        self.assertIn("selectedRating = Rating::Good", source)
        self.assertIn('Serial.printf("Shake good word=%s', source)
        self.assertIn("submitRating()", source)

    def test_platformio_build_output_is_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("firmware/.pio/", ignore)
        self.assertIn("firmware/.vscode/.browse.c_cpp.db*", ignore)

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

        ignored = subprocess.run(
            ["git", "check-ignore", "firmware/include/secrets.h"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ignored.returncode, 0, ignored.stderr)

        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "firmware/include/secrets.h"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(tracked.returncode, 0, tracked.stdout)

    def test_stage4_firmware_has_wifi_http_sync_storage(self):
        source = firmware_source()

        self.assertIn("#include <WiFi.h>", source)
        self.assertIn("#include <HTTPClient.h>", source)
        self.assertIn('__has_include("secrets.h")', source)
        self.assertIn('#include "secrets.h"', source)
        self.assertIn("copy firmware/include/secrets.example.h", source)
        self.assertIn("edit Wi-Fi and PC URL", source)
        self.assertIn("constexpr size_t kMaxSyncedCards", source)
        self.assertIn("constexpr size_t kMaxPendingReviews", source)
        self.assertIn("struct DeviceCard", source)
        self.assertIn("struct PendingReview", source)
        self.assertIn("ReviewResult reviewResults[kMaxSyncedCards]", source)
        self.assertIn("DeviceCard syncedCards[kMaxSyncedCards]", source)
        self.assertIn("PendingReview pendingReviews[kMaxPendingReviews]", source)
        self.assertIn("syncedCardCount > kMaxSyncedCards", source)
        self.assertIn("connectWifi()", source)
        self.assertIn("fetchDeviceTasks()", source)
        self.assertIn("uploadPendingReviews()", source)
        self.assertIn("STICKWORDS_SERVER_URL", source)
        self.assertIn("WiFi...", source)
        self.assertIn("Sync failed", source)
        self.assertIn("HTTPClient http", source)
        self.assertIn('/api/device/tasks?limit=', source)
        self.assertIn('/api/device/reviews', source)
        self.assertIn("http.GET()", source)
        self.assertIn("http.POST(", source)
        self.assertIn("parseDeviceTasksJson(", source)
        self.assertIn("buildPendingReviewsJson(", source)
        self.assertIn("markPendingReviewsUploaded()", source)
        self.assertNotIn("2026-05-24T00:00:00Z", source)
        self.assertIn("serverGeneratedAt", source)
        self.assertIn("esp_random", source)
        self.assertIn("reviewSequence", source)
        self.assertIn("uploadResponseAccepted(", source)
        self.assertNotIn("replace pending review", source)
        self.assertIn("char reviewedAt[kMaxTimestampLength]", source)
        self.assertIn("parseJsonStringAt(", source)
        self.assertIn("escaped = true", source)

    def test_stage4_firmware_has_setup_portal_runtime_config(self):
        source = firmware_source()
        setup_body = firmware_function_body(source, "setup")
        connect_body = firmware_function_body(source, "connectWifi")
        fetch_body = firmware_function_body(source, "fetchDeviceTasks")
        upload_body = firmware_function_body(source, "uploadPendingReviews")
        validate_body = firmware_function_body(source, "validateRuntimeConfig")
        normalize_body = firmware_function_body(source, "normalizeServerUrl")
        portal_body = firmware_function_body(source, "startSetupPortal")
        save_body = firmware_function_body(source, "handleSetupSave")
        html_body = firmware_function_body(source, "setupPageHtml")
        escape_body = firmware_function_body(source, "htmlEscape")
        loop_body = firmware_function_body(source, "loop")

        self.assertIn("#include <WebServer.h>", source)
        self.assertIn("constexpr size_t kMaxSsidLength", source)
        self.assertIn("constexpr size_t kMaxPasswordLength", source)
        self.assertIn("constexpr size_t kMaxServerUrlLength", source)
        self.assertIn("struct RuntimeConfig", source)
        self.assertIn("char ssid[kMaxSsidLength]", source)
        self.assertIn("char password[kMaxPasswordLength]", source)
        self.assertIn("char serverUrl[kMaxServerUrlLength]", source)
        self.assertIn("bool valid", source)
        self.assertIn("RuntimeConfig runtimeConfig", source)
        self.assertIn("loadRuntimeConfig()", source)
        self.assertIn("saveRuntimeConfig(", source)
        self.assertIn("validateRuntimeConfig(", source)
        self.assertIn("normalizeServerUrl(", source)
        self.assertIn("startSetupPortal()", source)
        self.assertIn("handleSetupRoot()", source)
        self.assertIn("handleSetupSave()", source)
        self.assertIn("setupPageHtml(", source)
        self.assertIn("handleSetupPortalLoop()", source)
        self.assertIn("WebServer setupServer(80)", source)
        self.assertIn('WiFi.softAP("StickWords-Setup")', source)
        self.assertIn("ESP.restart()", source)
        self.assertIn('storage.getString("cfg_ssid"', source)
        self.assertIn('storage.putString("cfg_ssid"', source)
        self.assertIn('storage.getString("cfg_pass"', source)
        self.assertIn('storage.putString("cfg_pass"', source)
        self.assertIn('storage.getString("cfg_server"', source)
        self.assertIn('storage.putString("cfg_server"', source)
        self.assertIn("runtimeConfig.valid", source)

        self.assertIn("M5.BtnB.isPressed()", setup_body)
        self.assertIn("loadRuntimeConfig()", setup_body)
        self.assertIn("startSetupPortal()", setup_body)
        self.assertIn("runtimeConfig.ssid", connect_body)
        self.assertIn("runtimeConfig.password", connect_body)
        self.assertIn("runtimeConfig.serverUrl", source)
        self.assertNotIn("STICKWORDS_WIFI_SSID", connect_body)
        self.assertNotIn("STICKWORDS_WIFI_PASSWORD", connect_body)
        self.assertIn("runtimeServerUrl()", fetch_body)
        self.assertIn("runtimeServerUrl()", upload_body)
        self.assertNotIn("STICKWORDS_SERVER_URL", fetch_body)
        self.assertNotIn("STICKWORDS_SERVER_URL", upload_body)
        self.assertIn('std::strlen(config.serverUrl) > std::strlen("http://")', validate_body)
        self.assertIn('std::strcmp(normalized.c_str(), "http://") != 0', normalize_body)
        self.assertIn('if (!WiFi.softAP("StickWords-Setup"))', portal_body)
        self.assertIn('Serial.println("Setup portal AP failed")', portal_body)
        self.assertIn('setStatusPage("Setup failed", "check serial")', portal_body)
        self.assertIn('drawStatusMessage("Setup failed", "check serial")', portal_body)
        self.assertIn('"WiFi: StickWords-Setup"', portal_body)
        self.assertIn('"Open: 192.168.4.1"', portal_body)
        self.assertIn('setStatusPage("Setup mode", "WiFi: StickWords-Setup", "Open: 192.168.4.1")', portal_body)
        self.assertIn('drawStatusMessage("Setup mode", "WiFi: StickWords-Setup", "Open: 192.168.4.1")', portal_body)
        self.assertIn("current == '\\''", escape_body)
        self.assertIn("&#39;", escape_body)
        self.assertNotIn("runtimeConfig.password", html_body)
        self.assertIn("leave blank to keep current password", html_body)
        self.assertIn('"SSID is required and server URL must start with http://"', source)
        self.assertIn('setupServer.send(400, "text/html"', save_body)
        self.assertIn('setupServer.send(200, "text/html"', save_body)
        self.assertIn("submitted.password[0] == '\\0' && runtimeConfig.valid", save_body)
        self.assertIn('drawStatusMessage("Saved", "restarting")', save_body)
        self.assertIn("handleSetupPortalLoop()", loop_body)
        self.assertNotIn("handleSetupPortalClient", source)

    def test_stage4_setup_portal_uses_captive_dns_redirects(self):
        source = firmware_source()
        portal_body = firmware_function_body(source, "startSetupPortal")
        loop_body = firmware_function_body(source, "handleSetupPortalLoop")
        captive_body = firmware_function_body(source, "handleCaptivePortal")

        self.assertIn("#include <DNSServer.h>", source)
        self.assertIn("DNSServer dnsServer", source)
        self.assertIn("dnsServer.start(53", portal_body)
        self.assertIn('"*"', portal_body)
        self.assertIn("WiFi.softAPIP()", portal_body)
        self.assertIn('setupServer.on("/generate_204"', source)
        self.assertIn('setupServer.on("/gen_204"', source)
        self.assertIn('setupServer.on("/hotspot-detect.html"', source)
        self.assertIn('setupServer.on("/fwlink"', source)
        self.assertIn("setupServer.onNotFound(handleCaptivePortal)", portal_body)
        self.assertIn("dnsServer.processNextRequest()", loop_body)
        self.assertIn('setupServer.sendHeader("Location"', captive_body)
        self.assertIn("http://192.168.4.1/", captive_body)
        self.assertIn("setupServer.send(302", captive_body)

    def test_stage4_firmware_persists_cached_tasks_and_pending_reviews(self):
        source = firmware_source()
        setup_body = firmware_function_body(source, "setup")
        fetch_body = firmware_function_body(source, "fetchDeviceTasks")
        queue_body = firmware_function_body(source, "queuePendingReview")
        mark_body = firmware_function_body(source, "markPendingReviewsUploaded")

        self.assertIn("#include <Preferences.h>", source)
        self.assertIn("Preferences storage", source)
        self.assertIn("saveCachedTasks()", source)
        self.assertIn("loadCachedTasks()", source)
        self.assertIn("clearCachedTasks()", source)
        self.assertIn("savePendingReviews()", source)
        self.assertIn("loadPendingReviews()", source)
        self.assertIn("clearPendingReviews()", source)
        self.assertIn('storage.begin("stickwords"', source)
        self.assertIn('cacheStorage.putBytes("cards"', source)
        self.assertIn('prefs.getBytes("cards"', source)
        self.assertIn('storage.putBytes("pending"', source)
        self.assertIn('storage.getBytes("pending"', source)

        self.assertIn("loadPendingReviews()", setup_body)
        self.assertIn("loadCachedTasks()", setup_body)
        self.assertIn("saveCachedTasks()", fetch_body)
        self.assertIn("clearCachedTasks()", fetch_body)
        self.assertIn("savePendingReviews()", queue_body)
        self.assertIn("clearPendingReviews()", mark_body)

    def test_stage4_review_timestamp_uses_generated_at_or_fallback(self):
        source = firmware_source()
        parse_body = firmware_function_body(source, "parseDeviceTasksJson")
        timestamp_body = firmware_function_body(source, "currentReviewTimestamp")
        queue_body = firmware_function_body(source, "queuePendingReview")
        reviews_body = firmware_function_body(source, "buildPendingReviewsJson")

        self.assertNotIn("2026-05-24T00:00:00Z", source)
        self.assertIn('jsonStringValue(body, "generated_at")', parse_body)
        self.assertIn("serverGeneratedAt[0] != '\\0'", timestamp_body)
        self.assertIn("return String(serverGeneratedAt)", timestamp_body)
        self.assertIn("1970-01-01T00:00:00Z", timestamp_body)
        self.assertIn("currentReviewTimestamp()", queue_body)

        ok, generated_at, cards = parse_device_tasks_json(
            '{"generated_at":"2026-05-24T09:30:00Z",'
            '"tasks":[{"id":"w1","word":"alpha","meaning":"first","example":"one"}]}'
        )
        self.assertTrue(ok)
        self.assertEqual(generated_at, "2026-05-24T09:30:00Z")
        self.assertEqual(cards[0]["word"], "alpha")

        queue = PendingReviewQueue()
        queue.queue("w1", "good", generated_at)
        synced = json.loads(queue.build_json(0x1A2B3C, generated_at))
        fallback = json.loads(queue.build_json(0x1A2B3C, ""))
        self.assertEqual(synced["reviews"][0]["reviewed_at"], "2026-05-24T09:30:00Z")
        self.assertEqual(fallback["reviews"][0]["reviewed_at"], "2026-05-24T09:30:00Z")

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
        self.assertIn("m5::rtc_time_t", source)
        self.assertIn("m5::rtc_date_t", source)
        self.assertIn("M5.Rtc.getTime", source)
        self.assertIn("M5.Rtc.getDate", source)
        self.assertIn("M5.Rtc.setTime", source)
        self.assertIn("M5.Rtc.setDate", source)

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

    def test_stage5a_rtc_timestamp_parser_rejects_impossible_calendar_dates(self):
        self.assertEqual(
            firmware_parse_utc_timestamp("2026-05-24T09:30:00Z"),
            {
                "year": 2026,
                "month": 5,
                "date": 24,
                "hour": 9,
                "minute": 30,
                "second": 0,
                "weekDay": 0,
            },
        )
        self.assertIsNone(firmware_parse_utc_timestamp("2026-02-31T10:00:00Z"))
        self.assertIsNone(firmware_parse_utc_timestamp("2026-04-31T10:00:00Z"))
        self.assertIsNone(firmware_parse_utc_timestamp("2025-02-29T10:00:00Z"))
        self.assertEqual(
            firmware_parse_utc_timestamp("2024-02-29T10:00:00Z")["date"],
            29,
        )
        self.assertIsNone(firmware_parse_utc_timestamp("2026-05-24T24:30:00Z"))
        self.assertIsNone(firmware_parse_utc_timestamp("2026-05-24T09:60:00Z"))
        self.assertIsNone(firmware_parse_utc_timestamp("2026-05-24T09:30:60Z"))
        self.assertIsNone(firmware_parse_utc_timestamp("2026-05-24T09:30:00"))

    def test_stage5b_boot_shows_clock_page_before_review_flow(self):
        source = firmware_source()
        setup_body = firmware_function_body(source, "setup")
        render_body = firmware_function_body(source, "render")
        short_press_body = firmware_function_body(source, "handleButtonAShortPress")
        loop_body = firmware_function_body(source, "loop")
        draw_clock_body = firmware_function_body(source, "drawClockPage")
        clock_ui_body = firmware_function_body(source, "updateClockUI")
        local_body = firmware_function_body(source, "toClockDisplayTimestamp")
        show_clock_body = firmware_function_body(source, "showClockPage")
        update_clock_body = firmware_function_body(source, "updateClockPage")

        self.assertIn("Clock", source)
        self.assertIn("Page clockExitPage", source)
        self.assertIn("uint32_t lastClockRefreshAt", source)
        self.assertIn("drawClockPage()", source)
        self.assertIn("showClockPage()", source)
        self.assertIn("updateClockPage(now)", source)
        self.assertIn("constexpr uint8_t kClockDisplayUtcOffsetHours = 8", source)
        self.assertIn("toClockDisplayTimestamp(", source)
        self.assertIn("case Page::Clock", render_body)
        self.assertIn("drawClockPage()", render_body)
        self.assertIn("case Page::Clock", short_press_body)
        self.assertIn("setPage(clockExitPage)", short_press_body)
        self.assertIn("showClockPage()", setup_body)
        self.assertIn("startSetupPortal()", setup_body)
        self.assertLess(setup_body.index("startSetupPortal()"), setup_body.rindex("showClockPage()"))
        self.assertIn("currentPage == Page::Clock", update_clock_body)
        self.assertIn("now - lastClockRefreshAt", update_clock_body)
        self.assertIn(">= kClockRefreshMs", update_clock_body)
        self.assertIn("needsRender = true", update_clock_body)
        self.assertIn("updateClockPage(now)", loop_body)
        self.assertIn("updateClockUI()", draw_clock_body)
        self.assertIn("RTC invalid", clock_ui_body)
        self.assertIn("Sync needed", clock_ui_body)
        self.assertIn("currentClockTimestamp()", clock_ui_body)
        self.assertIn("toClockDisplayTimestamp(timestamp)", clock_ui_body)
        self.assertIn("syncClockBase(", source)
        self.assertIn("addSecondsToTimestamp", source)
        self.assertIn("kClockDisplayUtcOffsetHours", local_body)
        self.assertIn("while (display.hour >= 24)", local_body)
        self.assertIn("daysInMonth(display.year, display.month)", local_body)
        self.assertIn("%04u-%02u-%02u", source)
        self.assertIn("%02u:%02u:%02u", source)

    def test_stage5b_clock_display_uses_utc_plus_8_without_changing_rtc_parse(self):
        evening = firmware_parse_utc_timestamp("2026-05-24T20:30:00Z")
        self.assertEqual(
            firmware_clock_display_timestamp(evening),
            {
                "year": 2026,
                "month": 5,
                "date": 25,
                "hour": 4,
                "minute": 30,
                "second": 0,
                "weekDay": 0,
            },
        )
        month_end = firmware_parse_utc_timestamp("2026-04-30T18:00:00Z")
        self.assertEqual(firmware_clock_display_timestamp(month_end)["month"], 5)
        self.assertEqual(firmware_clock_display_timestamp(month_end)["date"], 1)
        year_end = firmware_parse_utc_timestamp("2026-12-31T20:00:00Z")
        self.assertEqual(firmware_clock_display_timestamp(year_end)["year"], 2027)
        self.assertEqual(firmware_clock_display_timestamp(year_end)["month"], 1)
        self.assertEqual(firmware_clock_display_timestamp(year_end)["date"], 1)

    def test_stage5c_idle_timeout_powers_off_outside_setup_mode(self):
        source = firmware_source()
        loop_body = firmware_function_body(source, "loop")
        idle_body = firmware_function_body(source, "handleIdlePowerOff")
        interaction_body = firmware_function_body(source, "recordInteraction")
        setup_body = firmware_function_body(source, "setup")
        a_short_body = firmware_function_body(source, "handleButtonAShortPress")
        a_long_body = firmware_function_body(source, "handleButtonALongPress")
        b_short_body = firmware_function_body(source, "handleButtonBShortPress")
        shake_body = firmware_function_body(source, "updateShakeGood")

        self.assertIn("constexpr uint32_t kIdlePowerOffMs = 420000", source)
        self.assertIn("uint32_t lastInteractionAt", source)
        self.assertIn("bool powerOffStarted", source)
        self.assertIn("void recordInteraction(uint32_t now)", source)
        self.assertIn("void handleIdlePowerOff(uint32_t now)", source)
        self.assertIn("uint32_t idleTimeoutMs()", source)
        self.assertIn("M5.Power.powerOff()", idle_body)
        self.assertIn("savePendingReviews()", idle_body)
        self.assertIn("pendingReviewCount > 0", idle_body)
        self.assertIn("powerOffStarted", idle_body)
        self.assertIn("now < lastInteractionAt", idle_body)
        self.assertIn("now - lastInteractionAt < idleTimeoutMs()", idle_body)
        self.assertIn("handleIdlePowerOff(millis())", loop_body)
        self.assertLess(loop_body.index("setupPortalActive"), loop_body.index("handleIdlePowerOff(millis())"))
        self.assertIn("lastInteractionAt = millis()", setup_body)
        self.assertIn("lastInteractionAt = now", interaction_body)
        self.assertIn("recordInteraction(millis())", a_short_body)
        self.assertIn("recordInteraction(millis())", a_long_body)
        self.assertIn("recordInteraction(millis())", b_short_body)
        self.assertIn("recordInteraction(now)", shake_body)

    def test_stage6_clock_idle_and_no_due_status_return(self):
        source = firmware_source()
        idle_timeout_body = firmware_function_body(source, "idleTimeoutMs")
        a_short_body = firmware_function_body(source, "handleButtonAShortPress")
        b_short_body = firmware_function_body(source, "handleButtonBShortPress")

        self.assertIn("currentPage == Page::Clock", idle_timeout_body)
        self.assertIn("kClockIdlePowerOffMs", idle_timeout_body)
        self.assertIn("kIdlePowerOffMs", idle_timeout_body)
        self.assertIn("statusReturnsToClock", source)
        self.assertIn("statusReturnsToClock", a_short_body)
        self.assertIn("currentPage == Page::Status && statusReturnsToClock", source)
        self.assertIn("showClockPage()", a_short_body)
        self.assertLess(
            a_short_body.index("case Page::Status:"),
            a_short_body.index("const Card card = currentCard()"),
        )
        self.assertLess(
            b_short_body.index("case Page::Status:"),
            b_short_body.index("const Card card = currentCard()"),
        )

    def test_stage6_clock_rebuilds_lvgl_after_auto_rotation(self):
        source = firmware_source()
        rotation_body = firmware_function_body(source, "updateAutoRotation")

        self.assertIn("M5.Display.setRotation(currentRotation)", rotation_body)
        self.assertIn("currentPage == Page::Clock", rotation_body)
        self.assertIn("lv_obj_invalidate(clockScr)", rotation_body)
        self.assertIn("lastClockRefreshAt = 0", rotation_body)
        self.assertNotIn("createClockUI()", rotation_body)
        self.assertNotIn("M5.Display.fillScreen(BLACK)", rotation_body)

    def test_stage5d_firmware_parses_and_caches_offline_card_metadata(self):
        source = firmware_source()
        parse_body = firmware_function_body(source, "parseDeviceTasksJson")
        array_body = firmware_function_body(source, "parseCardArrayJson")
        save_body = firmware_function_body(source, "saveCachedTasks")
        load_body = firmware_function_body(source, "loadCachedTasks")
        fetch_body = firmware_function_body(source, "fetchDeviceTasks")
        platformio = (ROOT / "firmware" / "platformio.ini").read_text(encoding="utf-8")
        partitions = (ROOT / "firmware" / "partitions.csv").read_text(encoding="utf-8")

        self.assertIn("constexpr size_t kMaxImmediateCards = 20", source)
        self.assertIn("constexpr size_t kMaxOfflineCards = 40", source)
        self.assertIn("board_build.partitions = partitions.csv", platformio)
        self.assertIn("nvs,      data, nvs,     0x9000,  0x5000", partitions)
        self.assertIn("cache,    data, nvs,     0x190000,0x10000", partitions)
        self.assertIn("Preferences cacheStorage", source)
        self.assertIn('cacheStorage.begin("stickcache", false, "cache")', save_body)
        self.assertIn("struct LegacyDeviceCard", source)
        self.assertIn("char status", source)
        self.assertIn("char dueAt", source)
        self.assertIn("uint16_t reviewCount", source)
        self.assertIn("float ease", source)
        self.assertIn("int16_t intervalDays", source)
        self.assertIn("uint16_t lapses", source)
        self.assertIn("\"offline\"", parse_body)
        self.assertIn("\"cards\"", parse_body)
        self.assertIn("CardArrayParseResult", source)
        self.assertIn("return {false, 0}", array_body)
        self.assertIn("if (!tasksResult.valid)", parse_body)
        self.assertIn("if (!offlineResult.valid)", parse_body)
        self.assertIn("jsonStringValue(object, \"status\")", parse_body)
        self.assertIn("jsonStringValue(object, \"due_at\")", parse_body)
        self.assertIn("jsonIntValue(object, \"review_count\"", parse_body)
        self.assertIn("jsonFloatValue(object, \"ease\"", parse_body)
        self.assertIn("jsonIntValue(object, \"interval_days\"", parse_body)
        self.assertIn("jsonIntValue(object, \"lapses\"", parse_body)
        self.assertIn("offlineCardCount", source)
        self.assertIn("offlineCards", source)
        self.assertIn("cacheStorage.putUInt(\"offline_count\"", save_body)
        self.assertIn("cacheStorage.putBytes(\"offline\"", save_body)
        self.assertIn("savedOfflineBytes == expectedOfflineBytes", save_body)
        self.assertIn('cacheStorage.begin("stickcache", true, "cache")', load_body)
        self.assertIn("readCachedTasksFromStorage(cacheStorage, false)", load_body)
        self.assertIn("readCachedTasksFromStorage(storage, true)", load_body)
        self.assertIn("saveCachedTasks()", load_body)
        read_body = firmware_function_body(source, "readCachedTasksFromStorage")
        self.assertIn("prefs.getUInt(\"offline_count\"", read_body)
        self.assertIn("prefs.getBytes(\"offline\"", read_body)
        self.assertIn("prefs.getBytesLength(\"cards\")", read_body)
        self.assertIn("sizeof(LegacyDeviceCard) * storedCount", read_body)
        self.assertIn("copyLegacyCard(&syncedCards[i]", read_body)
        self.assertIn("storedCount == 0 && storedOfflineCount == 0", read_body)
        self.assertIn("offlineCardCount = storedOfflineCount", read_body)
        self.assertIn("if (offlineCardCount > 0)", fetch_body)
        self.assertLess(fetch_body.index("saveCachedTasks()"), fetch_body.index("clearCachedTasks()"))

    def test_stage5d_firmware_selects_cached_due_cards_using_rtc(self):
        source = firmware_source()
        select_body = firmware_function_body(source, "selectOfflineDueCards")
        setup_body = firmware_function_body(source, "setup")
        fetch_body = firmware_function_body(source, "fetchDeviceTasks")

        self.assertIn("bool selectOfflineDueCards()", source)
        self.assertIn("readRtcTimestamp()", select_body)
        self.assertIn("isValidRtcTimestamp(now)", select_body)
        self.assertIn("isCardDue(card, now)", select_body)
        self.assertIn('std::strcmp(card.status, "new")', select_body)
        self.assertIn("offlineCards", select_body)
        self.assertIn("syncedCards[syncedCardCount++] = card", select_body)
        self.assertIn("if (syncedCardCount == 0)", select_body)
        self.assertLess(
            select_body.index("if (syncedCardCount == 0)"),
            select_body.index('std::strcmp(card.status, "new") == 0'),
        )
        self.assertIn("selectOfflineDueCards()", setup_body)
        self.assertIn("selectOfflineDueCards()", fetch_body)
        self.assertIn('setStatusPage("RTC invalid", "sync needed")', select_body)

    def test_stage5d_pending_reviews_append_multiple_events_per_word(self):
        source = firmware_source()
        queue_body = firmware_function_body(source, "queuePendingReview")
        reviews_body = firmware_function_body(source, "buildPendingReviewsJson")

        self.assertNotIn("replace pending review", queue_body)
        self.assertNotIn("std::strcmp(existing.wordId, wordId) == 0", queue_body)
        self.assertIn("PendingReview& pending = pendingReviews[pendingReviewCount++]", queue_body)
        self.assertIn("currentReviewTimestamp()", queue_body)
        self.assertIn("pending.reviewedAt", queue_body)
        self.assertIn("pending.reviewedAt", reviews_body)
        self.assertNotIn("currentReviewTimestamp()", reviews_body)

        queue = PendingReviewQueue()
        queue.queue("w1", "hard", "2026-05-24T09:30:00Z")
        queue.queue("w1", "good", "2026-05-24T09:35:00Z")
        self.assertEqual(len(queue.items), 2)
        payload = json.loads(queue.build_json(0x1234))
        self.assertEqual(
            [review["event_id"] for review in payload["reviews"]],
            [
                "m5stick-c-plus-1234-1-w1",
                "m5stick-c-plus-1234-2-w1",
            ],
        )
        self.assertEqual(
            [review["reviewed_at"] for review in payload["reviews"]],
            ["2026-05-24T09:30:00Z", "2026-05-24T09:35:00Z"],
        )

    def test_stage5d_firmware_updates_cached_schedule_after_rating(self):
        source = firmware_source()
        apply_body = firmware_function_body(source, "applyLocalReview")
        submit_body = firmware_function_body(source, "submitRating")

        self.assertIn("void applyLocalReview(DeviceCard& card, Rating rating", source)
        self.assertIn("float minFloat(float left, float right)", source)
        self.assertIn("float maxFloat(float left, float right)", source)
        self.assertIn("addMinutesToTimestamp", source)
        self.assertIn("addDaysToTimestamp", source)
        self.assertIn("card.reviewCount += 1", apply_body)
        self.assertIn('copyBounded(card.status, sizeof(card.status), "learning")', apply_body)
        self.assertIn('copyBounded(card.status, sizeof(card.status), "review")', apply_body)
        self.assertIn("card.lapses += 1", apply_body)
        self.assertIn("card.ease = maxFloat(1.3F, card.ease - 0.2F)", apply_body)
        self.assertIn("card.ease = minFloat(3.0F, card.ease + 0.05F)", apply_body)
        self.assertIn("addMinutesToTimestamp(&due, 10)", apply_body)
        self.assertIn("addDaysToTimestamp(&due", apply_body)
        self.assertIn("copyBounded(card.dueAt, sizeof(card.dueAt), formatRtcTimestamp(due))", apply_body)
        self.assertNotIn('formatRtcTimestamp(due) + "Z"', apply_body)
        self.assertIn("applyLocalReview(syncedCards[currentCardIndex], selectedRating", submit_body)
        self.assertIn("offlineCards[i] = syncedCards[currentCardIndex]", submit_body)
        self.assertIn("saveCachedTasks()", submit_body)

    def test_stage5d_rating_submission_does_not_block_on_http_upload(self):
        source = firmware_source()
        submit_body = firmware_function_body(source, "submitRating")
        setup_body = firmware_function_body(source, "setup")

        self.assertIn("queuePendingReview(currentWordId(), selectedRating)", submit_body)
        self.assertNotIn("uploadPendingReviews()", submit_body)
        self.assertIn("uploadPendingReviews()", setup_body)

    def test_stage4_event_ids_include_boot_nonce_and_increasing_sequence(self):
        source = firmware_source()
        setup_body = firmware_function_body(source, "setup")
        queue_body = firmware_function_body(source, "queuePendingReview")
        reviews_body = firmware_function_body(source, "buildPendingReviewsJson")

        self.assertIn("reviewBootNonce = esp_random()", setup_body)
        self.assertIn("pending.sequence = ++reviewSequence", queue_body)
        self.assertIn("String(reviewBootNonce, HEX)", reviews_body)
        self.assertIn("String(pending.sequence)", reviews_body)
        self.assertIn("pending.wordId", reviews_body)

        queue = PendingReviewQueue()
        queue.queue("alpha", "forgot")
        queue.queue("beta", "hard")
        payload = json.loads(queue.build_json(0xC0FFEE, "2026-05-24T09:30:00Z"))
        self.assertEqual(
            [review["event_id"] for review in payload["reviews"]],
            [
                "m5stick-c-plus-c0ffee-1-alpha",
                "m5stick-c-plus-c0ffee-2-beta",
            ],
        )

    def test_stage4_upload_response_acceptance_requires_clean_complete_result(self):
        source = firmware_source()
        body = firmware_function_body(source, "uploadResponseAccepted")

        self.assertIn('"failed\\":0"', body)
        self.assertIn('jsonIntValue(compact, "accepted")', body)
        self.assertIn('jsonIntValue(compact, "skipped_duplicate")', body)
        self.assertIn("accepted + skipped", body)
        self.assertIn(">= attemptedReviews", body)

        self.assertTrue(upload_response_accepted(
            '{"accepted":2,"skipped_duplicate":1,"failed":0}', 3
        ))
        self.assertTrue(upload_response_accepted(
            '{\n  "accepted": 1,\n  "failed": 0,\n  "skipped_duplicate": 1\n}', 2
        ))
        self.assertFalse(upload_response_accepted(
            '{"accepted":3,"skipped_duplicate":0,"failed":1}', 3
        ))
        self.assertFalse(upload_response_accepted(
            '{"accepted":1,"skipped_duplicate":1,"failed":0}', 3
        ))
        self.assertFalse(upload_response_accepted('{"accepted":3,"failed":0}', 3))

    def test_stage4_same_pending_word_re_rate_appends_queue_entry(self):
        source = firmware_source()
        body = firmware_function_body(source, "queuePendingReview")

        self.assertNotIn("replace pending review", body)
        self.assertNotIn("std::strcmp(existing.wordId, wordId) == 0", body)
        self.assertIn("PendingReview& pending = pendingReviews[pendingReviewCount++]", body)

        queue = PendingReviewQueue()
        queue.queue("w1", "hard")
        queue.queue("w1", "good")
        self.assertEqual(len(queue.items), 2)
        self.assertEqual(queue.items[0]["wordId"], "w1")
        self.assertEqual(queue.items[0]["rating"], "hard")
        self.assertEqual(queue.items[0]["sequence"], 1)
        self.assertEqual(queue.items[1]["wordId"], "w1")
        self.assertEqual(queue.items[1]["rating"], "good")
        self.assertEqual(queue.items[1]["sequence"], 2)
        payload = json.loads(queue.build_json(0x1234, "2026-05-24T09:30:00Z"))
        self.assertEqual(
            [review["event_id"] for review in payload["reviews"]],
            [
                "m5stick-c-plus-1234-1-w1",
                "m5stick-c-plus-1234-2-w1",
            ],
        )

    def test_stage4_task_json_parser_survives_escaped_strings_and_braces(self):
        source = firmware_source()
        string_body = firmware_function_body(source, "parseJsonStringAt")
        array_body = firmware_function_body(source, "findJsonArrayEnd")
        object_body = firmware_function_body(source, "findJsonObjectEnd")

        self.assertIn("bool escaped = false", string_body)
        self.assertIn("current == '\\\\'", string_body)
        self.assertIn("current == '\"'", string_body)
        for helper_body in (array_body, object_body):
            self.assertIn("bool inString = false", helper_body)
            self.assertIn("bool escaped = false", helper_body)
            self.assertIn("continue", helper_body)

        body = (
            '{"generated_at":"2026-05-24T09:30:00Z","tasks":['
            '{"id":"w1","word":"quo\\"te","meaning":"path C:\\\\temp\\\\{x}",'
            '"example":"Use \\"braces\\" { inside } safely"},'
            '{"id":"w2","word":"slash\\\\word","meaning":"line\\\\break",'
            '"example":"closing brace } and bracket ] are text"}'
            ']}'
        )
        ok, generated_at, cards = parse_device_tasks_json(body)
        self.assertTrue(ok)
        self.assertEqual(generated_at, "2026-05-24T09:30:00Z")
        self.assertEqual(len(cards), 2)
        self.assertEqual(cards[0]["word"], 'quo"te')
        self.assertEqual(cards[0]["meaning"], r"path C:\temp\{x}")
        self.assertEqual(cards[0]["example"], 'Use "braces" { inside } safely')
        self.assertEqual(cards[1]["word"], r"slash\word")
        self.assertEqual(cards[1]["example"], "closing brace } and bracket ] are text")


if __name__ == "__main__":
    unittest.main()
