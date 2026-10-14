"""La grabación en la terminal se prueba con la sesión de mentira de tests/test_session.py, una
consola de rich que escribe en memoria y un teclado guionizado: no hay audio, ni Whisper, ni
pantalla, ni se toca config.json ni las carpetas reales.

Se comprueba lo que la ventana también hace (líneas con hora, 🎤 y 📸, pausa, captura, cerrar
preguntando por la cola) y lo propio de la terminal: el pie no se redibuja si nada cambió, Ctrl+C
dos veces, el panel de opciones [o] en plena grabación (dispositivos, pantallas y ventanas de
mentira), el modo ASCII sin emoji y la salida plana cuando no hay terminal.
"""

import io
import json
import pathlib
import re
import signal
import time
import unittest

from recorder import session as ses
from recorder.audio.capture import MUTE_WARN_SEC
from recorder.cli.consola import make_console
from recorder.cli.live import CTRL_C, ENTER, ESC, RETROCESO, PantallaEnVivo
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


class EntornoFalso:
    """Lo que el panel de opciones consulta: dispositivos, pantallas y ventanas fijos, sin PortAudio ni Win32."""

    def __init__(self, salidas=("Altavoces", "Auriculares"), micros=("Micro USB",)):
        self.salidas, self.micros = list(salidas), list(micros)
        self._pantallas = ["(todas las pantallas)", "Pantalla 1: 1920×1080 en (0, 0)"]
        self._ventanas = ["Daily | Teams"]
        self.releidas = 0  # veces que se pidieron las ventanas abiertas

    def dispositivos(self, kind):
        return list(self.salidas if kind == "out" else self.micros)

    def pantallas(self):
        return list(self._pantallas)

    def ventanas(self):
        self.releidas += 1
        return list(self._ventanas)


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
        self.entorno = EntornoFalso()

    def pantalla(self, *guion) -> PantallaEnVivo:
        return PantallaEnVivo(
            self.session, consola=self.consola, leer_tecla=Teclado(self.salida, guion), dormir=self.reloj,
            abrir=self.abiertos.append, entorno=self.entorno,
        )

    def config_guardada(self) -> dict:
        return json.loads(self.ruta.read_text(encoding="utf-8"))

    def resolver_falso(self):
        """Las fuentes resueltas que anota la sesión, sin PortAudio: el nombre configurado tal cual."""
        original = ses.resolve_wasapi_device
        ses.resolve_wasapi_device = lambda p, kind, pref: {"name": pref or ("Altavoces" if kind == "out" else "Micro USB")}
        self.addCleanup(lambda: setattr(ses, "resolve_wasapi_device", original))

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
        self.assertIn("[p] pausar · [c] captura · [r] reconectar audio · [a] abrir nota · [o] opciones · [q] salir", texto)
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


