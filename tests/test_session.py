"""La sesión de grabación se prueba sin ventana: con audio y transcriptor de mentira.

Estas pruebas no abren dispositivos, no cargan Whisper, no capturan la pantalla y no tocan
config.json ni las carpetas reales de notas: todo va a un temporal. Lo que comprueban es lo
que la ventana (y el frontal de terminal) pintan: eventos, cabecera, pausa, equipo despierto,
cierre esperando a la cola, Opciones y Calibrar, captura manual y primer arranque.
"""

import json
import pathlib
import tempfile
import threading
import time
import unittest

import numpy as np

from recorder import session as ses
from recorder.config.hardware import HardwareProfile
from recorder.config.manager import ConfigManager
from recorder.config.schema import AppConfig, recommended_cpu_threads
from recorder.session import (
    HardwareReady, Line, Notice, RecorderSession, SourceChanged, Status, compose_status,
)

RATE = 16000
# i5-9500: 6 núcleos no híbridos, AVX2, 16 GB → gama Media con 5 hilos (tests/test_recommendation.py)
PERFIL = dict(
    cpu_name="Intel(R) Core(TM) i5-9500 CPU @ 3.00GHz", physical_cores=6, logical_cores=6, p_cores=6,
    avx2=True, ram_total_mb=16000, desktop=True,
)


class PAFalso:
    """PyAudio de mentira: solo sirve para comprobar que nadie lo termina al cerrar."""

    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


class GestorAudioFalso:
    """AudioCaptureManager de mentira: el mismo estado que mira la sesión, sin hilos ni PortAudio."""

    def __init__(self, pa_instance, chunk_queue, source_callback, out_dev="", mic_dev="", mic_enabled=True):
        self.pa = pa_instance
        self.chunk_queue = chunk_queue
        self.source_callback = source_callback
        self.out_dev, self.mic_dev, self.mic_enabled = out_dev, mic_dev, mic_enabled
        self.paused = False
        self.levels = {"out": 0.0, "mic": 0.0}
        self.attempts = {"out": 0, "mic": 0}
        self.last_audio_at = time.time()
        self.llamadas = []  # ("start",), ("stop",), ("restart", out_dev, mic_dev, mic_enabled)

    def start(self):
        self.llamadas.append(("start",))

    def stop(self):
        self.llamadas.append(("stop",))
        self.levels = {"out": 0.0, "mic": 0.0}
        self.attempts = {"out": 0, "mic": 0}

    def restart(self, out_dev, mic_dev, mic_enabled):
        self.llamadas.append(("restart", out_dev, mic_dev, mic_enabled))
        self.out_dev, self.mic_dev, self.mic_enabled = out_dev, mic_dev, mic_enabled


class TranscriptorFalso:
    """TranscriberWorker de mentira: no carga modelo; `run` solo espera a que lo paren."""

    def __init__(self, config, chunk_queue, ui_queue, notes_session, stop_event):
        self.config = config
        self.chunk_queue = chunk_queue
        self.ui_queue = ui_queue
        self.notes_session = notes_session
        self.stop_event = stop_event
        self.busy = False
        self.errors = 0
        self.actualizaciones = []  # configs recibidas por update_pipeline
        self.arrancado = threading.Event()

    def update_pipeline(self, config):
        self.config = config
        self.actualizaciones.append(config)

    def run(self):
        self.arrancado.set()
        self.stop_event.wait()


class ManagerDePrueba(ConfigManager):
    """ConfigManager sobre un temporal que, cargue lo que cargue, manda notas y capturas al temporal.

    Ni el primer arranque ni una config rota (valores de fábrica) pueden escribir en ~/Documents.
    """

    def __init__(self, path, raiz):
        super().__init__(path)
        self.raiz = pathlib.Path(raiz)

    def load(self):
        cfg = super().load()
        cfg.notes_dir = str(self.raiz / "notas")
        cfg.caps_dir = str(self.raiz / "caps")
        return cfg


