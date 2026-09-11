"""Una fuente de audio que muere (auriculares desconectados, suspensión) debe volver sola,
y cerrar con cola pendiente no debe tirar el trabajo en silencio.

Estas pruebas usan un PyAudio de mentira: no abren dispositivos reales ni cargan Whisper.
"""

import queue
import threading
import time
import unittest

import numpy as np

from recorder.actions.power import AWAKE_GRACE_SEC, should_stay_awake
from recorder.audio import capture
from recorder.audio.capture import (
    FRAMES_PER_BUFFER, AudioCaptureManager, meter_label, pending_audio_sec, pending_summary, retry_delay,
)

RATE = 16000


class FlujoFalso:
    """Stream de PortAudio de mentira: entrega un tono estéreo y muere cuando se le pide."""

    def __init__(self):
        self.reads = 0
        self.dead = False
        self.closed = False
        self.frame = np.full(FRAMES_PER_BUFFER * 2, 3000, np.int16).tobytes()

    def read(self, n, exception_on_overflow=False):
        time.sleep(0.002)
        if self.dead:
            raise OSError(-9999, "Unanticipated host error")
        self.reads += 1
        return self.frame

    def close(self):
        self.closed = True


class PAFalso:
    """PyAudio de mentira con una salida (y su loopback) y un micrófono, como resolve_wasapi_device espera."""

    def __init__(self):
        self.streams = {"out": [], "mic": []}
        self.fail_open = {"out": 0, "mic": 0}  # cuántas aperturas seguidas deben fallar aún

    def _devs(self):
        base = {"hostApi": 0, "maxInputChannels": 2, "maxOutputChannels": 0,
                "defaultSampleRate": RATE, "isLoopbackDevice": False}
        return [
            dict(base, index=0, name="Otro"),
            dict(base, index=1, name="Salida", maxOutputChannels=2, maxInputChannels=0),
            dict(base, index=2, name="Mic"),
            dict(base, index=3, name="Salida [Loopback]", isLoopbackDevice=True),
        ]

    def get_host_api_info_by_type(self, _t):
        return {"index": 0, "defaultOutputDevice": 1, "defaultInputDevice": 2}

    def get_device_info_by_index(self, i):
        return self._devs()[i]

    def get_device_info_generator(self):
        return iter(self._devs())

    def get_loopback_device_info_generator(self):
        return (d for d in self._devs() if d["isLoopbackDevice"])

    def open(self, **kw):
        kind = "out" if kw["input_device_index"] == 3 else "mic"
        if self.fail_open[kind] > 0:
            self.fail_open[kind] -= 1
            raise OSError(-9996, "Invalid input device (no default output device)")
        s = FlujoFalso()
        self.streams[kind].append(s)
        return s


def esperar(cond, limite=4.0):
    fin = time.time() + limite
    while time.time() < fin:
        if cond():
            return True
        time.sleep(0.01)
    return False


class BaseCaptura(unittest.TestCase):
    def setUp(self):
        self.pa = PAFalso()
        self.chunks = queue.Queue()
        self.eventos = []
        # *args: el gestor viejo llamaba a este callback con un solo mensaje; el nuevo con (kind, up, detalle)
        self.mgr = AudioCaptureManager(self.pa, self.chunks, lambda *a: self.eventos.append(a))
        self.mgr.retry_delay = lambda n: 0.01  # sin esperas reales

    def tearDown(self):
        self.mgr.stop()
        for t in self.mgr._threads:
            t.join(timeout=2)

    def leyendo(self, kind):
        return bool(self.pa.streams[kind]) and self.pa.streams[kind][-1].reads > 0


