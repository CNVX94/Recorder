"""La ventana principal se prueba con la sesión de mentira de tests/test_session.py y una ventana
oculta: no se mira el aspecto, sino lo que cuesta pintarla y que no se pierda nada.

Lo que se comprueba: las etiquetas de la cabecera no se reescriben si no cambiaron (cada config()
cuesta aunque el texto sea el mismo), minimizada no se pinta pero se sigue sondeando y al volver
se repinta al momento, la captura manual no congela la ventana, el visor se recorta sin tocar la
nota y el sondeo acaba cuando la cola se vació. Sin Tk disponible, se saltan.

También, sin Tk: el punto de corte por ancho y escala, el recorte del estado con «…» y la tabla
de atajos. Con Tk: los puntos de corte recolocan la cabecera, los atajos actúan (también desde el
visor), el menú «Más» lleva lo que sacó la cabecera, el panel de rendimiento solo se redibuja
desplegado y el pulso del indicador se para minimizada.
"""

import io
import json
import pathlib
import sys
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from recorder import ayuda
from recorder import session as ses
from recorder.audio.capture import MUTE_WARN_SEC
from recorder.paleta import TEMAS
from recorder.session import mute_text
from recorder.ui import animacion, theme
from recorder.ui import main_window as mw
from recorder.ui.main_window import (
    ATAJO, ATAJOS, POLL_HIDDEN_MS, POLL_MS, MainWindow, punto_de_corte, recortar, separar_icono,
)
from tests.test_session import BaseSesion

# Las ventanas ya destruidas se conservan hasta que acabe el proceso. Si el recolector liberara
# su intérprete de Tk desde otro hilo (el de la captura manual), Tcl aborta el proceso entero:
# "Tcl_AsyncDelete: async handler deleted by the wrong thread".
_ventanas = []


class BaseVentana(BaseSesion):
    def setUp(self):
        super().setUp()
        try:
            self.win = MainWindow(session=self.session)
        except tk.TclError as e:
            self.skipTest(f"sin Tk: {e}")
        self.root = self.win.root
        _ventanas.append(self.win)
        self.addCleanup(self.root.destroy)
        # El sondeo lo lleva la prueba a mano con _tick(): se cancela el que programó el constructor
        self.root.after_cancel(self.win._poll_id)
        self.root.withdraw()  # la prueba no necesita verla (y así no parpadea)

    def contar_config(self, lbl):
        """Cuenta las llamadas a config() de una etiqueta sin dejar de hacerlas."""
        llamadas = []
        original = lbl.config

        def config(**opts):
            llamadas.append(opts)
            return original(**opts)

        lbl.config = config
        return llamadas

    def lineas_visor(self) -> list:
        return self.win.txt.get("1.0", "end-1c").splitlines()

    def tics_hasta(self, cond, limite=4.0):
        """Sondea con la ventana (como haría el `after`) hasta que cond() se cumpla."""
        fin = time.time() + limite
        while time.time() < fin:
            self.win._tick()
            if cond():
                return
            time.sleep(0.02)
        self.fail("no llegó lo esperado")


class TestCabeceraSinCambios(BaseVentana):
    def test_solo_se_escribe_lo_que_cambia(self):
        self.root.deiconify()  # retirada no se pinta (ver TestMinimizada); aquí interesa a la vista
        estado = self.contar_config(self.win.lbl_status)
        medidor = self.contar_config(self.win.lbl_meter)

        for _ in range(3):
            self.assertEqual(self.win._tick(), POLL_MS)
        self.assertEqual((estado, medidor), ([], []), "sin cambios no se toca ninguna etiqueta")
        self.assertIn("Fuentes: 🔊", self.win.txt.get("1.0", "end"), "la línea de las fuentes va al visor, no a la cabecera")

        self.escuchando()
        self.win._tick()
        self.assertEqual(len(estado), 1)
        # El símbolo del estado va en su propia etiqueta, la del indicador que late al grabar
        self.assertEqual(estado[0]["text"], "Escuchando + 🎤 · pendientes: 0 · ☕")
        self.assertEqual(self.win.lbl_icono.cget("text"), "●")
        self.assertEqual(medidor, [], "los medidores en silencio no cambian")

        self.audio.levels["mic"] = 32768.0
        self.win._tick()
        self.win._tick()
        self.assertEqual(len(medidor), 1, "el medidor se escribe una vez al cambiar, no en cada tic")
        self.assertEqual(medidor[0]["text"], "🔊 ░░░░░░░░   🎤 ████████")
        self.assertEqual(len(estado), 1)
        self.assertEqual(self.win.lbl_meter.cget("text"), "🔊 ░░░░░░░░   🎤 ████████")