class BaseSesion(unittest.TestCase):
    primer_arranque = False  # True: sin config.json
    contenido_config = None  # bytes del config.json; None = la config de config_inicial()

    def config_inicial(self) -> AppConfig:
        return AppConfig()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = pathlib.Path(self.tmp.name)
        self.ruta = self.raiz / "config.json"
        if not self.primer_arranque:
            contenido = self.contenido_config or json.dumps(self.config_inicial().to_dict()).encode("utf-8")
            self.ruta.write_bytes(contenido)
        self.mgr = ManagerDePrueba(self.ruta, self.raiz)
        self.perfil = HardwareProfile(**PERFIL)

        self.despierto = []  # lo que se le fue pidiendo a keep_awake
        original = ses.keep_awake
        ses.keep_awake = self.despierto.append
        self.addCleanup(lambda: setattr(ses, "keep_awake", original))

        self.pa = PAFalso()
        self.session = RecorderSession(
            self.mgr,
            pa_factory=lambda: self.pa,
            audio_manager_factory=GestorAudioFalso,
            transcriber_factory=TranscriptorFalso,
            hardware_detector=lambda: self.perfil,
        )
        self.addCleanup(self.session.shutdown)

    @property
    def audio(self) -> GestorAudioFalso:
        return self.session.audio_manager

    @property
    def worker(self) -> TranscriptorFalso:
        return self.session.transcriber

    @property
    def nota(self) -> str:
        return self.session.file_path.read_text(encoding="utf-8")

    def encolar(self, segundos=20.0, kind="out"):
        self.session.chunk_queue.put((time.time(), kind, np.zeros(int(RATE * segundos), np.float32)))

    def escuchando(self):
        """El transcriptor ya cargó el modelo."""
        self.session.ui_queue.put(("status", "● Escuchando"))
        self.session.poll()

    def sondear_hasta(self, cond, limite=4.0):
        """Llama a poll() acumulando eventos hasta que cond(eventos) se cumpla."""
        eventos = []
        fin = time.time() + limite
        while time.time() < fin:
            eventos += self.session.poll()
            if cond(eventos):
                return eventos
            time.sleep(0.02)
        self.fail(f"no llegó lo esperado; eventos: {eventos}")

    def esperar_hardware(self):
        eventos = self.sondear_hasta(lambda evs: any(isinstance(e, HardwareReady) for e in evs))
        return next(e for e in eventos if isinstance(e, HardwareReady)), eventos


class TestEventos(BaseSesion):
    def test_traduce_lo_que_llega_del_transcriptor(self):
        ui = self.session.ui_queue
        ui.put(("status", "● Escuchando"))
        ui.put(("line", "10:00:01", "mic", "Hola equipo", []))
        ui.put(("line", "10:00:05", "out", "Hay un bloqueo", ["bloqueo"]))
        self.assertEqual(self.session.poll(), [
            Status("● Escuchando"),
            Line("10:00:01", "mic", "Hola equipo", []),
            Line("10:00:05", "out", "Hay un bloqueo", ["bloqueo"]),
        ])
        self.assertEqual(self.session.poll(), [], "un evento no se entrega dos veces")

    def test_una_fuente_que_cae_se_anota_y_se_avisa(self):
        self.audio.source_callback("out", False, "OSError(-9999)")  # lo que llama el gestor de captura
        self.audio.source_callback("mic", True, "")
        caida, vuelta = self.session.poll()
        self.assertIsInstance(caida, SourceChanged)
        self.assertEqual((caida.kind, caida.up, caida.detail), ("out", False, "OSError(-9999)"))
        self.assertEqual(caida.text, "⚠ audio de salida caído, reintentando: OSError(-9999)")
        self.assertEqual(vuelta.text, "✔ audio de micrófono recuperado")
        self.assertIn(f"> ⚠ audio de salida caído, reintentando: OSError(-9999) {caida.stamp}", self.nota)
        self.assertIn("> ✔ audio de micrófono recuperado", self.nota)


