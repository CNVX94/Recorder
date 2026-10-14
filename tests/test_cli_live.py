"""La grabación en la terminal se prueba con la sesión de mentira de tests/test_session.py, una
consola de rich que escribe en memoria y un teclado guionizado: no hay audio, ni Whisper, ni
pantalla, ni se toca config.json ni las carpetas reales.

Se comprueba lo que la ventana también hace (líneas con hora, 🎤 y 📸, pausa, captura, cerrar
preguntando por la cola) y lo propio de la terminal: el pie no se redibuja si nada cambió, Ctrl+C
dos veces, el modo ASCII sin emoji y la salida plana cuando no hay terminal.
"""

import io
import pathlib
import re
import signal
import time
import unittest

from recorder import session as ses
from recorder.audio.capture import MUTE_WARN_SEC
from recorder.cli.consola import make_console
from recorder.cli.live import CTRL_C, PantallaEnVivo
from recorder.session import mute_text
from tests.test_session import BaseSesion

TENUE, ACENTO, MIC, ERROR = "127;132;156", "249;226;175", "137;180;250", "243;139;168"
ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def color(rgb: str, texto: str) -> str:
    """Cómo rinde rich un trozo con color (truecolor) seguido de `texto`."""
    return f"\x1b[38;2;{rgb}m{texto}"


def limpio(salida: str) -> str:
    """La salida sin códigos de control: solo el texto, para mirar qué se dijo y en qué orden."""
    return ANSI.sub("", salida)


class Teclado:
    """Lector de teclas de mentira: una entrada del guion por sondeo. Una entrada `(cond, tecla)`
    devuelve None (nada pulsado) hasta que cond(salida) se cumpla."""

    def __init__(self, salida: io.StringIO, guion):
        self.salida = salida
        self.guion = list(guion)

    def __call__(self):
        if not self.guion:
            return None
        paso = self.guion[0]
        if isinstance(paso, tuple):
            cond, tecla = paso
            if not cond(self.salida.getvalue()):
                return None
        else:
            tecla = paso
        self.guion.pop(0)
        return tecla


class Reloj:
    """`dormir` de mentira: no espera 200 ms, deja respirar a los hilos y acota la prueba."""

    def __init__(self, salida: io.StringIO, tope=400):
        self.salida = salida
        self.tope = tope
        self.tics = 0
        self.longitudes = []  # cuánto llevaba escrito la consola al acabar cada tic
        self.al_tic = None  # callable(tic) para meter mano en mitad del bucle

    def __call__(self, _segundos):
        self.tics += 1
        self.longitudes.append(len(self.salida.getvalue()))
        if self.al_tic:
            self.al_tic(self.tics)
        if self.tics > self.tope:
            raise AssertionError("el bucle no acaba")
        time.sleep(0.005)


class BasePantalla(BaseSesion):
    ascii_mode = False
    interactiva = True  # False: una salida redirigida (sin pie)

    def setUp(self):
        super().setUp()
        self.salida = io.StringIO()
        extra = dict(force_terminal=True, force_interactive=True, color_system="truecolor", legacy_windows=False)
        self.consola = make_console(ascii_mode=self.ascii_mode, file=self.salida, width=200, **(extra if self.interactiva else {}))
        self.reloj = Reloj(self.salida)
        self.abiertos = []

    def pantalla(self, *guion) -> PantallaEnVivo:
        return PantallaEnVivo(
            self.session, consola=self.consola, leer_tecla=Teclado(self.salida, guion), dormir=self.reloj,
            abrir=self.abiertos.append,
        )

    def correr(self, *guion) -> str:
        self.assertEqual(self.pantalla(*guion).run(), 0)
        return self.salida.getvalue()

    def encolar_lineas(self):
        ui = self.session.ui_queue
        ui.put(("status", "● Escuchando"))
        ui.put(("line", "10:00:01", "mic", "Hola equipo", []))
        ui.put(("line", "10:00:05", "out", "Hay un bloqueo", ["bloqueo"]))
        ui.put(("notice", "10:00:07", "⚠ algo falló", "err"))
        self.audio.source_callback("out", False, "OSError(-9999)")


