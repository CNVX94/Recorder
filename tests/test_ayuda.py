"""Textos de ayuda (recorder/ayuda.py) y globos de ayuda de la ventana (recorder/ui/tooltip.py).

Sin Tk: el largo de cada texto, que las claves no se repitan, que cada opción y tecla de la
terminal tenga su línea de ayuda y que el globo se coloque dentro del monitor. Con Tk (se omiten
sin pantalla): cada control de la ventana y de sus diálogos lleva globo, y el globo aparece con
los colores del tema, entra con el fundido que pide «animations» y se va al salir, al hacer clic
o con Esc.
"""

import pathlib
import time
import tkinter as tk
import unittest
from unittest import mock

from recorder import ayuda
from recorder.cli import calibrar, configurar, live, menu
from recorder.config import hardware
from recorder.config.schema import AppConfig
from recorder.paleta import TEMAS
from recorder.ui import theme, tooltip
from recorder.ui.dialogs import settings_dialog
from recorder.ui.dialogs.digest_dialog import DigestDialog
from recorder.ui.dialogs.settings_dialog import SettingsDialog
from recorder.ui.dialogs.tuning_dialog import TuningDialog
from recorder.ui.tooltip import Tooltip, posicion
from tests.test_dialogs import NOTA, PANTALLAS, PERFIL, VENTANAS, PyAudioFalso
from tests.test_main_window import BaseVentana

# Los controles con los que se interactúa: todos deben llevar globo (las etiquetas, solo las de la cabecera).
INTERACTIVOS = (tk.Button, tk.Checkbutton, tk.Radiobutton, tk.Entry, tk.Spinbox, tk.Scale, tk.Listbox, tk.Menubutton, tk.Text)


class TestTextos(unittest.TestCase):
    def test_cada_texto_es_corto_y_completo(self):
        for seccion, textos in ayuda.SECCIONES.items():
            for clave, (titulo, explicacion) in textos.items():
                with self.subTest(seccion=seccion, clave=clave):
                    self.assertTrue(titulo.strip())
                    self.assertLessEqual(len(titulo), ayuda.LARGO_TITULO)
                    self.assertLessEqual(len(explicacion), ayuda.LARGO_MAXIMO)
                    self.assertNotIn("\n", titulo + explicacion)
                    self.assertTrue(explicacion.endswith("."), "frases completas")

    def test_secciones_y_claves_unicas(self):
        self.assertEqual(list(ayuda.SECCIONES), ["Ventana", "Terminal", "Común", "Glosario"])
        claves = [c for textos in ayuda.SECCIONES.values() for c in textos]
        self.assertEqual(len(claves), len(set(claves)), "una clave en dos secciones: no se sabría cuál vale")
        with self.assertRaises(KeyError):
            ayuda.entrada("no_existe")

    def test_la_jerga_tiene_explicacion(self):
        for clave in ("haz", "vad", "alucinaciones", "vulkan", "flash_attention", "loopback", "int8", "hilos_cpu"):
            self.assertIn(clave, ayuda.GLOSARIO)
        for clave in ("cola", "atraso", "cafe", "reintento", "mudo", "fallos"):  # símbolos de cabecera y medidores
            self.assertIn(clave, ayuda.COMUN)

    def test_sin_tkinter_ni_rich(self):
        fuente = pathlib.Path(ayuda.__file__).read_text(encoding="utf-8")
        self.assertNotRegex(fuente, r"(?m)^\s*(import|from)\s+(tkinter|rich)")


class TestTerminal(unittest.TestCase):
    """Toda opción y tecla de la terminal tiene su línea de ayuda; si se añade una, esta prueba lo recuerda."""

    def test_opciones_del_menu(self):
        for _numero, _etiqueta, accion, _descripcion in menu.OPCIONES:
            self.assertTrue(ayuda.linea("menu_" + accion))

    def test_teclas_y_panel_de_la_grabacion(self):
        for tecla, _ in live.TECLAS + live.TECLAS_PAUSA:
            ayuda.linea(f"tecla_{tecla}")
        for tecla, _ in live.TECLAS_CIERRE + live.TECLAS_TERMINANDO:
            ayuda.linea(f"cierre_{tecla}")
        panel = {"out": "salida_audio", "mic": "microfono", "target": "que_capturar", "captures": "capturas_clave"}
        self.assertEqual([s for _t, s, _titulo in live.SECCIONES], list(panel))
        for clave in panel.values():
            ayuda.linea(clave)
        ayuda.linea("pie_motor")

    def test_secciones_de_config_y_calibrar(self):
        config = ["config_carpetas", "config_audio", "config_capturas", "config_calidad", "config_apariencia"]
        self.assertEqual(len(configurar.SECCIONES), len(config))
        por_opcion = {
            calibrar.VOCABULARIO: "vocabulario", calibrar.IGNORAR: "ignorar", calibrar.CORRECCIONES: "correcciones",
            calibrar.UMBRALES: "umbrales", calibrar.ECO: "eco_vocab", calibrar.PROBAR: "sandbox",
            calibrar.GUARDAR: "guardar_salir", calibrar.SALIR: "salir_sin_guardar",
        }
        self.assertEqual(sorted(por_opcion), list(range(len(calibrar.OPCIONES))))
        umbrales = {"no_speech_threshold": "umbral_silencio", "logprob_threshold": "umbral_confianza",
                    "compression_ratio_threshold": "umbral_bucles"}
        self.assertEqual([c for c, _ in calibrar.TEXTO_UMBRAL], list(umbrales))
        for clave in [*config, "config_todo", "guardar_salir", "salir_sin_guardar", *por_opcion.values(), *umbrales.values()]:
            ayuda.linea(clave)


