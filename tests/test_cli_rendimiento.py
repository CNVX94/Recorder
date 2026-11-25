"""Las vistas puras de Rendimiento (recorder/cli/pantallas/rendimiento.py): la del menú (sin grabación) y la
de la grabación, con métricas fijas, a 100 y a 60 columnas y en los tres juegos de símbolos."""
import unittest

from rich.cells import cell_len

from recorder.cli.consola import JUEGO_ASCII, JUEGO_COMPLETO, JUEGO_CONSOLA
from recorder.cli.pantallas import rendimiento as r
from recorder.config.hardware import GpuInfo, HardwareProfile
from recorder.metricas import Metricas, MotorEfectivo
from tests.apoyo_cli import solo_ascii

JUEGOS = (JUEGO_COMPLETO, JUEGO_CONSOLA, JUEGO_ASCII)
ANCHOS = (100, 60)
CPU = MotorEfectivo("faster-whisper", "cpu", "small", 5, hilos=4)
HW = HardwareProfile(
    cpu_name="12th Gen Intel(R) Core(TM) i7-1255U", physical_cores=10, logical_cores=12, p_cores=2, e_cores=8,
    avx2=True, ram_total_mb=32768, desktop=False,
    gpus=[GpuInfo("Intel(R) Iris(R) Xe Graphics", 0x8086, 0x46A8, 128, integrated=True)],
)


def metricas(**cambios) -> Metricas:
    base = dict(
        motor=CPU, velocidad=2.6, ultimo_fragmento_s=3.1, cpu_proceso=38.0, cpu_sistema=52.0, ram_mb=1434.0,
        gpu_proceso=None, gpu_sistema=6.0, cola=2, atraso_s=24.0, ram_sistema_mb=11468.8, ram_total_mb=32768.0,
    )
    return Metricas(**{**base, **cambios})


def historias(cpu_sistema=40.0, muestras=10, **otras):
    h = r.nuevas_historias()
    for i in range(muestras):
        r.anotar(h, metricas(cpu_sistema=cpu_sistema, **otras))
    return h


def texto(lineas) -> str:
    return "\n".join("".join(t for t, _e in linea) for linea in lineas)


def en_vivo(m=None, h=None, ancho=100, alto=30, juego=JUEGO_COMPLETO, **kw) -> str:
    return texto(r.vista_en_vivo(m or metricas(), h or historias(), ancho, alto, juego, **kw))


def en_reposo(m=None, h=None, ancho=100, alto=30, juego=JUEGO_COMPLETO, hw=HW, motor=CPU, **kw) -> str:
    return texto(r.vista_reposo(m or metricas(), h or historias(), hw, motor, "Calidad Media · CPU", ancho, alto, juego, **kw))


class TestVeredictos(unittest.TestCase):
    def test_margen_segun_la_media_de_los_ultimos_30_s(self):
        self.assertIsNone(r.margen([]))
        self.assertIsNone(r.margen([None, None]))
        self.assertEqual(r.margen([49.0] * 15), "ok")
        self.assertEqual(r.margen([50.0] * 15), "justo", "desde MARGEN_HOLGADO ya no es holgado")
        self.assertEqual(r.margen([75.0] * 15), "justo")
        self.assertEqual(r.margen([76.0] * 15), "no")
        self.assertEqual(r.margen([100.0] * 20 + [10.0] * 15), "ok", "solo cuentan las últimas 15 muestras (30 s)")
        self.assertEqual(r.margen([None, 90.0, None]), "no", "los huecos no cuentan")

    def test_velocidad_frente_al_tiempo_real(self):
        self.assertIsNone(r.veredicto_velocidad(None))
        self.assertEqual(r.veredicto_velocidad(1.5), "al_dia")
        self.assertEqual(r.veredicto_velocidad(1.49), "va_justo")
        self.assertEqual(r.veredicto_velocidad(1.0), "va_justo")
        self.assertEqual(r.veredicto_velocidad(0.99), "se_atrasa")


class TestHistorias(unittest.TestCase):
    def test_anotar_guarda_de_0_a_100_y_none_sin_dato(self):
        h = r.nuevas_historias()
        r.anotar(h, metricas(velocidad=2.0, gpu_proceso=None, ram_mb=3276.8))
        self.assertEqual(h["velocidad"][-1], 50.0, "2× sobre un tope de 4×")
        self.assertIsNone(h["gpu_proceso"][-1])
        self.assertEqual(h["ram_proceso"][-1], 10.0)
        self.assertAlmostEqual(h["ram_sistema"][-1], 35.0)
        r.anotar(h, metricas(velocidad=None, ram_total_mb=None))
        self.assertIsNone(h["velocidad"][-1])
        self.assertIsNone(h["ram_sistema"][-1])

    def test_guarda_unos_2_minutos(self):
        h = r.nuevas_historias()
        for _ in range(100):
            r.anotar(h, metricas())
        self.assertEqual({len(s) for s in h.values()}, {60})