class TestLineas(BasePantalla):
    def test_pinta_como_la_ventana_y_cierra_sin_cola(self):
        self.encolar_lineas()
        salida = self.correr(None, "q")  # un sondeo sin tecla para que el pie llegue a pintarse
        texto = limpio(salida)

        self.assertIn(f"Recorder · nota: {self.session.file_path}", texto)
        self.assertIn("small, haz 5, CPU, int8, hilos de la biblioteca", texto)
        self.assertIn("[p] pausar · [c] captura · [r] reconectar audio · [a] abrir nota · [q] salir", texto)
        self.assertIn("10:00:01  🎤 Hola equipo\n", texto)
        self.assertIn(color(TENUE, "10:00:01  "), salida, "la hora en tenue")
        self.assertIn(color(MIC, "🎤 "), salida, "el micrófono en su color")
        self.assertIn(color(ACENTO, "Hay un bloqueo"), salida, "con palabra clave, en acento")
        self.assertIn(color(TENUE, "          📸 captura: bloqueo"), salida)
        self.assertIn(color(ERROR, "⚠ algo falló"), salida)
        self.assertIn("⚠ audio de salida caído, reintentando: OSError(-9999)", texto)
        self.assertIn("● Escuchando + 🎤 · pendientes: 0 · ☕", texto, "la cabecera va en el pie")
        self.assertIn("🔊 ░░░░░░░░   🎤 ░░░░░░░░", texto, "los medidores también")
        self.assertIn("Grabación terminada", texto)
        self.assertNotIn("se perdieron", texto)

        self.assertEqual(self.audio.llamadas, [("start",), ("stop",)], "arranca al entrar y para al salir")
        self.assertTrue(self.session.stop_event.is_set())
        self.assertFalse(self.pa.terminated, "pa.terminate() revienta el proceso")

    def test_los_corchetes_de_una_frase_no_son_marcado(self):
        self.session.ui_queue.put(("line", "10:00:01", "out", "[Música] y [risas] (bold)", []))
        self.assertIn("[Música] y [risas] (bold)", self.correr("q"))

    def test_las_fuentes_resueltas_se_imprimen_al_arrancar(self):
        original = ses.resolve_wasapi_device
        ses.resolve_wasapi_device = lambda p, kind, pref: {"name": "Altavoces" if kind == "out" else "Micro USB"}
        self.addCleanup(lambda: setattr(ses, "resolve_wasapi_device", original))
        texto = limpio(self.correr("q"))
        self.assertIn("Fuentes: 🔊 Altavoces · 🎤 Micro USB", texto)
        self.assertIn("> Fuentes: 🔊 Altavoces · 🎤 Micro USB", self.nota)

    def test_los_marcadores_del_transcriptor_son_lineas(self):
        # el atraso y los pasos lentos llegan como líneas normales (así los escribe whisper_worker._marker)
        self.session.ui_queue.put(("line", "10:42:13", "out", "⏳ transcripción atrasada 5 min desde", []))
        self.assertIn("10:42:13  ⏳ transcripción atrasada 5 min desde\n", limpio(self.correr("q")))


class TestFuenteMuda(BasePantalla):
    def test_el_aviso_es_una_linea_y_el_medidor_marca_la_fuente(self):
        self.escuchando()
        self.audio.started_at = time.time() - 2 * MUTE_WARN_SEC
        self.audio.last_chunk_at = {"out": time.time() - 5, "mic": 0.0}

        def vuelve(tic):
            if tic == 3:
                self.audio.last_chunk_at["mic"] = time.time()

        self.reloj.al_tic = vuelve
        salida = self.correr(None, None, None, None, "q")
        texto = limpio(salida)
        self.assertIn(mute_text("mic", True), texto)
        self.assertIn("🔊 ░░░░░░░░   🎤 ░░░░░░░░ 🔇", texto, "el medidor del pie marca la fuente muda")
        self.assertIn(mute_text("mic", False), texto)
        self.assertLess(texto.index("sin audio de"), texto.index("vuelve a haber audio"))
        self.assertIn("> " + mute_text("mic", True), self.nota)
        self.assertIsNone(self.session.status.muted)

    def test_en_ascii_el_medidor_dice_mudo(self):
        self.consola = make_console(ascii_mode=True, file=self.salida, width=200, force_terminal=True,
                                    force_interactive=True, color_system="truecolor", legacy_windows=False)
        self.escuchando()
        self.audio.started_at = time.time() - 2 * MUTE_WARN_SEC
        self.audio.last_chunk_at = {"out": time.time() - 5, "mic": 0.0}
        texto = limpio(self.correr(None, "q"))
        self.assertIn("OUT ........   MIC ........ (mudo)", texto)
        self.assertIn("! sin audio de micrófono MIC desde hace 10 min", texto)


