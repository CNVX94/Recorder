"""Los tres diálogos abren, guardan y cierran bajo una raíz Tk oculta.

No comprueban el aspecto: comprueban que cada ventana se construye con una configuración, que
Guardar llama al callback de la ventana principal con lo esperado y que la ventana desaparece.
Sin dispositivos de audio reales (PyAudio falso), sin detectar el hardware (perfil sintético en
la caché), sin tocar config.json (el diálogo nunca escribe: guarda la ventana principal a través
del callback) y con las notas en una carpeta temporal. Si no hay pantalla para Tk, se omiten.
"""

import pathlib
import tempfile
import tkinter as tk
import unittest
from unittest import mock

from recorder.config import hardware
from recorder.config.hardware import HardwareProfile
from recorder.config.options import DEFAULT_DEV, WINDOW_PREFIX
from recorder.config.schema import AppConfig
from recorder.filters.tuning import COMMON_IGNORE
from recorder.ui.dialogs import settings_dialog
from recorder.ui.dialogs.digest_dialog import DigestDialog
from recorder.ui.dialogs.settings_dialog import SettingsDialog
from recorder.ui.dialogs.tuning_dialog import TuningDialog

PANTALLAS = ["(todas las pantallas)", "Pantalla 1: 1920×1080 en (0, 0)"]
VENTANAS = ["Chat | Microsoft Teams"]
# i5-9500 de sobremesa, sin GPU: la recomendación es Media con 5 hilos.
PERFIL = HardwareProfile(
    cpu_name="Intel(R) Core(TM) i5-9500 CPU @ 3.00GHz", physical_cores=6, logical_cores=6,
    p_cores=6, avx2=True, ram_total_mb=16327, desktop=True,
)
NOTA = "# Daily 2026-09-08 10:20\n\n- **10:20:08** Primera frase larga sobre el despliegue.\n- **10:55:12** Otra frase de otro tramo.\n"


class PyAudioFalso:
    """Lo justo de PyAudio para `wasapi_devices`: una salida y un micrófono WASAPI."""

    def get_host_api_info_by_type(self, _tipo):
        return {"index": 0}

    def get_device_info_generator(self):
        yield {"name": "Altavoces", "hostApi": 0, "maxOutputChannels": 2, "maxInputChannels": 0}
        yield {"name": "Micrófono", "hostApi": 0, "maxOutputChannels": 0, "maxInputChannels": 1}


class CasoTk(unittest.TestCase):
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


class TestSettingsDialog(CasoTk):
    def abrir(self, cfg, on_save=lambda *_: None):
        # Perfil ya en caché: no se lanza la detección en otro hilo ni se consulta CUDA.
        with mock.patch.object(hardware, "_cache", PERFIL), \
             mock.patch.object(settings_dialog, "screen_labels", lambda: list(PANTALLAS)), \
             mock.patch.object(settings_dialog, "window_titles", lambda: list(VENTANAS)):
            return SettingsDialog(self.root, cfg, PyAudioFalso(), on_save=on_save)

    def test_abre_con_los_valores_actuales_y_cierra(self):
        cfg = AppConfig()
        d = self.abrir(cfg)
        self.assertTrue(d.winfo_exists())
        self.assertEqual((d.v_out_dev.get(), d.v_mic_dev.get()), (DEFAULT_DEV, DEFAULT_DEV))
        self.assertEqual(d.v_screen.get(), PANTALLAS[0])
        self.assertEqual(d.v_quality.get(), "Media")
        self.assertTrue(d.v_wcpp_status.get().startswith("Vacía: sin motor Vulkan."))
        self.assertEqual(d.v_threads_hint.get(), "0 = 4 de la biblioteca · recomendado: 5 (6 núcleos)")
        self.assertTrue(d.v_rec.get().startswith("Recomendado para este equipo: Media"))
        # el selector de captura lista las pantallas y las ventanas abiertas
        menu = d.om_target["menu"]
        etiquetas = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1)]
        self.assertEqual(etiquetas, PANTALLAS + [WINDOW_PREFIX + VENTANAS[0]])
        d.destroy()
        self.assertFalse(d.winfo_exists())

    def test_guardar_avisa_de_lo_que_cambio_y_cierra(self):
        cfg = AppConfig()
        llamadas = []
        d = self.abrir(cfg, on_save=lambda c, notas, dispositivos: llamadas.append((c, notas, dispositivos)))
        with tempfile.TemporaryDirectory() as tmp:
            d.v_notes.set(tmp)
            d.v_mic.set(False)
            d.v_screen.set(WINDOW_PREFIX + VENTANAS[0])
            d.v_threads.set("7")
            d._save()
            self.assertEqual(llamadas, [(cfg, True, True)])
            self.assertEqual((cfg.notes_dir, cfg.mic, cfg.window, cfg.cpu_threads), (tmp, False, VENTANAS[0], 7))
        self.assertFalse(d.winfo_exists())

    def test_guardar_sin_cambios_no_avisa(self):
        cfg = AppConfig()
        antes = cfg.to_dict()
        llamadas = []
        d = self.abrir(cfg, on_save=lambda c, notas, dispositivos: llamadas.append((notas, dispositivos)))
        d._save()
        self.assertEqual(llamadas, [(False, False)])
        self.assertEqual(cfg.to_dict(), antes)

    def test_usar_recomendado(self):
        cfg = AppConfig(model="medium", beam_size=3, cpu_threads=0)
        d = self.abrir(cfg)
        self.assertEqual(d.v_quality.get(), "Personalizado")
        d._use_recommended()
        self.assertEqual((d.v_quality.get(), d.v_threads.get()), ("Media", "5"))
        d._save()
        self.assertEqual((cfg.model, cfg.beam_size, cfg.cpu_threads), ("small", 5, 5))


