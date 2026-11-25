"""Panel de rendimiento de la ventana (recorder/ui/rendimiento.py), sin Tk: el historial de ~2 min,
los textos de cada dato y las coordenadas de las sparklines."""

import unittest

from recorder.metricas import Metricas, MotorEfectivo
from recorder.ui.rendimiento import MUESTRAS, SERIES, Historial, puntos, textos


def metricas(**cambios) -> Metricas:
    base = dict(
        motor=MotorEfectivo("faster-whisper", "cpu", "small", 5, hilos=4), velocidad=2.14,
        ultimo_fragmento_s=3.2, cpu_proceso=12.4, cpu_sistema=34.0, ram_mb=850.6,
        gpu_proceso=None, gpu_sistema=None, cola=3, atraso_s=45.2,
    )
    return Metricas(**{**base, **cambios})


class TestHistorial(unittest.TestCase):
    def setUp(self):
        self.t = 0.0
        self.h = Historial(reloj=lambda: self.t)

    def test_una_muestra_por_intervalo(self):
        self.assertTrue(self.h.anotar(metricas()))
        self.t = 0.2
        self.assertFalse(self.h.anotar(metricas(cola=9)), "el sondeo de 200 ms no añade muestras")
        self.t = self.h.intervalo
        self.assertTrue(self.h.anotar(metricas(cola=4)))
        self.assertEqual(list(self.h.series["cola"]), [3.0, 4.0])
        self.assertEqual(self.h.version, 2)

    def test_guarda_unos_2_minutos_y_los_none(self):
        self.assertEqual(MUESTRAS * self.h.intervalo, 120)
        for i in range(MUESTRAS + 15):
            self.t = i * self.h.intervalo
            self.h.anotar(metricas(cpu_proceso=float(i)))
        self.assertEqual(len(self.h.series["cpu"]), MUESTRAS)
        self.assertEqual(self.h.series["cpu"][-1], MUESTRAS + 14.0, "las más viejas se van")
        self.assertEqual(set(self.h.series["gpu"]), {None}, "sin dato de GPU, None")

    def test_sin_foto_no_anota(self):
        self.assertFalse(self.h.anotar(None))
        self.assertEqual(self.h.version, 0)


class TestTextos(unittest.TestCase):
    def test_con_datos(self):
        self.assertEqual(textos(metricas()), {
            "motor": "faster-whisper · CPU, 4 hilos · small · haz 5",
            "velocidad": "2,1×",
            "cpu": "12 % (equipo 34 %)",
            "gpu": "n/d",
            "ram": "851 MB",
            "cola": "3",
            "atraso": "45 s",
        })

    def test_mientras_arranca(self):
        vacio = textos(None)
        self.assertEqual(vacio["motor"], "Cargando modelo…")
        self.assertEqual({vacio[s[0]] for s in SERIES}, {"n/d"})
        t = textos(metricas(motor=None, velocidad=None, cpu_proceso=None, gpu_sistema=20.0))
        self.assertEqual((t["motor"], t["velocidad"], t["cpu"], t["gpu"]),
                         ("Cargando modelo…", "n/d", "n/d (equipo 34 %)", "n/d (equipo 20 %)"))

    def test_cada_dato_tiene_ayuda_de_la_ventana(self):
        from recorder import ayuda
        for _clave, _titulo, clave_ayuda, _techo in SERIES:
            self.assertIn(clave_ayuda, {**ayuda.VENTANA, **ayuda.COMUN})


class TestPuntos(unittest.TestCase):
    def test_menos_de_dos_valores_no_dibuja(self):
        self.assertEqual(puntos([], 100, 30), [])
        self.assertEqual(puntos([None, 5.0, None], 100, 30), [])

    def test_alineada_a_la_derecha_y_escalada_con_techo(self):
        c = puntos([0.0, 50.0, 100.0], 102, 30, techo=10.0, n=3, margen=1)
        self.assertEqual(c, [1.0, 29.0, 51.0, 15.0, 101.0, 1.0])

    def test_el_techo_evita_montanas_de_ruido(self):
        c = puntos([1.0, 2.0], 100, 30, techo=10.0, n=2, margen=0)
        self.assertEqual(c[1], 27.0)
        self.assertEqual(c[3], 24.0, "2 de 10: abajo, no en el borde de arriba")

    def test_historial_a_medio_llenar_entra_por_la_derecha(self):
        c = puntos([1.0, 2.0], 100, 30, techo=None, n=11, margen=0)
        self.assertEqual((c[0], c[2]), (90.0, 100.0))

    def test_sin_techo_va_del_minimo_al_maximo_y_salta_los_none(self):
        c = puntos([800.0, None, 900.0, 850.0], 40, 20, techo=None, n=4, margen=0)
        xs, ys = c[0::2], c[1::2]
        self.assertEqual(len(xs), 3)
        self.assertEqual((ys[0], ys[1], ys[2]), (20.0, 0.0, 10.0))

    def test_serie_plana_no_divide_por_cero(self):
        c = puntos([5.0, 5.0, 5.0], 40, 20, techo=None, n=3, margen=0)
        self.assertEqual(c[1::2], [20.0, 20.0, 20.0])


if __name__ == "__main__":
    unittest.main()