class TestPanelOpciones(BasePantalla):
    """[o] abre en el pie un panel para cambiar audio y capturas sin parar la grabación."""

    INDICE = "[1] salida de audio 🔊 · [2] micrófono 🎤 · [3] qué capturar 📸 · [4] calidad de capturas · [Esc/o] volver"

    def setUp(self):
        super().setUp()
        self.escuchando()
        self.resolver_falso()

    def test_abre_el_indice_y_esc_lo_cierra_sin_cambios(self):
        texto = limpio(self.correr("o", None, ESC, None, "q"))
        self.assertIn(self.INDICE, texto)
        self.assertIn("⚙ Opciones   ahora: 🔊 (predeterminado de Windows) · 🎤 (predeterminado de Windows) · 📸 todas las pantallas · capturas normales", texto)
        self.assertLess(texto.index("[Esc/o] volver"), texto.rindex("[p] pausar"), "al cerrar vuelven las teclas de siempre")
        self.assertEqual(self.audio.llamadas, [("start",), ("stop",)], "no se reabre nada")
        self.assertEqual(self.config_guardada()["out_dev"], "")
        self.assertNotIn("⚙ Fuentes", self.nota)

    def test_elige_la_salida_por_numero(self):
        texto = limpio(self.correr("o", "1", None, "3", None, "q"))
        self.assertIn("⚙ Salida de audio 🔊  elige con el número", texto)
        self.assertIn("  [1] (predeterminado de Windows)  (actual)\n", texto)
        self.assertIn("  [2] Altavoces\n", texto)
        self.assertIn("  [3] Auriculares\n", texto)
        self.assertIn("¿no aparece? si se conectó después de arrancar, sal con q y vuelve a entrar", texto)
        self.assertIn("[1-3] elegir · [Esc] volver · [o] cerrar", texto)
        self.assertIn(("restart", "Auriculares", "", True), self.audio.llamadas, "solo se reabre el audio")
        self.assertEqual(self.config_guardada()["out_dev"], "Auriculares", "se guarda en el config.json temporal")
        self.assertEqual(self.session.config.out_dev, "Auriculares")
        self.assertIn("⚙ salida de audio 🔊: Auriculares", texto, "la confirmación")
        self.assertIn("⚙ Fuentes: 🔊 Auriculares · 🎤 Micro USB", texto, "y lo que resolvió la sesión")
        self.assertRegex(self.nota, r"> ⚙ Fuentes: 🔊 Auriculares · 🎤 Micro USB \d\d:\d\d:\d\d\n")
        self.assertLess(texto.index("[1-3] elegir"), texto.rindex("[p] pausar"), "tras elegir, el panel se cierra")
        self.assertTrue(self.session.stop_event.is_set())

    def test_elegir_la_actual_no_aplica_nada(self):
        texto = limpio(self.correr("o", "1", "1", None, "q"))
        self.assertNotIn("restart", [c[0] for c in self.audio.llamadas])
        self.assertNotIn("⚙ salida de audio", texto)
        self.assertLess(texto.index("[1-3] elegir"), texto.rindex("[p] pausar"), "el panel se cierra igual")

    def test_mas_de_nueve_opciones_se_teclean_y_enter(self):
        self.entorno.salidas = [f"Salida {i}" for i in range(1, 13)]  # 13 opciones con el predeterminado
        self.session.config.out_dev = "Salida 5"
        texto = limpio(self.correr("o", "1", "1", None, "3", None, "q"))
        self.assertIn("[1-13] y Enter, elegir · [Esc] volver · [o] cerrar", texto)
        self.assertIn("› 1_  [1-13] y Enter, elegir", texto, "se ve lo tecleado")
        self.assertIn(("restart", "Salida 12", "", True), self.audio.llamadas, "13 es la última: se elige sin Enter")
        self.assertIn("⚙ salida de audio 🔊: Salida 12", texto)

    def test_enter_confirma_y_retroceso_borra(self):
        self.entorno.salidas = [f"Salida {i}" for i in range(1, 13)]
        self.session.config.out_dev = "Salida 5"
        texto = limpio(self.correr("o", "1", "1", "2", None, RETROCESO, RETROCESO, "1", None, ENTER, None, "q"))
        # «12» se elige al momento (ningún dígito más daría un número válido); el guion sigue en una segunda vuelta
        self.assertIn(("restart", "Salida 11", "", True), self.audio.llamadas)
        self.assertIn("› 1_", texto)
        self.assertNotIn("Salida 12", [c[1] for c in self.audio.llamadas if c[0] == "restart"])

    def test_enter_sin_nada_tecleado_y_un_cero_no_hacen_nada(self):
        self.entorno.salidas = [f"Salida {i}" for i in range(1, 13)]
        texto = limpio(self.correr("o", "1", ENTER, "0", None, "q", "q"))
        self.assertNotIn("restart", [c[0] for c in self.audio.llamadas])
        self.assertIn("[1-13] y Enter, elegir", texto)
        self.assertNotIn("› ", texto)

    def test_microfono_apagar_y_elegir_otro(self):
        texto = limpio(self.correr("o", "2", None, "1", None, "o", "2", None, "3", None, "q"))
        self.assertIn("  [1] apagado: no se transcribe el micrófono\n", texto)
        self.assertIn("  [2] (predeterminado de Windows)  (actual)\n", texto)
        self.assertIn("  [3] Micro USB\n", texto)
        self.assertIn(("restart", "", "", False), self.audio.llamadas, "apagar el micrófono reabre sin él")
        self.assertIn("⚙ micrófono 🎤: apagado: no se transcribe el micrófono", texto)
        self.assertIn("⚙ Fuentes: 🔊 Altavoces · 🎤 desactivado", texto)
        self.assertIn(("restart", "", "Micro USB", True), self.audio.llamadas, "elegir uno lo enciende con ese dispositivo")
        self.assertEqual((self.config_guardada()["mic"], self.config_guardada()["mic_dev"]), (True, "Micro USB"))
        self.assertIn("  [1] apagado: no se transcribe el micrófono  (actual)\n", texto, "la segunda vez estaba apagado")

    def test_que_capturar_una_ventana_y_releer_las_abiertas(self):
        self.entorno._ventanas = ["Daily | Teams", "notas.txt - Bloc de notas"]
        texto = limpio(self.correr("o", "3", None, "r", None, "4", None, "q"))
        self.assertIn("  [1] (todas las pantallas)  (actual)\n", texto)
        self.assertIn("  [2] Pantalla 1: 1920×1080 en (0, 0)\n", texto)
        self.assertIn("  [3] Ventana: Daily | Teams\n", texto)
        self.assertIn("[1-4] elegir · [r] releer ventanas · [Esc] volver · [o] cerrar", texto)
        self.assertEqual(self.entorno.releidas, 2, "[r] vuelve a leer las ventanas abiertas")
        self.assertEqual(self.config_guardada()["window"], "notas.txt - Bloc de notas")
        self.assertEqual(self.session.config.screen, 0)
        self.assertIn("⚙ qué capturar 📸: Ventana: notas.txt - Bloc de notas", texto)
        self.assertNotIn("restart", [c[0] for c in self.audio.llamadas], "las capturas no tocan el audio")
        self.assertEqual(len(self.buffers), 1, "misma carpeta y calidad: el buffer sigue")

    def test_que_capturar_una_pantalla(self):
        self.session.config.window = "Daily | Teams"
        texto = limpio(self.correr("o", "3", None, "2", None, "q"))
        self.assertIn("  [3] Ventana: Daily | Teams  (actual)\n", texto)
        self.assertEqual((self.config_guardada()["window"], self.config_guardada()["screen"]), ("", 1))

    def test_calidad_de_capturas(self):
        texto = limpio(self.correr("o", "4", None, "2", None, "q"))
        self.assertIn("  [3] Normales: JPEG 85 a tamaño real, texto nítido (~470 MB/h)  (actual)\n", texto)
        self.assertEqual(self.config_guardada()["captures"], "light")
        self.assertEqual([b.quality for b in self.buffers], ["normal", "light"], "el buffer se rearranca con la nueva calidad")
        self.assertEqual(self.buffers[0].llamadas, ["start", "stop"])
        self.assertIn("⚙ calidad de capturas: Ligeras: JPEG a media resolución (~90 MB/h)", texto)
        self.assertNotIn("restart", [c[0] for c in self.audio.llamadas])

    def test_las_frases_siguen_saliendo_con_el_panel_abierto(self):
        def llega_una_frase(tic):
            if tic == 3:
                self.session.ui_queue.put(("line", "10:00:01", "mic", "Hola equipo", []))

        self.reloj.al_tic = llega_una_frase
        texto = limpio(self.correr("o", "1", None, None, None, None, ESC, "o", "q"))
        self.assertIn("10:00:01  🎤 Hola equipo", texto)
        self.assertLess(texto.index("[1-3] elegir"), texto.index("Hola equipo"), "la frase llegó con la lista abierta")
        self.assertGreater(texto.rindex("[1-3] elegir"), texto.index("Hola equipo"), "y el pie siguió mostrando la lista")

    def test_ctrl_c_con_el_panel_abierto_pregunta_por_la_cola(self):
        self.encolar(20)
        texto = limpio(self.correr("o", "1", None, CTRL_C, None, "c", None, "q", "s"))
        self.assertIn("Quedan 1 fragmento (~20 s de audio) sin transcribir. [e] esperar", texto)
        self.assertLess(texto.rindex("[1-3] elegir"), texto.index("Quedan 1 fragmento"), "el panel se cierra al preguntar")
        self.assertNotIn("restart", [c[0] for c in self.audio.llamadas])
        self.assertTrue(self.session.stop_event.is_set())

    def test_q_en_el_panel_solo_lo_cierra(self):
        texto = limpio(self.correr("o", "q", None, "o", "1", "q", None, "q"))
        self.assertEqual(texto.count("Grabación terminada"), 1)
        self.assertEqual(texto.count("elige con el número"), 1, "se abrió la sección una vez y q la cerró sin salir")

    def test_el_pie_no_se_redibuja_con_el_panel_abierto_si_nada_cambia(self):
        self.correr(None, "o", None, None, None, "q", "q")  # la primera q cierra el panel; la segunda sale
        l = self.reloj.longitudes
        self.assertGreater(l[1], l[0], "abrir el panel repinta el pie")
        self.assertEqual(l[1], l[2], "con el panel abierto y sin cambios no se escribe nada")
        self.assertEqual(l[2], l[3])

    def test_si_config_no_se_puede_guardar_se_avisa_y_se_aplica_igual(self):
        def no_guarda(cfg):
            raise OSError("disco lleno")

        self.mgr.save = no_guarda
        texto = limpio(self.correr("o", "1", "3", None, "q"))
        self.assertIn("⚠ no se pudo guardar config.json: disco lleno; lo cambiado vale solo para esta sesión", texto)
        self.assertIn(("restart", "Auriculares", "", True), self.audio.llamadas)
        self.assertIn("⚙ salida de audio 🔊: Auriculares", texto)


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

    def test_el_panel_tambien_va_en_ascii(self):
        self.escuchando()
        salida = self.correr("o", None, "1", None, ESC, None, "q", "q")
        texto = limpio(salida)
        self.assertIn("[1] salida de audio OUT · [2] micrófono MIC · [3] qué capturar [cap] · [4] calidad de capturas · [Esc/o] volver", texto)
        self.assertIn("Opciones   ahora: OUT (predeterminado de Windows) · MIC (predeterminado de Windows)", texto)
        self.assertIn("  [1] (predeterminado de Windows)  (actual)", texto)
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

    def test_sin_pie_las_opciones_solo_avisan(self):
        salida = self.correr("o", "1", "q")
        self.assertIn("  ⚙ opciones: hacen falta una terminal y su pie; con la salida redirigida usa `daily config` al terminar\n", salida)
        self.assertNotIn("elige con el número", salida)
        self.assertEqual(self.audio.llamadas, [("start",), ("stop",)])


if __name__ == "__main__":
    unittest.main()
