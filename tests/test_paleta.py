"""Temas claro y oscuro: contraste WCAG 2.2 AA de cada par que se pinta junto, «sistema» según
Windows, los colores de la terminal y el cambio de tema en caliente en la ventana y los diálogos.

Las pruebas con Tk abren las ventanas como tests/test_dialogs.py y tests/test_main_window.py (sin
audio, hardware ni config.json reales) y recorren todos sus widgets: ningún color del tema anterior
debe quedar y cada texto debe llegar a 4,5:1 sobre su fondo. Sin pantalla para Tk, se omiten.
"""

import contextlib
import copy
import ctypes
import json
import pathlib
import re
import sys
import tempfile
import tkinter as tk
import unittest
from tkinter import ttk
from unittest import mock

from recorder import paleta
from recorder.cli import app
from recorder.cli.consola import make_console, tema_rich
from recorder.config import hardware
from recorder.config.schema import AppConfig
from recorder.paleta import PARES, TEMAS, contraste, resolver
from recorder.ui import main_window as mw
from recorder.ui import theme
from recorder.ui.dialogs import settings_dialog
from recorder.ui.dialogs.digest_dialog import DigestDialog
from recorder.ui.dialogs.settings_dialog import SettingsDialog
from recorder.ui.dialogs.tuning_dialog import TuningDialog
from tests.test_dialogs import NOTA, PANTALLAS, PERFIL, VENTANAS, PyAudioFalso
from tests.test_main_window import BaseVentana


class TestContraste(unittest.TestCase):
    def test_formula_wcag(self):
        self.assertAlmostEqual(contraste("#000000", "#ffffff"), 21.0, places=2)
        self.assertEqual(contraste("#7f849c", "#7f849c"), 1.0)
        self.assertAlmostEqual(contraste("#7f849c", "#1e1e2e"), 4.44, places=2)  # el tenue de antes no llegaba

    def test_cada_par_usado_cumple_aa_en_cada_tema(self):
        for nombre, tema in TEMAS.items():
            for primero, fondo, minimo in PARES:
                with self.subTest(tema=nombre, par=f"{primero} sobre {fondo}"):
                    self.assertGreaterEqual(contraste(tema[primero], tema[fondo]), minimo)


class TestTokens(unittest.TestCase):
    def test_todos_los_temas_tienen_los_mismos_tokens_en_hex(self):
        tokens = set(TEMAS["oscuro"])
        for nombre, tema in TEMAS.items():
            self.assertEqual(set(tema), tokens, nombre)
            for token, color in tema.items():
                self.assertRegex(color, r"^#[0-9a-f]{6}$", f"{nombre}.{token}: Tk lo devuelve tal cual se escribió")

    def test_colores_compartidos_coinciden_en_todos_los_temas(self):
        """El cambio en caliente sustituye cada color por el del mismo token: dos tokens con el mismo
        color en un tema tienen que tenerlo igual en todos, o no se sabría cuál es."""
        for a in TEMAS.values():
            for b in TEMAS.values():
                destino = {}
                for token, color in a.items():
                    self.assertEqual(destino.setdefault(color, b[token]), b[token], token)

    def test_el_oscuro_es_el_mocha_de_siempre_salvo_lo_que_no_llegaba(self):
        oscuro = TEMAS["oscuro"]
        antes = {"fondo": "#1e1e2e", "superficie": "#313244", "texto": "#cdd6f4", "acento": "#f9e2af",
                 "mic": "#89b4fa", "error": "#f38ba8", "ok": "#a6e3a1"}
        self.assertEqual({k: oscuro[k] for k in antes}, antes)


@contextlib.contextmanager
def windows_en_modo(claro):
    """Un winreg de mentira: AppsUseLightTheme = `claro`, o sin la clave si es None."""
    class Clave:
        HKEY_CURRENT_USER = 0

        @staticmethod
        def OpenKey(*_):
            if claro is None:
                raise FileNotFoundError
            return contextlib.nullcontext()

        @staticmethod
        def QueryValueEx(_clave, nombre):
            assert nombre == "AppsUseLightTheme"
            return claro, 4

    with mock.patch.dict(sys.modules, {"winreg": Clave}):
        yield


