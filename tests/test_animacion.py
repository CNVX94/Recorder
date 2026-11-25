"""El helper de animaciones (recorder/ui/animacion.py) sin Tk: un widget de mentira con su propio
reloj y su cola de `after`, así se ve paso a paso qué se pinta y cuándo.

Lo que se comprueba: easing e interpolación de color, cuánto dura cada cosa según «animations»,
que una animación nueva cancela la anterior de la misma clave (nunca dos a la vez), que se puede
cancelar o completar, que no pasa de ~60 fps, que «ninguna» es instantáneo y que el fundido de
cierre bloquea la ventana y la destruye al final.
"""

import tkinter as tk
import unittest
from unittest.mock import patch

from recorder.ui import animacion
from recorder.ui.animacion import animar, cancelar, cerrar, duracion, ease_out, latir, mezclar


class WidgetFalso:
    """Lo que animacion.py usa de un widget: after/after_cancel sobre un reloj de mentira, y lo
    de una ventana para los fundidos de cierre."""

    def __init__(self, visible=True):
        self.ahora = 0.0
        self.cola = {}  # id -> (segundo en que toca, función)
        self.n = 0
        self.visible = visible
        self.atributos = {"-alpha": 1.0}
        self.destruido = 0
        self.soltado = False

    def reloj(self):
        return self.ahora

    def after(self, ms, funcion):
        self.n += 1
        ident = f"after#{self.n}"
        self.cola[ident] = (self.ahora + ms / 1000, funcion)
        return ident

    def after_cancel(self, ident):
        self.cola.pop(ident, None)

    def avanzar(self, ms):
        fin = self.ahora + ms / 1000
        while True:
            listos = sorted((t, i) for i, (t, _f) in self.cola.items() if t <= fin + 1e-9)
            if not listos:
                break
            t, ident = listos[0]
            _t, funcion = self.cola.pop(ident)
            self.ahora = t
            funcion()
        self.ahora = fin

    # ventana
    def winfo_viewable(self):
        return self.visible

    def attributes(self, nombre, valor=None):
        if valor is None:
            return self.atributos[nombre]
        self.atributos[nombre] = valor

    def grab_release(self):
        self.soltado = True

    def destroy(self):
        self.destruido += 1


class ConModo(unittest.TestCase):
    modo = "completas"

    def setUp(self):
        parche = patch.object(animacion, "modo", self.modo)
        parche.start()
        self.addCleanup(parche.stop)
        self.w = WidgetFalso()
        self.valores = []

    def animar(self, ms=180, clave="color", **kw):
        animar(self.w, clave, ms, self.valores.append, reloj=self.w.reloj, **kw)