class TestTeclas(BasePantalla):
    def test_pausar_y_continuar(self):
        self.escuchando()
        salida = limpio(self.correr("p", None, "P", None, "q"))
        self.assertIn("⏸ pausa: no se captura audio nuevo", salida)
        self.assertIn("⏸ En pausa · sin pendientes", salida)
        self.assertIn("[p] continuar", salida)
        self.assertIn("▶ continúa, se vuelve a capturar audio", salida)
        self.assertIn("> ⏸ Pausa", self.nota)
        self.assertIn("> ▶ Continúa", self.nota)
        self.assertFalse(self.session.paused)

    def test_captura_manual_llega_por_el_sondeo(self):
        original = ses.take_screenshot
        ses.take_screenshot = lambda tag, caps_dir, screen_idx=0, window="": pathlib.Path(caps_dir) / "manual_x.png"
        self.addCleanup(lambda: setattr(ses, "take_screenshot", original))

        salida = self.correr("c", (lambda s: "(captura manual)" in s, "q"))
        self.assertIn("📸 captura: manual", salida)
        self.assertIn("📸 captura manual → ![](../caps/manual_x.png)", self.nota)

    def test_reconectar_y_abrir_la_nota(self):
        self.session.config.out_dev = "Auriculares"
        self.correr("r", "a", "q")
        self.assertIn(("restart", "Auriculares", "", True), self.audio.llamadas)
        self.assertEqual(self.abiertos, [str(self.session.file_path)])

    def test_una_tecla_desconocida_no_hace_nada(self):
        salida = self.correr("x", "?", "q")
        self.assertNotIn("⚠", salida)


class TestCierreConCola(BasePantalla):
    def setUp(self):
        super().setUp()
        self.escuchando()
        self.encolar(20)

    def test_pregunta_cancela_y_al_final_sale_perdiendo(self):
        salida = limpio(self.correr("q", None, "c", None, "q", "s"))
        pregunta = "Quedan 1 fragmento (~20 s de audio) sin transcribir."
        self.assertIn(pregunta, salida)
        self.assertIn("[e] esperar", salida)
        self.assertLess(salida.index("[c] cancelar"), salida.rindex("[p] pausar"), "tras cancelar vuelven las teclas normales")
        self.assertIn("⚠ se perdieron 1 fragmento (~20 s de audio) sin transcribir", salida)
        self.assertEqual(self.session.chunk_queue.qsize(), 1)
        self.assertFalse(self.session.draining)
        self.assertTrue(self.session.stop_event.is_set())

    def test_esperar_hasta_vaciar_la_cola(self):
        def transcriptor_de_mentira(tic):
            # como si el transcriptor fuera vaciando la cola mientras se espera
            if self.session.draining and tic >= 6:
                self.worker.busy = False
                if self.session.chunk_queue.qsize():
                    self.session.chunk_queue.get()

        self.reloj.al_tic = transcriptor_de_mentira
        salida = limpio(self.correr("q", "e"))
        self.assertIn("⏳ Terminando 1 fragmento (~20 s de audio)…", salida)
        self.assertIn("[s] salir sin esperar", salida)
        self.assertTrue(self.session.status.finished)
        self.assertIn(("stop",), self.audio.llamadas)
        self.assertNotIn("se perdieron", salida)
        self.assertGreaterEqual(self.reloj.tics, 6)

    def test_mientras_termina_solo_valen_salir_y_abrir(self):
        salida = self.correr("q", "e", "p", "a", "s")
        self.assertNotIn("⏸ pausa", salida)
        self.assertEqual(self.abiertos, [str(self.session.file_path)])
        self.assertEqual(self.session.chunk_queue.qsize(), 1)
        self.assertTrue(self.session.stop_event.is_set())

    def test_ctrl_c_dos_veces_sale_perdiendo(self):
        salida = self.correr(CTRL_C, None, CTRL_C)
        self.assertIn("Quedan 1 fragmento", salida)
        self.assertEqual(self.session.chunk_queue.qsize(), 1)
        self.assertTrue(self.session.stop_event.is_set())

    def test_ctrl_c_mientras_termina_sale_ya(self):
        self.correr("q", "e", None, CTRL_C)
        self.assertTrue(self.session.draining)
        self.assertFalse(self.session.status.finished)
        self.assertTrue(self.session.stop_event.is_set())

    def test_el_manejador_de_sigint_encola_la_tecla_y_se_retira_al_salir(self):
        antes = signal.getsignal(signal.SIGINT)
        pantalla = self.pantalla("s")  # responde a la pregunta que abre el Ctrl+C
        pantalla._on_sigint(signal.SIGINT, None)
        self.assertEqual(pantalla._siguiente_tecla(), CTRL_C, "va antes que el teclado")
        pantalla._on_sigint(signal.SIGINT, None)

        instalados = []
        self.reloj.al_tic = lambda tic: instalados.append(signal.getsignal(signal.SIGINT))
        pantalla.run()
        self.assertTrue(instalados and all(h == pantalla._on_sigint for h in instalados), "durante el bucle Ctrl+C es suyo")
        self.assertIs(signal.getsignal(signal.SIGINT), antes)
        self.assertIn("Quedan 1 fragmento", self.salida.getvalue())


