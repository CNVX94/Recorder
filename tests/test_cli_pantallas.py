"""Las pantallas navegables de `daily menu` (cli/pantallas.py) con teclas guionizadas.

Sin teclado ni terminal reales: la consola escribe en memoria como una terminal de 80×24 (o la que
pida la prueba), el reloj y la espera son de mentira (cada vuelta avanza INTERVALO s), el equipo
es un perfil fijo en la caché, Opciones no enumera dispositivos ni pantallas de verdad y
Rendimiento lee un muestreo de mentira.
"""

import contextlib
import datetime
import io
import json
import pathlib
import re
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock

from rich.cells import cell_len

from recorder import ayuda
from recorder.cli import app, configurar, pantallas
from recorder.cli.consola import JUEGO_ASCII, JUEGO_CONSOLA, make_console
from recorder.cli.menu import menu
from recorder.cli.pantallas import Terminal, barra, nota_de_hoy, recorte, tendencia
from recorder.cli.teclas import ABAJO, ARRIBA, DERECHA, ENTER, ESC, RETROCESO
from recorder.config import hardware
from recorder.config.hardware import HardwareProfile
from recorder.config.manager import ConfigManager
from recorder.config.schema import AppConfig
from recorder.metricas import Metricas
from tests.apoyo_cli import solo_ascii

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")
PERFIL = HardwareProfile(
    cpu_name="Intel(R) Core(TM) i5-9500 CPU @ 3.00GHz", physical_cores=6, logical_cores=6,
    p_cores=6, avx2=True, ram_total_mb=16327, desktop=True,
)
ENTORNO = configurar.Entorno(
    ["(todas las pantallas)", "Pantalla 1: 1920×1080 en (0, 0)"], ["Chat | Microsoft Teams"],
    ["Altavoces", "Auriculares"], ["Micrófono"], PERFIL,
)
# Filas de Opciones (pantallas.opciones.Opciones._componer; sin carpeta de whisper.cpp no hay GPU ni flash attention)
NOTAS, MIC, TEMA = 0, 4, 12


def limpio(salida: str) -> str:
    return ANSI.sub("", salida)


class Teclado:
    """Una entrada del guion por vuelta. None = nada pulsado; una función se repite (sin tecla)
    hasta que devuelve algo cierto, para esperar a un hilo o tocar algo a mitad."""

    def __init__(self, guion):
        self.guion = list(guion)

    def __call__(self):
        if not self.guion:
            return None
        paso = self.guion[0]
        if callable(paso):
            if paso():
                self.guion.pop(0)
            return None
        return self.guion.pop(0)


class Reloj:
    """El reloj y la espera: cada espera avanza el tiempo de mentira y deja correr a los hilos."""

    def __init__(self, salida: io.StringIO, tope: int = 3000):
        self.t, self.vueltas, self.tope = 0.0, 0, tope
        self.salida = salida
        self.longitudes = []  # lo escrito al acabar cada vuelta

    def __call__(self) -> float:
        return self.t

    def dormir(self, segundos: float) -> None:
        self.t += segundos
        self.vueltas += 1
        self.longitudes.append(len(self.salida.getvalue()))
        if self.vueltas > self.tope:
            raise AssertionError("el bucle no acaba")
        time.sleep(0.001)


class MuestreoFalso:
    def __init__(self, cpu=None, gpu=None):
        self.cpu, self.gpu = cpu, gpu
        self.parado = False

    def iniciar(self):
        pass

    def parar(self):
        self.parado = True

    def foto(self):
        return Metricas(None, None, None, 1.0, self.cpu, 80.0, None, self.gpu, 0, 0.0)


def comando_falso(nombre, registro):
    def ejecutar(args, consola):
        registro.append(nombre)
        return 0

    return SimpleNamespace(NOMBRE=nombre, AYUDA=nombre, agregar_argumentos=lambda p: None, ejecutar=ejecutar)