class TestCabecera(BaseSesion):
    def test_antes_de_escuchar_se_muestra_lo_que_diga_el_transcriptor(self):
        st = self.session.status
        self.assertEqual((st.status_text, st.status_highlight), ("Iniciando…", False))
        self.session.ui_queue.put(("status", "Cargando modelo small…"))
        self.session.poll()
        st = self.session.status
        self.assertEqual((st.status_text, st.status_highlight), ("Cargando modelo small…", False))

    def test_escuchando_con_pendientes_fallos_y_cafe(self):
        self.escuchando()
        st = self.session.status
        self.assertTrue(st.status_highlight)
        # recién arrancado se "oyó" audio hace nada: se retiene el equipo (☕)
        self.assertEqual(st.status_text, "● Escuchando + 🎤 · pendientes: 0 · ☕")
        self.encolar()
        self.encolar()
        self.worker.errors = 2
        self.session.config.mic = False
        self.assertEqual(self.session.status.status_text, "● Escuchando · pendientes: 2 · ⚠ 2 con fallo · ☕")

    def test_en_pausa_muestra_el_avance_de_la_cola(self):
        self.escuchando()
        self.audio.last_audio_at = 0.0  # silencio largo: en pausa y sin cola no se retiene el equipo
        self.session.toggle_pause()
        self.session.poll()
        self.assertEqual(self.session.status.status_text, "⏸ En pausa · sin pendientes")
        self.encolar(20)
        self.encolar(20)
        self.session.poll()
        self.assertEqual(
            self.session.status.status_text, "⏸ En pausa · transcribiendo 2 fragmentos (~40 s de audio) · ☕"
        )
        self.worker.errors = 1
        self.assertEqual(
            self.session.status.status_text,
            "⏸ En pausa · transcribiendo 2 fragmentos (~40 s de audio) · ⚠ 1 con fallo · ☕",
        )

    def test_terminando_muestra_lo_que_queda(self):
        self.escuchando()
        self.encolar(30)
        self.session.begin_drain()
        self.session.poll()
        st = self.session.status
        self.assertEqual((st.status_text, st.status_highlight), ("⏳ Terminando 1 fragmento (~30 s de audio)…", True))

    def test_un_aviso_del_transcriptor_no_se_tapa_con_el_estado(self):
        self.escuchando()
        self.session.ui_queue.put(("status", "⚠ el servidor murió; se sigue en CPU."))
        self.session.poll()
        st = self.session.status
        self.assertEqual((st.status_text, st.status_highlight), ("⚠ el servidor murió; se sigue en CPU.", False))

    def test_compose_status_es_pura(self):
        comun = dict(pending=3, busy=False, errors=0, awake=False, mic=True,
                     pending_summary="3 fragmentos (~60 s de audio)")
        self.assertEqual(compose_status("Cargando modelo…", draining=False, paused=False, **comun), "Cargando modelo…")
        self.assertEqual(compose_status("● Escuchando", draining=True, paused=True, **comun),
                         "⏳ Terminando 3 fragmentos (~60 s de audio)…")
        self.assertEqual(compose_status("● Escuchando", draining=False, paused=True, **comun),
                         "⏸ En pausa · transcribiendo 3 fragmentos (~60 s de audio)")
        self.assertEqual(compose_status("● Escuchando", draining=False, paused=False, **comun),
                         "● Escuchando + 🎤 · pendientes: 3")
        self.assertEqual(compose_status("", draining=False, paused=False, **comun), "")

    def test_los_medidores_salen_del_gestor_de_audio(self):
        self.audio.levels["mic"] = 32768.0
        self.audio.attempts["out"] = 2
        self.assertEqual(self.session.status.meter_text, "🔊 ⛔ reintento 2   🎤 ████████")


