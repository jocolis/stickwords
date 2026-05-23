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
        self.assertIn("Button A pressed", source)
        self.assertIn("Button B pressed", source)
        self.assertIn("getAccelData", source)
        self.assertIn("setRotation(1)", source)

    def test_platformio_build_output_is_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("firmware/.pio/", ignore)
        self.assertIn("firmware/.vscode/.browse.c_cpp.db*", ignore)


if __name__ == "__main__":
    unittest.main()
