import dataclasses
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
        self.assertEqual(cfg.fixes, {})  # sin correcciones personales de fabrica
        self.assertEqual(cfg.vocab, "")  # sin vocabulario personal de fabrica
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

class TestExampleConfig(unittest.TestCase):
    """El config.example.json que se publica debe seguir el esquema y no llevar datos personales."""

    @property
    def example_path(self):
        return pathlib.Path(__file__).resolve().parent.parent / "config.example.json"

    def test_example_exists_and_is_valid_json(self):
        self.assertTrue(self.example_path.exists(), "falta config.example.json en la raiz")
        json.loads(self.example_path.read_text(encoding="utf-8"))

    def test_example_keys_match_schema(self):
        data = json.loads(self.example_path.read_text(encoding="utf-8"))
        valid = {f.name for f in dataclasses.fields(AppConfig)}
        unknown = set(data) - valid
        self.assertEqual(unknown, set(), f"claves que ya no existen en AppConfig: {unknown}")

    def test_example_loads_into_appconfig(self):
        data = json.loads(self.example_path.read_text(encoding="utf-8"))
        cfg = AppConfig.from_dict(data)
        self.assertTrue(cfg.vocab.strip())
        self.assertTrue(cfg.keywords)
        self.assertTrue(cfg.ignore)

    def test_example_carries_no_personal_data(self):
        raw = self.example_path.read_text(encoding="utf-8")
        self.assertNotIn("C:\\Users", raw)  # sin rutas de una maquina concreta
        self.assertNotIn("Realtek", raw)  # sin dispositivos de audio de una maquina concreta
