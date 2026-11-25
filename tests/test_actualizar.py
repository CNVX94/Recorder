"""Actualizar Recorder: la versión que se ve con `daily --version`, el mutex que comparten la
aplicación y el instalador, y que un config.json de una versión anterior se lee bien."""

import contextlib
import io
import json
import pathlib
import re
import tempfile
import unittest

from recorder import __version__, registro
from recorder.cli import app
from recorder.config.manager import ConfigManager

RAIZ = pathlib.Path(__file__).resolve().parent.parent
# Lo único que traía un config.json de las primeras versiones; los campos nuevos no estaban.
CONFIG_ANTIGUO = {"keywords": ["bloqueo"], "mic": True, "screen": 0}


class Actualizar(unittest.TestCase):
    def test_version_dice_la_de_init(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida), self.assertRaises(SystemExit) as cierre:
            app.main(["--version"])
        self.assertEqual(cierre.exception.code, 0)
        self.assertEqual(salida.getvalue().strip(), f"Recorder {__version__}")

    def test_el_instalador_espera_el_mutex_que_crea_la_aplicacion(self):
        iss = (RAIZ / "packaging" / "recorder.iss").read_text(encoding="utf-8-sig")
        self.assertEqual(re.search(r"^AppMutex=(\S+)", iss, re.M).group(1), registro.NOMBRE_MUTEX)

    def test_config_de_una_version_anterior_se_lee_sin_aviso(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = pathlib.Path(tmp) / "config.json"
            ruta.write_text(json.dumps(CONFIG_ANTIGUO), encoding="utf-8")
            gestor = ConfigManager(ruta)
            cfg = gestor.load()
        self.assertEqual(gestor.last_error, "")
        self.assertEqual(cfg.keywords, ["bloqueo"])
        self.assertFalse(cfg.intro_seen)  # los campos que faltan toman el valor de fábrica
        self.assertFalse(cfg.allow_igpu)
        self.assertEqual(cfg.process_priority, "normal")


if __name__ == "__main__":
    unittest.main()