class BaseTerminal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = pathlib.Path(self.tmp.name)
        self.notas = raiz / "notas"
        self.ruta = raiz / "config.json"
        cfg = AppConfig()
        cfg.notes_dir = str(self.notas)
        self.ruta.write_text(json.dumps(cfg.to_dict()), encoding="utf-8")
        self.mgr = ConfigManager(self.ruta)
        self.ejecutados = []
        self.comandos = {n: comando_falso(n, self.ejecutados) for n in ("config", "recomendar")}
        self.muestreo = MuestreoFalso(cpu=50.0)
        parche = mock.patch.object(hardware, "_cache", PERFIL)
        parche.start()
        self.addCleanup(parche.stop)

    def terminal(self, *guion, ancho=80, alto=24, ascii_mode=False, windows=True, inicial=None) -> Terminal:
        self.salida = io.StringIO()
        self.consola = make_console(
            ascii_mode=ascii_mode, file=self.salida, width=ancho, height=alto,
            force_terminal=True, color_system="truecolor", legacy_windows=False, no_color=False,  # aunque haya NO_COLOR
        )
        self.reloj = Reloj(self.salida)
        self.teclado = Teclado(guion)
        self.t = Terminal(
            self.consola, self.comandos, self.mgr, leer_tecla=self.teclado, dormir=self.reloj.dormir,
            reloj=self.reloj, windows=windows, detectar=lambda: ENTORNO, muestreador=lambda: self.muestreo, inicial=inicial,
        )
        return self.t

    def correr(self, *guion, **kwargs):
        codigo = self.terminal(*guion, **kwargs).run()
        return codigo, limpio(self.salida.getvalue())

    def opciones_listas(self):
        return self.t._entorno is not None

    def guardado(self) -> dict:
        return json.loads(self.ruta.read_text(encoding="utf-8"))


class TestLogica(unittest.TestCase):
    def test_recorte_sigue_a_lo_elegido(self):
        self.assertEqual(recorte(5, 3, 10), range(0, 5), "si cabe, todo")
        self.assertEqual(recorte(20, 0, 5), range(0, 5))
        self.assertEqual(recorte(20, 10, 5), range(8, 13), "centrado")
        self.assertEqual(recorte(20, 19, 5), range(15, 20), "al final no deja hueco")

    def test_barra_y_tendencia(self):
        self.assertEqual(barra(50, 10), ("█████", "░░░░░"))
        self.assertEqual(barra(140, 4), ("████", ""), "lo que pasa de 100 se queda en 100")
        self.assertEqual(tendencia([0, 50, 100, None], 4), "▁▅█ ")
        self.assertEqual(tendencia([0, 50, 100, None], 2), "█ ", "las últimas")
        self.assertEqual(tendencia([0, 50, 100], 3, JUEGO_ASCII), "_=#")
        self.assertEqual(tendencia([0, 50, 100], 3, JUEGO_CONSOLA), "·▄█")
        self.assertEqual(tendencia([10], 0), "")

    def test_nota_de_hoy_es_la_ultima_y_no_una_copia(self):
        with tempfile.TemporaryDirectory() as d:
            hoy = datetime.date(2026, 11, 24)
            self.assertEqual(nota_de_hoy(d, hoy), "aún no hay (se crea al grabar)")
            for nombre in ("daily_2026-11-24_09-30.md", "daily_2026-11-24_15-02.md", "daily_2026-11-24_15-02_reagrupada.md", "daily_2026-11-25_08-00.md"):
                (pathlib.Path(d) / nombre).write_text("", encoding="utf-8")
            self.assertEqual(nota_de_hoy(d, hoy), "daily_2026-11-24_15-02.md")