class TestFuenteQueMuere(BaseCaptura):
    def test_la_fuente_caida_se_reabre_y_la_otra_sigue_viva(self):
        self.mgr.start()
        self.assertTrue(esperar(lambda: self.leyendo("out") and self.leyendo("mic")))

        mic_antes = self.pa.streams["mic"][0].reads
        self.pa.streams["out"][0].dead = True  # se desconectan los auriculares

        self.assertTrue(esperar(lambda: len(self.pa.streams["out"]) >= 2 and self.leyendo("out")),
                        "la salida nunca se reabrió: el hilo murió para siempre")
        self.assertEqual(self.mgr.attempts["out"], 0, "tras volver a leer, la fuente debe constar como viva")
        self.assertTrue(self.pa.streams["out"][0].closed, "el flujo muerto debe cerrarse")

        self.assertEqual(len(self.pa.streams["mic"]), 1, "el micrófono no debe reabrirse por la caída de la salida")
        self.assertGreater(self.pa.streams["mic"][0].reads, mic_antes, "el micrófono dejó de leer durante la caída")

    def test_avisa_al_caer_y_al_volver(self):
        self.mgr.start()
        self.assertTrue(esperar(lambda: self.leyendo("out")))
        self.pa.streams["out"][0].dead = True
        self.assertTrue(esperar(lambda: ("out", True, "") in self.eventos), self.eventos)
        caida = [e for e in self.eventos if e[0] == "out" and e[1] is False]
        self.assertEqual(len(caida), 1, "un solo aviso de caída por incidente, no uno por reintento")
        self.assertIn("Unanticipated host error", caida[0][2])
        self.assertLess(self.eventos.index(caida[0]), self.eventos.index(("out", True, "")))

    def test_reintenta_con_espera_creciente_hasta_que_el_dispositivo_vuelve(self):
        self.pa.fail_open["out"] = 3  # las tres primeras aperturas fallan (auriculares aún fuera)
        intentos = []
        self.mgr.retry_delay = lambda n: (intentos.append(n), 0.01)[1]
        self.mgr.start()

        self.assertTrue(esperar(lambda: self.leyendo("out")), "nunca se abrió la salida tras los fallos")
        self.assertEqual(intentos[:3], [1, 2, 3], "cada reintento debe pedir una espera mayor")
        self.assertTrue(esperar(lambda: self.mgr.attempts["out"] == 0))
        self.assertEqual(len(self.pa.streams["mic"]), 1)
        self.assertTrue(self.leyendo("mic"))

    def test_stop_termina_los_hilos_aunque_una_fuente_este_en_espera(self):
        self.pa.fail_open["out"] = 10 ** 6
        self.mgr.retry_delay = lambda n: 60.0  # una espera larga que stop() debe interrumpir
        self.mgr.start()
        self.assertTrue(esperar(lambda: self.mgr.attempts["out"] >= 1))
        self.mgr.stop()
        for t in self.mgr._threads:
            t.join(timeout=2)
            self.assertFalse(t.is_alive(), f"{t.name} sigue vivo tras stop()")
        self.assertEqual(self.mgr.attempts, {"out": 0, "mic": 0})

    def test_restart_mata_los_hilos_del_arranque_anterior(self):
        self.mgr.start()
        self.assertTrue(esperar(lambda: self.leyendo("out") and self.leyendo("mic")))
        viejo = self.pa.streams["out"][0]

        self.mgr.restart(out_dev="", mic_dev="", mic_enabled=True)
        self.assertTrue(esperar(lambda: len(self.pa.streams["out"]) >= 2 and self.leyendo("out")))
        self.assertTrue(esperar(lambda: viejo.closed), "el flujo del arranque anterior sigue abierto")
        lecturas = viejo.reads
        time.sleep(0.1)
        self.assertEqual(viejo.reads, lecturas, "el hilo viejo sigue leyendo el dispositivo anterior")


class TestBufferAMedias(unittest.TestCase):
    def test_lo_grabado_a_medias_se_encola_cuando_el_flujo_muere(self):
        flujo = FlujoFalso()
        chunks = queue.Queue()
        stop = threading.Event()
        lecturas_antes_de_morir = int(RATE * 2 / FRAMES_PER_BUFFER)  # ~2 s de tono

        def lee(n, exception_on_overflow=False):
            if flujo.reads >= lecturas_antes_de_morir:
                raise OSError("device invalidated")
            flujo.reads += 1
            return flujo.frame

        flujo.read = lee
        with self.assertRaises(OSError):
            capture._read_loop("out", flujo, RATE, 2, chunks, lambda k, v: None, lambda: None,
                               lambda: False, lambda: True, stop)
        t0, kind, audio = chunks.get_nowait()
        self.assertEqual(kind, "out")
        self.assertAlmostEqual(len(audio) / RATE, 2.0, delta=0.2)


class TestPoliticas(unittest.TestCase):
    def test_retry_delay_crece_y_se_acota(self):
        self.assertEqual([retry_delay(n) for n in range(1, 8)], [1, 2, 4, 8, 16, 30, 30])

    def test_meter_label_muestra_barras_o_reintento(self):
        vivo = meter_label({"out": 0.0, "mic": 32768.0}, {"out": 0, "mic": 0})
        self.assertEqual(vivo, "🔊 ░░░░░░░░   🎤 ████████")
        caido = meter_label({"out": 0.0, "mic": 0.0}, {"out": 3, "mic": 0})
        self.assertEqual(caido, "🔊 ⛔ reintento 3   🎤 ░░░░░░░░")

    def test_pending_summary(self):
        chunks = [(0.0, "out", np.zeros(RATE * 20, np.float32))] * 150
        secs = pending_audio_sec(chunks)
        self.assertEqual(secs, 3000)
        self.assertEqual(pending_summary(150, secs), "150 fragmentos (~50 min de audio)")
        self.assertEqual(pending_summary(1, 12), "1 fragmento (~12 s de audio)")

    def test_should_stay_awake(self):
        ahora = 10_000.0
        self.assertTrue(should_stay_awake(ahora, ahora - 3600, pending=5, busy=False, paused=True))
        self.assertTrue(should_stay_awake(ahora, ahora - 3600, pending=0, busy=True, paused=True))
        self.assertTrue(should_stay_awake(ahora, ahora - 60, pending=0, busy=False, paused=False))
        self.assertFalse(should_stay_awake(ahora, ahora - 60, pending=0, busy=False, paused=True))
        self.assertFalse(should_stay_awake(ahora, ahora - AWAKE_GRACE_SEC, pending=0, busy=False, paused=False),
                         "sin trabajo y en silencio prolongado no se retiene el equipo")


if __name__ == "__main__":
    unittest.main()
