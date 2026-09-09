import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from recorder.actions.screenshot import app_name, find_window, is_black, pick_window, take_screenshot, windows
from recorder.config.manager import ConfigManager
from recorder.config.schema import AppConfig


class TestWindowPolicy(unittest.TestCase):
    """Política pura: qué ventana abierta corresponde a la guardada en config."""

    def test_app_name_is_last_segment(self):
        self.assertEqual(app_name("Chat | Equipo (Externo) | Microsoft Teams"), "Microsoft Teams")
        self.assertEqual(app_name("notas.txt - Bloc de notas"), "Bloc de notas")
        self.assertEqual(app_name("Microsoft Teams"), "Microsoft Teams")
        self.assertEqual(app_name("a-b|c"), "a-b|c")  # separadores sin espacios alrededor no cuentan

    def test_exact_title_wins(self):
        titles = ["Reunión | Microsoft Teams", "Chat | Microsoft Teams"]
        self.assertEqual(pick_window("Chat | Microsoft Teams", titles), "Chat | Microsoft Teams")

    def test_same_app_when_title_changed(self):
        titles = ["x - Bloc de notas", "Reunión semanal | Microsoft Teams", "Chat | Microsoft Teams"]
        self.assertEqual(pick_window("Chat | Equipo | Microsoft Teams", titles), "Reunión semanal | Microsoft Teams")
        self.assertEqual(pick_window("Chat | Equipo | microsoft teams", titles), "Reunión semanal | Microsoft Teams")

    def test_none_when_missing_or_empty(self):
        self.assertIsNone(pick_window("Chat | Microsoft Teams", ["x - Bloc de notas"]))
        self.assertIsNone(pick_window("", ["Microsoft Teams"]))
        self.assertIsNone(pick_window("Microsoft Teams", []))


class TestBlackDetection(unittest.TestCase):
    def test_black_image(self):
        self.assertTrue(is_black(Image.new("RGB", (40, 30))))

    def test_dark_theme_is_not_black(self):
        img = Image.new("RGB", (40, 30), (30, 30, 46))  # fondo oscuro tipo Catppuccin
        img.putpixel((3, 3), (205, 214, 244))  # un píxel de texto claro
        self.assertFalse(is_black(img))


class TestWindowConfig(unittest.TestCase):
    def test_default_has_no_window(self):
        self.assertEqual(AppConfig().window, "")

    def test_legacy_config_without_window_keeps_screen(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = pathlib.Path(tmp) / "config.json"
            f.write_text(json.dumps({"screen": 2}), encoding="utf-8")
            cfg = ConfigManager(f).load()
        self.assertEqual((cfg.screen, cfg.window), (2, ""))

    def test_window_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            mgr = ConfigManager(pathlib.Path(tmp) / "config.json")
            mgr.save(AppConfig(window="Reunión | Microsoft Teams"))
            self.assertEqual(mgr.load().window, "Reunión | Microsoft Teams")


@unittest.skipUnless(sys.platform == "win32", "API Win32")
class TestWin32(unittest.TestCase):
    MISSING = "ventana-inexistente-9f3a | app-inexistente-9f3a"

    def test_windows_have_handle_and_title(self):
        for hwnd, title in windows():
            self.assertIsInstance(hwnd, int)
            self.assertTrue(title.strip())

    def test_find_window_missing(self):
        self.assertIsNone(find_window(""))
        self.assertIsNone(find_window(self.MISSING))

    def test_missing_window_falls_back_to_screen(self):
        """La ventana guardada ya no existe: se captura la pantalla, nunca revienta."""
        with tempfile.TemporaryDirectory() as tmp:
            path = take_screenshot("prueba", tmp, 0, self.MISSING)
            with Image.open(path) as img:
                self.assertGreater(img.width * img.height, 0)

    def test_black_window_falls_back_to_its_rect(self):
        """PrintWindow devuelve negro: se recorta lo visible en el rectángulo de la ventana."""
        with tempfile.TemporaryDirectory() as tmp, patch(
            "recorder.actions.screenshot.find_window", return_value=12345
        ), patch("recorder.actions.screenshot.grab_window", return_value=None), patch(
            "recorder.actions.screenshot.window_rect", return_value=(0, 0, 50, 40)
        ):
            path = take_screenshot("negra", tmp, 0, "x")
            with Image.open(path) as img:
                self.assertEqual(img.size, (50, 40))

    def test_win32_failure_falls_back_to_screen(self):
        """Cualquier excepción Win32 al buscar la ventana degrada a pantalla, no se propaga."""
        with tempfile.TemporaryDirectory() as tmp, patch(
            "recorder.actions.screenshot.find_window", side_effect=OSError("boom")
        ):
            path = take_screenshot("fallo", tmp, 0, "x")
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