class TestFuenteMudaEnVentana(BaseVentana):
    def test_la_linea_se_pinta_y_el_medidor_marca_la_fuente(self):
        self.root.deiconify()
        self.escuchando()
        self.audio.started_at = time.time() - 2 * MUTE_WARN_SEC
        self.audio.last_chunk_at = {"out": time.time() - 5, "mic": 0.0}
        self.win._tick()
        visor = self.win.txt.get("1.0", "end")
        self.assertIn(mute_text("mic", True) + ". Si hablaste, elige el dispositivo que usa Teams en ⚙ Opciones.\n", visor,
                      "la acción, con las palabras de la ventana")
        self.assertEqual(self.win.lbl_meter.cget("text"), "🔊 ░░░░░░░░   🎤 ░░░░░░░░ 🔇")
        self.audio.last_chunk_at["mic"] = time.time()
        self.win._tick()
        self.assertIn(mute_text("mic", False), self.win.txt.get("1.0", "end"))
        self.assertEqual(self.win.lbl_meter.cget("text"), "🔊 ░░░░░░░░   🎤 ░░░░░░░░")

    def test_las_fuentes_resueltas_se_pintan_al_arrancar(self):
        # la sesión ya arrancó en el constructor; el aviso espera al primer sondeo
        self.win._tick()
        self.assertIn("Fuentes: 🔊 ", self.win.txt.get("1.0", "end"))


class TestMinimizada(BaseVentana):
    def test_no_pinta_pero_sigue_sondeando_y_al_volver_repinta(self):
        self.root.iconify()
        self.assertEqual(self.win._tick(), POLL_HIDDEN_MS, "minimizada se sondea más despacio")
        self.assertEqual(self.despierto, [True], "el ☕ se sigue decidiendo (poll corre igual)")

        self.session.ui_queue.put(("status", "● Escuchando"))
        self.session.ui_queue.put(("line", "10:00:01", "mic", "Hola equipo", []))
        self.assertEqual(self.win._tick(), POLL_HIDDEN_MS)
        self.assertIn("10:00:01  🎤 Hola equipo", self.lineas_visor(), "las líneas no se pierden")
        self.assertTrue(any("Fuentes: 🔊" in l for l in self.lineas_visor()), "el aviso de las fuentes tampoco")
        self.assertEqual(self.win.lbl_status.cget("text"), "Iniciando…", "la cabecera no se pinta sin verse")

        # Al restaurar, <Map> adelanta el sondeo: la cabecera se repinta sin esperar al tic lento
        self.win._poll_id = self.root.after(POLL_HIDDEN_MS, self.win.poll)
        self.root.deiconify()
        self.root.update()
        self.assertEqual(self.win.lbl_status.cget("text"), "Escuchando + 🎤 · pendientes: 0 · ☕")
        self.assertEqual(self.win.lbl_icono.cget("text"), "●")
        self.assertEqual(self.win._tick(), POLL_MS)
        self.root.after_cancel(self.win._poll_id)


