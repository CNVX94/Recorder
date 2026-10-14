"""`daily calibrar` (cli/calibrar.py) con respuestas guionizadas, sobre un config.json temporal.

El menú edita el formulario y guarda solo con «Guardar y salir»; el sandbox prueba con lo
escrito ahora, sin guardar; `--probar` devuelve 0 o 1 según el veredicto. Sin modelo ni ventana.
"""

import json
import pathlib
import tempfile
import unittest

from recorder.cli import calibrar
from recorder.config.manager import ConfigManager
from recorder.config.schema import AppConfig
from recorder.filters.tuning import COMMON_IGNORE, apply_tuning, tuning_form
from tests.apoyo_cli import argumentos, consola_de_prueba, respuestas, solo_ascii

# Posiciones (1-based) en el menú.
VOCAB, IGNORAR, FIXES, UMBRALES, PROBAR, GUARDAR, SALIR = "1", "2", "3", "4", "5", "6", "7"


class CasoCalibrar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mgr = ConfigManager(pathlib.Path(self.tmp.name) / "config.json")
        self.cfg = AppConfig(fixes={"cuba": "QA"})
        self.mgr.save(self.cfg)
        self.antes = self.mgr.path.read_bytes()

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, *argv, ascii_mode=False):
        consola, buf = consola_de_prueba(ascii_mode)
        codigo = calibrar.ejecutar(argumentos(calibrar, *argv), consola, self.mgr)
        return codigo, buf.getvalue()

    def guardado(self) -> dict:
        return json.loads(self.mgr.path.read_text(encoding="utf-8"))


class TestMenu(CasoCalibrar):
    def test_edita_y_guarda_lo_mismo_que_la_ventana(self):
        with respuestas(VOCAB, "  Términos: QA, IIS  ", FIXES, "cuba=QA; ayayas=IIS", UMBRALES, "0.45", "", "", GUARDAR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        esperado = AppConfig(fixes={"cuba": "QA"})
        form = tuning_form(esperado)
        form.vocab, form.fixes, form.no_speech_threshold = "  Términos: QA, IIS  ", "cuba=QA; ayayas=IIS", 0.45
        apply_tuning(esperado, form)
        self.assertEqual(self.guardado(), esperado.to_dict())
        self.assertEqual(self.guardado()["vocab"], "Términos: QA, IIS")  # recortado
        self.assertIn("2 correcciones", salida)
        self.assertIn("Calibración guardada", salida)
        self.assertIn("próximo arranque", salida)

    def test_menu_ensena_lo_que_hay_ahora(self):
        with respuestas(SALIR):
            _, salida = self.correr()
        self.assertIn("(vacío)", salida)  # vocabulario de fábrica
        self.assertIn("9 frases", salida)
        self.assertIn("1 corrección", salida)
        self.assertIn("silencio 0.6 · confianza -1.0 · anti-bucles 2.4", salida)

    def test_frases_a_ignorar_con_las_comunes(self):
        with respuestas(IGNORAR, "-", "s", GUARDAR):  # vaciar la lista, añadir las comunes, guardar
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        self.assertEqual(self.guardado()["ignore"], COMMON_IGNORE)
        self.assertIn(f"{len(COMMON_IGNORE)} frases en la lista negra", salida)

    def test_umbral_fuera_de_rango_se_vuelve_a_pedir(self):
        with respuestas(UMBRALES, "5", "0.5", "-3", "", "", GUARDAR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        self.assertIn("Debe estar entre 0.1 y 0.95.", salida)
        self.assertIn("Debe estar entre -2.5 y -0.2.", salida)
        g = self.guardado()
        self.assertEqual((g["no_speech_threshold"], g["logprob_threshold"], g["compression_ratio_threshold"]), (0.5, -1.0, 2.4))

    def test_guardar_sin_cambios_no_escribe(self):
        with respuestas(GUARDAR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        self.assertIn("Sin cambios.", salida)
        self.assertEqual(self.mgr.path.read_bytes(), self.antes)

    def test_salir_sin_guardar(self):
        with respuestas(VOCAB, "QA", SALIR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("No se guardó nada.", salida)
        self.assertEqual(self.mgr.path.read_bytes(), self.antes)
        with respuestas(SALIR):
            self.assertEqual(self.correr()[0], 0)  # sin cambios, salir es normal

    def test_cancelar_no_guarda(self):
        with respuestas(VOCAB, "QA", UMBRALES):  # y la entrada se cierra en el primer umbral
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("Cancelado, no se guardó nada.", salida)
        self.assertEqual(self.mgr.path.read_bytes(), self.antes)

    def test_config_rota(self):
        self.mgr.path.write_text("{", encoding="utf-8")
        codigo, salida = self.correr("--probar", "hola")
        self.assertEqual(codigo, 2)
        self.assertIn("No se pudo leer", salida)


class TestSandbox(CasoCalibrar):
    def test_veredictos_con_lo_guardado(self):
        with respuestas(PROBAR, "Hoy desplegamos. ¡Suscríbete!", "Hay un bloqueo en cuba.", "", SALIR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        self.assertIn("frase> ", salida)
        self.assertIn("⛔ DESCARTADA: Contiene una frase de la lista negra de alucinaciones.", salida)
        self.assertIn('✅ ACEPTADA: "Hay un bloqueo en QA."  (📸 Palabras clave detectadas: bloqueo)', salida)

    def test_prueba_lo_escrito_ahora_sin_guardar(self):
        # sin lista negra en el formulario, «Suscríbete» pasa; pero al salir sin guardar el archivo no cambia
        with respuestas(IGNORAR, "-", "n", PROBAR, "¡Suscríbete!", "", SALIR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn('✅ ACEPTADA: "¡Suscríbete!"', salida)
        self.assertEqual(self.mgr.path.read_bytes(), self.antes)

    def test_frase_de_ejemplo(self):
        with respuestas(PROBAR, calibrar.EJEMPLO, "", SALIR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        self.assertTrue("ACEPTADA" in salida or "DESCARTADA" in salida)

    def test_cancelar_dentro_del_sandbox(self):
        with respuestas(PROBAR, "una frase"):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("Cancelado", salida)


class TestProbar(CasoCalibrar):
    def test_codigos_de_salida(self):
        with respuestas():  # no pregunta nada
            aceptada, salida = self.correr("--probar", "Hay un bloqueo en cuba.")
            descartada, salida2 = self.correr("--probar", "Gracias por ver. ¡Suscríbete!")
        self.assertEqual((aceptada, descartada), (0, 1))
        self.assertIn('✅ ACEPTADA: "Hay un bloqueo en QA."', salida)
        self.assertIn("⛔ DESCARTADA", salida2)

    def test_en_ascii_no_trae_emoji(self):
        _, salida = self.correr("--probar", "Hay un bloqueo en cuba.", ascii_mode=True)
        self.assertTrue(solo_ascii(salida), salida)
        self.assertIn('OK ACEPTADA: "Hay un bloqueo en QA."  ([cap] Palabras clave detectadas: bloqueo)', salida)
        _, salida = self.correr("--probar", "¡Suscríbete!", ascii_mode=True)
        self.assertIn("x DESCARTADA", salida)


if __name__ == "__main__":
    unittest.main()
