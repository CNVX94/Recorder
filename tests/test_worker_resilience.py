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


class ModeloConHora:
    """Un segmento con palabra clave y hora dentro del fragmento, como los de faster-whisper."""

    def __init__(self, texto="Toma captura ahora.", start=2.0, end=4.0):
        self.seg = S(text=texto, start=start, end=end, no_speech_prob=0.1, avg_logprob=-0.3)
        self.vistos = []

    def transcribe(self, audio, **_):
        self.vistos.append(audio)
        return [self.seg], None


class BufferFalso:
    """CaptureBuffer de mentira: 'tiene' decide si hay fotograma cerca de la hora pedida."""

    ext = "jpg"

    def __init__(self, tiene=True):
        self.tiene, self.pedidos, self.purgas = tiene, [], []

    def take(self, t, dest, max_gap=None):
        self.pedidos.append(t)
        if not self.tiene:
            return None
        dest = pathlib.Path(dest).with_suffix(".jpg")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"jpg")
        return dest

    def purge_before(self, t):
        self.purgas.append(t)


class TestCapturas(BaseWorker):
    def setUp(self):
        super().setUp()
        self.shots = []
        original = ww.take_screenshot

        def falsa(tag, caps_dir, screen_idx=0, window=""):
            p = pathlib.Path(caps_dir) / f"inmediata_{len(self.shots)}.png"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"png")
            self.shots.append(p)
            return p

        ww.take_screenshot = falsa
        self.addCleanup(lambda: setattr(ww, "take_screenshot", original))

    def test_el_enlace_solo_se_escribe_si_el_archivo_existe(self):
        ww.take_screenshot = lambda *a, **k: pathlib.Path(self.tmp.name) / "caps" / "nunca-escrita.png"
        self.cfg.keywords = ["valida"]
        self.worker.update_pipeline(self.cfg)
        self.arrancar(ModeloFalso())
        self.chunks.put((time.time(), "out", "bueno"))
        self.assertTrue(self.esperar(lambda: "perfectamente valida" in self.nota))
        self.assertNotIn("![](", self.nota)
        self.assertIn("captura no guardada", self.nota)

    def test_la_captura_sale_del_buffer_con_la_hora_de_la_palabra(self):
        buf = BufferFalso()
        self.worker.buffer = buf
        modelo = ModeloConHora()
        self.arrancar(modelo)
        t_ini = time.time() - 3.0
        self.chunks.put((t_ini + 1.0, "out", "audio", t_ini))
        self.assertTrue(self.esperar(lambda: "📸" in self.nota))
        # "captura" empieza en el carácter 5 de 19, en un segmento de 2 s a 4 s del inicio del audio
        esperado = t_ini + 2.0 + 5 / 19 * 2.0
        self.assertAlmostEqual(buf.pedidos[0], esperado, places=3)
        self.assertIn(ww.capture_name("captura", esperado, "jpg"), self.nota)
        self.assertNotIn("tardía", self.nota)
        self.assertEqual(self.shots, [], "con fotograma en el buffer no se captura la pantalla de ahora")
        self.assertAlmostEqual(buf.purgas[0], t_ini - ww.PURGE_MARGIN_SEC, places=3)

    def test_sin_fotograma_captura_ahora_y_la_marca_tardia(self):
        self.worker.buffer = BufferFalso(tiene=False)
        self.arrancar(ModeloConHora())
        viejo = time.time() - 600  # la frase se dijo hace 10 min: hay cola
        self.chunks.put((viejo, "out", "audio", viejo))
        self.assertTrue(self.esperar(lambda: "📸" in self.nota))
        self.assertEqual(len(self.shots), 1)
        self.assertIn("tardía, +10 min", self.nota)

    def test_enfriamiento_en_tiempo_de_reunion(self):
        # Al drenar la cola, dos palabras dichas con 1 min de distancia se procesan con milisegundos
        # de diferencia: las dos llevan captura. Dos dichas con 5 s de distancia, solo la primera.
        buf = BufferFalso()
        self.worker.buffer = buf
        modelo = ModeloConHora()
        self.arrancar(modelo)
        t = time.time() - 100
        for t_ini in (t, t + 60, t + 65):
            self.chunks.put((t_ini, "out", f"a{t_ini}", t_ini))
        self.assertTrue(self.esperar(lambda: len(modelo.vistos) == 3 and not self.worker.busy))
        self.assertEqual(self.nota.count("📸"), 2)

    def test_capturas_apagadas(self):
        self.cfg.captures = "off"
        buf = BufferFalso()
        self.worker.buffer = buf
        self.arrancar(ModeloConHora())
        self.chunks.put((time.time(), "out", "audio"))
        self.assertTrue(self.esperar(lambda: "Toma captura" in self.nota))
        self.assertNotIn("📸", self.nota)
        self.assertEqual((buf.pedidos, self.shots), ([], []))


class TestAtraso(BaseWorker):
    def test_politica_lag_marker(self):
        self.assertIsNone(ww.lag_marker(60, 0), "un minuto de cola es normal")
        self.assertEqual(ww.lag_marker(130, 0), 2)
        self.assertIsNone(ww.lag_marker(200, 2), "no se repite hasta que se duplique")
        self.assertEqual(ww.lag_marker(4 * 60, 2), 4)
        self.assertEqual(ww.lag_marker(54 * 60, 0), 54, "un salto grande se anota tal cual")
        self.assertIsNone(ww.lag_marker(41 * 60, 54), "bajando, no se repite")
        self.assertEqual(ww.lag_marker(30, 54), 0, "al volver a estar al día se dice una vez")
        self.assertIsNone(ww.lag_marker(30, 0))

    def test_la_nota_dice_cuando_va_atrasada_y_cuando_se_pone_al_dia(self):
        self.arrancar(ModeloFalso())
        self.chunks.put((time.time() - 300, "out", "bueno-1"))
        self.chunks.put((time.time(), "out", "bueno-2"))
        self.assertTrue(self.esperar(lambda: "al día" in self.nota))
        self.assertRegex(self.nota, r"> ⏳ transcripción atrasada 5 min desde \d\d:\d\d:\d\d")
        self.assertLess(self.nota.index("atrasada"), self.nota.index("> ✔ transcripción al día"))


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
