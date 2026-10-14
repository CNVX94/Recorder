"""`daily config` (cli/configurar.py) con respuestas guionizadas, sobre un config.json temporal.

Sin dispositivos de audio reales, sin detectar el hardware (perfil sintético en la caché, el
mismo que en test_dialogs) y sin pantallas ni ventanas de verdad. El asistente debe guardar
exactamente lo que guardaría la ventana ⚙ con los mismos valores (`apply_settings`), y
cancelar o salir sin guardar no debe tocar el archivo.
"""

import json
import pathlib
import tempfile
import unittest
from unittest import mock

from recorder.cli import configurar
from recorder.config import hardware
from recorder.config.hardware import HardwareProfile
from recorder.config.manager import ConfigManager
from recorder.config.options import AUTO_GPU, CAPTURE_LABELS, DEFAULT_DEV, WINDOW_PREFIX, apply_settings, settings_form
from recorder.config.schema import QUALITY_PRESETS, AppConfig
from tests.apoyo_cli import argumentos, consola_de_prueba, respuestas, solo_ascii

PANTALLAS = ["(todas las pantallas)", "Pantalla 1: 1920×1080 en (0, 0)"]
VENTANAS = ["Chat | Microsoft Teams"]
SALIDAS, MICROS = ["Altavoces", "Auriculares"], ["Micrófono"]
# i5-9500 de sobremesa, sin GPU: la recomendación es Media con 5 hilos.
PERFIL = HardwareProfile(
    cpu_name="Intel(R) Core(TM) i5-9500 CPU @ 3.00GHz", physical_cores=6, logical_cores=6,
    p_cores=6, avx2=True, ram_total_mb=16327, desktop=True,
)
# Posiciones (1-based) en el menú del asistente.
CARPETAS, AUDIO, CAPTURAS, CALIDAD, TODO, GUARDAR, SALIR = "1", "2", "3", "4", "5", "6", "7"


class CasoConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self.tmp.name)
        self.mgr = ConfigManager(self.raiz / "config.json")
        parches = [
            mock.patch.object(hardware, "_cache", PERFIL),
            mock.patch.object(configurar, "screen_labels", lambda: list(PANTALLAS)),
            mock.patch.object(configurar, "window_titles", lambda: list(VENTANAS)),
            mock.patch.object(configurar, "dispositivos_audio", lambda: (list(SALIDAS), list(MICROS))),
        ]
        for parche in parches:
            parche.start()
            self.addCleanup(parche.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def guardar(self, cfg: AppConfig) -> bytes:
        self.mgr.save(cfg)
        return self.mgr.path.read_bytes()

    def correr(self, *argv, ascii_mode=False):
        consola, buf = consola_de_prueba(ascii_mode)
        codigo = configurar.ejecutar(argumentos(configurar, *argv), consola, self.mgr)
        return codigo, buf.getvalue()

    def guardado(self) -> dict:
        return json.loads(self.mgr.path.read_text(encoding="utf-8"))


class TestAsistente(CasoConfig):
    def test_carpetas_guarda_lo_mismo_que_la_ventana(self):
        self.guardar(AppConfig())
        notas = str(self.raiz / "notas")
        with respuestas(CARPETAS, notas, "", " bloqueo , demo ", "s"):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        # lo que guardaría la ventana con los mismos valores en el formulario
        esperado = AppConfig()
        form = settings_form(esperado, PANTALLAS)
        form.notes_dir, form.keywords = notas, " bloqueo , demo "
        apply_settings(esperado, form, PANTALLAS)
        self.assertEqual(self.guardado(), esperado.to_dict())
        self.assertIn("Cambios", salida)
        self.assertIn("Carpeta de notas", salida)
        self.assertIn("próximo arranque", salida)  # la grabación abierta no recarga

    def test_audio_y_capturas_en_dos_secciones_antes_de_guardar(self):
        self.guardar(AppConfig())
        with respuestas(AUDIO, "2", "n", "n", CAPTURAS, "3", "1", "s"):
            # salida 2 = Altavoces, sin micrófono; no guardar aún; capturar la ventana; capturas apagadas; guardar
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        g = self.guardado()
        self.assertEqual((g["out_dev"], g["mic"], g["mic_dev"]), ("Altavoces", False, ""))
        self.assertEqual((g["window"], g["screen"]), (VENTANAS[0], 0))
        self.assertEqual(g["captures"], "off")
        self.assertIn(WINDOW_PREFIX + VENTANAS[0], salida)
        self.assertIn(DEFAULT_DEV, salida)
        self.assertIn("Capturas por palabra clave", salida)
        self.assertIn(CAPTURE_LABELS["off"], salida)
        self.assertIn(CAPTURE_LABELS["normal"], salida)  # en la tabla de cambios: antes → después

    def test_calidad_de_capturas_como_la_ventana(self):
        self.guardar(AppConfig(captures="light"))
        with respuestas(CAPTURAS, "", "4", "s"):  # misma pantalla; máxima calidad; guardar
            codigo, _ = self.correr()
        self.assertEqual(codigo, 0)
        esperado = AppConfig(captures="light")
        form = settings_form(esperado, PANTALLAS)
        form.captures = CAPTURE_LABELS["high"]
        apply_settings(esperado, form, PANTALLAS)
        self.assertEqual(self.guardado(), esperado.to_dict())
        self.assertEqual(self.guardado()["captures"], "high")

    def test_dispositivo_guardado_que_ya_no_se_detecta_sigue_elegible(self):
        self.guardar(AppConfig(out_dev="Cable virtual"))
        with respuestas(AUDIO, "", "", "", GUARDAR, SALIR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        self.assertIn("Cable virtual", salida)
        self.assertEqual(self.guardado()["out_dev"], "Cable virtual")  # Enter lo conservó

    def test_calidad_con_la_recomendacion(self):
        self.guardar(AppConfig(model="medium", beam_size=3, cpu_threads=0))
        with respuestas(CALIDAD, "", "s", "s"):
            # carpeta de whisper.cpp: Enter (vacía); usar recomendado: sí; guardar: sí
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        g = self.guardado()
        self.assertEqual((g["model"], g["beam_size"], g["device"], g["compute_type"], g["cpu_threads"]), ("small", 5, "cpu", "int8", 5))
        self.assertIn("Recomendado para este equipo: Media", salida)
        self.assertIn("Vacía: sin motor Vulkan.", salida)

    def test_calidad_a_mano(self):
        self.guardar(AppConfig())
        with respuestas(CALIDAD, "", "n", "3", "7", "s"):
            # sin whisper.cpp; no usar recomendado; Alta; 7 hilos; guardar
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        g = self.guardado()
        alta = QUALITY_PRESETS["alta"]
        self.assertEqual((g["model"], g["beam_size"], g["cpu_threads"]), (alta.model, alta.beam_size, 7))
        self.assertIn("Extra (no disponible en este equipo)", salida)  # sin GPU
        self.assertIn(alta.summary[:40], salida)
        self.assertIn("recomendado: 5 (6 núcleos)", salida)  # la pista de hilos
        self.assertNotIn("GPU de whisper.cpp", salida)  # sin carpeta no se pregunta

    def test_con_whispercpp_pregunta_gpu_y_flash_attention(self):
        self.guardar(AppConfig())
        carpeta = str(self.raiz / "wcpp")
        with respuestas(CALIDAD, carpeta, "n", "", "", "", "s", "s"):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        g = self.guardado()
        self.assertEqual((g["whispercpp_dir"], g["whispercpp_device"], g["whispercpp_flash_attn"]), (carpeta, -1, True))
        self.assertIn("No hay bin\\whisper-server.exe", salida)
        self.assertIn(AUTO_GPU, salida)

    def test_todo_sin_cambios_no_escribe(self):
        antes = self.guardar(AppConfig())
        # carpetas (3), audio (3), capturas (2), whisper.cpp (1), recomendado: no, calidad e hilos (2)
        with respuestas(TODO, "", "", "", "", "", "", "", "", "", "n", "", "", SALIR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        self.assertIn("Sin cambios.", salida)
        self.assertEqual(self.mgr.path.read_bytes(), antes)

    def test_cancelar_no_guarda(self):
        antes = self.guardar(AppConfig())
        with respuestas(CARPETAS, str(self.raiz / "otras")):  # y la entrada se cierra
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("Cancelado, no se guardó nada.", salida)
        self.assertEqual(self.mgr.path.read_bytes(), antes)

    def test_salir_sin_guardar_con_cambios(self):
        antes = self.guardar(AppConfig())
        with respuestas(CARPETAS, str(self.raiz / "otras"), "", "", "n", SALIR):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("No se guardó nada.", salida)
        self.assertEqual(self.mgr.path.read_bytes(), antes)

    def test_primer_arranque_crea_el_archivo_al_guardar(self):
        self.assertFalse(self.mgr.path.exists())
        with respuestas(CARPETAS, "", "", "demo", "s"):
            codigo, _ = self.correr()
        self.assertEqual(codigo, 0)
        self.assertEqual(self.guardado()["keywords"], ["demo"])

    def test_config_rota_no_se_guarda_encima(self):
        self.mgr.path.write_text("{ esto no es json", encoding="utf-8")
        with respuestas(CARPETAS, "x", "", "", "s"):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("No se pudo leer", salida)
        self.assertEqual(self.mgr.path.read_text(encoding="utf-8"), "{ esto no es json")


class TestBanderas(CasoConfig):
    def test_ver(self):
        self.guardar(AppConfig(window="Chat | Microsoft Teams", cpu_threads=5, fixes={"cuba": "QA"}))
        codigo, salida = self.correr("--ver")
        self.assertEqual(codigo, 0)
        for texto in ("Carpeta de notas", "Media: small, haz 5, CPU, int8", WINDOW_PREFIX + "Chat | Microsoft Teams",
                      "Hilos de CPU", "1 corrección", "10 frases", AUTO_GPU, "Capturas por palabra clave",
                      CAPTURE_LABELS["normal"]):
            self.assertIn(texto, salida)

    def test_ver_en_ascii_no_trae_emoji(self):
        self.guardar(AppConfig())
        codigo, salida = self.correr("--ver", ascii_mode=True)
        self.assertEqual(codigo, 0)
        self.assertTrue(solo_ascii(salida), salida)
        self.assertIn("Salida a capturar OUT", salida)

    def test_ver_con_config_rota_avisa(self):
        self.mgr.path.write_text("{", encoding="utf-8")
        codigo, salida = self.correr("--ver")
        self.assertEqual(codigo, 1)
        self.assertIn("valores de fábrica", salida)

    def test_editor_crea_el_archivo_si_falta_y_lo_abre(self):
        with mock.patch("os.startfile", create=True) as startfile:
            codigo, salida = self.correr("--editor")
        self.assertEqual(codigo, 0)
        startfile.assert_called_once_with(self.mgr.path)
        self.assertEqual(self.guardado(), AppConfig().to_dict())
        self.assertIn("Abriendo", salida)

    def test_editor_no_pisa_el_archivo_existente(self):
        antes = self.guardar(AppConfig(cpu_threads=3))
        with mock.patch("os.startfile", create=True):
            self.assertEqual(self.correr("--editor")[0], 0)
        self.assertEqual(self.mgr.path.read_bytes(), antes)

    def test_editor_sin_programa_asociado(self):
        self.guardar(AppConfig())
        with mock.patch("os.startfile", create=True, side_effect=OSError("sin asociación")):
            codigo, salida = self.correr("--editor")
        self.assertEqual(codigo, 1)
        self.assertIn("No se pudo abrir", salida)

    def test_recomendado_aplica_y_guarda(self):
        self.guardar(AppConfig(model="medium", beam_size=3, cpu_threads=0, vocab="QA"))
        with respuestas():  # no pregunta nada
            codigo, salida = self.correr("--recomendado")
        self.assertEqual(codigo, 0)
        g = self.guardado()
        self.assertEqual((g["model"], g["beam_size"], g["cpu_threads"], g["vocab"]), ("small", 5, 5, "QA"))
        self.assertIn("Equipo:      Intel Core i5-9500", salida)
        self.assertIn("Recomendado: Media (small, haz 5, CPU, int8, 5 hilos) [estimada]", salida)
        self.assertIn("Motivo:", salida)
        self.assertIn("Aplicado en", salida)

    def test_recomendado_con_config_rota_no_aplica(self):
        self.mgr.path.write_text("{", encoding="utf-8")
        codigo, _ = self.correr("--recomendado")
        self.assertEqual(codigo, 1)
        self.assertEqual(self.mgr.path.read_text(encoding="utf-8"), "{")


class TestQueCambio(unittest.TestCase):
    def test_diferencias_legibles(self):
        antes = AppConfig()
        despues = AppConfig(out_dev="Altavoces", mic=False, keywords=[], whispercpp_device=1, window="Excel", fixes={"a": "b"}, captures="off")
        cambios = configurar.diferencias(antes, despues)
        self.assertEqual(cambios, [
            ("Palabras clave", "pendiente, bloqueo, captura", "(ninguna)"),
            ("Transcribir el micrófono", "sí", "no"),
            ("Salida a capturar", DEFAULT_DEV, "Altavoces"),
            ("Ventana a capturar", "(ninguna: se captura la pantalla)", "Excel"),
            ("Capturas por palabra clave", CAPTURE_LABELS["normal"], CAPTURE_LABELS["off"]),
            ("GPU de whisper.cpp", AUTO_GPU, "1"),
            ("Correcciones", "(ninguna)", "a=b"),
        ])
        self.assertEqual(configurar.diferencias(antes, AppConfig()), [])

    def test_resumen(self):
        filas = dict(configurar.filas_resumen(AppConfig(screen=2, mic=False, whispercpp_dir="C:/w")))
        self.assertEqual(filas["Qué capturar 📸"], "Pantalla 2")
        self.assertEqual(filas["Micrófono 🎤"], "no se transcribe")
        self.assertEqual(filas["whisper.cpp"], "C:/w")
        self.assertEqual(filas["Calidad"], "Media: small, haz 5, CPU, int8")


if __name__ == "__main__":
    unittest.main()