class TestPausa(BaseSesion):
    def test_pausar_y_continuar(self):
        linea = self.session.toggle_pause()
        self.assertTrue(self.session.paused)
        self.assertTrue(self.audio.paused, "la pausa se le dice al gestor de captura")
        self.assertEqual(linea, Line(linea.stamp, "out", "⏸ pausa: no se captura audio nuevo", []))
        self.assertIn(f"> ⏸ Pausa {linea.stamp}", self.nota)

        linea = self.session.toggle_pause()
        self.assertFalse(self.session.paused)
        self.assertEqual(linea.text, "▶ continúa, se vuelve a capturar audio")
        self.assertIn(f"> ▶ Continúa {linea.stamp}", self.nota)

    def test_la_pausa_dice_cuanto_queda_por_transcribir(self):
        self.encolar(12)
        self.assertEqual(
            self.session.toggle_pause().text,
            "⏸ pausa: no se captura audio nuevo; siguen 1 fragmento (~12 s de audio) por transcribir",
        )


class TestEquipoDespierto(BaseSesion):
    def test_se_retiene_con_audio_reciente_y_se_suelta_en_silencio_pausado(self):
        self.session.poll()
        self.assertTrue(self.session.awake)
        self.assertEqual(self.despierto, [True])
        self.session.poll()
        self.assertEqual(self.despierto, [True], "sin cambio no se vuelve a pedir")

        self.audio.last_audio_at = time.time() - 3600
        self.audio.paused = True
        self.session.poll()
        self.assertFalse(self.session.awake)
        self.assertEqual(self.despierto, [True, False])

        self.encolar()  # con cola, siempre despierto aunque esté en pausa
        self.session.poll()
        self.assertEqual(self.despierto, [True, False, True])

    def test_al_cerrar_se_suelta_el_equipo(self):
        self.session.poll()
        self.session.shutdown()
        self.assertEqual(self.despierto, [True, False])


class TestCierre(BaseSesion):
    def test_sin_cola_se_cierra_sin_preguntar(self):
        self.session.start()
        self.assertIsNone(self.session.request_close())
        self.session.shutdown()
        self.assertEqual(self.audio.llamadas[-1], ("stop",))
        self.assertTrue(self.session.stop_event.is_set())
        self.assertFalse(self.pa.terminated, "pa.terminate() revienta el proceso con el loopback bloqueado en read()")

    def test_con_cola_devuelve_el_resumen_para_preguntar(self):
        self.encolar(20)
        self.encolar(25)
        self.assertEqual(self.session.request_close(), "2 fragmentos (~45 s de audio)")

    def test_esperar_para_la_captura_y_termina_al_vaciar_la_cola(self):
        self.session.start()
        self.encolar(20)
        self.session.begin_drain()
        self.assertTrue(self.session.draining)
        self.assertEqual(self.audio.llamadas[-1], ("stop",), "no entran fragmentos nuevos")

        self.session.poll()
        self.assertFalse(self.session.status.finished, "con cola no se puede cerrar aún")
        self.session.chunk_queue.get()
        self.worker.busy = True
        self.session.poll()
        self.assertFalse(self.session.status.finished, "un fragmento en curso también cuenta")
        self.worker.busy = False
        self.session.poll()
        self.assertTrue(self.session.status.finished)
        self.assertFalse(self.session.stop_event.is_set(), "cerrar del todo lo decide la interfaz con shutdown()")

    def test_mientras_se_termina_no_se_reconecta_el_audio(self):
        self.encolar()
        self.session.begin_drain()
        self.session.reconnect_audio()
        self.assertNotIn("restart", [c[0] for c in self.audio.llamadas])

    def test_reconectar_reabre_con_los_dispositivos_configurados(self):
        self.session.config.out_dev = "Auriculares"
        self.session.reconnect_audio()
        self.assertEqual(self.audio.llamadas[-1], ("restart", "Auriculares", "", True))


