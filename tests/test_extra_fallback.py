"""Pedir el preset Extra en un equipo sin GPU no puede descargar ni ejecutar large-v3 en CPU.

WhisperModel descarga los pesos ANTES de validar el dispositivo. Si la caída a CPU se decide
después del fallo, ya se han bajado varios GB de un modelo que en CPU va a un tercio del
tiempo real. Estas pruebas fijan que la decisión se toma antes de construir el modelo.
"""

import queue
import sys
import tempfile
import threading
import types
import unittest

from recorder.actions.notes import NotesSession
from recorder.config.schema import AppConfig, apply_preset, resolve_runtime
from recorder.engine import whisper_worker as ww


class TestResolveRuntime(unittest.TestCase):
    def test_extra_sin_gpu_cae_al_preset_de_cpu_entero(self):
        cfg = AppConfig()
        apply_preset(cfg, "extra")
        model, device, _ct, _beam, aviso = resolve_runtime(cfg, 0)
        self.assertEqual(device, "cpu")
        self.assertNotEqual(model, "large-v3", "large-v3 en CPU no sirve para tiempo real")
        self.assertTrue(aviso, "hay que avisar de la caída")

    def test_extra_con_gpu_se_respeta(self):
        cfg = AppConfig()
        apply_preset(cfg, "extra")
        model, device, _ct, _beam, aviso = resolve_runtime(cfg, 1)
        self.assertEqual((model, device), ("large-v3", "cuda"))
        self.assertEqual(aviso, "")

    def test_un_preset_de_cpu_no_se_toca(self):
        cfg = AppConfig()
        apply_preset(cfg, "alta")
        antes = (cfg.model, cfg.device, cfg.compute_type, cfg.beam_size)
        model, device, ct, beam, aviso = resolve_runtime(cfg, 0)
        self.assertEqual((model, device, ct, beam), antes)
        self.assertEqual(aviso, "")


class TestWorkerNoPideLargeV3(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pedidos = []

        previo = sys.modules.get("faster_whisper")
        falso = types.ModuleType("faster_whisper")

        def WhisperModel(nombre, **kw):
            self.pedidos.append((nombre, kw.get("device")))
            return object()

        falso.WhisperModel = WhisperModel
        sys.modules["faster_whisper"] = falso
        self.addCleanup(
            lambda: sys.modules.__setitem__("faster_whisper", previo)
            if previo else sys.modules.pop("faster_whisper", None)
        )

        original = ww.detect_cuda_device_count
        ww.detect_cuda_device_count = lambda: 0  # equipo sin GPU
        self.addCleanup(lambda: setattr(ww, "detect_cuda_device_count", original))

    def arrancar(self, cfg):
        ui = queue.Queue()
        stop = threading.Event()
        stop.set()  # construye el modelo y sale del bucle al instante
        worker = ww.TranscriberWorker(cfg, queue.Queue(), ui, NotesSession(self.tmp.name), stop)
        worker.run()
        estados = []
        while not ui.empty():
            m = ui.get()
            if m[0] == "status":
                estados.append(m[1])
        return worker, estados

    def test_extra_sin_gpu_nunca_pide_large_v3(self):
        cfg = AppConfig()
        apply_preset(cfg, "extra")
        worker, estados = self.arrancar(cfg)
        modelos = [n for n, _ in self.pedidos]
        self.assertTrue(self.pedidos, "no se llegó a construir ningún modelo")
        self.assertNotIn("large-v3", modelos, "se habría descargado large-v3 para usarlo en CPU")
        self.assertTrue(all(d == "cpu" for _, d in self.pedidos))
        self.assertTrue(any("GPU" in e for e in estados), estados)

    def test_extra_sin_gpu_usa_el_haz_del_preset_de_cpu(self):
        cfg = AppConfig()
        apply_preset(cfg, "extra")
        cfg.beam_size = 9  # valor distinto para detectar si se respeta el resuelto
        worker, _ = self.arrancar(cfg)
        cpu = AppConfig()
        apply_preset(cpu, "alta")
        self.assertEqual(worker.beam_size, cpu.beam_size)


if __name__ == "__main__":
    unittest.main()
