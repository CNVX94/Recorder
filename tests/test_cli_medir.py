"""La pantalla «Medir mi equipo» de `daily menu` (cli/pantallas/medir.py) con un equipo fijo y motores falsos:
el progreso cancelable, la tabla de resultados con «la mejor» marcada, «Aplicar el mejor» con su confirmación
(solo escribe las claves de la prueba), el equipo ocupado y el ancho de 60 columnas en los tres juegos de símbolos.
La prueba corre en su hilo de verdad (con un reloj de mentira y modelos que no transcriben nada)."""
import io
import json
import threading
import unittest
from unittest import mock

from rich.cells import cell_len

from recorder import medicion as m
from recorder.cli import recomendar
from recorder.cli.consola import JUEGO_ASCII, JUEGO_CONSOLA, make_console
from recorder.cli.pantallas.medir import Medir, columna_dos_fuentes, tiempo, veces
from recorder.cli.pantallas.rendimiento import Rendimiento
from recorder.cli.teclas import ABAJO, ENTER, ESC
from recorder.config.schema import AppConfig
from tests.test_cli_pantallas import BaseTerminal, limpio
from tests.test_medicion import ModeloFalso, Reloj, candidato, escribir_wav, lista

# Las pruebas de PERFIL (6 núcleos sin HT, gama media): Baja con 5 hilos, Media con 4 y 5, Alta con 4 y 5
VELOCIDADES = {
    "small-1-cpu-5--1": 5.0, "small-5-cpu-4--1": 2.6, "small-5-cpu-5--1": 3.0,
    "large-v3-turbo-5-cpu-4--1": 1.3, "large-v3-turbo-5-cpu-5--1": 1.1,
}


def plano(texto: str) -> str:
    """El texto en una sola línea de palabras: las frases largas se parten al ancho de la terminal."""
    return " ".join(texto.split())


def inicial(terminal):
    return Medir(terminal)


class TestLogica(unittest.TestCase):
    def test_tiempo_redondeado_y_veces(self):
        self.assertEqual(tiempo(80), "1 min 20 s")
        self.assertEqual(tiempo(82), "1 min 20 s", "se redondea a 5 s para que no baile")
        self.assertEqual(tiempo(43), "45 s")
        self.assertEqual(veces(2.64), "2,6×")

    def test_columna_dos_fuentes(self):
        c = candidato()
        self.assertEqual(columna_dos_fuentes(lista(c, 3.0)), ("sí", "ok"))
        self.assertEqual(columna_dos_fuentes(lista(c, 1.4)), ("no: va justo", "aviso"))
        self.assertEqual(columna_dos_fuentes(lista(c, 0.9)), ("no: se atrasa", "error"))
        self.assertEqual(columna_dos_fuentes(m.Resultado(c)), ("", "tenue"), "«en espera» va en la columna de velocidad")
        self.assertEqual(columna_dos_fuentes(m.Resultado(c, m.OMITIDA, motivo=m.MOTIVO_MODELO))[0], "modelo sin descargar")
        self.assertEqual(columna_dos_fuentes(m.Resultado(c, m.OMITIDA, motivo=m.MOTIVO_PODA))[0], "no hace falta")