class TestResolver(unittest.TestCase):
    def test_sistema_sigue_a_windows(self):
        with windows_en_modo(1):
            self.assertEqual(resolver("sistema"), "claro")
        with windows_en_modo(0):
            self.assertEqual(resolver("sistema"), "oscuro")
        with windows_en_modo(None):
            self.assertEqual(resolver("sistema"), "oscuro")

    def test_nombres_fijos_y_desconocidos(self):
        self.assertEqual(resolver("claro"), "claro")
        self.assertEqual(resolver("oscuro"), "oscuro")
        self.assertEqual(resolver("cristal"), "oscuro")  # no se entrega: cae al de fábrica
        self.assertEqual(resolver(""), "oscuro")


class TestTerminal(unittest.TestCase):
    def test_la_terminal_usa_la_paleta_del_tema(self):
        for nombre in ("oscuro", "claro"):
            estilos = tema_rich(nombre).styles
            self.assertEqual(estilos["tenue"].color.triplet.hex, TEMAS[nombre]["texto_tenue"])
            self.assertEqual(estilos["acento"].color.triplet.hex, TEMAS[nombre]["acento"])
        with windows_en_modo(1):
            consola = make_console(ascii_mode=True, tema="sistema", file=None)
        self.assertEqual(consola.get_style("error").color.triplet.hex, TEMAS["claro"]["error"])

    def test_daily_lee_el_tema_de_config_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = pathlib.Path(tmp) / "config.json"
            with mock.patch.object(app, "ruta_config", lambda: ruta):
                self.assertEqual(app.tema_guardado(), "oscuro")  # sin archivo
                ruta.write_text("{roto", encoding="utf-8")
                self.assertEqual(app.tema_guardado(), "oscuro")
                ruta.write_text(json.dumps({"theme": "claro"}), encoding="utf-8")
                self.assertEqual(app.tema_guardado(), "claro")
            self.assertFalse((pathlib.Path(tmp) / "config.json.roto").exists(), "solo lee")


# ------------------------------------------------------------------ en caliente
TEXTO = [("foreground", "background"), ("activeforeground", "activebackground"), ("selectforeground", "selectbackground")]


def revisar(caso: unittest.TestCase, raiz, nombre: str):
    """Todos los widgets bajo `raiz` pintados con el tema `nombre`: sin colores de otro tema y con
    cada texto (también las etiquetas de Text) a 4,5:1 o más sobre su fondo."""
    colores = set(TEMAS[nombre].values())
    ajenos = set().union(*(t.values() for t in TEMAS.values())) - colores
    pila = [raiz]
    while pila:
        w = pila.pop()
        pila.extend(w.winfo_children())
        valores = {}
        for op in theme.OPCIONES_COLOR:
            with contextlib.suppress(tk.TclError):
                valores[op] = str(w.cget(op))
        for op, v in valores.items():
            caso.assertNotIn(v, ajenos, f"{w} {op}: quedó un color de otro tema")
        for primero, fondo in TEXTO:
            if valores.get(primero) in colores and valores.get(fondo) in colores:
                caso.assertGreaterEqual(contraste(valores[primero], valores[fondo]), 4.5, f"{w} {primero}")
        if isinstance(w, tk.Text):
            for tag in w.tag_names():
                color = str(w.tag_cget(tag, "foreground"))
                if color in colores:
                    caso.assertGreaterEqual(contraste(color, valores["background"]), 4.5, f"{w} etiqueta {tag}")


def barra_oscura(win):
    """Lo que Windows tiene puesto en DWMWA_USE_IMMERSIVE_DARK_MODE para `win`, o None si no se puede leer."""
    v = ctypes.c_int(-1)
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(int(win.wm_frame(), 16), 20, ctypes.byref(v), ctypes.sizeof(v))
    return bool(v.value) if hr == 0 else None