class TestInicio(BaseTerminal):
    def test_flechas_mueven_y_enter_abre_un_comando(self):
        codigo, texto = self.correr(ABAJO, ABAJO, ENTER, "x", "q")
        self.assertEqual(codigo, 0)
        self.assertEqual(self.ejecutados, ["recomendar"])
        self.assertIn("▶ 5  Recomendación del equipo", texto, "lo elegido lleva la marca")
        self.assertIn(ayuda.linea("menu_recomendar")[:60], texto, "y su línea de ayuda debajo")
        self.assertIn("[Enter] Abrir · [Esc] Salir · [?] Ayuda · [t] Tema", texto)
        self.assertIn("[una tecla] volver al menú", texto)
        self.assertEqual(texto.count("▶ 5  Recomendación del equipo"), 2, "se vuelve a las pantallas, con lo elegido")

    def test_lo_elegido_cambia_de_color_al_moverse(self):
        self.correr(ABAJO, "q")
        salida = self.salida.getvalue()
        acento = r"\x1b\[1;38;2;249;226;175(;48;2;49;50;68)?m"  # bold acento del tema oscuro (y el fondo de la fila elegida)
        self.assertRegex(salida, acento + "Grabar")
        self.assertRegex(salida, acento + "Opciones")
        self.assertRegex(salida, r"\x1b\[[0-9;]*48;2;49;50;68m +\x1b\[0m", "la fila elegida llega al borde con el fondo de la superficie")

    def test_j_k_numeros_y_esc_vuelve(self):
        codigo, texto = self.correr("j", "k", "8", *["j"] * 80, ESC, ESC)
        self.assertEqual(codigo, 0)
        self.assertIn("Inicio › Ayuda", texto)
        self.assertIn("Teclas de las pantallas", texto)
        self.assertIn("  [p] Pausar / seguir: ", texto, "las de la grabación, de recorder/ayuda.py")
        self.assertIn("Glosario", texto, "bajando se llega al glosario")
        self.assertIn("  Markdown (.md): ", texto, "y a su final")
        self.assertEqual(self.ejecutados, [])

    def test_grabar_y_ventana_terminan_el_menu(self):
        with mock.patch("recorder.cli.live.grabar", return_value=4) as grabar:
            self.assertEqual(self.correr(ENTER)[0], 4)
        grabar.assert_called_once_with(consola=self.consola)
        with mock.patch.object(app, "abrir_ventana", return_value=0) as ventana:
            self.assertEqual(self.correr("6")[0], 0)
        ventana.assert_called_once()

    def test_fuera_de_windows_grabar_y_ventana_desactivadas(self):
        with mock.patch("recorder.cli.live.grabar") as grabar, mock.patch.object(app, "abrir_ventana") as ventana:
            codigo, texto = self.correr(ENTER, "6", "q", windows=False)
        self.assertEqual(codigo, 0)
        grabar.assert_not_called()
        ventana.assert_not_called()
        self.assertIn("1  Grabar                    (solo Windows)", texto)
        self.assertIn("Necesita la captura de audio de Windows (WASAPI)", texto)
        self.assertIn("⚠ Solo en Windows: no se puede aquí.", texto)

    def test_la_cabecera_se_refresca_en_el_tic(self):
        hoy = f"daily_{datetime.date.today():%Y-%m-%d}_09-30.md"

        def crear_nota():
            self.notas.mkdir()
            (self.notas / hoy).write_text("", encoding="utf-8")
            return True

        _codigo, texto = self.correr(None, crear_nota, *[None] * 25, "q")
        self.assertIn("Recorder · nota de hoy: aún no hay (se crea al grabar)", texto)
        self.assertIn(f"Recorder · nota de hoy: {hoy}", texto)
        self.assertIn("Calidad Media · CPU · se usaría faster-whisper · CPU, 4 hilos · small · haz 5", texto)
        self.assertIn("Equipo: Intel Core i5-9500", texto)

    def test_quieto_no_redibuja(self):
        self.correr(*[None] * 70, "q")  # 3,5 s de mentira: tres tics de la cabecera
        longitudes = self.reloj.longitudes
        self.assertEqual(longitudes[5], longitudes[-1], "sin cambios no se escribe nada")

    def test_t_alterna_el_tema_y_lo_guarda(self):
        _codigo, texto = self.correr("t", "T", "t", "q")
        self.assertEqual(self.guardado()["theme"], "claro")
        self.assertIn("Tema claro guardado: vale también para la ventana", texto)
        salida = self.salida.getvalue()
        self.assertRegex(salida, r"\x1b\[1;38;2;138;81;0(;48;2;220;224;232)?mGrabar", "el acento del tema claro (#8a5100)")
        self.assertIn("48;2;239;241;245m", salida, "sobre el fondo propio del tema claro (#eff1f5)")

    def test_con_config_ilegible_el_tema_no_se_guarda(self):
        self.ruta.write_bytes(b"{ roto")
        _codigo, texto = self.correr("t", "q")
        self.assertEqual(self.ruta.read_bytes(), b"{ roto")
        self.assertIn("⚠ No se pudo leer «config.json»", texto)
        self.assertIn("Tema cambiado solo en esta terminal", texto)


