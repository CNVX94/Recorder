import json
import tempfile
import unittest
import pathlib

from recorder.config.schema import AppConfig
from recorder.config.manager import ConfigManager


class TestConfig(unittest.TestCase):
    def test_default_config(self):
        cfg = AppConfig()
        self.assertEqual(cfg.model, "small")
        self.assertTrue(cfg.mic)
        self.assertIn("cuba", cfg.fixes)
        self.assertIn("suscríbete", cfg.ignore)
        self.assertGreater(cfg.no_speech_threshold, 0)

    def test_config_save_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_file = pathlib.Path(tmp) / "custom_config.json"
            mgr = ConfigManager(cfg_file)
            cfg = mgr.load()
            cfg.model = "medium"
            cfg.fixes["prueba"] = "Test"
            mgr.save(cfg)

            loaded = mgr.load()
            self.assertEqual(loaded.model, "medium")
            self.assertEqual(loaded.fixes["prueba"], "Test")

    def test_backward_compatibility_with_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg_file = pathlib.Path(tmp) / "legacy_config.json"
            data = {
                "notes_dir": "C:/Dailies",
                "model": "base",
                "unknown_legacy_field": 12345,
            }
            cfg_file.write_text(json.dumps(data), encoding="utf-8")

            mgr = ConfigManager(cfg_file)
            cfg = mgr.load()
            self.assertEqual(cfg.notes_dir, "C:/Dailies")
            self.assertEqual(cfg.model, "base")
            self.assertIn("pendiente", cfg.keywords)


if __name__ == "__main__":
    unittest.main()
