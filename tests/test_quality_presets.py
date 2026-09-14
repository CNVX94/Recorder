"""Presets de calidad de transcripcion (Baja/Media/Alta/Extra).

Las politicas son funciones puras: mapear preset -> parametros, reconocer que preset
corresponde a una configuracion guardada, y decidir si un preset es viable en el
hardware detectado (sin necesitar GPU real: se le pasa el numero de GPUs como dato).
La ultima parte prueba que whisper_worker cae a CPU sin romper el hilo si se pide GPU
y no hay, con un `faster_whisper` falso, igual que test_worker_resilience.py.
"""

import pathlib
import queue
import sys
import tempfile
import threading
import time
import types
import unittest

from recorder.actions.notes import NotesSession
from recorder.config.schema import (
    CUSTOM_PRESET,
    PRESET_ORDER,
    QUALITY_PRESETS,
    AppConfig,
    apply_preset,
    detect_cuda_device_count,
    preset_availability,
    preset_key_for_config,
)
from recorder.engine.whisper_worker import TranscriberWorker


class TestMapeoDePresets(unittest.TestCase):
    """Que modelo/haz/dispositivo/precision usa cada preset (docs/rendimiento.md y
    docs/hardware-y-modelos.md dictan el mapeo; aqui solo se fija por escrito)."""

    def test_hay_exactamente_cuatro_presets_en_orden_de_calidad(self):
        self.assertEqual(PRESET_ORDER, ["baja", "media", "alta", "extra"])
        self.assertEqual(set(QUALITY_PRESETS), set(PRESET_ORDER))

    def test_baja_y_media_corren_en_cpu(self):
        for key in ("baja", "media"):
            preset = QUALITY_PRESETS[key]
            self.assertEqual(preset.model, "small")
            self.assertEqual(preset.device, "cpu")
            self.assertEqual(preset.compute_type, "int8")
            self.assertFalse(preset.requires_cuda)
        self.assertEqual(QUALITY_PRESETS["baja"].beam_size, 1)
        self.assertEqual(QUALITY_PRESETS["media"].beam_size, 5)

    def test_alta_es_large_v3_turbo_en_cpu(self):
        preset = QUALITY_PRESETS["alta"]
        self.assertEqual(preset.model, "large-v3-turbo")
        self.assertEqual(preset.beam_size, 5)
        self.assertEqual(preset.device, "cpu")
        self.assertEqual(preset.compute_type, "int8")
        self.assertFalse(preset.requires_cuda)

    def test_extra_es_large_v3_en_gpu(self):
        preset = QUALITY_PRESETS["extra"]
        self.assertEqual(preset.model, "large-v3")
        self.assertEqual(preset.device, "cuda")
        self.assertEqual(preset.compute_type, "float16")
        self.assertTrue(preset.requires_cuda)


class TestReconocerElPresetDeUnaConfiguracion(unittest.TestCase):
    def test_la_configuracion_de_fabrica_es_un_preset_valido(self):
        # AppConfig() por defecto: small, haz 5, cpu, int8 -> coincide con Media.
        self.assertEqual(preset_key_for_config(AppConfig()), "media")

    def test_large_v3_turbo_beam_5_en_cpu_se_reconoce_como_alta(self):
        cfg = AppConfig(model="large-v3-turbo", beam_size=5, device="cpu", compute_type="int8")
        self.assertEqual(preset_key_for_config(cfg), "alta")

    def test_una_combinacion_que_no_coincide_es_personalizada(self):
        cfg = AppConfig(model="large-v3-turbo", beam_size=3, device="cpu", compute_type="int8")
        self.assertIsNone(preset_key_for_config(cfg))

    def test_config_json_vieja_sin_device_ni_compute_type_sigue_reconociendose(self):
        """Un config.json de antes de este cambio no tiene 'device' ni 'compute_type'."""
        vieja = AppConfig.from_dict({"model": "large-v3-turbo", "beam_size": 5})
        self.assertEqual(vieja.device, "cpu")  # comportamiento de siempre, sin GPU
        self.assertEqual(vieja.compute_type, "int8")
        self.assertEqual(preset_key_for_config(vieja), "alta")

    def test_config_json_vieja_sin_ningun_campo_de_calidad_cae_en_media(self):
        vieja = AppConfig.from_dict({"notes_dir": "C:/Dailies"})
        self.assertEqual(preset_key_for_config(vieja), "media")


