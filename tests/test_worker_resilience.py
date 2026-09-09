"""Un fallo en un fragmento no debe costar el resto de la reunion.

Estas pruebas montan el hilo de transcripcion con un modelo falso, asi que no cargan
Whisper ni tocan el audio.
"""

import pathlib
import queue
import sys
import tempfile
import threading
import time
import types
import unittest
from types import SimpleNamespace as S

from recorder.actions.notes import NotesSession
from recorder.config.schema import AppConfig
from recorder.engine import whisper_worker as ww
from recorder.engine.whisper_worker import TranscriberWorker

BUENO = S(text="Una frase larga y perfectamente valida.", no_speech_prob=0.1, avg_logprob=-0.3)


class ModeloFalso:
    """Devuelve un segmento valido, salvo para el audio marcado como veneno."""

    def __init__(self, veneno="veneno"):
        self.veneno = veneno
        self.vistos = []

    def transcribe(self, audio, **_):
        self.vistos.append(audio)
        if audio == self.veneno:
            raise RuntimeError("fallo simulado del decodificador")
        return [BUENO], None


def instalar_modelo(modelo):
    """Sustituye faster_whisper por un modulo falso y devuelve una funcion para restaurarlo."""
    previo = sys.modules.get("faster_whisper")
    falso = types.ModuleType("faster_whisper")
    falso.WhisperModel = lambda *a, **k: modelo
    sys.modules["faster_whisper"] = falso

    def restaurar():
        if previo is None:
            sys.modules.pop("faster_whisper", None)
        else:
            sys.modules["faster_whisper"] = previo

    return restaurar


class BaseWorker(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = AppConfig()
        self.cfg.notes_dir = self.tmp.name
        self.cfg.caps_dir = str(pathlib.Path(self.tmp.name) / "caps")
        self.cfg.keywords = ["captura"]
        self.cfg.vocab = ""
        self.session = NotesSession(self.tmp.name)
        self.chunks = queue.Queue()
        self.ui = queue.Queue()
        self.stop = threading.Event()
        self.worker = TranscriberWorker(self.cfg, self.chunks, self.ui, self.session, self.stop)

    def tearDown(self):
        self.stop.set()
        self.tmp.cleanup()

    def arrancar(self, modelo):
        restaurar = instalar_modelo(modelo)
        self.addCleanup(restaurar)
        hilo = threading.Thread(target=self.worker.run, daemon=True)
        hilo.start()
        return hilo

    def esperar(self, cond, limite=4.0):
        fin = time.time() + limite
        while time.time() < fin:
            if cond():
                return True
            time.sleep(0.05)
        return False

    @property
    def nota(self):
        return self.session.file_path.read_text(encoding="utf-8")


class TestFragmentoQueFalla(BaseWorker):
    def test_un_fragmento_roto_no_mata_el_hilo(self):
        modelo = ModeloFalso()
        hilo = self.arrancar(modelo)
        for audio in ("bueno-1", "veneno", "bueno-2"):
            self.chunks.put((time.time(), "out", audio))

        self.assertTrue(self.esperar(lambda: modelo.vistos.count("bueno-2") == 1),
                        "el tercer fragmento nunca se proceso: el hilo murio")
        self.assertTrue(hilo.is_alive(), "el hilo de transcripcion termino")
        self.assertEqual(self.worker.errors, 1)

    def test_deja_constancia_del_fragmento_perdido_en_la_nota(self):
        self.arrancar(ModeloFalso())
        self.chunks.put((time.time(), "out", "veneno"))
        self.assertTrue(self.esperar(lambda: "fragmento perdido" in self.nota))
        self.assertIn("fallo simulado", self.nota)

    def test_las_frases_buenas_si_se_anotan(self):
        self.arrancar(ModeloFalso())
        self.chunks.put((time.time(), "out", "bueno"))
        self.assertTrue(self.esperar(lambda: "perfectamente valida" in self.nota))


class TestCapturaQueFalla(BaseWorker):
    def test_una_captura_fallida_no_pierde_la_frase(self):
        def explota(*a, **k):
            raise OSError("disco lleno")

        original = ww.take_screenshot
        ww.take_screenshot = explota
        self.addCleanup(lambda: setattr(ww, "take_screenshot", original))

        self.cfg.keywords = ["valida"]  # la frase del modelo falso contiene esta palabra
        self.worker.update_pipeline(self.cfg)
        self.arrancar(ModeloFalso())
        self.chunks.put((time.time(), "out", "bueno"))

        self.assertTrue(self.esperar(lambda: "perfectamente valida" in self.nota),
                        "se perdio la frase por culpa de la captura")
        self.assertIn("captura fallida", self.nota)
        self.assertIn("disco lleno", self.nota)
        self.assertEqual(self.worker.errors, 1)


class TestModeloQueNoCarga(BaseWorker):
    def test_sin_modelo_el_hilo_termina_avisando(self):
        previo = sys.modules.get("faster_whisper")
        falso = types.ModuleType("faster_whisper")

        def revienta(*a, **k):
            raise RuntimeError("modelo inexistente")

        falso.WhisperModel = revienta
        sys.modules["faster_whisper"] = falso
        self.addCleanup(lambda: sys.modules.__setitem__("faster_whisper", previo)
                        if previo else sys.modules.pop("faster_whisper", None))

        hilo = threading.Thread(target=self.worker.run, daemon=True)
        hilo.start()
        hilo.join(timeout=4)
        self.assertFalse(hilo.is_alive(), "el hilo deberia terminar si no hay modelo")

        mensajes = []
        while not self.ui.empty():
            mensajes.append(self.ui.get())
        textos = [m[1] for m in mensajes if m[0] == "status"]
        self.assertTrue(any("No se pudo cargar el modelo" in t for t in textos), textos)


if __name__ == "__main__":
    unittest.main()