class TestPieBarato(BasePantalla):
    def test_no_se_redibuja_si_nada_cambio(self):
        self.escuchando()

        def sube_el_mic(tic):
            if tic == 3:
                self.audio.levels["mic"] = 32768.0

        self.reloj.al_tic = sube_el_mic
        self.correr(None, None, None, None, None, None, "q")
        l = self.reloj.longitudes
        self.assertGreater(l[0], 0, "el primer tic pinta cabecera y pie")
        self.assertEqual(l[0], l[1], "sin cambios no se escribe nada")
        self.assertEqual(l[1], l[2])
        self.assertGreater(l[3], l[2], "el medidor cambió: se redibuja una vez")
        self.assertEqual(l[3], l[4])
        self.assertEqual(l[4], l[5])
        self.assertIn("🎤 ████████", self.salida.getvalue())


class TestAscii(BasePantalla):
    ascii_mode = True

    def test_sin_emoji_ni_bloques(self):
        self.encolar_lineas()
        salida = self.correr(None, "q")
        texto = limpio(salida)
        self.assertIn("MIC Hola equipo", texto)
        self.assertIn("[cap] captura: bloqueo", texto)
        self.assertIn("! algo falló", texto)
        self.assertIn("OUT ........   MIC ........", texto)
        self.assertIn("* Escuchando + MIC · pendientes: 0 · (despierto)", texto)
        self.assertFalse([c for c in salida if ord(c) >= 0x2000 and c not in "–—·"], "nada que conhost no pinte")


class TestSinTerminal(BasePantalla):
    interactiva = False

    def test_salida_plana_y_cierre_limpio(self):
        self.encolar_lineas()
        larga = "palabra " * 60  # 480 caracteres: más que el ancho de la consola (200)
        self.session.ui_queue.put(("line", "10:00:09", "out", larga, []))
        self.encolar(20)
        salida = self.correr("q", "s")
        self.assertNotIn("\x1b", salida, "ni colores ni pie: va a un archivo")
        self.assertIn(f"10:00:09  {larga}\n", salida, "hacia un archivo no se parte a lo ancho de la consola")
        self.assertIn("  ● Escuchando\n", salida, "sin pie, los cambios de cabecera quedan como líneas")
        self.assertIn("10:00:01  🎤 Hola equipo\n", salida)
        self.assertIn("10:00:05  Hay un bloqueo\n          📸 captura: bloqueo\n", salida)
        self.assertIn("Quedan 1 fragmento (~20 s de audio) sin transcribir. [e] esperar · [s] salir perdiéndolos · [c] cancelar\n", salida)
        self.assertIn("⚠ se perdieron 1 fragmento", salida)
        self.assertTrue(self.session.stop_event.is_set())

    def test_esperar_tambien_se_anuncia_como_linea(self):
        self.escuchando()
        self.encolar(20)
        self.reloj.al_tic = lambda tic: self.session.chunk_queue.get() if tic >= 3 and self.session.chunk_queue.qsize() else None
        salida = self.correr("q", "e")
        self.assertIn("  ⏳ Terminando 1 fragmento (~20 s de audio)…\n", salida)
        self.assertTrue(self.session.status.finished)


if __name__ == "__main__":
    unittest.main()