class TestCapturaManualEnVentana(BaseVentana):
    def test_no_congela_y_la_linea_se_pinta_al_llegar(self):
        suelta = threading.Event()

        def captura_falsa(tag, caps_dir, screen_idx=0, window=""):
            suelta.wait(2)
            return pathlib.Path(caps_dir) / "manual_x.png"

        original = ses.take_screenshot
        ses.take_screenshot = captura_falsa
        self.addCleanup(lambda: setattr(ses, "take_screenshot", original))

        self.win.manual_screenshot()
        self.win.manual_screenshot()  # repetir el clic mientras captura no encola otra
        self.win._tick()
        self.assertNotIn("(captura manual)", self.win.txt.get("1.0", "end"), "la ventana sigue viva mientras captura")

        suelta.set()
        self.tics_hasta(lambda: "(captura manual)" in self.win.txt.get("1.0", "end"))
        visor = self.win.txt.get("1.0", "end")
        self.assertEqual(visor.count("(captura manual)"), 1)
        self.assertIn("📸 captura: manual", visor)
        self.assertEqual(self.nota.count("📸 captura manual"), 1)


class TestVisorAcotado(BaseVentana):
    # Con los valores reales (5 000 / 500) la prueba tarda 4 s en insertar; la lógica es la misma
    @patch.object(mw, "MAX_LINES", 200)
    @patch.object(mw, "TRIM_LINES", 50)
    def test_se_recorta_por_arriba_sin_tocar_la_nota(self):
        nota_antes = self.nota
        total = mw.MAX_LINES + mw.TRIM_LINES + 10
        for i in range(total):
            self.win.add_line(f"{i:08d}", "out", "frase", [])

        lineas = self.lineas_visor()
        self.assertLessEqual(len(lineas), mw.MAX_LINES)
        self.assertGreater(len(lineas), mw.MAX_LINES - mw.TRIM_LINES - 1, "se borra de TRIM_LINES en TRIM_LINES, no más")
        self.assertTrue(lineas[-1].startswith(f"{total - 1:08d}"), "lo último siempre se conserva")
        self.assertTrue(lineas[0].startswith(f"{total - len(lineas):08d}"), "se borra por arriba, en orden")
        self.assertEqual(self.nota, nota_antes, "el visor es solo lo que se ve; la nota en disco no se toca")


class TestFalloEnCallback(BaseVentana):
    def test_una_excepcion_en_un_callback_de_tk_va_al_registro_y_a_stderr_como_siempre(self):
        self.assertEqual(self.root.report_callback_exception, self.win._fallo_en_callback)
        try:
            raise RuntimeError("en un botón")
        except RuntimeError:
            info = sys.exc_info()
        with patch("recorder.registro.anotar") as anotar, patch.object(sys, "stderr", io.StringIO()) as err:
            self.root.report_callback_exception(*info)
        anotar.assert_called_once_with("en la ventana", info)
        self.assertIn("Exception in Tkinter callback", err.getvalue())
        self.assertIn("RuntimeError: en un botón", err.getvalue())
        with patch("recorder.registro.anotar"), patch.object(sys, "stderr", None):
            self.root.report_callback_exception(*info)  # sin consola: solo el registro, sin reventar


class TestCierre(BaseVentana):
    def test_el_sondeo_acaba_cuando_la_cola_se_vacia(self):
        self.encolar(20)
        self.session.begin_drain()
        self.assertIsNotNone(self.win._tick(), "con cola se sigue sondeando")
        self.session.chunk_queue.get()
        self.assertIsNone(self.win._tick(), "vaciada la cola toca cerrar")


# ------------------------------------------------------------------ lógica pura de la cabecera
class TestPuntoDeCorte(unittest.TestCase):
    def test_por_ancho_a_cada_escala(self):
        casos = [
            # (px físicos, escala, punto de corte)
            (1040, 1.0, "amplio"), (1000, 1.0, "amplio"), (999, 1.0, "compacto"), (700, 1.0, "compacto"),
            (699, 1.0, "estrecho"),
            (1300, 1.25, "amplio"), (1249, 1.25, "compacto"), (875, 1.25, "compacto"), (874, 1.25, "estrecho"),
            (1560, 1.5, "amplio"), (1499, 1.5, "compacto"), (1049, 1.5, "estrecho"),
            # 1366×768 maximizada (fit_window deja 16 px): a 150 % ya no caben los textos
            (1350, 1.0, "amplio"), (1350, 1.25, "amplio"), (1350, 1.5, "compacto"),
        ]
        for px, escala, esperado in casos:
            with self.subTest(px=px, escala=escala):
                self.assertEqual(punto_de_corte(px, escala), esperado)