class TestAplicarUnPreset(unittest.TestCase):
    def test_aplicar_extra_cambia_los_cuatro_campos(self):
        cfg = AppConfig()  # arranca en Media
        apply_preset(cfg, "extra")
        self.assertEqual(cfg.model, "large-v3")
        self.assertEqual(cfg.beam_size, 5)
        self.assertEqual(cfg.device, "cuda")
        self.assertEqual(cfg.compute_type, "float16")

    def test_aplicar_un_preset_no_toca_el_resto_de_la_configuracion(self):
        cfg = AppConfig()
        cfg.vocab = "mi vocabulario"
        cfg.notes_dir = "D:/mis-notas"
        apply_preset(cfg, "baja")
        self.assertEqual(cfg.vocab, "mi vocabulario")
        self.assertEqual(cfg.notes_dir, "D:/mis-notas")

    def test_personalizado_no_es_una_clave_aplicable(self):
        with self.assertRaises(KeyError):
            apply_preset(AppConfig(), CUSTOM_PRESET)


class TestViabilidadSegunElHardware(unittest.TestCase):
    """Funcion pura: recibe el numero de GPUs ya detectado, no pregunta al hardware."""

    def test_baja_media_y_alta_estan_siempre_disponibles(self):
        for key in ("baja", "media", "alta"):
            self.assertTrue(preset_availability(key, cuda_device_count=0).available)
            self.assertTrue(preset_availability(key, cuda_device_count=2).available)

    def test_extra_no_esta_disponible_sin_gpu(self):
        result = preset_availability("extra", cuda_device_count=0)
        self.assertFalse(result.available)
        self.assertTrue(result.reason)  # explica por que, no se queda muda

    def test_extra_esta_disponible_con_gpu(self):
        result = preset_availability("extra", cuda_device_count=1)
        self.assertTrue(result.available)
        self.assertEqual(result.reason, "")


class TestDeteccionDeCuda(unittest.TestCase):
    """detect_cuda_device_count no necesita torch ni GPU real para no romperse."""

    def _con_ctranslate2_falso(self, ctranslate2_falso_o_excepcion):
        previo = sys.modules.get("ctranslate2")
        if isinstance(ctranslate2_falso_o_excepcion, Exception):
            falso = types.ModuleType("ctranslate2")

            def revienta():
                raise ctranslate2_falso_o_excepcion

            falso.get_cuda_device_count = revienta
        else:
            falso = ctranslate2_falso_o_excepcion
        sys.modules["ctranslate2"] = falso
        try:
            return detect_cuda_device_count()
        finally:
            if previo is None:
                sys.modules.pop("ctranslate2", None)
            else:
                sys.modules["ctranslate2"] = previo

    def test_sin_gpu_devuelve_cero(self):
        falso = types.ModuleType("ctranslate2")
        falso.get_cuda_device_count = lambda: 0
        self.assertEqual(self._con_ctranslate2_falso(falso), 0)

    def test_con_gpu_devuelve_el_numero_real(self):
        falso = types.ModuleType("ctranslate2")
        falso.get_cuda_device_count = lambda: 2
        self.assertEqual(self._con_ctranslate2_falso(falso), 2)

    def test_si_ctranslate2_falla_no_rompe_se_trata_como_sin_gpu(self):
        self.assertEqual(self._con_ctranslate2_falso(RuntimeError("driver roto")), 0)