class TestPosicion(unittest.TestCase):
    AREA = (0, 0, 1920, 1040)

    def test_debajo_y_alineado_a_la_izquierda(self):
        self.assertEqual(posicion((100, 100, 200, 130), (300, 80), self.AREA), (100, 136))

    def test_sin_sitio_debajo_va_encima(self):
        self.assertEqual(posicion((100, 1000, 200, 1030), (300, 80), self.AREA), (100, 914))

    def test_nunca_sale_por_los_lados(self):
        self.assertEqual(posicion((1800, 100, 1900, 130), (300, 80), self.AREA)[0], 1620)
        self.assertEqual(posicion((-50, 100, 10, 130), (300, 80), self.AREA)[0], 0)
        # otro monitor a la izquierda, con coordenadas negativas
        self.assertEqual(posicion((-50, 10, -10, 30), (300, 80), (-1920, 0, 0, 1040)), (-300, 36))

    def test_mas_alto_que_el_monitor_se_pega_arriba(self):
        self.assertEqual(posicion((100, 500, 200, 530), (300, 2000), self.AREA)[1], 0)


class TestGlobo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
        except tk.TclError as e:  # sin escritorio
            raise unittest.SkipTest(f"sin pantalla para Tk: {e}")
        cls.root.geometry("+40+40")  # a la vista: el globo no sale en una ventana oculta

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.addCleanup(theme.aplicar_tema, self.root, "oscuro")
        self.addCleanup(setattr, tooltip, "animaciones", tooltip.animaciones)
        self.boton = tk.Button(self.root, text="📸 Captura")
        self.boton.pack()
        self.addCleanup(self.boton.destroy)
        self.root.update()
        self.globo = Tooltip(self.boton, "captura", "cola", atajo="Ctrl+K")

    def mostrar(self):
        self.globo._por_raton = False
        self.globo.mostrar()
        self.assertIsNotNone(self.globo._globo, "el globo debe verse")
        self.globo._globo.update()
        return self.globo._globo

    def etiquetas(self, globo):
        return [w for w in globo.winfo_children() if isinstance(w, tk.Label)]

    def test_textos_atajo_y_colores_de_cada_tema(self):
        for nombre, tema in TEMAS.items():
            with self.subTest(tema=nombre):
                theme.aplicar_tema(self.root, nombre)
                g = self.mostrar()
                textos = [l.cget("text") for l in self.etiquetas(g)]
                self.assertEqual(textos, [
                    "Captura  ·  Ctrl+K", ayuda.entrada("captura")[1], "Pendientes", ayuda.entrada("cola")[1],
                ])
                for l in self.etiquetas(g):
                    self.assertEqual((str(l.cget("bg")), str(l.cget("fg"))), (tema["tooltip_fondo"], tema["tooltip_texto"]))
                self.globo.ocultar()

    def test_cambio_de_tema_con_el_globo_a_la_vista(self):
        g = self.mostrar()
        theme.aplicar_tema(self.root, "claro")
        self.assertEqual(str(self.etiquetas(g)[0].cget("bg")), TEMAS["claro"]["tooltip_fondo"])

    def test_dentro_del_area_util_del_monitor(self):
        g = self.mostrar()
        l, t, r, b = theme.work_area(self.boton)
        x, y = g.winfo_rootx(), g.winfo_rooty()
        self.assertTrue(l <= x and x + g.winfo_width() <= r and t <= y and y + g.winfo_height() <= b)
        self.assertGreaterEqual(y, self.boton.winfo_rooty() + self.boton.winfo_height(), "con el teclado, bajo el control")

    def test_se_va_al_salir_al_hacer_clic_y_con_esc(self):
        self.mostrar()
        self.boton.event_generate("<Leave>")
        self.assertIsNone(self.globo._globo)
        self.mostrar()
        self.boton.event_generate("<Button-1>")
        self.assertIsNone(self.globo._globo)
        self.mostrar()
        raiz = self.boton.winfo_toplevel()
        self.assertIn(self.globo._esc, raiz.bind("<Escape>"), "Esc, mientras se ve")
        self.globo.ocultar()
        self.assertEqual(raiz.bind("<Escape>"), "", "al ocultarse se quita su Esc")

    def test_esc_lo_oculta(self):
        self.mostrar()
        self.boton.focus_force()
        self.root.update()
        self.globo.ocultar()  # el foco recién llegado programa otro globo; aquí interesa el de antes
        self.mostrar()
        self.boton.event_generate("<KeyPress-Escape>", when="now")
        self.root.update()
        if self.root.focus_get() is not self.boton:
            self.skipTest("Windows no dio el foco a la ventana de prueba")
        self.assertIsNone(self.globo._globo)

    def test_aparece_con_retardo_y_el_foco_de_un_clic_no_lo_abre(self):
        self.boton.event_generate("<Enter>")
        self.assertIsNotNone(self.globo._espera, "programado, aún no visible")
        self.assertIsNone(self.globo._globo)
        self.boton.event_generate("<Button-1>")
        self.boton.event_generate("<FocusIn>")
        self.assertIsNone(self.globo._espera, "el foco que trae un clic no abre el globo")
        self.boton.event_generate("<FocusOut>")
        self.boton.event_generate("<FocusIn>")
        self.assertIsNotNone(self.globo._espera, "el foco por teclado sí")
        fin = time.time() + 2
        while self.globo._globo is None and time.time() < fin:
            self.root.update()
            time.sleep(0.02)
        self.assertIsNotNone(self.globo._globo, f"aparece tras {tooltip.RETARDO_MS} ms")

    def test_el_fundido_sigue_animations(self):
        tooltip.animaciones = "ninguna"
        self.assertEqual(float(self.mostrar().attributes("-alpha")), 1.0)
        self.globo.ocultar()
        tooltip.animaciones = "completas"
        g = self.mostrar()
        self.assertLess(float(g.attributes("-alpha")), 0.5, "empieza casi transparente")
        fin = time.time() + 2
        while float(g.attributes("-alpha")) < 1.0 and time.time() < fin:
            self.root.update()
            time.sleep(0.01)
        self.assertEqual(float(g.attributes("-alpha")), 1.0)

    def test_una_clave_sin_texto_falla_al_construir(self):
        with self.assertRaises(KeyError):
            Tooltip(self.boton, "no_existe")


