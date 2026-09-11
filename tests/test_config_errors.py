"""Una configuración ilegible no puede pasar desapercibida.

La secuencia que estas pruebas impiden es silenciosa y destructiva: el archivo se corrompe,
la aplicación arranca con los valores de fábrica sin avisar, el usuario guarda desde
Opciones y pierde para siempre su vocabulario y sus correcciones.
"""

import json
import pathlib
import tempfile
import unittest

from recorder.config.manager import ConfigManager
from recorder.config.schema import AppConfig

# El sufijo se escribe aqui a proposito, sin importarlo: es un nombre que ve el usuario,
# y asi la prueba sigue valiendo contra versiones que aun no tenian la constante.
SUFIJO_ROTO = ".roto"

VALIDA = {"model": "medium", "vocab": "API Core, endpoint", "keywords": ["bloqueo"]}


class BaseConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ruta = pathlib.Path(self.tmp.name) / "config.json"

    def escribir(self, contenido: bytes):
        self.ruta.write_bytes(contenido)

    @property
    def copia_rota(self):
        return self.ruta.with_name(self.ruta.name + SUFIJO_ROTO)


class TestConfigLegible(BaseConfig):
    def test_sin_archivo_no_es_un_error(self):
        mgr = ConfigManager(self.ruta)
        cfg = mgr.load()
        self.assertEqual(mgr.last_error, "")  # primer arranque, nada que avisar
        self.assertEqual(cfg.model, AppConfig().model)
        self.assertFalse(self.copia_rota.exists())

    def test_archivo_valido_carga_sin_aviso(self):
        self.escribir(json.dumps(VALIDA).encode("utf-8"))
        mgr = ConfigManager(self.ruta)
        cfg = mgr.load()
        self.assertEqual(mgr.last_error, "")
        self.assertEqual(cfg.model, "medium")

    def test_tolera_la_marca_bom(self):
        """Un BOM al inicio ya no rompe la carga: es lo que dejan varios editores de Windows."""
        self.escribir(b"\xef\xbb\xbf" + json.dumps(VALIDA).encode("utf-8"))
        mgr = ConfigManager(self.ruta)
        cfg = mgr.load()
        self.assertEqual(mgr.last_error, "", "el BOM no deberia impedir leer la configuracion")
        self.assertEqual(cfg.model, "medium")
        self.assertEqual(cfg.vocab, "API Core, endpoint")


class TestConfigIlegible(BaseConfig):
    def test_json_roto_deja_constancia(self):
        self.escribir(b"{ esto no es json")
        mgr = ConfigManager(self.ruta)
        cfg = mgr.load()
        self.assertTrue(mgr.last_error, "una configuracion ilegible no puede cargarse en silencio")
        self.assertIn("config.json", mgr.last_error)
        self.assertEqual(cfg.model, AppConfig().model)  # sigue arrancando, con valores de fabrica

    def test_json_roto_se_aparta_una_copia(self):
        original = b"{ roto pero con mi vocabulario dentro"
        self.escribir(original)
        ConfigManager(self.ruta).load()
        self.assertTrue(self.copia_rota.exists(), "hay que conservar el archivo ilegible")
        self.assertEqual(self.copia_rota.read_bytes(), original)

    def test_guardar_despues_no_destruye_el_original(self):
        """El caso que de verdad importa: guardar tras un fallo no puede borrar lo que habia."""
        original = b"{ roto pero con mi vocabulario dentro"
        self.escribir(original)
        mgr = ConfigManager(self.ruta)
        cfg = mgr.load()
        mgr.save(cfg)  # el usuario abre Opciones y guarda
        self.assertNotEqual(self.ruta.read_bytes(), original)  # el archivo activo se sobrescribio
        self.assertEqual(self.copia_rota.read_bytes(), original)  # pero el contenido sigue recuperable

    def test_la_copia_no_se_rehace_en_cada_arranque(self):
        self.escribir(b"{ roto")
        ConfigManager(self.ruta).load()
        self.copia_rota.write_bytes(b"{ roto")  # simula que el usuario ya la tenia
        self.escribir(b"{ tambien roto pero distinto")
        mgr = ConfigManager(self.ruta)
        mgr.load()
        self.assertTrue(mgr.last_error, "sigue siendo ilegible: hay que avisar igual")
        self.assertEqual(self.copia_rota.read_bytes(), b"{ roto", "no debe pisar la primera copia")

    def test_guardar_bien_limpia_el_aviso(self):
        self.escribir(b"{ roto")
        mgr = ConfigManager(self.ruta)
        mgr.save(mgr.load())
        self.assertEqual(mgr.last_error, "")
        self.assertEqual(ConfigManager(self.ruta).load().model, AppConfig().model)


if __name__ == "__main__":
    unittest.main()
