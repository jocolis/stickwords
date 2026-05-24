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
        self.assertIn("StickWords Stage 3B boot", source)
        self.assertIn("enum class Page", source)
        self.assertIn("Word", source)
        self.assertIn("MeaningSummary", source)
        self.assertIn("FullExample", source)
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
        self.assertIn("M5.Lcd.setRotation(1)", source)
        self.assertNotIn("M5.Imu.Init", source)
        self.assertNotIn("getAccelData", source)

    def test_platformio_build_output_is_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("firmware/.pio/", ignore)
        self.assertIn("firmware/.vscode/.browse.c_cpp.db*", ignore)


if __name__ == "__main__":
    unittest.main()