class TestTodoLlevaAyuda(BaseVentana):
    """Cada control de la ventana y de sus tres diálogos tiene globo, con claves que existen."""

    def test_ventana_y_dialogos(self):
        tmp = pathlib.Path(self.tmp.name) / "notas_reagrupar"
        tmp.mkdir()
        (tmp / "daily_2026-09-08_10-20.md").write_text(NOTA, encoding="utf-8")
        cfg = AppConfig(notes_dir=str(tmp))
        with mock.patch.object(hardware, "_cache", PERFIL), \
             mock.patch.object(settings_dialog, "screen_labels", lambda: list(PANTALLAS)), \
             mock.patch.object(settings_dialog, "window_titles", lambda: list(VENTANAS)):
            opciones = SettingsDialog(self.root, cfg, PyAudioFalso(), on_save=lambda *_: None)
        for d in (opciones, TuningDialog(opciones, cfg, on_save=lambda c: None), DigestDialog(self.root, cfg)):
            self.addCleanup(d.destroy)

        for etiqueta in (self.win.lbl_status, self.win.lbl_meter, self.win.lbl_path):
            self.assertTrue(hasattr(etiqueta, "tooltip"), etiqueta)
        vistos, pila = 0, [self.root]
        while pila:
            w = pila.pop()
            pila.extend(w.winfo_children())
            if isinstance(w, INTERACTIVOS):
                vistos += 1
                with self.subTest(widget=str(w)):
                    self.assertTrue(hasattr(w, "tooltip"), f"{w.winfo_class()} sin globo de ayuda")
                    for clave in w.tooltip.claves:
                        self.assertIn(clave, {**ayuda.VENTANA, **ayuda.COMUN}, "la ventana usa textos de Ventana o Común")
        self.assertGreater(vistos, 40, "se recorrieron la ventana y los tres diálogos")


if __name__ == "__main__":
    unittest.main()
