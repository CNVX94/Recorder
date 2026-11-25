"""La grabación a pantalla completa (`PantallaCompleta`, recorder/cli/live.py) se prueba con la sesión de mentira de
tests/test_session.py, una consola de rich que escribe en memoria, un teclado guionizado y un reloj virtual: no hay
audio, ni Whisper, ni pantalla, ni se toca config.json ni las carpetas reales.

Cada cuadro que la pantalla pinta de verdad (solo se pinta si cambió) queda en `cuadros`, así que se mira lo que
había en pantalla en cada momento: el arranque, el autodesplazamiento y la revisión con RePág y Fin («N frases
nuevas»), el panel [o] con flechas y números, [m] y [?], la pregunta de salida, el vaciado, el resumen que queda
en el historial y que `--historial` y la salida redirigida siguen como antes.
"""
import io
import pathlib
import re
import time
import unittest
from typing import List

from rich.cells import cell_len

from recorder import session as ses
from recorder.audio.capture import MUTE_WARN_SEC
from recorder.cli import live
from recorder.cli.consola import JUEGO_CONSOLA, SEGUROS_CONSOLA, make_console
from recorder.cli.live import CTRL_C, ENTER, ESC, PantallaCompleta
from tests.test_cli_live import EntornoFalso, limpio
from tests.test_session import BaseSesion

PALANTE = "\x1b[?1049l"  # salir de la pantalla alternativa: lo que viene después es el historial


class Guion:
    """Lector de teclas de mentira: una entrada por sondeo. Un `str` es una tecla, None es «nada pulsado» y una
    función se ejecuta (con la pantalla) sin gastar el sondeo: sirve para mirar qué hay a la vista en ese momento."""

    def __init__(self, *pasos):
        self.pasos = list(pasos)
        self.pantalla = None

    def __call__(self):
        while self.pasos:
            paso = self.pasos.pop(0)
            if callable(paso):
                paso(self.pantalla)
                continue
            return paso
        return None


class Reloj:
    """El tiempo virtual: `dormir` lo avanza lo que se le pide, sin esperar de verdad."""

    def __init__(self, tope=6000):
        self.t = 1000.0
        self.tope, self.llamadas = tope, 0

    def __call__(self) -> float:
        return self.t

    def dormir(self, segundos: float) -> None:
        self.llamadas += 1
        if self.llamadas > self.tope:
            raise AssertionError("el bucle no acaba")
        self.t += segundos
        time.sleep(0.001)  # deja respirar a los hilos de la sesión