class TestVistaEnVivo(unittest.TestCase):
    def test_va_al_dia(self):
        t = en_vivo()
        self.assertIn("Va al día. Transcribe 2,6 veces más rápido de lo que se habla.", t)
        self.assertRegex(t, r"Velocidad\s+2,6×\s+█+░+")
        self.assertIn("1× = al ritmo del habla", t)
        self.assertIn("2 trozos · 24 s de audio · último trozo: 3,1 s", t)
        self.assertRegex(t, r"Procesador\s+38 %")
        self.assertIn("equipo 52 %", t)
        self.assertRegex(t, r"Memoria\s+1,4 GB")
        self.assertIn("de 32 GB", t)
        self.assertIn("faster-whisper · CPU, 4 hilos · small · haz 5", t)

    def test_va_justo_y_se_atrasa(self):
        self.assertIn("Va justo. Transcribe casi a la velocidad del habla", en_vivo(metricas(velocidad=1.2)))
        t = en_vivo(metricas(velocidad=0.8))
        self.assertIn("Se atrasa. Transcribe más lento de lo que se habla", t)
        self.assertIn("⚠", t)

    def test_cargando_el_modelo_y_sin_cola(self):
        t = en_vivo(metricas(motor=None, velocidad=None, ultimo_fragmento_s=None, cola=0, atraso_s=0.0), giro="/")
        self.assertIn("/ Cargando el modelo. La velocidad se sabrá con la primera frase.", t)
        self.assertRegex(t, r"Velocidad\s+/\s")
        self.assertIn("nada pendiente", t)
        self.assertNotIn("Motor", t, "sin motor cargado no hay línea de motor")

    def test_un_solo_trozo(self):
        self.assertIn("1 trozo · 3 s de audio", en_vivo(metricas(cola=1, atraso_s=3.0)))

    def test_gpu_nd_con_la_del_equipo(self):
        t = en_vivo()
        self.assertRegex(t, r"Tarjeta gráfica\s+n/d\s+░+")
        self.assertIn("equipo 6 %", t)
        self.assertRegex(en_vivo(metricas(gpu_proceso=30.0)), r"Tarjeta gráfica\s+30 %")

    def test_sin_dato_de_procesador_ni_memoria(self):
        t = en_vivo(metricas(cpu_proceso=None, cpu_sistema=None, ram_mb=None, ram_total_mb=None), r.nuevas_historias())
        self.assertRegex(t, r"Procesador\s+n/d")
        self.assertRegex(t, r"Memoria\s+n/d")

    def test_caida_a_cpu(self):
        motor = MotorEfectivo("faster-whisper", "cpu", "small", 5, hilos=4, caida="Vulkan no arrancó")
        t = en_vivo(metricas(motor=motor))
        self.assertIn("Se transcribe con el procesador porque la tarjeta gráfica falló (Vulkan no arrancó).", t)
        self.assertNotIn("caída a CPU", t, "el motivo va en su línea, no repetido en la del motor")

    def test_en_los_tres_juegos_y_dos_anchos(self):
        for juego in JUEGOS:
            for ancho in ANCHOS:
                with self.subTest(juego=juego, ancho=ancho):
                    lineas = r.vista_en_vivo(metricas(), historias(), ancho, 30, juego)
                    t = texto(lineas)
                    self.assertFalse([l for l in t.split("\n") if cell_len(l) > ancho], t)
                    self.assertIn("2,6×", t)
                    if juego == JUEGO_ASCII:
                        self.assertTrue(solo_ascii(t), t)
                    if juego != JUEGO_COMPLETO:
                        self.assertNotIn("▁", t, "▁▂▃ no los dibuja Consolas")
                        self.assertNotIn("▅", t)

    def test_se_aprieta_para_caber_en_el_alto(self):
        completa = r.vista_en_vivo(metricas(), historias(), 100, 40)
        self.assertGreater(len(completa), 12)
        for alto in (len(completa), 12, 10, 6):
            lineas = r.vista_en_vivo(metricas(), historias(), 100, alto)
            self.assertLessEqual(len(lineas), alto)
        self.assertIn("Va al día", texto(r.vista_en_vivo(metricas(), historias(), 100, 6)), "el veredicto siempre se ve")

    def test_no_depende_de_la_pantalla_del_menu(self):
        # Se puede llamar sin terminal, sin consola y con historias vacías.
        self.assertTrue(r.vista_en_vivo(metricas(), r.nuevas_historias(), 60, 24))