class TestWorkerCaeACpuSinGpu(unittest.TestCase):
    """El preset Extra pide device='cuda'; sin GPU, el hilo de transcripcion no debe morir."""

    def _instalar_faster_whisper_falso(self, llamadas: list):
        def WhisperModel(*args, **kwargs):
            llamadas.append(kwargs)
            if kwargs.get("device") == "cuda":
                raise RuntimeError("no cuda-capable device is detected")
            return object()  # modelo falso: la cola queda vacia, no se usa mas

        falso = types.ModuleType("faster_whisper")
        falso.WhisperModel = WhisperModel
        previo = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = falso

        def restaurar():
            if previo is None:
                sys.modules.pop("faster_whisper", None)
            else:
                sys.modules["faster_whisper"] = previo

        self.addCleanup(restaurar)

    def _worker_con_cfg(self, cfg: AppConfig) -> TranscriberWorker:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        cfg.notes_dir = tmp.name
        cfg.caps_dir = str(pathlib.Path(tmp.name) / "caps")
        return TranscriberWorker(
            cfg, queue.Queue(), queue.Queue(), NotesSession(tmp.name), threading.Event()
        )

    def test_gpu_detectada_que_no_carga_reintenta_en_cpu_sin_reventar_el_hilo(self):
        """Hay GPU pero no arranca (driver, VRAM): se reintenta el mismo modelo en CPU.

        Es el unico caso en que intentar CUDA primero es correcto. Sin GPU detectada, el worker
        cae al preset de CPU antes de construir nada, porque WhisperModel descarga los pesos
        antes de validar el dispositivo: ver tests/test_extra_fallback.py.
        """
        import recorder.engine.whisper_worker as ww
        original = ww.detect_cuda_device_count
        ww.detect_cuda_device_count = lambda: 1  # simula una GPU presente
        self.addCleanup(lambda: setattr(ww, "detect_cuda_device_count", original))
        llamadas = []
        self._instalar_faster_whisper_falso(llamadas)
        cfg = AppConfig(model="large-v3", beam_size=5, device="cuda", compute_type="float16")
        worker = self._worker_con_cfg(cfg)

        hilo = threading.Thread(target=worker.run, daemon=True)
        hilo.start()
        fin = time.time() + 4
        while time.time() < fin and len(llamadas) < 2:
            time.sleep(0.05)
        worker.stop_event.set()
        hilo.join(timeout=2)

        self.assertFalse(hilo.is_alive(), "el hilo debe terminar limpio, no reventar")
        self.assertEqual(len(llamadas), 2, "debe intentar cuda y despues cpu")
        self.assertEqual(llamadas[0]["device"], "cuda")
        self.assertEqual(llamadas[1]["device"], "cpu")
        self.assertEqual(llamadas[1]["compute_type"], "int8")

        mensajes = []
        while not worker.ui_queue.empty():
            mensajes.append(worker.ui_queue.get())
        textos = [m[1] for m in mensajes if m[0] == "status"]
        self.assertTrue(any("GPU" in t and "CPU" in t for t in textos), textos)

    def test_preset_alta_en_cpu_no_intenta_gpu_ni_avisa(self):
        llamadas = []
        self._instalar_faster_whisper_falso(llamadas)
        cfg = AppConfig(model="large-v3-turbo", beam_size=5, device="cpu", compute_type="int8")
        worker = self._worker_con_cfg(cfg)
        worker.stop_event.set()  # que no entre al bucle: solo interesa la carga del modelo
        worker.run()

        self.assertEqual(len(llamadas), 1)
        self.assertEqual(llamadas[0]["device"], "cpu")
        mensajes = []
        while not worker.ui_queue.empty():
            mensajes.append(worker.ui_queue.get())
        textos = [m[1] for m in mensajes if m[0] == "status"]
        self.assertFalse(any("GPU no disponible" in t for t in textos), textos)


if __name__ == "__main__":
    unittest.main()
