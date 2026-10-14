"""El menú de `daily menu`, con comandos de mentira, la entrada guionizada y un config.json temporal."""

import io
import json
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from recorder.cli import app
from recorder.cli.consola import make_console
from recorder.cli.menu import menu, opciones_disponibles
from recorder.config.manager import ConfigManager
from recorder.config.schema import AppConfig


def comando_falso(nombre, registro):
    """Un módulo del contrato hecho con SimpleNamespace; anota en `registro` cada ejecución."""

    def ejecutar(args, consola):
        registro.append((nombre, consola))
        return 0

    return SimpleNamespace(
        NOMBRE=nombre, AYUDA=f"ayuda de {nombre}", agregar_argumentos=lambda parser: None, ejecutar=ejecutar,
    )


class TestMenu(unittest.TestCase):
    def setUp(self):
        self.ejecutados = []
        self.comandos = {n: comando_falso(n, self.ejecutados) for n in ("config", "recomendar")}  # sin calibrar ni sintesis
        self.salida = io.StringIO()
        self.consola = make_console(ascii_mode=False, file=self.salida, width=120)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = pathlib.Path(self.tmp.name) / "config.json"
        cfg = AppConfig()
        cfg.notes_dir = r"C:\Dailies"
        self.ruta.write_text(json.dumps(cfg.to_dict()), encoding="utf-8")
        self.mgr = ConfigManager(self.ruta)

    def correr(self, *lineas):
        guion = iter(lineas)

        def entrada():
            try:
                return next(guion)
            except StopIteration:
                raise EOFError

        return menu(self.consola, entrada, self.comandos, self.mgr)

    def test_ofrece_solo_lo_que_hay_con_numeros_fijos(self):
        filas = opciones_disponibles(self.comandos)
        self.assertEqual([(n, e) for n, e, _a, _h in filas], [
            ("1", "Grabar"), ("2", "Opciones"), ("5", "Recomendación del equipo"), ("6", "Abrir la ventana"), ("0", "Salir"),
        ])
        self.assertEqual(self.correr("0"), 0)
        salida = self.salida.getvalue()
        self.assertIn("Recorder · ¿qué quieres hacer?\nnotas en C:\\Dailies · Calidad Media · CPU\n\n", salida, "título y una línea de resumen")
        # etiquetas en una columna, descripciones cortas del menú alineadas (no la AYUDA larga de argparse)
        self.assertIn("  1  Grabar                    transcribe en vivo a la nota de hoy, aquí en la terminal\n", salida)
        self.assertIn("  2  Opciones                  carpetas, audio, capturas, calidad y motor\n", salida)
        self.assertIn("  5  Recomendación del equipo  qué equipo se detecta y qué configuración conviene\n", salida)
        self.assertIn("  0  Salir\nOpción: ", salida)
        self.assertNotIn("ayuda de config", salida)
        self.assertNotIn("Calibrar", salida)
        self.assertNotIn("Reagrupar", salida)
        self.assertFalse([l for l in salida.splitlines() if l != l.rstrip() and l != "Opción: "], "sin espacios al final de las líneas")

    def test_una_config_ilegible_se_dice_en_el_resumen(self):
        self.ruta.write_bytes(b"{ roto")
        self.correr("0")
        self.assertIn("⚠ No se pudo leer «config.json»", self.salida.getvalue())

    def test_vuelve_al_menu_tras_un_comando_y_rechaza_lo_que_no_hay(self):
        self.assertEqual(self.correr("2", "3", "5", "0"), 0)
        self.assertEqual([n for n, _c in self.ejecutados], ["config", "recomendar"])
        self.assertTrue(all(c is self.consola for _n, c in self.ejecutados), "los comandos pintan en la misma consola")
        self.assertIn("No hay opción «3»", self.salida.getvalue())
        self.assertEqual(self.salida.getvalue().count("¿qué quieres hacer?"), 4, "se vuelve a pintar tras cada cosa")

    def test_grabar_y_ventana_terminan_el_menu(self):
        with patch("recorder.cli.live.grabar", return_value=4) as grabar:
            self.assertEqual(self.correr("1", "0"), 4)
        grabar.assert_called_once_with(consola=self.consola)
        with patch.object(app, "abrir_ventana", return_value=0) as ventana:
            self.assertEqual(self.correr("6", "0"), 0)
        ventana.assert_called_once()

    def test_fin_de_entrada_y_ctrl_c_salen_limpio(self):
        self.assertEqual(self.correr(), 0)

        def interrumpir():
            raise KeyboardInterrupt

        self.assertEqual(menu(self.consola, interrumpir, self.comandos, self.mgr), 0)

    def test_en_ascii_no_salen_emoji_ni_simbolos(self):
        consola = make_console(ascii_mode=True, file=io.StringIO())
        self.ruta.write_bytes(b"{ roto")  # el resumen lleva ⚠: en ASCII sale como «!»
        menu(consola, lambda: "0", self.comandos, self.mgr)
        salida = consola.file.getvalue()
        self.assertIn("Recorder", salida)
        self.assertIn("! No se pudo leer", salida)
        self.assertFalse([c for c in salida if ord(c) >= 0x2000 and c not in "–—·"])


if __name__ == "__main__":
    unittest.main()