class PantallaGrabada(PantallaCompleta):
    """La pantalla de siempre, que además guarda cada cuadro que pinta: (hora virtual, líneas de texto)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cuadros: List[tuple] = []
        self.visuales: List[tuple] = []  # lo que cambia el aspecto sin cambiar el texto: pulso y frases resaltadas

    def _repintar(self, st, ahora):
        antes = self._firma
        super()._repintar(st, ahora)
        if self._firma is not antes:
            self.cuadros.append((ahora, self._firma[0]))
            self.visuales.append((ahora, self._firma[2]))


class BaseCompleta(BaseSesion):
    ancho, alto = 100, 30
    ascii_mode = False
    animaciones = "ninguna"  # sin pulso ni resalte: los cuadros solo cambian cuando cambia algo que se lee

    def setUp(self):
        super().setUp()
        self.salida = io.StringIO()
        self.reloj = Reloj()
        self.abiertos = []
        self.entorno = EntornoFalso()
        self.escuchando_ya = True
        original = ses.resolve_wasapi_device
        ses.resolve_wasapi_device = lambda p, kind, pref: {"name": pref or ("Altavoces" if kind == "out" else "Micro USB")}
        self.addCleanup(lambda: setattr(ses, "resolve_wasapi_device", original))

    def consola(self, ancho=None, alto=None, ascii_mode=None):
        return make_console(
            ascii_mode=self.ascii_mode if ascii_mode is None else ascii_mode, file=self.salida, width=ancho or self.ancho,
            height=alto or self.alto, force_terminal=True, force_interactive=True, color_system="truecolor", legacy_windows=False,
        )

    def pantalla(self, *guion, consola=None, **kwargs) -> PantallaGrabada:
        self.session.config.animations = self.animaciones
        teclado = Guion(*guion)
        p = PantallaGrabada(
            self.session, consola=consola or self.consola(), leer_tecla=teclado, dormir=self.reloj.dormir, reloj=self.reloj,
            abrir=self.abiertos.append, entorno=self.entorno, **kwargs,
        )
        teclado.pantalla = p
        return p

    def correr(self, *guion, **kwargs) -> PantallaGrabada:
        p = self.pantalla(*guion, **kwargs)
        self.assertEqual(p.run(), 0)
        return p

    @staticmethod
    def texto(cuadro) -> str:
        """Un cuadro como texto: sin los espacios que sobran a la derecha."""
        return "\n".join(linea.rstrip() for linea in cuadro)

    def ahora(self, p) -> str:
        """Lo que hay en pantalla ahora mismo (el último cuadro pintado)."""
        return self.texto(p._firma[0])

    def vio(self, p, frase: str) -> bool:
        return any(frase in self.texto(c) for _t, c in p.cuadros)

    def frases(self, n: int, kind="out", desde=0):
        for i in range(desde, desde + n):
            self.session.ui_queue.put(("line", f"10:{i // 60:02d}:{i % 60:02d}", kind, f"Frase número {i}", []))

    def tras_el_alt(self) -> str:
        """Lo que quedó escrito en el historial al salir de la pantalla alternativa."""
        return limpio(self.salida.getvalue().split(PALANTE)[-1])


class TestFunciones(unittest.TestCase):
    def test_duracion_y_reloj(self):
        self.assertEqual([live.duracion_texto(s) for s in (0, 45, 60, 28 * 60 + 40, 3900, 7500)], ["0 s", "45 s", "1 min", "28 min", "1 h 05 min", "2 h 05 min"])
        self.assertEqual([live.reloj_texto(s) for s in (0, 242, 3725, -3)], ["00:00:00", "00:04:02", "01:02:05", "00:00:00"])
        self.assertEqual(live.cantidad_texto(1, "grabacion_una_frase", "grabacion_n_frases"), "1 frase")
        self.assertEqual(live.cantidad_texto(142, "grabacion_una_frase", "grabacion_n_frases"), "142 frases")

    def test_el_pie_se_recorta_por_prioridad_y_se_pinta_en_su_orden(self):
        botones = [("p", "Pausar"), ("c", "Captura"), ("a", "Nota"), ("o", "Opciones"), ("m", "Rendimiento"), ("q", "Salir"), ("?", "Teclas")]
        largo = lambda lista: len("".join(f"[{t}] {w} · " for t, w in lista)) <= 100  # noqa: E731
        corto = lambda lista: len("".join(f"[{t}] {w} · " for t, w in lista)) <= 55  # noqa: E731
        mas = ("?", "Más")
        self.assertEqual(live.pie_con_prioridad(botones, "pqcoma", largo, mas), botones, "si caben todos, tal cual")
        recortado = live.pie_con_prioridad(botones, ("p", "q", "c", "o", "m", "a"), corto, mas)
        self.assertEqual([t for t, _w in recortado], ["p", "c", "q", "?"], "los de más prioridad, en el orden de pantalla")
        self.assertEqual(recortado[-1], mas)
        sin_mas = live.pie_con_prioridad(botones, ("p", "q"), corto, mas, con_mas=False)
        self.assertNotIn("?", [t for t, _w in sin_mas])

    def test_cada_texto_de_la_pantalla_existe(self):
        for clave in (
            "grabacion_nombre", "grabacion_preparando", "grabacion_cargando_modelo", "grabacion_nuevas", "grabacion_nueva_una",
            "grabacion_muda", "grabacion_caida", "grabacion_vuelve", "grabacion_esc", "grabacion_salir", "grabacion_vaciando",
            "tecla_m", "tecla_ayuda", "tecla_revisar", "grabacion_perdido", "grabacion_fin_aviso",
        ):
            live.ayuda.entrada(clave)


class TestArranque(BaseCompleta):
    def test_el_arranque_se_ve_en_la_propia_pantalla_y_pasa_solo_a_escuchando(self):
        def carga(p):
            self.assertIn("Preparando", self.ahora(p))

        p = self.correr(None, None, carga, lambda p: self.session.ui_queue.put(("status", "● Escuchando")), *[None] * 8, "q")
        antes = self.texto(p.cuadros[0][1])
        self.assertIn("Recorder · daily_", antes.splitlines()[0])
        self.assertIn("Preparando", antes.splitlines()[1])
        self.assertIn("Cargando el modelo (Calidad Media)…", antes)
        self.assertIn("√ Salida de audio: Altavoces", antes)
        self.assertIn("√ Micrófono: Micro USB", antes)
        self.assertIn("· Capturas: todas las pantallas, al oír", antes)
        self.assertEqual(antes.splitlines()[-1].strip(), "[q] Cancelar · [?] Teclas")
        despues = self.texto(p.cuadros[-1][1])
        self.assertIn("● Escuchando", despues.splitlines()[1])
        self.assertIn("Empieza la grabación · Altavoces · Micro USB", despues, "el arranque queda como primera línea")
        self.assertNotIn("Cargando el modelo", despues)

    def test_sin_escribir_en_el_historial_salvo_el_resumen(self):
        self.escuchando()
        self.correr("q")
        historial = self.tras_el_alt()
        self.assertTrue(historial.startswith("Recorder · grabación terminada\n"), historial)
        self.assertNotIn("Escuchando", historial)

    def test_una_fuente_que_falla_dice_por_que(self):
        ses.resolve_wasapi_device = lambda p, kind, pref: (_ for _ in ()).throw(OSError("sin dispositivo"))
        p = self.correr(None, "q")
        self.assertIn("× Salida de audio: no encontrado: predeterminado", self.texto(p.cuadros[0][1]))

    def test_si_el_modelo_falla_se_ve_el_motivo(self):
        self.session.ui_queue.put(("status", "⚠ No se pudo cargar el modelo"))
        p = self.correr(None, "q")
        self.assertIn("× ⚠ No se pudo cargar el modelo", self.texto(p.cuadros[-1][1]))


class TestEscuchando(BaseCompleta):
    def setUp(self):
        super().setUp()
        self.escuchando()

    def test_regiones_cabecera_transcripcion_y_pie(self):
        ui = self.session.ui_queue
        ui.put(("line", "10:00:01", "mic", "Hola equipo", []))
        ui.put(("line", "10:00:05", "out", "Hay un bloqueo", ["bloqueo"]))
        ui.put(("line", "10:00:06", "info", "(captura manual)", ["manual"]))
        ui.put(("notice", "10:00:07", "⚠ algo falló", "err"))
        self.encolar(20)
        p = self.correr(None, None, None, "q", "s")
        cuadro = self.texto([c for _t, c in p.cuadros if "Hay un bloqueo" in self.texto(c)][0]).splitlines()
        self.assertEqual(len(cuadro), 30, "ocupa la altura entera")
        self.assertRegex(cuadro[0], r"^ Recorder · daily_\d{4}-\d\d-\d\d_\d\d-\d\d\.md · Calidad Media · CPU")
        self.assertRegex(cuadro[1], r"^ ● Escuchando  00:00:\d\d · en cola 1 +PC [█░]{8}  Mic [█░]{8}$")
        self.assertTrue(set(cuadro[2].strip()) == {"─"}, "la regla")
        cuerpo = "\n".join(cuadro[3:])
        self.assertIn("10:00:01  Mic Hola equipo\n", cuerpo + "\n")
        self.assertIn("10:00:05  PC  Hay un bloqueo\n", cuerpo + "\n")
        self.assertIn("              📸 captura: bloqueo", cuerpo, "la captura, bajo el texto")
        self.assertIn("10:00:06      📸 captura manual", cuerpo, "la manual es una sola línea, sin icono de fuente")
        self.assertIn("10:00:07      ⚠ algo falló", cuerpo)
        self.assertEqual(
            cuadro[-1].strip(), "[p] Pausar · [c] Captura · [a] Nota · [o] Opciones · [m] Rendimiento · [q] Salir · [?] Teclas",
        )

    def test_a_60_columnas_nada_se_sale_y_el_pie_se_recorta_con_criterio(self):
        self.frases(3)
        self.session.ui_queue.put(("line", "10:00:09", "out", "palabra " * 20, []))
        p = self.correr(None, None, "q", consola=self.consola(60, 24))
        cuadro = [c for _t, c in p.cuadros if "Frase número 2" in self.texto(c)][-1]
        self.assertEqual(len(cuadro), 24)
        self.assertTrue(all(cell_len(linea) <= 60 for linea in cuadro), "ninguna línea pasa de 60 columnas")
        texto = self.texto(cuadro)
        self.assertEqual(texto.splitlines()[-1].strip(), "[p] Pausar · [c] Captura · [q] Salir · [?] Más")
        self.assertRegex(texto.splitlines()[1], r"PC [█░]{4}  Mic [█░]{4}$")
        self.assertIn("\n               palabra palabra", texto, "las frases largas se parten con sangría bajo el texto")

    def test_pausa_y_seguir(self):
        p = self.correr("p", None, lambda p: self.assertIn("⏸ En pausa", self.ahora(p)), "p", None, "q")
        pausa = [self.texto(c) for _t, c in p.cuadros if "⏸ En pausa" in self.texto(c)][-1]
        self.assertIn("[p] Seguir", pausa)
        self.assertIn("⏸ pausa: no se escucha audio nuevo", pausa)
        self.assertIn("▶ sigue la grabación", self.ahora(p))
        self.assertIn("> ⏸ Pausa", self.nota)
        self.assertIn("> ▶ Continúa", self.nota)

    def test_capturar_reconectar_y_abrir_la_nota(self):
        self.session.config.out_dev = "Auriculares"
        self.correr("r", "a", "q")
        self.assertIn(("restart", "Auriculares", "", True), self.audio.llamadas)
        self.assertEqual(self.abiertos, [str(self.session.file_path)])

    def test_la_captura_manual_llega_por_el_sondeo_y_cuenta(self):
        original = ses.take_screenshot
        ses.take_screenshot = lambda tag, caps_dir, screen_idx=0, window="": pathlib.Path(caps_dir) / "manual_x.png"
        self.addCleanup(lambda: setattr(ses, "take_screenshot", original))
        p = self.pantalla("c", *[None] * 60, "q")
        p.run()
        self.assertTrue(self.vio(p, "📸 captura manual"))
        self.assertEqual(p.resumen.capturas, 1)

    def test_esc_nunca_termina_la_grabacion(self):
        p = self.correr(ESC, None, lambda p: self.assertIn("Para terminar la grabación pulsa q. Esc solo cierra paneles.", self.ahora(p)), ESC, None, "q")
        self.assertEqual(self.audio.llamadas, [("start",), ("stop",)], "sigue grabando tras dos Esc")
        self.assertTrue(self.session.stop_event.is_set(), "salió con q, no con Esc")

    def test_el_aviso_pasajero_se_va_solo(self):
        p = self.pantalla(ESC, *[None] * 200, "q")
        p.run()
        aviso = [t for t, c in p.cuadros if "Esc solo cierra paneles" in self.texto(c)]
        sin = [t for t, c in p.cuadros if "Esc solo cierra paneles" not in self.texto(c)]
        self.assertTrue(aviso and sin[-1] - aviso[0] >= live.DURACION_AVISO, "dura DURACION_AVISO s")

    def test_izquierda_y_derecha_no_reabren_el_audio(self):
        self.correr("izquierda", "derecha", "o", "izquierda", "derecha", ESC, "q")
        self.assertEqual(self.audio.llamadas, [("start",), ("stop",)])

    def test_una_tecla_desconocida_no_hace_nada(self):
        p = self.correr("x", "z", "q")
        self.assertNotIn("⚠", self.ahora(p))


class TestRevisar(BaseCompleta):
    def setUp(self):
        super().setUp()
        self.escuchando()

    def test_sigue_lo_ultimo_y_no_empieza_a_media_frase(self):
        self.frases(80)
        p = self.correr(None, None, "q", consola=self.consola(60, 24))
        texto = self.texto(p.cuadros[-1][1])
        self.assertIn("Frase número 79", texto, "lo último a la vista")
        self.assertNotIn("Frase número 0\n", texto)
        primera = [linea for linea in texto.splitlines()[3:] if linea.strip()][0]
        self.assertRegex(primera, r"^ \d\d:\d\d:\d\d  PC  Frase", "la primera línea es el principio de una frase")

    def test_repag_revisa_y_cuenta_las_frases_nuevas_hasta_que_fin_vuelve(self):
        self.frases(80)

        def nuevas(p):
            self.frases(3, desde=80)

        mirando = {}

        def foto(nombre):
            return lambda p: mirando.__setitem__(nombre, self.ahora(p))

        p = self.correr(
            None, None, "repag", None, foto("revisando"), nuevas, *[None] * 6, foto("con nuevas"), "fin", None, foto("al final"),
            "q", consola=self.consola(100, 30),
        )
        revisando = mirando["revisando"]
        self.assertNotIn("Frase número 79", revisando)
        self.assertIn("[RePág/AvPág] Revisar · [Fin] Lo último · [p] Pausar · [c] Captura · [q] Salir · [?] Teclas", revisando)
        self.assertNotIn("frases nuevas", revisando)
        con = mirando["con nuevas"]
        self.assertIn("↓ 3 frases nuevas abajo · Fin vuelve a lo último", con)
        self.assertNotIn("Frase número 82", con, "lo nuevo no mueve la vista")
        al_final = mirando["al final"]
        self.assertIn("Frase número 82", al_final)
        self.assertNotIn("frases nuevas", al_final)
        self.assertIn("[p] Pausar", al_final.splitlines()[-1])

    def test_una_frase_nueva_se_cuenta_en_singular(self):
        self.frases(80)
        vista = {}
        p = self.correr(
            None, None, "inicio", None, lambda p: self.frases(1, desde=80), *[None] * 6,
            lambda p: vista.__setitem__("s", self.ahora(p)), "q",
        )
        self.assertIn("↓ 1 frase nueva abajo · Fin vuelve a lo último", vista["s"])

    def test_avpag_al_llegar_abajo_vuelve_a_seguir_y_las_flechas_mueven_una_frase(self):
        self.frases(80)
        vista = {}

        def foto(nombre):
            return lambda p: vista.__setitem__(nombre, (self.ahora(p), p._arriba))

        self.correr(
            None, None, "inicio", None, foto("inicio"), "abajo", None, foto("abajo"), "arriba", "arriba", None, foto("arriba"),
            "avpag", "avpag", "avpag", "avpag", "avpag", "avpag", "avpag", "avpag", "avpag", "avpag", None, foto("abajo del todo"), "q",
        )
        primero = self.frases_a_la_vista(vista["inicio"][0])
        self.assertEqual(primero, 0, "Inicio va a la primera frase")
        self.assertEqual(vista["abajo"][1], 1, "↓ baja una frase")
        self.assertEqual(vista["arriba"][1], 0, "↑ no pasa de la primera")
        self.assertIsNone(vista["abajo del todo"][1], "AvPág hasta llegar abajo vuelve a seguir lo último")
        self.assertIn("Frase número 79", vista["abajo del todo"][0])

    @staticmethod
    def frases_a_la_vista(texto: str) -> int:
        return [int(n) for n in re.findall(r"Frase número (\d+)", texto)][0]

    def test_la_frase_nueva_se_resalta_1_5_s_y_se_apaga_con_un_solo_cambio(self):
        self.animaciones = "completas"
        self.frases(1)
        p = self.correr(*[None] * 60, "q")
        n = next(f.n for f in p._frases if f.texto == "Frase número 0")
        resaltada = [t for t, v in p.visuales if (n,) in v]
        self.assertTrue(resaltada, "se pintó resaltada")
        self.assertLessEqual(resaltada[-1] - resaltada[0], live.DURACION_FRASE_NUEVA + live.INTERVALO, "dura DURACION_FRASE_NUEVA")
        self.assertNotIn((n,), p.visuales[-1][1], "y al final ya no")
        apagado = [t for t, v in p.visuales if (n,) not in v and t > resaltada[-1]]
        self.assertTrue(apagado, "el repintado por el fin del resalte ocurre solo")

    def test_con_animaciones_ninguna_no_hay_resalte_ni_pulso(self):
        self.frases(1)
        p = self.correr(*[None] * 30, "q")
        self.assertEqual({f.nueva_hasta for f in p._frases}, {0.0})
        self.assertTrue(all(vis[-1] == () for _t, vis in p.visuales), "sin resalte en ningún cuadro")

    def test_el_pulso_del_indicador_cambia_una_vez_por_segundo(self):
        self.animaciones = "completas"
        p = self.correr(*[None] * 90, "q")
        pulsos = [vis[0] for _t, vis in p.visuales]
        cambios = sum(1 for a, b in zip(pulsos, pulsos[1:]) if a != b)
        segundos = p.visuales[-1][0] - p.visuales[0][0]
        self.assertGreaterEqual(cambios, 2)
        self.assertLessEqual(cambios, segundos / live.TIC_LENTO + 1, "como mucho uno por segundo")
    def test_solo_se_guardan_las_ultimas_lineas_en_memoria(self):
        p = self.pantalla("q")
        for i in range(live.LINEAS_MEMORIA + 25):
            p._anadir("10:00:00", "out", f"frase {i}", "texto")
        self.assertEqual(len(p._frases), live.LINEAS_MEMORIA)
        self.assertEqual(p._frases[0].texto, "frase 25")
        self.assertEqual(p._frases[0].n, 25, "el número de orden no se reutiliza")


class TestPanelOpciones(BaseCompleta):
    def setUp(self):
        super().setUp()
        self.escuchando()

    def test_indice_con_flechas_y_ayuda_de_la_fila(self):
        vista = {}
        self.correr(
            "o", None, lambda p: vista.__setitem__("indice", self.ahora(p)), "abajo", None,
            lambda p: vista.__setitem__("abajo", self.ahora(p)), ESC, None, lambda p: vista.__setitem__("cerrado", self.ahora(p)), "q",
        )
        indice = vista["indice"]
        self.assertIn("── Opciones de la grabación ─", indice)
        self.assertIn("▶ 1  Salida de audio", indice)
        self.assertIn("  2  Micrófono", indice)
        self.assertIn("  3  Qué capturar         todas las pantallas", indice)
        self.assertIn("(predeterminado de Windows)", indice)
        self.assertIn("El altavoz o los auriculares por los que oyes la reunión", indice, "la ayuda de la fila elegida")
        self.assertIn("[↑↓] Mover · [Enter] Abrir · [1-4] Directo · [Esc] Cerrar · [q] Salir", indice)
        self.assertIn("▶ 2  Micrófono", vista["abajo"])
        self.assertIn("El micrófono con el que hablas en la reunión", vista["abajo"])
        self.assertNotIn("Opciones de la grabación", vista["cerrado"], "Esc en el índice lo cierra")
        self.assertIn("[p] Pausar", vista["cerrado"].splitlines()[-1], "y vuelven las teclas de siempre")

    def test_la_transcripcion_sigue_viva_con_el_panel_abierto(self):
        vista = {}
        p = self.correr(
            "o", None, lambda p: self.frases(1), *[None] * 8, lambda p: vista.__setitem__("v", self.ahora(p)), ESC, "q",
        )
        self.assertIn("Frase número 0", vista["v"])
        self.assertIn("Opciones de la grabación", vista["v"])

    def test_elige_la_salida_por_numero_y_se_aplica_solo_el_audio(self):
        vista = {}
        p = self.correr(
            "o", "1", None, lambda p: vista.__setitem__("lista", self.ahora(p)), "3", None,
            lambda p: vista.__setitem__("tras", self.ahora(p)), "q",
        )
        lista = vista["lista"]
        self.assertIn("── Opciones de la grabación › Salida de audio ─", lista)
        self.assertIn("▶ 1  (predeterminado de Windows)  (actual)", lista, "se abre con la fila en lo actual")
        self.assertIn("  2  Altavoces", lista)
        self.assertIn("  3  Auriculares", lista)
        self.assertIn("¿No aparece? Si lo conectaste después de empezar, sal con q y vuelve a entrar.", lista)
        self.assertIn("[↑↓] Mover · [Enter] Elegir · [1-3] Directo · [Esc] Volver · [q] Salir", lista)
        self.assertIn(("restart", "Auriculares", "", True), self.audio.llamadas)
        self.assertEqual(self.session.config.out_dev, "Auriculares")
        tras = vista["tras"]
        self.assertNotIn("Opciones de la grabación", tras, "al elegir, el panel se cierra")
        self.assertIn("✅ Salida de audio: Auriculares", tras, "y el aviso dice qué cambió")

    def test_elige_con_flechas_y_enter(self):
        self.correr("o", "abajo", ENTER, None, "abajo", ENTER, None, "q")
        # Micrófono (segunda fila) → su lista; la fila inicial es la actual (el predeterminado, tras «apagado»)
        self.assertIn(("restart", "", "Micro USB", True), self.audio.llamadas)

    def test_esc_vuelve_de_la_seccion_al_indice_y_de_ahi_cierra(self):
        vista = {}
        self.correr(
            "o", "2", None, ESC, None, lambda p: vista.__setitem__("indice", (self.ahora(p), p._panel.fila)), ESC, None,
            lambda p: vista.__setitem__("fuera", p._panel), "q",
        )
        self.assertIn("▶ 2  Micrófono", vista["indice"][0], "el índice vuelve con la sección que se dejó")
        self.assertIsNone(vista["fuera"])
        self.assertEqual(self.audio.llamadas, [("start",), ("stop",)], "sin cambiar nada")

    def test_que_capturar_ofrece_releer_las_ventanas(self):
        vista = {}
        self.correr("o", "3", None, lambda p: vista.__setitem__("pie", self.ahora(p).splitlines()[-1]), "r", None, "q")
        self.assertIn("[r] Releer ventanas", vista["pie"])
        self.assertEqual(self.entorno.releidas, 2)

    def test_una_lista_larga_se_recorta_con_marcas(self):
        self.entorno.salidas = [f"Salida {i}" for i in range(1, 40)]
        vista = {}
        self.correr("o", "1", None, "abajo", "abajo", *["abajo"] * 20, None, lambda p: vista.__setitem__("v", self.ahora(p)), "q", consola=self.consola(60, 24))
        self.assertRegex(vista["v"], r"↑ \d+ más arriba")
        self.assertRegex(vista["v"], r"↓ \d+ más abajo")

    def test_q_en_el_panel_lo_cierra_y_sale_igual(self):
        self.encolar(20)
        p = self.correr("o", "q", None, "s")
        self.assertTrue(self.vio(p, "Salir de la grabación"), "q con audio pendiente pregunta")
        self.assertTrue(self.session.stop_event.is_set())


class TestVistas(BaseCompleta):
    def setUp(self):
        super().setUp()
        self.escuchando()
        self.frases(2)

    def test_rendimiento_en_vivo_y_esc_vuelve(self):
        vista = {}
        self.correr(
            "m", None, lambda p: vista.__setitem__("m", self.ahora(p)), ESC, None, lambda p: vista.__setitem__("atras", self.ahora(p)), "q",
        )
        m = vista["m"]
        self.assertIn("Grabación › Rendimiento", m)
        self.assertIn("Cargando el modelo", m, "sin ningún fragmento transcrito aún")
        self.assertIn("Velocidad", m)
        self.assertIn("En cola", m)
        self.assertIn("[Esc] Volver a la transcripción · [p] Pausar · [c] Captura · [q] Salir · [?] Teclas", m)
        self.assertNotIn("Rendimiento", vista["atras"].replace("[m] Rendimiento", ""))
        self.assertIn("Frase número 1", vista["atras"])

    def test_rendimiento_con_datos(self):
        from recorder.metricas import MotorEfectivo, Velocidad

        self.worker.velocidad = Velocidad()
        self.worker.motor = MotorEfectivo("faster-whisper", "cpu", "small", 5, 4)
        self.worker.velocidad.registrar(10, 4)
        vista = {}
        self.correr("m", None, lambda p: vista.__setitem__("m", self.ahora(p)), "q")
        self.assertIn("Va al día", vista["m"])
        self.assertIn("2,5×", vista["m"])
        self.assertIn("faster-whisper · CPU, 4 hilos · small · haz 5", vista["m"])

    def test_leyenda_de_teclas_y_esc_vuelve(self):
        vista = {}
        self.correr("?", None, lambda p: vista.__setitem__("t", self.ahora(p)), ESC, None, lambda p: vista.__setitem__("atras", self.ahora(p)), "q")
        t = vista["t"]
        self.assertIn("Grabación › Teclas", t)
        for fragmento in ("Pausar / seguir:", "Captura:", "Abrir la nota:", "Reconectar:", "Opciones:", "Rendimiento:", "Revisar:", "Teclas:", "Salir:"):
            self.assertIn(fragmento, t)
        self.assertIn("RePág AvPág", t)
        self.assertEqual(t.splitlines()[-1].strip(), "[Esc] Volver a la transcripción · [q] Salir")
        self.assertIn("Frase número 1", vista["atras"])

    def test_la_leyenda_se_desplaza_si_no_cabe(self):
        vista = {}
        self.correr(
            "?", None, lambda p: vista.__setitem__("a", self.ahora(p)), *["abajo"] * 3, None, lambda p: vista.__setitem__("b", self.ahora(p)),
            "fin", None, lambda p: vista.__setitem__("c", self.ahora(p)), "q", consola=self.consola(60, 24),
        )
        self.assertRegex(vista["a"], r"↓ \d+ más abajo")
        self.assertRegex(vista["b"], r"↑ \d+ más arriba")
        self.assertIn("Salir:", vista["c"])
        self.assertNotRegex(vista["c"], r"↓ \d+ más abajo")

    def test_p_y_c_valen_en_las_vistas_y_q_sale_igual(self):
        self.correr("m", "p", None, "q")
        self.assertTrue(self.session.paused)
        self.assertTrue(self.session.stop_event.is_set())

    def test_m_y_o_no_abren_nada_en_la_leyenda(self):
        vista = {}
        self.correr("?", "m", "o", None, lambda p: vista.__setitem__("t", self.ahora(p)), "q")
        self.assertIn("Grabación › Teclas", vista["t"])
        self.assertNotIn("Opciones de la grabación", vista["t"])


class TestAvisosDeFuentes(BaseCompleta):
    def setUp(self):
        super().setUp()
        self.escuchando()

    def test_fuente_caida_con_su_reintento_y_aviso_que_dura(self):
        self.audio.attempts["out"] = 2
        self.audio.source_callback("out", False, "OSError(-9999)")
        p = self.correr(None, None, "q")
        cuadro = self.texto(p.cuadros[-1][1])
        self.assertRegex(cuadro.splitlines()[1], r"PC × reintento 2  Mic [█░]{8}$")
        self.assertIn("× PC se cortó: reintento 2. Si no vuelve, pulsa r o revisa que siga conectado.", cuadro)
        self.assertIn("⚠ PC se cortó: reintento 2.", cuadro, "y queda como línea de la transcripción")
        self.assertEqual(p.resumen.avisos, ((ses.AVISO_CAIDA, "out"),))

    def test_fuente_sin_audio_en_pausa(self):
        self.audio.started_at = time.time() - 2 * MUTE_WARN_SEC
        self.audio.last_chunk_at = {"out": time.time() - 5, "mic": 0.0}
        p = self.correr(None, None, "p", None, None, "q")
        cuadro = [self.texto(c) for _t, c in p.cuadros if "En pausa" in self.texto(c)][-1]
        self.assertRegex(cuadro.splitlines()[1], r"Mic sin audio$")
        self.assertIn("Mic lleva 10 min sin audio mientras la otra fuente suena. Si alguien habló por ahí, pulsa o y elige otro dispositivo.", " ".join(cuadro.split()))
        self.assertIn("⚠ Mic lleva 10 min sin audio", cuadro.split("\n", 3)[3], "también como línea con hora")

    def test_micro_apagado_no_se_pinta_su_medidor(self):
        self.session.config.mic = False
        p = self.correr(None, "q")
        self.assertNotIn("Mic", self.texto(p.cuadros[-1][1]).splitlines()[1])

    def test_la_fuente_vuelve(self):
        self.audio.source_callback("mic", True, "")
        p = self.correr(None, "q")
        self.assertTrue(self.vio(p, "✅ Mic ha vuelto: se sigue transcribiendo"))


class TestSalida(BaseCompleta):
    def setUp(self):
        super().setUp()
        self.escuchando()
        self.encolar(20)

    def test_la_pregunta_esc_sigue_grabando_y_s_sale_perdiendo(self):
        vista = {}
        p = self.correr(
            "q", None, lambda p: vista.__setitem__("pregunta", self.ahora(p)), ESC, None, lambda p: vista.__setitem__("sigue", self.ahora(p)),
            "q", None, "s",
        )
        pregunta = vista["pregunta"]
        self.assertIn("── Salir de la grabación ─", pregunta)
        self.assertIn("Quedan 1 fragmento (~20 s de audio) sin transcribir.", pregunta)
        self.assertIn("▶ Esperar y salir", pregunta)
        self.assertIn("  Salir sin esperar", pregunta)
        self.assertIn("  Seguir grabando", pregunta)
        self.assertIn("Termina de transcribir lo pendiente sin escuchar audio nuevo", pregunta, "la ayuda de la fila elegida")
        self.assertEqual(pregunta.splitlines()[-1].strip(), "[e] Esperar y salir · [s] Salir sin esperar · [Esc] Seguir grabando")
        self.assertNotIn("Salir de la grabación", vista["sigue"], "Esc sigue grabando")
        self.assertEqual(self.session.chunk_queue.qsize(), 1)
        self.assertTrue(self.session.stop_event.is_set())
        historial = self.tras_el_alt()
        self.assertIn("⚠ Se perdieron 1 fragmento (~20 s de audio) sin transcribir.", historial)
        self.assertEqual(p.perdido, "1 fragmento (~20 s de audio)")

    def test_a_60_columnas_el_pie_de_la_pregunta_cabe(self):
        vista = {}
        self.correr("q", None, lambda p: vista.__setitem__("p", self.ahora(p)), "s", consola=self.consola(60, 24))
        self.assertEqual(vista["p"].splitlines()[-1].strip(), "[e] Esperar y salir · [s] Salir sin esperar · [Esc] Seguir")

    def test_las_filas_se_eligen_con_flechas_y_enter(self):
        vista = {}
        self.correr(
            "q", None, "abajo", None, lambda p: vista.__setitem__("fila", self.ahora(p)), ENTER,
        )
        self.assertIn("  Esperar y salir", vista["fila"])
        self.assertIn("▶ Salir sin esperar", vista["fila"])
        self.assertIn("Sale ya. Lo que faltaba por transcribir no llega a la nota.", vista["fila"])
        self.assertEqual(self.session.chunk_queue.qsize(), 1)
        self.assertFalse(self.session.draining, "Enter en «Salir sin esperar» no espera")

    def test_enter_en_seguir_grabando(self):
        self.correr("q", "abajo", "abajo", ENTER, None, None, "q", "s")
        self.assertFalse(self.session.draining)

    def test_mientras_pregunta_la_c_no_captura(self):
        capturas = []
        self.session.manual_screenshot = lambda: capturas.append(1)
        self.correr("q", None, "c", None, "s")
        self.assertEqual(capturas, [])

    def test_esperar_vacia_la_cola_con_progreso_y_sale_sola(self):
        self.encolar(20)
        vista = {}

        def transcribe(tic=[0]):
            if self.session.draining and self.session.chunk_queue.qsize():
                self.session.chunk_queue.get()

        p = self.correr(
            "q", "e", None, None, lambda p: vista.__setitem__("espera", self.ahora(p)), *[lambda p: transcribe(), None] * 3, None, None,
        )
        espera = vista["espera"]
        self.assertIn("── Terminando lo pendiente ─", espera)
        self.assertRegex(espera, r"█*░* +0 de 2 trozos · unos \d+ s")
        self.assertIn("… Terminando", espera.splitlines()[1])
        self.assertRegex(espera.splitlines()[1], r"PC ░{8}  Mic ░{8}$", "ya no se escucha: los medidores vacíos")
        self.assertEqual(espera.splitlines()[-1].strip(), "[s] Salir sin esperar · [a] Nota")
        self.assertTrue(self.session.status.finished)
        self.assertNotIn("Se perdieron", self.tras_el_alt())
        self.assertEqual(p.perdido, "")

    def test_mientras_termina_solo_valen_salir_y_abrir_la_nota(self):
        self.correr("q", "e", "p", "c", "o", "a", "s")
        self.assertEqual(self.abiertos, [str(self.session.file_path)])
        self.assertFalse(self.session.paused)
        self.assertEqual(self.session.chunk_queue.qsize(), 1)

    def test_ctrl_c_dos_veces_sale_perdiendo_y_una_sola_pregunta(self):
        self.correr(CTRL_C, None, CTRL_C)
        self.assertEqual(self.session.chunk_queue.qsize(), 1)
        self.assertTrue(self.session.stop_event.is_set())

    def test_sin_audio_pendiente_q_sale_sin_preguntar(self):
        self.session.chunk_queue.get()
        p = self.correr("q")
        self.assertFalse(self.vio(p, "Salir de la grabación"))


class TestResumen(BaseCompleta):
    def test_el_resumen_es_lo_unico_que_queda_en_el_historial(self):
        self.escuchando()
        ui = self.session.ui_queue
        ui.put(("line", "10:00:01", "mic", "Hola equipo", []))
        ui.put(("line", "10:00:05", "out", "Hay un bloqueo", ["bloqueo"]))
        ui.put(("line", "10:00:06", "out", "Otra frase", []))
        self.audio.source_callback("out", False, "OSError(-9999)")
        p = self.correr(None, lambda p: setattr(self.session, "_inicio", time.monotonic() - 28 * 60), None, None, "q")
        historial = self.tras_el_alt().splitlines()
        self.assertEqual(historial[0], "Recorder · grabación terminada")
        self.assertEqual(historial[1], f"  Nota      {self.session.file_path}")
        self.assertEqual(historial[2], "  Duración  28 min · 3 frases · 1 captura")
        self.assertEqual(historial[3], "  Avisos    1: PC se cortó")
        self.assertEqual(len(historial), 4, "sin «se perdieron» si se salió sin pendientes")
        self.assertIn("\x1b[1m", self.salida.getvalue().split(PALANTE)[-1], "el título en negrita")

    def test_sin_avisos_no_hay_linea_de_avisos(self):
        self.escuchando()
        self.correr("q")
        self.assertNotIn("Avisos", self.tras_el_alt())

    def test_el_resumen_se_puede_devolver_como_aviso_para_el_menu(self):
        self.escuchando()
        self.session.ui_queue.put(("line", "10:00:01", "mic", "Hola equipo", []))
        p = self.correr(None, lambda p: setattr(self.session, "_inicio", time.monotonic() - 90), "q", imprimir_resumen=False)
        self.assertEqual(self.tras_el_alt(), "", "abierta desde el menú no imprime nada")
        self.assertEqual(p.aviso_fin(), f"Grabación terminada: 1 min · 1 frase · 0 capturas · {self.session.file_path}")


class TestSimbolos(BaseCompleta):
    def setUp(self):
        super().setUp()
        self.escuchando()
        ui = self.session.ui_queue
        ui.put(("line", "10:00:01", "mic", "Hola equipo", []))
        ui.put(("line", "10:00:05", "out", "Hay un bloqueo", ["bloqueo"]))
        ui.put(("line", "10:00:06", "info", "(captura manual)", ["manual"]))

    def recorrer(self, p) -> str:
        return "\n".join("\n".join(c) for _t, c in p.cuadros)

    def test_ascii_sin_emoji_ni_bloques(self):
        self.ascii_mode = True
        vista = []
        p = self.correr(
            None, "p", None, "o", None, lambda p: vista.append(1), ESC, "m", None, ESC, "?", None, ESC, "q",
            consola=self.consola(100, 30, ascii_mode=True),
        )
        todo = self.recorrer(p) + limpio(self.salida.getvalue().split(PALANTE)[-1])
        self.assertIn("* Escuchando", todo)
        self.assertIn("[cap] captura: bloqueo", todo)
        self.assertIn("PC ........", todo)
        self.assertEqual([c for c in todo if ord(c) >= 0x2000 and c not in "–—·"], [], "nada que conhost no pinte")

    def test_juego_consola_solo_con_simbolos_seguros(self):
        consola = self.consola(100, 30)
        consola.juego, consola.ascii_mode = JUEGO_CONSOLA, False
        p = self.correr(None, "p", None, "o", None, ESC, "m", None, ESC, "?", None, ESC, "q", consola=consola)
        todo = self.recorrer(p) + limpio(self.salida.getvalue().split(PALANTE)[-1])
        fuera = sorted({c for c in todo if ord(c) >= 0x2000 and c not in SEGUROS_CONSOLA and c not in "–—"})
        self.assertEqual(fuera, [], "solo lo que Consolas dibuja")
        self.assertIn("‖ En pausa", todo)
        self.assertIn("■ captura: bloqueo", todo)


class TestCoste(BaseCompleta):
    def test_quieto_no_se_repinta_y_nunca_mas_de_cinco_por_segundo(self):
        self.escuchando()
        p = self.pantalla(*[None] * 400, "q")
        p.run()
        tiempos = [t for t, _c in p.cuadros]
        segundos = tiempos[-1] - tiempos[0]
        self.assertLess(len(p.cuadros), segundos + 3, "solo cambia el reloj, una vez por segundo")
        for t in tiempos:
            self.assertLessEqual(sum(1 for u in tiempos if t <= u < t + 1.0), live.INTERVALO ** -1)

    def test_ctrl_c_y_salida_dejan_la_terminal_limpia(self):
        import signal

        antes = signal.getsignal(signal.SIGINT)
        self.escuchando()
        p = self.pantalla(None, CTRL_C)
        p.run()
        self.assertIs(signal.getsignal(signal.SIGINT), antes)
        self.assertIn(PALANTE, self.salida.getvalue(), "sale de la pantalla alternativa")
        self.assertIn("\x1b[?25h", self.salida.getvalue(), "y devuelve el cursor")

    def test_demasiado_pequena_solo_pinta_el_aviso(self):
        self.escuchando()
        p = self.correr(None, "q", consola=self.consola(50, 20))
        texto = self.texto(p.cuadros[-1][1])
        self.assertIn("Ventana demasiado pequeña", texto)
        self.assertNotIn("Escuchando", texto)


class TestElegirPantalla(BaseCompleta):
    def llamar(self, consola, **kwargs):
        teclado = Guion(None, "q")
        return live.grabar(
            consola, session=self.session, leer_tecla=teclado, dormir=self.reloj.dormir, abrir=self.abiertos.append,
            entorno=self.entorno, **kwargs,
        )

    def test_en_una_terminal_es_la_pantalla_completa(self):
        self.escuchando()
        self.assertEqual(self.llamar(self.consola()), 0)
        self.assertIn("\x1b[?1049h", self.salida.getvalue(), "pantalla alternativa")
        self.assertIn("Recorder · grabación terminada", self.tras_el_alt())

    def test_con_historial_se_conserva_el_modo_de_antes(self):
        self.escuchando()
        self.session.ui_queue.put(("line", "10:00:01", "mic", "Hola equipo", []))
        self.assertEqual(self.llamar(self.consola(), historial=True), 0)
        salida = self.salida.getvalue()
        self.assertNotIn("\x1b[?1049h", salida, "sin pantalla alternativa")
        texto = limpio(salida)
        self.assertIn("10:00:01  🎤 Hola equipo\n", texto, "las frases en el historial")
        self.assertIn("[p] pausar · [c] captura", texto, "con su pie vivo")
        self.assertIn(f"Grabación terminada · nota: {self.session.file_path}", texto)

    def test_con_la_salida_redirigida_tambien(self):
        self.escuchando()
        redirigida = make_console(ascii_mode=False, file=self.salida, width=200)
        self.assertEqual(self.llamar(redirigida), 0)
        salida = self.salida.getvalue()
        self.assertNotIn("\x1b", salida)
        self.assertIn("(Ctrl+C también sale)", salida)

    def test_en_el_menu_devuelve_el_aviso(self):
        self.escuchando()
        teclado = Guion("q")
        codigo, aviso = live.grabar_en_menu(
            self.consola(), session=self.session, leer_tecla=teclado, dormir=self.reloj.dormir, abrir=self.abiertos.append,
            entorno=self.entorno,
        )
        self.assertEqual(codigo, 0)
        self.assertTrue(aviso.startswith("Grabación terminada: "), aviso)
        self.assertEqual(self.tras_el_alt(), "")


if __name__ == "__main__":
    unittest.main()

