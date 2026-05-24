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


if __name__ == "__main__":
    unittest.main()