class TestVistaReposo(unittest.TestCase):
    def test_hay_margen(self):
        t = en_reposo()
        self.assertIn("Hay margen para grabar. El equipo va desahogado: puedes grabar con la calidad elegida.", t)
        self.assertIn("Se transcribiría con: CPU, 4 hilos · Calidad Media", t)
        self.assertIn("Ahora, en todo el equipo", t)
        self.assertIn("últimos 2 min", t)
        self.assertRegex(t, r"Procesador\s+52 %")
        self.assertIn("pico 40 %", t, "el pico es el de la historia, no el de ahora")
        self.assertRegex(t, r"Tarjeta gráfica\s+6 %")
        self.assertRegex(t, r"Memoria\s+35 %")
        self.assertIn("11,2 de 32 GB", t)

    def test_equipo_con_nucleos_y_gpu_integrada(self):
        t = en_reposo()
        self.assertIn("10 núcleos (2P+8E), 12 hilos", t)
        self.assertIn("32 GB de RAM", t)
        self.assertIn("GPU: Intel(R) Iris(R) Xe Graphics (integrada)", t)

    def test_va_justo_y_cargado(self):
        self.assertIn("El equipo va justo. Ya está ocupado", en_reposo(h=historias(cpu_sistema=60.0)))
        t = en_reposo(h=historias(cpu_sistema=90.0))
        self.assertIn("El equipo va cargado. Cierra algo o baja la calidad", t)
        self.assertIn("⚠", t)

    def test_primer_dato_sin_huecos_vacios(self):
        vacio = metricas(cpu_sistema=None, gpu_sistema=None, ram_sistema_mb=None, ram_total_mb=None)
        t = en_reposo(vacio, r.nuevas_historias(), midiendo=True, giro="/")
        self.assertIn("/ Midiendo. La primera cifra llega en un par de segundos.", t)
        self.assertRegex(t, r"Procesador\s+/\s")
        self.assertNotIn("__", t)
        t = en_reposo(vacio, r.nuevas_historias(), midiendo=False)
        self.assertRegex(t, r"Procesador\s+n/d")
        self.assertIn("Windows no da este dato en este equipo.", t)

    def test_con_la_primera_muestra_ya_hay_veredicto(self):
        h = r.nuevas_historias()
        r.anotar(h, metricas(cpu_sistema=20.0))
        self.assertIn("Hay margen para grabar", en_reposo(h=h, midiendo=True))

    def test_caida_a_cpu_dice_por_que(self):
        motor = MotorEfectivo("faster-whisper", "cpu", "small", 5, hilos=4, caida="no hay tarjeta compatible")
        self.assertIn("la tarjeta gráfica falló (no hay tarjeta compatible)", en_reposo(motor=motor))

    def test_detectando_el_equipo(self):
        t = en_reposo(hw=None, motor=None, giro="/")
        self.assertIn("/ Detectando el equipo…", t)
        self.assertNotIn("Equipo\n", t)

    def test_en_los_tres_juegos_y_dos_anchos(self):
        for juego in JUEGOS:
            for ancho in ANCHOS:
                with self.subTest(juego=juego, ancho=ancho):
                    t = en_reposo(ancho=ancho, juego=juego)
                    self.assertFalse([l for l in t.split("\n") if cell_len(l) > ancho], t)
                    self.assertIn("35 %", t)
                    if juego == JUEGO_ASCII:
                        self.assertTrue(solo_ascii(t), t)
                    if juego != JUEGO_COMPLETO:
                        self.assertNotIn("▁", t)

    def test_se_aprieta_para_caber_en_el_alto(self):
        for alto in (20, 14, 12, 9, 5):
            lineas = r.vista_reposo(metricas(), historias(), HW, CPU, "Calidad Media · CPU", 100, alto)
            self.assertLessEqual(len(lineas), alto)
        t = en_reposo(alto=9)
        self.assertIn("Hay margen para grabar", t)
        self.assertRegex(t, r"Memoria\s+35 %", "con poco alto quedan las cifras en una fila cada una")

    def test_la_tendencia_se_alinea_a_la_derecha_y_el_hueco_no_dibuja(self):
        arriba, abajo = r.tendencia_doble([None, 0.0, 100.0], 5, JUEGO_COMPLETO)
        self.assertEqual(len(arriba), 5)
        self.assertEqual(abajo[:3], "   ")
        self.assertEqual(abajo[3:], "▁█")
        self.assertEqual(arriba[4], "█", "al 100 % también llena la fila de arriba")
        self.assertEqual(r.tendencia_doble([], 0, JUEGO_ASCII), ("", ""))


if __name__ == "__main__":
    unittest.main()