class TestRecortar(unittest.TestCase):
    @staticmethod
    def medir(texto):
        return 10 * len(texto)  # 10 px por carácter

    def test_si_cabe_va_tal_cual(self):
        self.assertEqual(recortar("Escuchando", 100, self.medir), "Escuchando")

    def test_si_no_cabe_lleva_elipsis_y_cabe(self):
        r = recortar("Escuchando + 🎤 · pendientes: 12", 100, self.medir)
        self.assertEqual(r, "Escuchand…")
        self.assertLessEqual(self.medir(r), 100)

    def test_sin_espacio_antes_de_la_elipsis(self):
        self.assertEqual(recortar("ab cd", 40, self.medir), "ab…")

    def test_sin_tamano_aun_no_recorta(self):
        self.assertEqual(recortar("un estado largo", 1, self.medir), "un estado largo")
        self.assertEqual(recortar("un estado largo", -5, self.medir), "un estado largo")


class TestSepararIcono(unittest.TestCase):
    def test_estados_y_avisos(self):
        self.assertEqual(separar_icono("● Escuchando · pendientes: 0"), ("●", "Escuchando · pendientes: 0"))
        self.assertEqual(separar_icono("⏸ En pausa · sin pendientes"), ("⏸", "En pausa · sin pendientes"))
        self.assertEqual(separar_icono("⏳ Terminando 2 fragmentos…"), ("⏳", "Terminando 2 fragmentos…"))
        self.assertEqual(separar_icono("Cargando modelo…"), ("", "Cargando modelo…"))
        self.assertEqual(separar_icono("⚠ algo"), ("", "⚠ algo"), "un aviso se muestra tal cual")
        self.assertEqual(separar_icono(""), ("", ""))


class TestTablaDeAtajos(unittest.TestCase):
    def test_sin_repetidos_con_ayuda_y_metodo(self):
        secuencias = [s for _c, _a, ss, _m in ATAJOS for s in ss]
        self.assertEqual(len(secuencias), len(set(secuencias)))
        for clave, _atajo, _ss, metodo in ATAJOS:
            with self.subTest(clave=clave):
                self.assertIn(clave, ayuda.VENTANA, "los textos nuevos van en la sección Ventana")
                self.assertTrue(callable(getattr(MainWindow, metodo)))
        self.assertEqual(
            (ATAJO["pausar"], ATAJO["opciones"], ATAJO["ayuda"], ATAJO["tema_alternar"]),
            ("Ctrl+P", "Ctrl+,", "F1", "Ctrl+Shift+T"),
        )