class TestCurvaYColor(unittest.TestCase):
    def test_ease_out_va_de_0_a_1_y_frena_al_final(self):
        self.assertEqual((ease_out(0.0), ease_out(1.0)), (0.0, 1.0))
        valores = [ease_out(i / 20) for i in range(21)]
        self.assertEqual(valores, sorted(valores), "nunca retrocede")
        self.assertGreater(ease_out(0.5), 0.5, "más de la mitad del camino a mitad de tiempo")
        self.assertLess(ease_out(1.0) - ease_out(0.9), ease_out(0.1) - ease_out(0.0), "frena al final")

    def test_mezclar_colores(self):
        self.assertEqual(mezclar("#000000", "#ffffff", 0.0), "#000000")
        self.assertEqual(mezclar("#000000", "#ffffff", 1.0), "#ffffff")
        self.assertEqual(mezclar("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(mezclar("#1e1e2e", "#eff1f5", 0.25), "#525360")
        self.assertEqual(mezclar("#102030", "#102030", 0.7), "#102030")
        self.assertEqual(mezclar("#000000", "#ffffff", -1), "#000000")
        self.assertEqual(mezclar("#000000", "#ffffff", 2), "#ffffff", "fuera de rango, el extremo")

    def test_un_nombre_de_color_no_rompe(self):
        self.assertEqual(mezclar("SystemButtonFace", "#ffffff", 0.3), "SystemButtonFace")
        self.assertEqual(mezclar("SystemButtonFace", "#ffffff", 0.7), "#ffffff")


class TestDuracion(unittest.TestCase):
    def test_segun_animations(self):
        casos = {
            "completas": (180, 1500, 2400),
            "reducidas": (animacion.CORTO_MS, animacion.CORTO_MS, 0),
            "ninguna": (0, 0, 0),
        }
        for modo, (ventana, resalte, pulso) in casos.items():
            with self.subTest(modo=modo), patch.object(animacion, "modo", modo):
                self.assertEqual(duracion(180), ventana)
                self.assertEqual(duracion(1500), resalte)
                self.assertEqual(duracion(2400, fundido=False), pulso, "lo que no es fundido")
                self.assertEqual(duracion(60), 0 if modo == "ninguna" else 60)


class TestAnimar(ConModo):
    def test_recorre_de_0_a_1_y_acaba(self):
        fin = []
        self.animar(180, fin=lambda: fin.append(1))
        self.assertEqual(self.valores, [0.0], "el primer paso, al momento")
        self.w.avanzar(1000)
        self.assertEqual(self.valores[-1], 1.0)
        self.assertEqual(self.valores, sorted(self.valores))
        self.assertEqual(fin, [1])
        self.assertEqual(self.w.cola, {}, "nada pendiente al acabar")
        self.assertNotIn("color", self.w._animaciones)

    def test_no_pasa_de_60_fps(self):
        self.animar(1000)
        self.w.avanzar(1000)
        self.assertLessEqual(len(self.valores), 1000 / animacion.PASO_MS + 2)
        self.assertGreater(len(self.valores), 30, "y no va a saltos")

    def test_un_tic_tardio_salta_adelante_sin_alargarla(self):
        self.animar(180)
        self.w.ahora = 0.5  # el bucle de Tk estuvo ocupado medio segundo
        self.w.avanzar(20)
        self.assertEqual(self.valores[-1], 1.0)
        self.assertEqual(self.w.cola, {})

    def test_otra_con_la_misma_clave_cancela_la_anterior(self):
        primera, segunda = [], []
        animar(self.w, "color", 300, primera.append, reloj=self.w.reloj)
        self.w.avanzar(100)
        hechos = len(primera)
        animar(self.w, "color", 300, segunda.append, reloj=self.w.reloj)
        self.assertEqual(len(self.w.cola), 1, "un solo after pendiente: no se acumulan")
        self.w.avanzar(1000)
        self.assertEqual(len(primera), hechos, "la primera ya no pinta")
        self.assertEqual(segunda[-1], 1.0)

    def test_claves_distintas_conviven(self):
        otra = []
        self.animar(300, clave="color")
        animar(self.w, "alfa", 300, otra.append, reloj=self.w.reloj)
        self.assertEqual(len(self.w.cola), 2)
        self.w.avanzar(1000)
        self.assertEqual((self.valores[-1], otra[-1]), (1.0, 1.0))

    def test_cancelar_la_deja_donde_estaba(self):
        fin = []
        self.animar(300, fin=lambda: fin.append(1))
        self.w.avanzar(100)
        ultimo = self.valores[-1]
        cancelar(self.w, "color")
        self.w.avanzar(1000)
        self.assertEqual(self.valores[-1], ultimo)
        self.assertLess(ultimo, 1.0)
        self.assertEqual((fin, self.w.cola), ([], {}))

    def test_cancelar_completando_la_lleva_al_final(self):
        fin = []
        self.animar(300, fin=lambda: fin.append(1))
        self.w.avanzar(50)
        cancelar(self.w, "color", completar=True)
        self.assertEqual((self.valores[-1], fin, self.w.cola), (1.0, [1], {}))
        cancelar(self.w, "color", completar=True)  # sin animación: nada
        self.assertEqual(fin, [1])

    def test_un_widget_destruido_la_para_sin_error(self):
        def paso(v):
            if v > 0:
                raise tk.TclError('invalid command name ".!label"')
        animar(self.w, "color", 300, paso, reloj=self.w.reloj)
        self.w.avanzar(1000)
        self.assertEqual(self.w.cola, {})


class TestNinguna(ConModo):
    modo = "ninguna"

    def test_instantanea_sin_after(self):
        fin = []
        self.animar(180, fin=lambda: fin.append(1))
        self.assertEqual(self.valores, [1.0])
        self.assertEqual(fin, [1])
        self.assertEqual(self.w.cola, {})

    def test_el_pulso_queda_quieto(self):
        latir(self.w, "pulso", 2400, self.valores.append, reloj=self.w.reloj)
        self.assertEqual((self.valores, self.w.cola), ([0.0], {}))

    def test_cerrar_destruye_al_momento(self):
        cerrar(self.w)
        self.assertEqual(self.w.destruido, 1)
        self.assertEqual(self.w.cola, {})


class TestReducidas(ConModo):
    modo = "reducidas"

    def test_fundidos_cortos(self):
        self.animar(1500)
        self.w.avanzar(animacion.CORTO_MS + animacion.PASO_MS)
        self.assertEqual(self.valores[-1], 1.0)
        self.assertEqual(self.w.cola, {})

    def test_lo_que_no_es_fundido_es_instantaneo(self):
        self.animar(300, fundido=False)
        self.assertEqual(self.valores, [1.0])

    def test_sin_pulso(self):
        latir(self.w, "pulso", 2400, self.valores.append, reloj=self.w.reloj)
        self.assertEqual((self.valores, self.w.cola), ([0.0], {}))


class TestLatir(ConModo):
    def test_sube_y_baja_hasta_cancelar(self):
        latir(self.w, "pulso", 1000, self.valores.append, reloj=self.w.reloj)
        self.w.avanzar(1000)
        self.assertTrue(all(0.0 <= v <= 1.0 for v in self.valores))
        self.assertGreater(max(self.valores), 0.95)
        self.assertLess(self.valores[0], 0.01, "empieza apagado: sin salto al arrancar")
        pico = self.valores.index(max(self.valores))
        self.assertTrue(400 <= pico * 66 <= 600, "el máximo, a mitad del periodo")
        self.assertLessEqual(len(self.valores), 1000 / 66 + 2, "~15 fps")
        cancelar(self.w, "pulso")
        n = len(self.valores)
        self.w.avanzar(1000)
        self.assertEqual(len(self.valores), n)


class TestCerrar(ConModo):
    def test_funde_bloquea_y_destruye_al_final(self):
        with patch.object(animacion.time, "monotonic", self.w.reloj):
            cerrar(self.w)
        self.assertTrue(self.w.soltado, "suelta el foco de la aplicación ya")
        self.assertTrue(self.w.atributos.get("-disabled"), "y no admite otro clic")
        self.assertEqual(self.w.destruido, 0)
        self.w.avanzar(animacion.SALIDA_MS + 20)
        self.assertEqual(self.w.atributos["-alpha"], 0.0)
        self.assertEqual(self.w.destruido, 1)

    def test_oculta_se_destruye_al_momento(self):
        self.w.visible = False
        cerrar(self.w)
        self.assertEqual((self.w.destruido, self.w.cola), (1, {}))

    def test_cerrar_dos_veces_destruye_una(self):
        with patch.object(animacion.time, "monotonic", self.w.reloj):
            cerrar(self.w)
            self.w.avanzar(40)
            cerrar(self.w)
        self.w.avanzar(1000)
        self.assertEqual(self.w.destruido, 1)


if __name__ == "__main__":
    unittest.main()