class TestTemaEnCaliente(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as e:  # sin escritorio
            raise unittest.SkipTest(f"sin pantalla para Tk: {e}")
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.addCleanup(theme.aplicar_tema, self.root, "oscuro")  # la paleta es global: se deja como estaba
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        nota = pathlib.Path(self.tmp.name) / "daily_2026-09-08_10-20.md"
        nota.write_text(NOTA, encoding="utf-8")
        self.cfg = AppConfig(notes_dir=self.tmp.name)

    def abrir_dialogos(self):
        with mock.patch.object(hardware, "_cache", PERFIL), \
             mock.patch.object(settings_dialog, "screen_labels", lambda: list(PANTALLAS)), \
             mock.patch.object(settings_dialog, "window_titles", lambda: list(VENTANAS)):
            opciones = SettingsDialog(self.root, self.cfg, PyAudioFalso(), on_save=lambda *_: None)
        dialogos = [opciones, TuningDialog(opciones, self.cfg, on_save=lambda c: None), DigestDialog(self.root, self.cfg)]
        for d in dialogos:
            self.addCleanup(d.destroy)
        return dialogos

    def test_los_dialogos_abiertos_cambian_y_vuelven(self):
        dialogos = self.abrir_dialogos()
        revisar(self, self.root, "oscuro")
        self.assertEqual(theme.aplicar_tema(self.root, "claro"), "claro")
        revisar(self, self.root, "claro")
        scroll = ttk.Style(self.root).configure("Digest.Vertical.TScrollbar")
        self.assertEqual(str(scroll["troughcolor"]), TEMAS["claro"]["fondo"])
        self.assertEqual(theme.BTN_STYLE["bg"], TEMAS["claro"]["superficie"])
        if barra_oscura(dialogos[0]) is not None:
            self.assertFalse(barra_oscura(dialogos[0]), "barra de título clara")
        theme.aplicar_tema(self.root, "oscuro")
        revisar(self, self.root, "oscuro")
        if barra_oscura(dialogos[0]) is not None:
            self.assertTrue(barra_oscura(dialogos[0]), "barra de título oscura")

    def test_un_dialogo_nuevo_nace_con_el_tema_activo(self):
        theme.aplicar_tema(self.root, "claro")
        self.abrir_dialogos()
        revisar(self, self.root, "claro")

    def test_cambia_lo_que_se_pinta_despues(self):
        """Los colores que se ponen al vuelo (estado del sandbox, de whisper.cpp) salen del tema activo."""
        opciones, calibrar, _ = self.abrir_dialogos()
        theme.aplicar_tema(self.root, "claro")
        calibrar._run_test()
        opciones._refresh_engine()
        revisar(self, self.root, "claro")


class TestTemaEnLaVentana(BaseVentana):
    def test_guardar_opciones_cambia_el_tema_sin_reiniciar(self):
        self.addCleanup(theme.aplicar_tema, self.root, "oscuro")
        self.win.add_line("10:00:01", "mic", "Hola equipo", [])
        self.win.add_line("10:00:05", "out", "Hay un bloqueo", ["bloqueo"])
        guardar = []
        with mock.patch.object(mw, "SettingsDialog", lambda *_a, on_save, **_k: guardar.append(on_save)):
            self.win.open_options()
        abierto = TuningDialog(self.root, self.session.config, on_save=lambda c: None)
        self.addCleanup(abierto.destroy)

        cfg = copy.deepcopy(self.session.config)
        cfg.theme = "claro"
        guardar[0](cfg, False, False)  # lo que hace ⚙ Opciones al guardar
        self.win._tick()
        revisar(self, self.root, "claro")
        self.assertEqual(self.session.config.theme, "claro")

        cfg = copy.deepcopy(cfg)
        cfg.theme = "oscuro"
        guardar[0](cfg, False, False)
        self.win._tick()
        revisar(self, self.root, "oscuro")


class TestSinColoresSueltos(unittest.TestCase):
    def test_la_interfaz_no_escribe_colores_a_mano(self):
        """Todos los colores de la ventana salen de la paleta: ni hex sueltos ni las constantes de antes."""
        ui = pathlib.Path(theme.__file__).parent
        for archivo in [*ui.glob("*.py"), *ui.glob("dialogs/*.py")]:
            texto = archivo.read_text(encoding="utf-8")
            with self.subTest(archivo=archivo.name):
                self.assertIsNone(re.search(r"#[0-9a-fA-F]{6}\b", texto))
                self.assertIsNone(re.search(r"\b(BG|PANEL|FG|DIM|ACC|MIC|ERR|SUCCESS|BORDER)\b", texto))


if __name__ == "__main__":
    unittest.main()