# ------------------------------------------------------------------ cabecera, menú y panel con Tk
class TestCabeceraResponsive(BaseVentana):
    def botones(self):
        return [self.win.btn_pause, self.win.btn_shot, self.win.btn_nota, self.win.btn_mas]

    def test_cada_punto_de_corte_recoloca_la_cabecera(self):
        w = self.win
        w._aplicar_modo("amplio")
        self.assertEqual([b.cget("text") for b in self.botones()], ["⏸ Pausar", "📸 Capturar", "📄 Abrir nota", "☰ Más"])
        self.assertEqual(int(w.botonera.grid_info()["row"]), 0)
        w._aplicar_modo("compacto")
        self.assertEqual([b.cget("text") for b in self.botones()], ["⏸", "📸", "📄", "☰"])
        self.assertEqual((w.btn_shot.tooltip.claves, w.btn_shot.tooltip.atajo), (("captura",), "Ctrl+K"),
                         "sin texto, el nombre y el atajo quedan en el tooltip")
        w._aplicar_modo("estrecho")
        self.assertEqual(int(w.botonera.grid_info()["row"]), 1, "dos filas: botones abajo")
        self.assertEqual(int(w.lbl_status.grid_info()["columnspan"]), 3, "el estado, con toda la fila")
        w._aplicar_modo("amplio")
        self.assertEqual((int(w.botonera.grid_info()["row"]), int(w.lbl_status.grid_info()["columnspan"])), (0, 1))

    def test_al_redimensionar_elige_el_punto_de_corte(self):
        self.root.deiconify()
        k = self.win._escala
        for ancho, modo in ((1100, "amplio"), (850, "compacto"), (600, "estrecho"), (1050, "amplio")):
            with self.subTest(ancho=ancho):
                self.root.geometry(f"{int(ancho * k)}x{int(500 * k)}")
                self.root.update()
                self.assertEqual(self.win._modo, modo)

    def test_un_estado_que_no_cambia_no_se_vuelve_a_medir(self):
        # Medir un texto con emojis cuesta ~4 ms en Windows: hacerlo en cada sondeo eran ~2 % de un núcleo
        self.root.deiconify()
        self.root.update()
        self.escuchando()
        self.win._tick()
        self.assertGreater(self.win.lbl_status.winfo_width(), 1, "con tamaño, para que se mida")
        medidas = self.win._medir.cache_info().misses
        for _ in range(5):
            self.win._tick()
        self.assertEqual(self.win._medir.cache_info().misses, medidas)

    def test_el_estado_largo_se_recorta_y_no_empuja_los_botones(self):
        self.root.deiconify()
        k = self.win._escala
        for ancho in (720, 600, 480):  # compacto cerca del mínimo, estrecho y el mínimo
            with self.subTest(ancho=ancho):
                self.root.geometry(f"{int(ancho * k)}x{int(420 * k)}")
                self.root.update()
                self.session.ui_queue.put(("status", "⚠ " + "un aviso muy largo del transcriptor " * 8))
                self.win._tick()
                self.root.update()
                self.assertTrue(self.win.lbl_status.cget("text").endswith("…"))
                derecha = self.win.btn_mas.winfo_rootx() + self.win.btn_mas.winfo_width()
                self.assertLessEqual(derecha, self.root.winfo_rootx() + self.root.winfo_width(), "«Más» sigue dentro")


class TestAtajosEnVentana(BaseVentana):
    def enfocar_visor(self):
        self.root.deiconify()
        self.win.txt.focus_force()
        self.root.update()
        if self.root.focus_get() is not self.win.txt:
            self.skipTest("Windows no dio el foco a la ventana de prueba")

    def test_ctrl_p_pausa_y_sigue_tambien_desde_el_visor(self):
        self.enfocar_visor()
        self.win.txt.event_generate("<Control-p>")
        self.assertTrue(self.session.paused)
        self.assertEqual(self.win.btn_pause.cget("text"), "▶ Continuar")
        self.win.txt.event_generate("<Control-P>")  # con Bloq Mayús
        self.assertFalse(self.session.paused)

    def test_ctrl_k_captura_sin_borrar_el_visor(self):
        llamadas = []
        self.session.manual_screenshot = lambda: llamadas.append(1)
        self.win.add_line("10:00:01", "out", "Una frase que no debe borrarse", [])
        self.enfocar_visor()
        self.win.txt.mark_set("insert", "1.0")
        antes = self.win.txt.get("1.0", "end")
        self.win.txt.event_generate("<Control-k>")
        self.assertEqual(llamadas, [1])
        self.assertEqual(self.win.txt.get("1.0", "end"), antes, "Ctrl+K de Text borraría la línea")

    def test_anillo_de_foco_en_botones_y_medidores(self):
        # Tk en Windows no pinta highlightcolor en botones: el anillo es el marco que los rodea
        self.root.deiconify()  # retirada, Tk no entrega los eventos de foco
        self.root.update()
        for control in (self.win.btn_shot, self.win.btn_mas, self.win.lbl_meter):
            with self.subTest(control=str(control)):
                control.event_generate("<FocusIn>")
                self.assertEqual(str(control.master.cget("bg")), theme.P.foco)
                control.event_generate("<FocusOut>")
                self.assertEqual(str(control.master.cget("bg")), theme.P.fondo)

    def test_orden_de_tab_de_la_cabecera(self):
        self.root.deiconify()  # Tab salta lo que no se ve
        self.root.update()
        orden, w = [], self.win.lbl_meter
        for _ in range(5):
            orden.append(w)
            w = w.tk_focusNext()
        self.assertEqual(orden, [self.win.lbl_meter, self.win.btn_pause, self.win.btn_shot, self.win.btn_nota, self.win.btn_mas])

    def test_cerrando_el_atajo_no_pausa(self):
        self.win.btn_pause.config(state="disabled")
        self.win.toggle_pause()
        self.assertFalse(self.session.paused)


