"""La ventana principal se prueba con la sesión de mentira de tests/test_session.py y una ventana
oculta: no se mira el aspecto, sino lo que cuesta pintarla y que no se pierda nada.

Lo que se comprueba: las etiquetas de la cabecera no se reescriben si no cambiaron (cada config()
cuesta aunque el texto sea el mismo), minimizada no se pinta pero se sigue sondeando y al volver
se repinta al momento, la captura manual no congela la ventana, el visor se recorta sin tocar la
nota y el sondeo acaba cuando la cola se vació. Sin Tk disponible, se saltan.
"""

import pathlib
import threading
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from recorder import session as ses
from recorder.ui import main_window as mw
from recorder.ui.main_window import POLL_HIDDEN_MS, POLL_MS, MainWindow
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

        self.escuchando()
        self.win._tick()
        self.assertEqual(len(estado), 1)
        self.assertEqual(estado[0]["text"], "● Escuchando + 🎤 · pendientes: 0 · ☕")
        self.assertEqual(medidor, [], "los medidores en silencio no cambian")

        self.audio.levels["mic"] = 32768.0
        self.win._tick()
        self.win._tick()
        self.assertEqual(len(medidor), 1, "el medidor se escribe una vez al cambiar, no en cada tic")
        self.assertEqual(medidor[0]["text"], "🔊 ░░░░░░░░   🎤 ████████")
        self.assertEqual(len(estado), 1)
        self.assertEqual(self.win.lbl_meter.cget("text"), "🔊 ░░░░░░░░   🎤 ████████")


class TestMinimizada(BaseVentana):
    def test_no_pinta_pero_sigue_sondeando_y_al_volver_repinta(self):
        self.root.iconify()
        self.assertEqual(self.win._tick(), POLL_HIDDEN_MS, "minimizada se sondea más despacio")
        self.assertEqual(self.despierto, [True], "el ☕ se sigue decidiendo (poll corre igual)")

        self.session.ui_queue.put(("status", "● Escuchando"))
        self.session.ui_queue.put(("line", "10:00:01", "mic", "Hola equipo", []))
        self.assertEqual(self.win._tick(), POLL_HIDDEN_MS)
        self.assertIn("10:00:01  🎤 Hola equipo", self.lineas_visor(), "las líneas no se pierden")
        self.assertEqual(self.win.lbl_status.cget("text"), "Iniciando…", "la cabecera no se pinta sin verse")

        # Al restaurar, <Map> adelanta el sondeo: la cabecera se repinta sin esperar al tic lento
        self.win._poll_id = self.root.after(POLL_HIDDEN_MS, self.win.poll)
        self.root.deiconify()
        self.root.update()
        self.assertEqual(self.win.lbl_status.cget("text"), "● Escuchando + 🎤 · pendientes: 0 · ☕")
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


class TestCierre(BaseVentana):
    def test_el_sondeo_acaba_cuando_la_cola_se_vacia(self):
        self.encolar(20)
        self.session.begin_drain()
        self.assertIsNotNone(self.win._tick(), "con cola se sigue sondeando")
        self.session.chunk_queue.get()
        self.assertIsNone(self.win._tick(), "vaciada la cola toca cerrar")


if __name__ == "__main__":
    unittest.main()
