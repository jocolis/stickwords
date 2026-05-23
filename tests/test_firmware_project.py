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

    def test_platformio_build_output_is_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("firmware/.pio/", ignore)
        self.assertIn("firmware/.vscode/.browse.c_cpp.db*", ignore)


if __name__ == "__main__":
    unittest.main()