class TestOpcionesYCalibrar(BaseSesion):
    def test_guardar_opciones_mueve_la_nota_recarga_filtros_y_reabre_el_audio(self):
        cfg = self.session.config
        cfg.notes_dir = str(self.raiz / "otras")
        cfg.keywords = ["demo"]
        cfg.out_dev = "Auriculares"
        cfg.mic = False
        self.session.recommend_pending = True
        self.session.apply_settings(cfg, notes_changed=True, devices_changed=True)

        self.assertEqual(self.session.file_path.parent, self.raiz / "otras")
        self.assertTrue(self.session.file_path.exists(), "la nota de hoy se mueve con la carpeta")
        self.assertEqual(json.loads(self.ruta.read_text(encoding="utf-8"))["keywords"], ["demo"])
        self.assertIs(self.worker.actualizaciones[-1], cfg, "los filtros se recargan sin tocar el modelo")
        self.assertEqual(self.audio.llamadas[-1], ("restart", "Auriculares", "", False))
        self.assertFalse(self.session.recommend_pending, "lo elegido en Opciones manda sobre la recomendación")
        self.assertEqual(self.session.status.status_text, "● Escuchando · pendientes: 0")

    def test_guardar_sin_cambiar_dispositivos_no_reabre_el_audio(self):
        self.session.apply_settings(self.session.config, notes_changed=False, devices_changed=False)
        self.assertEqual(self.audio.llamadas, [])
        self.assertEqual(self.session.status.status_text, "Iniciando…")

    def test_calibrar_recarga_filtros_sin_tocar_audio_ni_recomendacion(self):
        self.session.recommend_pending = True
        cfg = self.session.config
        cfg.ignore = ["gracias por ver"]
        self.session.apply_tuning(cfg)
        self.assertIs(self.worker.actualizaciones[-1], cfg)
        self.assertEqual(json.loads(self.ruta.read_text(encoding="utf-8"))["ignore"], ["gracias por ver"])
        self.assertEqual(self.audio.llamadas, [])
        self.assertTrue(self.session.recommend_pending)


class TestCapturaManual(BaseSesion):
    def falsear_captura(self, fn):
        original = ses.take_screenshot
        ses.take_screenshot = fn
        self.addCleanup(lambda: setattr(ses, "take_screenshot", original))

    def test_captura_en_otro_hilo_y_la_linea_llega_por_poll(self):
        pedidas = []
        suelta = threading.Event()  # la captura de mentira se queda "capturando" hasta que se le dice

        def captura_falsa(tag, caps_dir, screen_idx=0, window=""):
            pedidas.append((threading.current_thread(), tag, caps_dir, screen_idx, window))
            suelta.wait(2)
            return pathlib.Path(caps_dir) / "manual_x.png"

        self.falsear_captura(captura_falsa)
        self.session.config.screen = 2
        self.assertTrue(self.session.manual_screenshot())
        self.assertEqual(self.session.poll(), [], "la interfaz no espera a la captura")
        self.assertFalse(self.session.manual_screenshot(), "otro clic con una en curso se ignora")

        suelta.set()
        eventos = self.sondear_hasta(lambda evs: any(isinstance(e, Line) for e in evs))
        linea = next(e for e in eventos if isinstance(e, Line))
        self.assertEqual(linea, Line(linea.stamp, "out", "(captura manual)", ["manual"]))
        self.assertIn(f"- **{linea.stamp}** 📸 captura manual → ![](../caps/manual_x.png)", self.nota)
        self.assertEqual(len(pedidas), 1)
        hilo, *peticion = pedidas[0]
        self.assertIsNot(hilo, threading.current_thread(), "capturar y guardar el PNG no congela la interfaz")
        self.assertEqual(peticion, ["manual", str(self.raiz / "caps"), 2, ""])
        self.assertTrue(self.session.manual_screenshot(), "al llegar la línea ya se puede volver a capturar")

    def test_si_la_captura_falla_se_avisa_sin_reventar_y_se_puede_repetir(self):
        def captura_rota(tag, caps_dir, screen_idx=0, window=""):
            raise OSError("sin pantalla")

        self.falsear_captura(captura_rota)
        self.assertTrue(self.session.manual_screenshot())
        eventos = self.sondear_hasta(lambda evs: any(isinstance(e, Notice) for e in evs))
        aviso = next(e for e in eventos if isinstance(e, Notice))
        self.assertEqual((aviso.text, aviso.level), ("⚠ captura manual fallida: OSError('sin pantalla')", "err"))
        self.assertIn(f"- **{aviso.stamp}** ⚠ captura manual fallida: OSError('sin pantalla')", self.nota)
        self.assertEqual(self.session.status.errors, 1, "cuenta en la cabecera como las capturas automáticas fallidas")
        self.assertTrue(self.session.manual_screenshot(), "el fallo no deja la captura bloqueada")


