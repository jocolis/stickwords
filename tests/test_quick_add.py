import importlib.util
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.temp_utils import workspace_temp_dir


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "quick_add.py"


def load_quick_add_module():
    spec = importlib.util.spec_from_file_location("stickwords_quick_add", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class QuickAddTests(unittest.TestCase):
    def test_windows_shortcut_files_point_to_quick_add_entrypoint(self):
        batch = ROOT / "scripts" / "quick_add.bat"
        setup = ROOT / "scripts" / "setup_quick_add_hotkey.ps1"

        self.assertIn("quick_add.py", batch.read_text(encoding="utf-8"))
        setup_text = setup.read_text(encoding="utf-8")
        self.assertIn("quick_add.bat", setup_text)
        self.assertIn("Ctrl+Alt+W", setup_text)

    def test_add_or_update_uses_stickwords_service_data_dir(self):
        module = load_quick_add_module()
        now = datetime(2026, 5, 23, 10, 0, tzinfo=timezone.utc)

        with workspace_temp_dir() as temp_dir:
            action, word = module.add_or_update(
                temp_dir,
                "benefit",
                "advantage",
                "This change has a clear benefit.",
                clock=lambda: now,
            )
            second_action, updated = module.add_or_update(
                temp_dir,
                "Benefit",
                "good effect",
                "Daily review has a benefit.",
                clock=lambda: now,
            )

            self.assertEqual(action, "created")
            self.assertEqual(word.id, "w-000001")
            self.assertEqual(second_action, "updated")
            self.assertEqual(updated.id, word.id)
            self.assertEqual(updated.meaning, "good effect")


if __name__ == "__main__":
    unittest.main()
