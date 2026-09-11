"""El numero de hilos de CPU de config.json llega a WhisperModel; 0 deja el valor de la biblioteca.

Se sustituye faster_whisper por un modulo falso que apunta los argumentos y "falla" al cargar,
asi el hilo termina al momento y no se carga ningun modelo de verdad.
"""

import pathlib
import queue
import sys
import tempfile
import threading
import types
import unittest

from recorder.actions.notes import NotesSession
from recorder.config.schema import AppConfig
from recorder.engine.whisper_worker import TranscriberWorker


class TestCpuThreads(unittest.TestCase):
    def _argumentos_de_carga(self, cfg: AppConfig) -> dict:
        capturado = {}
        falso = types.ModuleType("faster_whisper")

        def WhisperModel(*args, **kwargs):
            capturado.update(kwargs)
            raise RuntimeError("modelo falso: no hace falta cargarlo")

        falso.WhisperModel = WhisperModel
        previo = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = falso
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cfg.notes_dir = tmp
                cfg.caps_dir = str(pathlib.Path(tmp) / "caps")
                worker = TranscriberWorker(
                    cfg, queue.Queue(), queue.Queue(), NotesSession(tmp), threading.Event()
                )
                worker.run()  # sin modelo, run() avisa y vuelve enseguida
        finally:
            if previo is None:
                sys.modules.pop("faster_whisper", None)
            else:
                sys.modules["faster_whisper"] = previo
        return capturado

    def test_por_defecto_se_deja_el_valor_de_la_biblioteca(self):
        self.assertEqual(AppConfig().cpu_threads, 0)
        self.assertEqual(self._argumentos_de_carga(AppConfig())["cpu_threads"], 0)

    def test_el_valor_configurado_llega_al_modelo(self):
        cfg = AppConfig()
        cfg.cpu_threads = 8
        self.assertEqual(self._argumentos_de_carga(cfg)["cpu_threads"], 8)

    def test_se_lee_desde_config_json(self):
        self.assertEqual(AppConfig.from_dict({"cpu_threads": 6}).cpu_threads, 6)
        self.assertEqual(AppConfig.from_dict({"model": "small"}).cpu_threads, 0)  # configs antiguas


if __name__ == "__main__":
    unittest.main()