class TestArranque(BaseSesion):
    def test_arranca_captura_y_transcriptor_y_detecta_el_equipo(self):
        self.session.start()
        self.assertEqual(self.audio.llamadas, [("start",)])
        self.assertTrue(self.worker.arrancado.wait(2), "con config.json el transcriptor arranca ya")
        listo, eventos = self.esperar_hardware()
        self.assertIs(listo.profile, self.perfil)
        self.assertFalse(listo.applied)
        self.assertEqual(listo.recommendation.preset, "media")
        self.assertIs(self.session.hardware, self.perfil)
        self.assertEqual([e for e in eventos if isinstance(e, Notice)], [],
                         "config Media en un equipo de gama media: nada que avisar")


class TestArranqueConConfigPesada(BaseSesion):
    def config_inicial(self):
        cfg = AppConfig()
        cfg.model = "large-v3"  # en CPU no llega al tiempo real
        return cfg

    def test_se_avisa_en_el_visor(self):
        self.session.start()
        _, eventos = self.esperar_hardware()
        avisos = [e for e in eventos if isinstance(e, Notice)]
        self.assertEqual(len(avisos), 1, avisos)
        self.assertEqual(avisos[0].level, "err")
        self.assertIn("más pesada que la recomendada", avisos[0].text)


class TestPrimerArranque(BaseSesion):
    primer_arranque = True

    def test_espera_al_equipo_aplica_la_recomendacion_y_arranca(self):
        self.assertTrue(self.session.recommend_pending)
        self.session.start()
        self.assertEqual(self.session.status.status_text, "Detectando el equipo…")
        self.assertIsNone(self.session.transcribe_thread, "el modelo no se carga hasta saber cuál conviene")

        listo, eventos = self.esperar_hardware()
        self.assertTrue(listo.applied)
        aviso = next(e for e in eventos if isinstance(e, Notice))
        self.assertEqual(aviso.level, "info")
        self.assertIn("🖥 Primer arranque en este equipo", aviso.text)
        self.assertIn("Media", aviso.text)

        hilos = recommended_cpu_threads(self.perfil)
        self.assertEqual(hilos, 5)
        self.assertEqual(self.session.config.cpu_threads, hilos)
        guardada = json.loads(self.ruta.read_text(encoding="utf-8"))
        self.assertEqual(guardada["cpu_threads"], hilos, "la recomendación se guarda en config.json")
        self.assertEqual(guardada["notes_dir"], str(self.raiz / "notas"))
        self.assertFalse(self.session.recommend_pending)
        self.assertTrue(self.worker.arrancado.wait(2), "tras aplicar arranca el transcriptor")
        self.assertIs(self.worker.config, self.session.config, "el transcriptor ve la config ya recomendada")

    def test_guardar_opciones_antes_de_la_deteccion_manda(self):
        self.session.start()
        self.session.apply_settings(self.session.config, notes_changed=False, devices_changed=False)
        listo, _ = self.esperar_hardware()
        self.assertFalse(listo.applied)
        self.assertEqual(self.session.config.cpu_threads, 0, "no se pisa lo que eligió el usuario")
        self.assertTrue(self.worker.arrancado.wait(2), "el transcriptor arranca igual al terminar la detección")


class TestConfigIlegible(BaseSesion):
    contenido_config = b"{ esto no es json"

    def test_se_avisa_en_el_visor_y_en_la_nota(self):
        self.assertTrue(self.mgr.last_error)
        self.session.start()
        aviso = self.session.poll()[0]  # va antes que nada, también que la detección del equipo
        self.assertIsInstance(aviso, Notice)
        self.assertEqual(aviso.level, "err")
        self.assertTrue(aviso.text.startswith("⚠ No se pudo leer"), aviso.text)
        self.assertIn(f"> ⚠ {aviso.stamp} No se pudo leer", self.nota)


if __name__ == "__main__":
    unittest.main()
