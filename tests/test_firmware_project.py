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


class PendingReviewQueue:
    def __init__(self):
        self.items = []
        self.sequence = 0

    def queue(self, word_id, rating):
        for item in self.items:
            if not item["uploaded"] and item["wordId"] == word_id:
                self.sequence += 1
                item.update({"rating": rating, "sequence": self.sequence})
                return
        self.sequence += 1
        self.items.append({
            "wordId": word_id,
            "rating": rating,
            "sequence": self.sequence,
            "uploaded": False,
        })

    def build_json(self, boot_nonce, generated_at=""):
        reviewed_at = generated_at if generated_at else "1970-01-01T00:00:00Z"
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
                "reviewed_at": reviewed_at,
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
        self.assertIn("m5stack/M5StickCPlus", config)

    def test_firmware_source_contains_stage3b_review_ui(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("#include <M5StickCPlus.h>", source)
        self.assertIn("StickWords Stage 3C boot", source)
        self.assertIn("enum class Page", source)
        self.assertIn("Word", source)
        self.assertIn("Meaning", source)
        self.assertIn("Example", source)
        self.assertIn("Rating", source)
        self.assertIn("Done", source)
        self.assertIn("struct Card", source)
        self.assertIn("struct ReviewResult", source)
        self.assertIn("kCards[]", source)
        self.assertIn("abandon", source)
        self.assertIn("benefit", source)
        self.assertIn("curious", source)
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
        self.assertIn("M5.Lcd.setRotation(currentRotation)", source)
        self.assertIn("M5.Imu.Init()", source)
        self.assertIn("M5.IMU.getAccelData", source)

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
        self.assertIn("StickWords Stage 3C boot", source)

    def test_stage3b_uses_single_flow_content_paging(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("constexpr size_t kContentPageChars", source)
        self.assertIn("uint8_t contentPageIndex", source)
        self.assertIn("contentPageCount(", source)
        self.assertIn("drawContentPage(", source)
        self.assertIn("hasMoreContentPage(", source)
        self.assertIn("Page::Meaning", source)
        self.assertIn("Page::Example", source)
        self.assertNotIn("MeaningSummary", source)
        self.assertNotIn("FullExample", source)
        self.assertNotIn("M5.Lcd.println(card.word);", source)
        self.assertNotIn('M5.Lcd.print("ex: ");', source)

    def test_stage3c_uses_stable_imu_landscape_auto_rotation(self):
        source = (ROOT / "firmware" / "src" / "main.cpp").read_text(encoding="utf-8")

        self.assertIn("constexpr float kOrientationThreshold", source)
        self.assertIn("constexpr uint32_t kOrientationStableMs", source)
        self.assertIn("uint8_t currentRotation = 1", source)
        self.assertIn("uint8_t pendingRotation = 1", source)
        self.assertIn("void readImu()", source)
        self.assertIn("uint8_t detectLandscapeRotation()", source)
        self.assertIn("void updateAutoRotation(uint32_t now)", source)
        self.assertIn("M5.Lcd.setRotation(currentRotation)", source)
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
        self.assertIn("replace pending review", source)
        self.assertIn("parseJsonStringAt(", source)
        self.assertIn("escaped = true", source)

    def test_stage4_review_timestamp_uses_generated_at_or_fallback(self):
        source = firmware_source()
        parse_body = firmware_function_body(source, "parseDeviceTasksJson")
        timestamp_body = firmware_function_body(source, "currentReviewTimestamp")
        reviews_body = firmware_function_body(source, "buildPendingReviewsJson")

        self.assertNotIn("2026-05-24T00:00:00Z", source)
        self.assertIn('jsonStringValue(body, "generated_at")', parse_body)
        self.assertIn("serverGeneratedAt[0] != '\\0'", timestamp_body)
        self.assertIn("return String(serverGeneratedAt)", timestamp_body)
        self.assertIn("1970-01-01T00:00:00Z", timestamp_body)
        self.assertIn("currentReviewTimestamp()", reviews_body)

        ok, generated_at, cards = parse_device_tasks_json(
            '{"generated_at":"2026-05-24T09:30:00Z",'
            '"tasks":[{"id":"w1","word":"alpha","meaning":"first","example":"one"}]}'
        )
        self.assertTrue(ok)
        self.assertEqual(generated_at, "2026-05-24T09:30:00Z")
        self.assertEqual(cards[0]["word"], "alpha")

        queue = PendingReviewQueue()
        queue.queue("w1", "good")
        synced = json.loads(queue.build_json(0x1A2B3C, generated_at))
        fallback = json.loads(queue.build_json(0x1A2B3C, ""))
        self.assertEqual(synced["reviews"][0]["reviewed_at"], "2026-05-24T09:30:00Z")
        self.assertEqual(fallback["reviews"][0]["reviewed_at"], "1970-01-01T00:00:00Z")

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

    def test_stage4_same_pending_word_re_rate_replaces_queue_entry(self):
        source = firmware_source()
        body = firmware_function_body(source, "queuePendingReview")

        replacement_index = body.index("replace pending review")
        append_index = body.index("PendingReview& pending = pendingReviews[pendingReviewCount++]")
        self.assertLess(replacement_index, append_index)
        self.assertIn("std::strcmp(existing.wordId, wordId) == 0", body)
        self.assertIn("existing.rating = rating", body)
        self.assertIn("existing.sequence = ++reviewSequence", body)
        self.assertIn("return", body[replacement_index:append_index])

        queue = PendingReviewQueue()
        queue.queue("w1", "hard")
        queue.queue("w1", "good")
        self.assertEqual(len(queue.items), 1)
        self.assertEqual(queue.items[0]["wordId"], "w1")
        self.assertEqual(queue.items[0]["rating"], "good")
        self.assertEqual(queue.items[0]["sequence"], 2)
        payload = json.loads(queue.build_json(0x1234, "2026-05-24T09:30:00Z"))
        self.assertEqual(payload["reviews"][0]["event_id"], "m5stick-c-plus-1234-2-w1")

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