class TestMenuMas(BaseVentana):
    def test_lleva_lo_que_salio_de_la_cabecera_con_sus_atajos(self):
        m = self.win.menu_mas
        entradas = {
            m.entrycget(i, "label"): m.entrycget(i, "accelerator")
            for i in range(m.index("end") + 1) if m.type(i) != "separator"
        }
        for nombre in ("Opciones", "Calibrar", "Reagrupar nota", "Rendimiento", "Tema", "Ayuda"):
            self.assertTrue(any(nombre in e for e in entradas), nombre)
        self.assertEqual(entradas["⚙ Opciones…"], "Ctrl+,")
        self.assertEqual(entradas["📊 Rendimiento"], "Ctrl+Shift+R")
        self.assertEqual(entradas["❓ Ayuda"], "F1")

    def test_tema_desde_el_menu_se_guarda_y_se_pinta(self):
        self.addCleanup(theme.aplicar_tema, self.root, "oscuro")
        self.win.cambiar_tema("claro")
        self.assertEqual(self.session.config.theme, "claro")
        self.assertEqual(json.loads(self.ruta.read_text(encoding="utf-8"))["theme"], "claro")
        self.assertEqual(str(self.win.txt.cget("bg")), TEMAS["claro"]["fondo"], "oculta: sin fundido, al momento")
        self.assertEqual(self.win.v_tema.get(), "claro")
        self.win.alternar_tema()
        self.assertEqual((self.session.config.theme, str(self.win.txt.cget("bg"))), ("oscuro", TEMAS["oscuro"]["fondo"]))

    def test_ayuda_lista_los_atajos(self):
        self.win.abrir_ayuda()
        d = self.win._ayuda
        self.addCleanup(d.destroy)
        textos = [w.cget("text") for w in d.winfo_children() if isinstance(w, tk.Label)]
        for _clave, atajo, _ss, _m in ATAJOS:
            self.assertIn(atajo, textos)
        self.win.abrir_ayuda()
        self.assertIs(self.win._ayuda, d, "una sola ventana de ayuda")

    def test_abrir_nota(self):
        with patch.object(mw.os, "startfile", create=True) as abrir:
            self.win.abrir_nota()
        abrir.assert_called_once_with(self.session.file_path)
        with patch.object(mw.os, "startfile", side_effect=OSError(2, "No existe"), create=True):
            self.win.abrir_nota()  # avisa con un toast, sin excepción


class TestPanelRendimiento(BaseVentana):
    def test_solo_se_redibuja_desplegado(self):
        self.root.deiconify()
        llamadas = []
        panel = self.win.panel
        original = panel.actualizar
        panel.actualizar = lambda m: (llamadas.append(m), original(m))
        self.win._tick()
        self.assertEqual(llamadas, [], "plegado no se pinta")
        self.assertEqual(self.win.historial.version, 1, "pero el historial sí se anota")

        self.win.mostrar_rendimiento(True)
        self.assertTrue(self.win.v_rendimiento.get(), "el menú marca el panel")
        self.win._tick()
        self.assertEqual(len(llamadas), 2, "al desplegarlo y en cada tic")
        self.assertEqual(panel.valores["cola"].cget("text"), "0")
        self.assertEqual(panel.lbl_motor.cget("text"), "Cargando modelo…")

        self.root.iconify()
        self.win._tick()
        self.assertEqual(len(llamadas), 2, "minimizada tampoco")
        self.root.deiconify()
        self.win.toggle_rendimiento()
        self.assertFalse(self.win.v_rendimiento.get())
        self.win._tick()
        self.assertEqual(len(llamadas), 2)