class TestOpciones(BaseTerminal):
    def test_cambia_una_lista_y_guarda_como_daily_config(self):
        antes = AppConfig.from_dict(self.guardado())
        codigo, texto = self.correr("2", self.opciones_listas, ARRIBA, DERECHA, "g", ENTER, ESC, "q")
        self.assertEqual(codigo, 0)
        self.assertIn("Inicio › Opciones", texto)
        self.assertRegex(texto, r"▶ +Tema {5,}‹ Claro ›")
        self.assertIn("● cambios sin guardar", texto, "la marca junto a la ruta")
        self.assertIn("Inicio › Opciones › Guardar", texto, "la confirmación es una subpantalla")
        self.assertIn("Se guardará en config.json:", texto)
        self.assertRegex(texto, r"Tema +Oscuro +→ +Claro")
        self.assertIn("Guardado en", texto)
        esperado = configurar.aplicado(antes, configurar.settings_form(antes, ENTORNO.screens), ENTORNO.screens)
        esperado.theme = "claro"
        self.assertEqual(self.guardado(), esperado.to_dict(), "lo mismo que guardaría daily config")
        self.assertEqual(self.ejecutados, [], "Opciones es una pantalla, no el asistente")

    def test_enter_edita_un_texto(self):
        carpeta = str(self.notas)
        guion = ["2", self.opciones_listas, ENTER] + [RETROCESO] * len("notas") + list("NotasQ?") + [ENTER, "g", ENTER, "q", "q"]
        _codigo, texto = self.correr(*guion, ancho=160)
        self.assertIn(ayuda.linea("opciones_editar")[:50], texto)
        self.assertIn(carpeta[:-len("notas")] + "NotasQ?▌", texto, "se teclea tal cual: q y ? no salen ni abren la ayuda")
        self.assertEqual(self.guardado()["notes_dir"], carpeta[:-len("notas")] + "NotasQ?")

    def test_hilos_no_numericos_no_se_aceptan(self):
        guion = ["2", self.opciones_listas] + ["j"] * 9 + [ENTER, RETROCESO, "x", ENTER, ESC, "q", "q"]
        _codigo, texto = self.correr(*guion)
        self.assertIn("⚠ Hilos de CPU: Escribe un número entre 0 y 256.", texto)
        self.assertEqual(self.guardado()["cpu_threads"], 0)

    def test_avisa_de_cambios_sin_guardar_y_el_segundo_esc_los_descarta(self):
        guardado = self.ruta.read_bytes()
        _codigo, texto = self.correr("2", self.opciones_listas, *["j"] * MIC, DERECHA, ESC, ESC, "q")
        self.assertIn("⚠ Hay cambios sin guardar", texto)
        self.assertEqual(self.ruta.read_bytes(), guardado)

    def test_el_aviso_vuelve_si_se_sigue_editando(self):
        guardado = self.ruta.read_bytes()
        guion = ["2", self.opciones_listas, *["j"] * MIC, DERECHA, ESC, "j", DERECHA, ESC, ESC, "q"]
        _codigo, texto = self.correr(*guion)
        self.assertEqual(texto.count("⚠ Hay cambios sin guardar"), 2, "avisa otra vez tras volver a editar")
        self.assertRegex(texto[texto.rindex("⚠ Hay cambios sin guardar"):], r"\n Inicio +\n", "y el Esc siguiente sí sale")
        self.assertEqual(self.ruta.read_bytes(), guardado)

    def test_usar_la_recomendada(self):
        _codigo, texto = self.correr("2", self.opciones_listas, ARRIBA, ARRIBA, ENTER, "g", ENTER, "q", "q")
        self.assertIn("Recomendado para este equipo:", texto)
        self.assertEqual(self.guardado()["cpu_threads"], 5, "i5-9500: Media con 5 hilos")

    def test_con_config_ilegible_no_se_guarda(self):
        self.ruta.write_bytes(b"{ roto")
        _codigo, texto = self.correr("2", self.opciones_listas, ARRIBA, ARRIBA, DERECHA, "g", ESC, ESC, "q")
        self.assertIn("⚠ No se guarda: No se pudo leer", texto)
        self.assertEqual(self.ruta.read_bytes(), b"{ roto")

    def test_spinner_mientras_detecta(self):
        listo = []

        def detectar():
            while not listo:
                time.sleep(0.001)
            return ENTORNO

        t = self.terminal("2", *[None] * 5, lambda: listo.append(1) or True, self.opciones_listas, "q", "q")
        t._detectar = detectar
        self.assertEqual(t.run(), 0)
        texto = limpio(self.salida.getvalue())
        self.assertIn("Detectando dispositivos, pantallas y equipo…", texto)
        self.assertIn("Carpeta de notas", texto)