class TestTuningDialog(CasoTk):
    def test_abre_prueba_y_cierra(self):
        cfg = AppConfig(fixes={"cuba": "QA"})
        d = TuningDialog(self.root, cfg, on_save=lambda c: None)
        self.assertEqual(d.var_fixes.get(), "cuba=QA")
        self.assertTrue(d.var_test_result.get().startswith("⛔ DESCARTADA"))  # la frase de ejemplo trae «Suscríbete»
        d.var_ignore.set("")
        d._run_test()
        self.assertEqual(d.var_test_result.get(), '✅ ACEPTADA: "Desplegamos en QA y en el ayayas. ¡Suscríbete!"')
        d._append_common_ignore()
        for frase in COMMON_IGNORE:
            self.assertIn(frase, d.var_ignore.get())
        self.assertTrue(d.var_test_result.get().startswith("⛔ DESCARTADA"))
        d.destroy()
        self.assertFalse(d.winfo_exists())

    def test_guardar_vuelca_y_cierra(self):
        cfg = AppConfig()
        guardadas = []
        d = TuningDialog(self.root, cfg, on_save=guardadas.append)
        d.var_vocab.set("  Términos: QA, IIS  ")
        d.var_fixes.set("cuba=QA; ayayas=IIS")
        d.var_no_speech.set(0.45)
        d._save_changes()
        self.assertEqual(guardadas, [cfg])
        self.assertEqual(cfg.vocab, "Términos: QA, IIS")
        self.assertEqual(cfg.fixes, {"cuba": "QA", "ayayas": "IIS"})
        self.assertEqual(cfg.no_speech_threshold, 0.45)
        self.assertFalse(d.winfo_exists())


class TestDigestDialog(CasoTk):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = AppConfig(notes_dir=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sin_notas_abre_con_el_aviso_y_cierra(self):
        d = DigestDialog(self.root, self.cfg)
        self.assertEqual(d.notas, [])
        d.destroy()
        self.assertFalse(d.winfo_exists())

    def test_con_notas_previsualiza_y_genera_sin_tocar_el_original(self):
        src = pathlib.Path(self.tmp.name) / "daily_2026-09-08_10-20.md"
        src.write_text(NOTA, encoding="utf-8")
        d = DigestDialog(self.root, self.cfg, active_note=src)
        self.assertEqual(d.lista.size(), 1)
        self.assertTrue(d.lista.get(0).endswith("● en curso"))
        self.assertIn("2 bloques", d.var_stats.get())  # cada 15 min por defecto: 10:15 - 10:30 y 10:45 - 11:00
        self.assertIn("## 10:15 - 10:30", d.preview.get("1.0", "end"))
        d._generar()
        self.assertTrue(d.var_estado.get().startswith("✅ Creada daily_2026-09-08_10-20_sintesis-15min.md"))
        self.assertEqual(src.read_text(encoding="utf-8"), NOTA)  # el original sigue intacto
        self.assertTrue((src.parent / "daily_2026-09-08_10-20_sintesis-15min.md").exists())
        d.destroy()
        self.assertFalse(d.winfo_exists())


if __name__ == "__main__":
    unittest.main()