class TestMovimiento(BaseVentana):
    def esperar(self, cond, msg=None, limite=2.0):
        fin = time.time() + limite
        while not cond() and time.time() < fin:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(cond(), msg)

    def test_el_indicador_late_al_escuchar_y_para_minimizada_o_en_pausa(self):
        self.root.deiconify()
        with patch.object(animacion, "modo", "completas"):
            self.escuchando()
            self.win._tick()
            self.assertIn("pulso", self.win.lbl_icono._animaciones)
            self.root.iconify()
            self.win._tick()
            self.assertNotIn("pulso", self.win.lbl_icono._animaciones, "minimizada no gasta en latir")
            self.root.deiconify()
            self.win._tick()
            self.assertIn("pulso", self.win.lbl_icono._animaciones, "al volver, late otra vez")
            self.win.toggle_pause()
            self.win._tick()
            self.assertEqual(self.win.lbl_icono.cget("text"), "⏸")
            self.assertNotIn("pulso", self.win.lbl_icono._animaciones)
            self.assertEqual(str(self.win.lbl_icono.cget("fg")), theme.P.aviso)

    def test_con_reducidas_el_indicador_no_late(self):
        self.root.deiconify()
        with patch.object(animacion, "modo", "reducidas"):
            self.escuchando()
            self.win._tick()
        self.assertNotIn("pulso", self.win.lbl_icono._animaciones)
        self.assertEqual(str(self.win.lbl_icono.cget("fg")), theme.P.error)

    def test_la_ultima_linea_se_resalta_y_se_desvanece(self):
        self.root.deiconify()
        with patch.object(animacion, "modo", "completas"), patch.object(mw, "RESALTE_MS", 80):
            self.win.add_line("10:00:01", "out", "Primera", [])
            self.win.add_line("10:00:02", "mic", "Segunda", [])
            desde, hasta = self.win.txt.tag_ranges("nueva")
            self.assertEqual(self.win.txt.get(desde, hasta), "10:00:02  🎤 Segunda\n", "solo la última")
            self.esperar(lambda: not self.win.txt.tag_ranges("nueva"))
        with patch.object(animacion, "modo", "ninguna"):
            self.win.add_line("10:00:03", "out", "Tercera", [])
            self.assertEqual(self.win.txt.tag_ranges("nueva"), ())

    def test_hover_con_transicion_de_color(self):
        self.root.deiconify()
        self.root.update()
        b = self.win.btn_nota
        with patch.object(animacion, "modo", "completas"):
            b.event_generate("<Enter>")
            self.assertEqual(str(b.cget("bg")), theme.P.superficie, "empieza en reposo: transición, no salto")
            self.esperar(lambda: str(b.cget("bg")) == theme.P.superficie_elevada)
            b.event_generate("<Leave>")
            self.esperar(lambda: str(b.cget("bg")) == theme.P.superficie)
            with patch.object(b, "winfo_containing", return_value=None):  # soltado con el ratón fuera
                b.event_generate("<ButtonRelease-1>")
            self.esperar(lambda: str(b.cget("bg")) == theme.P.superficie, "no se queda resaltado")

    def test_toast_abajo_a_la_derecha_que_se_va_solo(self):
        self.root.deiconify()
        self.root.update()
        with patch.object(mw, "TOAST_MS", 60):
            self.win.aviso("Primero")
            primero, _ = self.win._toast
            self.win.aviso("✔ Opciones guardadas")
        self.assertFalse(primero.winfo_exists(), "uno a la vez")
        t, _ = self.win._toast
        self.assertEqual([w.cget("text") for w in t.winfo_children()], ["✔ Opciones guardadas"])
        t.update_idletasks()
        self.assertGreater(t.winfo_rootx(), self.root.winfo_rootx() + self.root.winfo_width() // 2)
        self.esperar(lambda: not t.winfo_exists())

    def test_sin_verse_no_hay_toast(self):
        self.win.aviso("✔ Opciones guardadas")  # la ventana de prueba está retirada
        self.assertIsNone(self.win._toast)


if __name__ == "__main__":
    unittest.main()