class TestRendimiento(BaseTerminal):
    def test_barras_tendencia_y_motor_que_se_usaria(self):
        _codigo, texto = self.correr("7", *[None] * 90, ESC, "q")
        self.assertIn("No hay ninguna grabación en curso", texto)
        self.assertIn("Motor que se usaría: faster-whisper · CPU, 4 hilos · small · haz 5", texto)
        self.assertRegex(texto, r"CPU del equipo  █+░+  50 %  ▅▅")
        self.assertIn("GPU del equipo  ░", texto)
        self.assertIn("n/d", texto)
        self.assertTrue(self.muestreo.parado, "al volver se para el muestreo")

    def test_spinner_hasta_la_primera_muestra(self):
        self.muestreo = MuestreoFalso()
        _codigo, texto = self.correr("7", None, None, ESC, "q")
        self.assertIn("midiendo…", texto)


class TestTerminal(BaseTerminal):
    def test_ascii_y_60_columnas(self):
        guion = ["8", "j", ESC, "7", *[None] * 50, ESC, "2", self.opciones_listas, ARRIBA, ENTER, ESC, "q", "q"]
        _codigo, _texto = self.correr(*guion, ancho=60, ascii_mode=True)
        texto = limpio(self.salida.getvalue().replace("\x1b[H", "\n"))  # cada cuadro empieza arriba del todo
        self.assertTrue(solo_ascii(texto), [c for c in texto if ord(c) >= 0x2000 and c not in "–—·"][:10])
        self.assertIn("> 1  Grabar", texto)
        self.assertIn("[Enter] Abrir · [Esc] Salir · [?] Ayuda · [t] Tema", texto)
        self.assertIn("Inicio > Ayuda", texto)
        largas = [l for l in texto.split("\n") if cell_len(l) > 60]
        self.assertFalse(largas, largas[:3])

    def test_pantalla_alternativa_y_se_restaura_con_ctrl_c(self):
        def interrumpir():
            raise KeyboardInterrupt

        estado = []

        @contextlib.contextmanager
        def teclado():
            estado.append("preparada")
            try:
                yield interrumpir
            finally:
                estado.append("restaurada")

        t = self.terminal()
        t._leer_tecla = None
        with mock.patch("recorder.cli.teclas.teclado", teclado):
            self.assertEqual(t.run(), 0)
        self.assertEqual(estado, ["preparada", "restaurada"])
        salida = self.salida.getvalue()
        self.assertIn("\x1b[?1049h", salida)
        self.assertTrue(salida.rstrip().endswith("\x1b[?1049l") or "\x1b[?1049l" in salida[-40:], "se sale de la pantalla alternativa")


class TestSinTerminal(BaseTerminal):
    def test_con_la_entrada_redirigida_sigue_el_menu_numerado(self):
        consola = make_console(ascii_mode=False, file=io.StringIO(), width=120)
        with mock.patch("sys.stdin", io.StringIO("0\n")):  # input() lee de ahí cuando no es la consola
            self.assertEqual(menu(consola, comandos=self.comandos, mgr=self.mgr), 0)
        self.assertIn("Opción: ", consola.file.getvalue())

    def test_menu_elige_las_pantallas_en_una_terminal(self):
        consola = make_console(file=io.StringIO(), force_terminal=True)
        with mock.patch.object(pantallas.Terminal, "run", return_value=7) as run, \
                mock.patch("sys.stdin", SimpleNamespace(isatty=lambda: True)):
            self.assertEqual(menu(consola, comandos=self.comandos, mgr=self.mgr), 7)
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