class TestMedir(BaseTerminal):
    def setUp(self):
        super().setUp()
        self.reloj_medicion = Reloj()
        self.wav = escribir_wav(self.raiz / "muestra.wav")
        self.puerta = None  # si se pone, cada transcripción espera a que se abra
        self.velocidades = dict(VELOCIDADES)
        self.reposo = 2
        self.prueba = None
        self.cargados = []
        parche = mock.patch.object(Medir, "_nueva_prueba", lambda pantalla: self._nueva_prueba(pantalla))
        parche.start()
        self.addCleanup(parche.stop)
        self.addCleanup(self._parar_hilo)

    def _parar_hilo(self):
        """Antes de borrar la carpeta temporal, que el hilo de la prueba (si sigue) acabe."""
        if self.puerta is not None:
            self.puerta.set()
        if self.prueba is not None:
            self.prueba.cancelar()
            self.prueba.esperar(10)

    @property
    def raiz(self):
        return self.ruta.parent

    def _cargar(self, c):
        self.cargados.append(c)
        guion = " ".join(m.GUION[:m.TURNOS_PRUEBA])
        modelo = ModeloFalso(self.reloj_medicion, self.velocidades.get(c.clave, 3.0))
        original = modelo.transcribe

        def transcribir(audio, **kw):
            if self.puerta is not None:
                self.puerta.wait(10)
            resultado = original(audio, **kw)
            return ([__import__("types").SimpleNamespace(text=guion)], {}) if modelo.llamadas == 1 else resultado

        modelo.transcribe = transcribir
        return modelo

    def _nueva_prueba(self, pantalla):
        r = self.reloj_medicion
        self.prueba = m.Prueba(
            pantalla.perfil, pantalla.app.config, pantalla.app.mgr.path, cargar=self._cargar,
            generar=lambda _turnos: self.wav, reposo=lambda: self.reposo, reloj=r,
            tiempos=lambda: (int(r.t * 1e7 * 0.6), int(r.t * 1e7)),  # 40 % de procesador ocupado
        )
        return self.prueba

    def fase(self, fase):
        return lambda: self.prueba is not None and self.prueba.fase == fase

    def correr_medir(self, *guion, **kwargs):
        return self.correr(*guion, inicial=inicial, **kwargs)

    def informe(self):
        return self.raiz / m.NOMBRE_INFORME

    # ------------------------------------------------------------ progreso
    def test_el_progreso_dice_cual_se_mide_y_solo_vale_esc(self):
        self.puerta = threading.Event()
        _codigo, texto = self.correr_medir(
            self.fase(m.EN_CURSO), None, None, "t", "?", ABAJO, ENTER, None, None, ESC, alto=26,
        )
        self.assertIn("Medir mi equipo", texto)
        self.assertRegex(texto, r"Midiendo 1 de 5: Baja · procesador, 5 hilos")
        self.assertRegex(texto, r"█*░+ +\d+ %")
        self.assertRegex(texto, r"Prueba +Velocidad +Procesador +¿Dos fuentes\?")
        self.assertRegex(texto, r"Media · procesador, 4 hilos +en espera")
        self.assertIn("midiendo…", texto)
        self.assertIn("No uses el equipo para cosas pesadas mientras se mide", plano(texto))
        self.assertIn("Para la medición y descarta lo medido. No cambia nada.", texto)
        self.assertIn("[Esc] Cancelar", texto)
        self.assertNotIn("[t]", texto, "mientras mide solo vale Esc")
        self.assertNotIn("[?]", texto)
        self.assertEqual(self.guardado()["theme"], AppConfig().theme, "«t» no cambió el tema")

    def test_esc_cancela_sin_cambiar_nada_ni_guardar_la_medicion(self):
        self.puerta = threading.Event()
        antes = self.ruta.read_bytes()
        t = self.terminal(self.fase(m.EN_CURSO), None, ESC, None, "q", inicial=lambda t: Rendimiento(t))
        t.abrir(Medir(t))
        codigo = t.run()
        texto = limpio(self.salida.getvalue())
        self.assertEqual(codigo, 0)
        self.assertIn("Medición cancelada. No se cambió nada.", texto, "la ve quien queda debajo")
        self.assertEqual(self.ruta.read_bytes(), antes)
        self.assertFalse(self.informe().exists())
        self.puerta.set()
        self.prueba.esperar(10)
        self.assertEqual(self.prueba.fase, m.CANCELADA)
        self.assertFalse(self.informe().exists(), "lo medido a medias se descarta")

    # ------------------------------------------------------------ resultados
    def test_tabla_con_la_mejor_marcada_y_dos_fuentes(self):
        _codigo, texto = self.correr_medir(self.fase(m.TERMINADA), None, None, ESC, alto=26)
        self.assertRegex(texto, r"Baja · procesador, 5 hilos +5,0× +40 % +sí")
        self.assertRegex(texto, r"Media · procesador, 4 hilos +2,6× +40 % +sí")
        self.assertRegex(texto, r"● +Media · procesador, 5 hilos +3,0× +40 % +sí +la mejor")
        self.assertRegex(texto, r"Alta · procesador, 4 hilos +1,3× +40 % +no: va justo")
        self.assertRegex(texto, r"Alta · procesador, 5 hilos +1,1× +40 % +no: va justo")
        self.assertIn("¿Dos fuentes? Los demás y tu micrófono a la vez: hace falta ir a 2,0× o más.", plano(texto))
        self.assertIn("▶ Aplicar el mejor: Media · procesador, 5 hilos", texto)
        self.assertIn("Medir otra vez", texto)
        self.assertIn("[Enter] Aplicar el mejor", texto)
        self.assertIn("Guarda la calidad, los hilos y dónde se transcribe de la mejor prueba. Antes te enseña qué cambia.", plano(texto))
        self.assertTrue(self.informe().is_file(), "la última medición queda junto al config.json")

    def test_la_mejor_es_la_de_mas_calidad_que_aguanta_dos_fuentes(self):
        self.velocidades.update({"large-v3-turbo-5-cpu-5--1": 2.2, "large-v3-turbo-5-cpu-4--1": 1.2})
        _codigo, texto = self.correr_medir(self.fase(m.TERMINADA), None, None, ESC, alto=26)
        self.assertRegex(texto, r"● +Alta · procesador, 5 hilos +2,2× +40 % +sí +la mejor")
        self.assertIn("▶ Aplicar el mejor: Alta · procesador, 5 hilos", texto)

    def test_si_ninguna_aguanta_dos_fuentes_ofrece_la_mas_rapida_y_lo_dice(self):
        self.velocidades = {c: 1.5 for c in VELOCIDADES}
        self.velocidades["small-5-cpu-5--1"] = 1.8
        _codigo, texto = self.correr_medir(self.fase(m.TERMINADA), None, None, ESC, alto=28)
        self.assertIn("Ninguna aguanta dos fuentes.", texto)
        self.assertIn("▶ Aplicar la más rápida: Media · procesador, 5 hilos", texto)

    def test_aplicar_ensena_antes_y_despues_y_escribe_solo_lo_de_la_prueba(self):
        antes = self.guardado()
        _codigo, texto = self.correr_medir(self.fase(m.TERMINADA), None, None, ENTER, None, ENTER, None, None, ESC, alto=26)
        self.assertIn("Se guardará en config.json:", texto)
        self.assertRegex(texto, r"Hilos de CPU +0 +→ +5")
        self.assertIn("Aplicado. Vale desde la próxima grabación.", texto)
        despues = self.guardado()
        cambiadas = {k for k in despues if despues[k] != antes.get(k)}
        self.assertEqual(cambiadas, {"cpu_threads"}, "ya era small, haz 5, cpu, int8: solo cambian los hilos")
        self.assertEqual(despues["notes_dir"], antes["notes_dir"])

    def test_esc_en_la_confirmacion_no_guarda(self):
        antes = self.ruta.read_bytes()
        _codigo, texto = self.correr_medir(self.fase(m.TERMINADA), None, None, ENTER, None, ESC, None, ESC, alto=26)
        self.assertIn("Se guardará en config.json:", texto)
        self.assertEqual(self.ruta.read_bytes(), antes)

    def test_con_config_ilegible_no_se_aplica(self):
        self.mgr.load()
        _codigo, texto = self.correr_medir(
            self.fase(m.TERMINADA), None, None, lambda: self.ruta.write_bytes(b"{ roto") or True, ENTER, None, None, ESC, alto=26,
        )
        self.assertIn("No se aplica: No se pudo leer", texto)
        self.assertEqual(self.ruta.read_bytes(), b"{ roto")

    def test_si_ya_usas_la_mejor_no_hay_accion_de_aplicar(self):
        cfg = AppConfig(notes_dir=str(self.notas), model="small", beam_size=5, device="cpu", compute_type="int8", cpu_threads=5)
        self.ruta.write_text(json.dumps(cfg.to_dict()), encoding="utf-8")
        _codigo, texto = self.correr_medir(self.fase(m.TERMINADA), None, None, ESC, alto=26)
        self.assertNotIn("Aplicar el mejor:", texto)
        self.assertIn("Medir otra vez", texto)

    def test_medir_otra_vez_repite_las_pruebas(self):
        _codigo, texto = self.correr_medir(
            self.fase(m.TERMINADA), None, None, ABAJO, ENTER, None, lambda: len(self.cargados) >= 10, None, ESC, alto=26,
        )
        self.assertGreaterEqual(len(self.cargados), 10, "las cinco pruebas dos veces")

    def test_la_recomendacion_del_equipo_usa_la_medicion(self):
        self.velocidades.update({"large-v3-turbo-5-cpu-5--1": 2.2})
        self.correr_medir(self.fase(m.TERMINADA), None, None, ESC)
        salida = io.StringIO()
        self.assertEqual(recomendar.recomendar(False, make_console(file=salida, width=200), self.mgr), 0)
        texto = salida.getvalue()
        self.assertIn("Medido en tu equipo el", texto)
        self.assertIn("Alta · procesador, 5 hilos", texto)
        self.assertIn("[medida]", texto)

    # ------------------------------------------------------------ equipo ocupado, errores y detalles
    def test_equipo_ocupado_pide_decidir_y_no_mide_sin_permiso(self):
        self.reposo = 45
        _codigo, texto = self.correr_medir(self.fase(m.OCUPADO), None, None, ESC, alto=26)
        self.assertIn("El equipo está ocupado", texto)
        self.assertIn("Va al 45 % de procesador", plano(texto))
        self.assertIn("▶ Medir de todos modos", texto)
        self.assertEqual(self.cargados, [])
        self.assertFalse(self.informe().exists())

    def test_medir_de_todos_modos_sigue_con_la_prueba(self):
        self.reposo = 45
        _codigo, texto = self.correr_medir(self.fase(m.OCUPADO), None, None, ENTER, self.fase(m.TERMINADA), None, None, ESC, alto=26)
        self.assertIn("la mejor", texto)
        self.assertTrue(self.prueba.informe.forzada)

    def test_sin_voz_dice_que_hacer(self):
        self.prueba = None

        def nueva(pantalla):
            self.prueba = m.Prueba(
                pantalla.perfil, pantalla.app.config, pantalla.app.mgr.path, cargar=self._cargar,
                generar=lambda _t: (_ for _ in ()).throw(m.SinVoz()), reposo=lambda: 2,
            )
            return self.prueba

        with mock.patch.object(Medir, "_nueva_prueba", nueva):
            _codigo, texto = self.correr_medir(self.fase(m.ERROR), None, None, ESC, alto=26)
        self.assertIn("Windows no tiene ninguna voz en español", plano(texto))
        self.assertIn("Medir otra vez", texto)

    def test_gpu_integrada_sin_permiso_se_dice_en_los_resultados(self):
        self.prueba = None
        antes = self.prueba

        def nueva(pantalla):
            p = self._nueva_prueba(pantalla)
            p.igpu_sin_permiso = True
            return p

        with mock.patch.object(Medir, "_nueva_prueba", nueva):
            _codigo, texto = self.correr_medir(self.fase(m.TERMINADA), None, None, ESC, alto=30)
        self.assertIn("Gráfica integrada sin probar.", texto)
        self.assertIn("activa «Permitir GPU integrada» en Opciones", plano(texto))

    def test_se_abre_desde_rendimiento_con_enter(self):
        self.puerta = threading.Event()
        _codigo, texto = self.correr("7", *[None] * 200, ENTER, self.fase(m.EN_CURSO), None, ESC, None, ESC, "q", alto=26)
        self.assertIn("Inicio › Rendimiento › Medir mi equipo", texto)
        self.assertIn("Midiendo 1 de 5", texto)

    def test_sin_equipo_detectado_gira_el_spinner(self):
        from recorder.config import hardware

        with mock.patch.object(hardware, "_cache", None), \
                mock.patch("recorder.cli.pantallas.medir.cached_hardware", side_effect=lambda: None):
            _codigo, texto = self.correr_medir(None, None, ESC)
        self.assertIn("Detectando el equipo…", texto)

    def test_60_columnas_en_los_tres_juegos_cabe_y_no_deja_restos(self):
        for juego in (None, JUEGO_CONSOLA, JUEGO_ASCII):
            with self.subTest(juego=juego):
                t = self.terminal(self.fase(m.TERMINADA), None, None, ESC, inicial=inicial, ancho=60, alto=26, ascii_mode=juego == JUEGO_ASCII)
                if juego == JUEGO_CONSOLA:
                    t.consola.juego = t.juego = JUEGO_CONSOLA
                t.run()
                texto = limpio(self.salida.getvalue().replace("\x1b[H", "\n"))
                self.assertFalse([l for l in texto.split("\n") if cell_len(l) > 60], "nada pasa de 60 columnas")
                self.assertRegex(texto, r"Vel\. +CPU +¿Dos fuentes\?", "cabeceras cortas")
                self.assertRegex(texto, r"[●*] +Media · CPU, 5 hilos +3,0× +40 % +sí")
                self.assertNotIn("la mejor", texto, "a 60 columnas «la mejor» es solo el marcador")
                if juego == JUEGO_ASCII:
                    for simbolo in "●○✔✅▶►⚠•":
                        self.assertNotIn(simbolo, texto)


if __name__ == "__main__":
    unittest.main()
