"""La introducción: el contrato, el guion, cuándo sale, la ventana y el logotipo de la terminal.

Sin Tk: que los assets cumplan el contrato y que sin ellos se omita, la tabla de cuándo se muestra,
`intro_seen` en config.json (también el anterior a este campo), el guion en instantes clave (con
«completas» y con «reducidas») y el logotipo de terminal en sus tres juegos, con tecla que lo salta,
con movimiento reducido y con la salida redirigida. Con Tk (se omiten sin pantalla): la ventana salta
con Esc, Enter, Espacio, clic y el botón, acaba sola al terminar el guion y avisa una sola vez; la
ventana principal no se ve hasta que acaba; «intro_seen» se guarda; sin fotogramas o con «ninguna» no
sale; «Más» → «Ver introducción» y `--sin-intro`.
"""

import io
import json
import pathlib
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from recorder import ayuda, intro
from recorder.cli import app
from recorder.cli import intro as intro_terminal
from recorder.cli.consola import JUEGO_ASCII, JUEGO_COMPLETO, JUEGO_CONSOLA, make_console
from recorder.config.manager import ConfigManager
from recorder.config.schema import AppConfig
from recorder.paleta import TEMAS
from recorder.ui import animacion, theme
from recorder.ui.intro import TECLAS_SALTO, Introduccion
from tests.test_main_window import BaseVentana

CONTRATO = intro.cargar_contrato()
CORTO = 120  # animacion.CORTO_MS


def guion(reducido=False):
    return intro.Guion(CONTRATO, reducido, CORTO)


class TestAssets(unittest.TestCase):
    def test_el_contrato_se_carga_y_cada_clave_de_texto_existe(self):
        self.assertIsNotNone(CONTRATO, "faltan los fotogramas de recorder/assets/intro")
        claves = {p["texto"] for e in CONTRATO["escenas"] for p in e["pasos"] if "texto" in p}
        claves |= {CONTRATO["boton"][b]["rotulo"] for b in ("secundario", "principal")}
        claves |= {"intro.nombre", "intro.pista", "intro.terminal.lema"}
        for clave in claves:
            self.assertTrue(ayuda.texto_intro(clave).strip(), clave)
        with self.assertRaises(KeyError):
            ayuda.texto_intro("intro.no_existe")

    def test_los_colores_del_contrato_son_tokens_de_la_paleta(self):
        usados = {CONTRATO["lienzo"]["color"], CONTRATO["boton"]["anillo_foco"]}
        for b in CONTRATO["boton"].values():
            if isinstance(b, dict):
                usados |= {b["fondo"], b["texto"], b["borde"]}
        for tema in TEMAS.values():
            self.assertTrue(usados <= set(tema), usados - set(tema))

    def test_sin_assets_se_omite_sin_error(self):
        with tempfile.TemporaryDirectory() as vacio, patch.object(intro, "carpeta_assets", return_value=pathlib.Path(vacio)):
            self.assertIsNone(intro.cargar_contrato())

    def test_un_fotograma_que_falta_basta_para_omitirla(self):
        with tempfile.TemporaryDirectory() as tmp:
            copia = pathlib.Path(tmp)
            origen = intro.carpeta_assets()
            (copia / "logo").mkdir()
            for archivo in origen.rglob("*"):
                if archivo.is_file():
                    destino = copia / archivo.relative_to(origen)
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    destino.write_bytes(archivo.read_bytes())
            with patch.object(intro, "carpeta_assets", return_value=copia):
                self.assertIsNotNone(intro.cargar_contrato())
                (copia / "logo" / CONTRATO["logotipo"]["patron"].format(n=7).split("/")[-1]).unlink()
                self.assertIsNone(intro.cargar_contrato())

    def test_contrato_ilegible_se_omite(self):
        with tempfile.TemporaryDirectory() as tmp:
            (pathlib.Path(tmp) / intro.ARCHIVO_CONTRATO).write_text("{no es json", encoding="utf-8")
            with patch.object(intro, "carpeta_assets", return_value=pathlib.Path(tmp)):
                self.assertIsNone(intro.cargar_contrato())


class TestCuandoSale(unittest.TestCase):
    def test_tabla(self):
        c, r, n = intro.COMPLETAS, intro.REDUCIDAS, intro.NINGUNA
        self.assertTrue(intro.debe_mostrarse(c, vista=False))
        self.assertTrue(intro.debe_mostrarse(r, vista=False))
        self.assertFalse(intro.debe_mostrarse(c, vista=True), "ya vista: no se repite")
        self.assertTrue(intro.debe_mostrarse(c, vista=True, bajo_demanda=True), "«Ver introducción»")
        self.assertFalse(intro.debe_mostrarse(c, vista=False, sin_intro=True), "--sin-intro")
        self.assertFalse(intro.debe_mostrarse(n, vista=False), "«ninguna»: sin intro animada")
        self.assertFalse(intro.debe_mostrarse(n, vista=True, bajo_demanda=True))

    def test_config_anterior_a_la_introduccion_carga_como_no_vista(self):
        antiguo = {k: v for k, v in AppConfig().to_dict().items() if not k.startswith("intro_")}
        cfg = AppConfig.from_dict(antiguo)
        self.assertEqual((cfg.intro_seen, cfg.intro_terminal_seen), (False, False))
        self.assertIs(AppConfig.from_dict({"intro_seen": "si"}).intro_seen, False, "solo un true de verdad cuenta")
        self.assertIs(AppConfig.from_dict({"intro_seen": True}).intro_seen, True)

    def test_marcar_vista_se_guarda_y_conserva_lo_demas(self):
        with tempfile.TemporaryDirectory() as tmp:
            gestor = ConfigManager(pathlib.Path(tmp) / "config.json")
            gestor.save(AppConfig(model="base"))
            config = gestor.load()
            intro.marcar_vista(gestor, config)
            guardado = json.loads(gestor.path.read_text(encoding="utf-8"))
            self.assertEqual((guardado["intro_seen"], guardado["intro_terminal_seen"], guardado["model"]), (True, False, "base"))
            self.assertTrue(ConfigManager(gestor.path).load().intro_seen, "persistido")
            intro.marcar_vista(gestor, config, "intro_terminal_seen")
            self.assertTrue(ConfigManager(gestor.path).load().intro_terminal_seen)

    def test_marcar_vista_no_crea_config_ni_pisa_una_ilegible(self):
        with tempfile.TemporaryDirectory() as tmp:
            sin = ConfigManager(pathlib.Path(tmp) / "config.json")
            config = sin.load()
            intro.marcar_vista(sin, config)
            self.assertTrue(config.intro_seen, "vale en memoria: la recomendación del primer arranque la guardará")
            self.assertFalse(sin.path.exists(), "crearlo le quitaría al primer arranque su recomendación")
            roto = ConfigManager(pathlib.Path(tmp) / "roto.json")
            roto.path.write_text("{no es json", encoding="utf-8")
            config = roto.load()
            intro.marcar_vista(roto, config)
            self.assertEqual(roto.path.read_text(encoding="utf-8"), "{no es json")


class TestGuion(unittest.TestCase):
    def test_arranca_con_el_logotipo_y_nada_mas(self):
        e = guion().estado(0)
        self.assertEqual((e.logo, e.titulo[0], e.rotulo, e.equipo, e.captura, e.boton, e.trazos), (1, None, 0, 0, 0, 0, ()))
        self.assertEqual(e.logo_centro, tuple(CONTRATO["logotipo"]["centro_inicial"]))

    def test_los_fotogramas_siguen_el_ritmo_y_se_quedan_en_el_ultimo(self):
        logo = CONTRATO["logotipo"]
        self.assertEqual(guion().estado(1000 / logo["fps"] * 5).logo, 6)
        self.assertEqual(guion().estado(5000).logo, logo["fotogramas"])

    def test_cada_escena_dice_su_titulo(self):
        g = guion()
        for escena, instante in (("graba", 2400), ("transcribe", 3900), ("notas", 5400), ("comenzar", 7000)):
            self.assertEqual(g.estado(instante).titulo, (f"intro.{escena}.titulo", 1.0), escena)
            self.assertEqual(g.estado(instante).subtitulo[0], f"intro.{escena}.subtitulo")

    def test_nunca_hay_dos_textos_a_la_vez_y_el_cambio_pasa_por_cero(self):
        g = guion()
        cambio = next(e for e in CONTRATO["escenas"] if e["id"] == "transcribe")["inicio_ms"]
        clave, opacidad = g.estado(cambio + CONTRATO["duraciones_ms"]["cruce_escena"] / 2).titulo
        self.assertEqual(clave, "intro.graba.titulo", "aún el anterior, yéndose")
        self.assertTrue(0 < opacidad < 1)
        self.assertEqual(g.estado(cambio + CONTRATO["duraciones_ms"]["cruce_escena"]).titulo[1], 0.0)

    def test_el_boton_pasa_de_saltar_a_comenzar(self):
        self.assertEqual(guion().estado(1000).boton, 0)
        self.assertEqual(guion().estado(7000).boton, 1)

    def test_la_ilustracion_acaba_en_la_nota(self):
        ilu = CONTRATO["ilustracion"]
        e = guion().estado(guion().total_ms)
        self.assertEqual(len(e.trazos), len(ilu["lineas"]["trazos"]))
        for trazo, (x, y, ancho) in zip(e.trazos, ilu["nota"]["trazos"]):
            self.assertEqual((round(trazo.x, 6), round(trazo.y, 6), round(trazo.ancho, 6)), (x, y, ancho))
            self.assertEqual((trazo.alto, trazo.en_nota, trazo.opacidad), (ilu["grosor_trazo"], 1.0, 1.0))
        self.assertEqual((e.equipo, e.base, e.captura), (1.0, 0.0, 1.0), "la base se va y la captura entra")

    def test_las_barras_laten_mientras_son_barras(self):
        altos = {round(guion().estado(t).trazos[3].alto, 3) for t in range(2100, 2500, 50)}
        self.assertGreater(len(altos), 3)

    def test_el_guion_es_funcion_del_reloj(self):
        self.assertEqual(guion().estado(4321.0), guion().estado(4321.0), "un tic tardío salta adelante, sin estado oculto")


class TestGuionReducido(unittest.TestCase):
    def test_logotipo_estatico_en_su_sitio_y_sin_rotulo(self):
        g = guion(True)
        for t in (0, 1000, 4000, 7000):
            e = g.estado(t)
            self.assertEqual((e.logo, e.logo_centro, e.rotulo), (0, tuple(CONTRATO["logotipo"]["centro_final"]), 0), t)

    def test_cada_fundido_dura_el_techo_como_mucho(self):
        g = guion(True)
        self.assertTrue(all(g.duracion(n) <= CORTO for n in CONTRATO["duraciones_ms"]))
        inicio = next(e for e in CONTRATO["escenas"] if e["id"] == "transcribe")["inicio_ms"]
        self.assertEqual(g.estado(inicio + 250 + CORTO).equipo, 1.0, "el equipo ya está entero tras CORTO_MS")

    def test_barras_quietas_a_media_altura(self):
        altos = {round(guion(True).estado(t).trazos[3].alto, 6) for t in range(2100, 2500, 50)}
        self.assertEqual(len(altos), 1)

    def test_sin_escalonado_y_sin_recorrido_cada_trazo_cambia_de_forma_a_la_vez(self):
        g = guion(True)
        conv = g.paso("graba", "onda", "convertir_en_lineas")["t0"]
        antes, despues = g.estado(conv - 1).trazos, g.estado(conv + CORTO).trazos
        self.assertTrue(all(a.ancho == CONTRATO["ilustracion"]["onda"]["ancho"] for a in antes))
        self.assertEqual([round(t.ancho) for t in despues], [t[2] for t in CONTRATO["ilustracion"]["lineas"]["trazos"]])

    def test_el_final_es_el_mismo_que_con_completas(self):
        completas, reducidas = guion().estado(7400), guion(True).estado(7400)
        self.assertEqual((completas.titulo, completas.boton, completas.captura), (reducidas.titulo, reducidas.boton, reducidas.captura))
        self.assertEqual(completas.trazos, reducidas.trazos)


# ---------------------------------------------------------------------------------- terminal
def consola_de(juego, **kwargs):
    salida = io.StringIO()
    consola = make_console(ascii_mode=juego == JUEGO_ASCII, file=salida, force_terminal=kwargs.pop("terminal", True),
                           color_system="truecolor", width=100, **kwargs)
    consola.juego = juego
    return consola, salida


class TestLogoTerminal(unittest.TestCase):
    def test_cada_juego_cabe_en_60_columnas_y_usa_solo_sus_simbolos(self):
        permitidos = {JUEGO_COMPLETO: "█▄▀●", JUEGO_CONSOLA: "█─●", JUEGO_ASCII: ""}
        for juego in (JUEGO_COMPLETO, JUEGO_CONSOLA, JUEGO_ASCII):
            lineas = intro.lineas_logo_terminal(CONTRATO, juego)
            sin_marcas = [__import__("re").sub(r"\[/?\w*\]", "", linea) for linea in lineas]
            with self.subTest(juego=juego):
                self.assertLessEqual(max(len(linea) for linea in sin_marcas), 60)
                fuera = {ch for linea in sin_marcas for ch in linea if ord(ch) > 127} - set(permitidos[juego])
                self.assertEqual(fuera, set())
                self.assertIn(ayuda.texto_intro("intro.terminal.lema"), "\n".join(sin_marcas))

    def test_sin_archivo_del_juego_no_hay_logotipo(self):
        self.assertIsNone(intro.lineas_logo_terminal({"terminal": {"juegos": {}}}, JUEGO_ASCII))

    def test_con_movimiento_reducido_o_sin_cursor_se_imprime_una_sola_vez_el_ultimo_paso(self):
        for animaciones, terminal in ((intro.REDUCIDAS, True), (intro.COMPLETAS, False)):
            consola, salida = consola_de(JUEGO_COMPLETO, terminal=terminal)
            with self.subTest(animaciones=animaciones, terminal=terminal):
                self.assertTrue(intro_terminal.mostrar_logo(consola, animaciones))
                texto = salida.getvalue()
                self.assertEqual(texto.count("Recorder"), 1)
                self.assertNotIn("\x1b[9A", texto)
                self.assertIn(ayuda.texto_intro("intro.terminal.lema"), texto)

    def test_en_ascii_no_queda_ningun_caracter_fuera_de_ascii(self):
        consola, salida = consola_de(JUEGO_ASCII, terminal=False)
        intro_terminal.mostrar_logo(consola, intro.COMPLETAS)
        self.assertTrue(salida.getvalue().isascii())

    def correr(self, leer_tecla, juego=JUEGO_COMPLETO):
        """El logotipo animado con un reloj de mentira: cada espera adelanta 20 ms."""
        consola, salida = consola_de(juego)
        ahora = [0.0]
        with patch.object(intro_terminal, "hay_cursor", return_value=True):
            intro_terminal.mostrar_logo(
                consola, intro.COMPLETAS, leer_tecla=lambda: leer_tecla(ahora[0]),
                reloj=lambda: ahora[0], esperar=lambda s: ahora.__setitem__(0, ahora[0] + s))
        return salida.getvalue(), ahora[0]

    def test_son_tres_repintados_en_el_mismo_sitio_y_dura_lo_del_contrato(self):
        texto, duracion = self.correr(lambda t: None)
        alto = len(intro.lineas_logo_terminal(CONTRATO, JUEGO_COMPLETO))
        self.assertEqual(texto.count(f"\x1b[{alto}A"), len(CONTRATO["terminal"]["pasos"]) - 1)
        self.assertEqual(texto.count("Recorder"), 2, "oculto en el primer paso; visible en los otros dos")
        self.assertAlmostEqual(duracion, CONTRATO["terminal"]["duracion_ms"] / 1000, delta=0.03)
        self.assertLessEqual(duracion, 1.0, "como mucho un segundo")

    def test_cualquier_tecla_lo_salta_y_deja_el_ultimo_paso(self):
        texto, duracion = self.correr(lambda t: "x" if t >= 0.1 else None)
        self.assertLess(duracion, 0.3)
        self.assertEqual(texto.rstrip().splitlines()[-1].count("-"), 0)
        self.assertIn("Recorder", texto.rsplit("\x1b[9A", 1)[-1], "el que queda impreso es el último paso")
        texto, duracion = self.correr(lambda t: "x")
        self.assertEqual(duracion, 0.0, "tecla desde el principio: el último paso directamente")
        self.assertNotIn("\x1b[9A", texto)
        self.assertIn("Recorder", texto)

    def test_el_color_de_cada_papel_sale_del_tema_de_la_consola(self):
        consola, salida = consola_de(JUEGO_CONSOLA)
        intro_terminal.mostrar_logo(consola, intro.REDUCIDAS)
        tema = TEMAS["oscuro"]
        for token in ("acento", "mic", "error", "texto_tenue"):
            rgb = ";".join(str(int(tema[token][i:i + 2], 16)) for i in (1, 3, 5))
            self.assertIn(f"38;2;{rgb}", salida.getvalue(), token)

    def test_sin_assets_no_hay_logotipo_ni_error(self):
        consola, salida = consola_de(JUEGO_COMPLETO)
        with tempfile.TemporaryDirectory() as vacio, patch.object(intro, "carpeta_assets", return_value=pathlib.Path(vacio)):
            self.assertFalse(intro_terminal.mostrar_logo(consola, intro.COMPLETAS))
        self.assertEqual(salida.getvalue(), "")


class TestPrimerDaily(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.gestor = ConfigManager(pathlib.Path(self.tmp.name) / "config.json")
        self.gestor.save(AppConfig(animations=intro.REDUCIDAS))

    def test_sale_la_primera_vez_y_no_la_segunda(self):
        consola, salida = consola_de(JUEGO_COMPLETO)
        self.assertTrue(intro_terminal.primer_daily(consola, self.gestor))
        self.assertIn("Recorder", salida.getvalue())
        self.assertTrue(ConfigManager(self.gestor.path).load().intro_terminal_seen)
        self.assertFalse(ConfigManager(self.gestor.path).load().intro_seen, "la de la ventana es otra")
        consola, salida = consola_de(JUEGO_COMPLETO)
        self.assertFalse(intro_terminal.primer_daily(consola, self.gestor))
        self.assertEqual(salida.getvalue(), "")

    def test_con_la_salida_redirigida_no_sale_ni_se_marca(self):
        consola, salida = consola_de(JUEGO_COMPLETO, terminal=False)
        self.assertFalse(intro_terminal.primer_daily(consola, self.gestor))
        self.assertFalse(ConfigManager(self.gestor.path).load().intro_terminal_seen)

    def test_animaciones_ninguna_no_la_muestra(self):
        self.gestor.save(AppConfig(animations=intro.NINGUNA))
        consola, salida = consola_de(JUEGO_COMPLETO)
        self.assertFalse(intro_terminal.primer_daily(consola, self.gestor))
        self.assertEqual(salida.getvalue(), "")


class TestSinIntroEnLaTerminal(unittest.TestCase):
    def setUp(self):
        patch.object(app, "abrir_ventana", return_value=0).start()
        self.grabar = patch("recorder.cli.live.grabar", return_value=0).start()
        self.primer = patch("recorder.cli.intro.primer_daily", return_value=False).start()
        self.addCleanup(patch.stopall)

    def test_daily_muestra_el_logotipo_y_sin_intro_lo_omite(self):
        app.main([])
        self.primer.assert_called_once()
        self.primer.reset_mock()
        app.main(["--sin-intro"])
        self.primer.assert_not_called()
        self.grabar.assert_called()

    def test_la_opcion_llega_a_la_ventana(self):
        app.main(["--gui", "--sin-intro"])
        app.abrir_ventana.assert_called_with(True)
        app.main(["ventana"])
        app.abrir_ventana.assert_called_with(False)


class TestOpcionEnRecorderExe(unittest.TestCase):
    """Recorder.exe no pasa por argparse: abrir_ventana lee `--sin-intro` de la línea de órdenes."""

    def abrir(self, argv):
        from recorder.ui import main_window

        with patch.object(main_window, "MainWindow") as ventana, patch("sys.argv", argv):
            app.abrir_ventana()
        return ventana.call_args.kwargs["con_intro"]

    def test_lee_la_opcion(self):
        self.assertFalse(self.abrir(["Recorder.exe", "--sin-intro"]))
        self.assertTrue(self.abrir(["Recorder.exe"]))

# ---------------------------------------------------------------------------------- ventana
class ReinoDeTk(unittest.TestCase):
    """Una raíz oculta, la paleta oscura y «completas», que se restauran al acabar."""

    animaciones = intro.COMPLETAS

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"sin Tk: {e}")
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        theme.aplicar_tema(self.root, "oscuro")
        self.addCleanup(setattr, animacion, "modo", animacion.modo)
        animacion.modo = self.animaciones

    def bombear(self, condicion, limite=5.0):
        fin = time.time() + limite
        while not condicion() and time.time() < fin:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(condicion(), "no llegó lo esperado")


class TestVentanaDeLaIntroduccion(ReinoDeTk):
    def abrir(self):
        """La ventana con un reloj de mentira (`self.ahora`, en s) y avisos contados en `self.fin`."""
        self.ahora, self.fin = [0.0], []
        i = Introduccion(self.root, CONTRATO, self.animaciones, lambda: self.fin.append(1), reloj=lambda: self.ahora[0])
        self.addCleanup(lambda: i.win.winfo_exists() and i.win.destroy())
        i.mostrar()
        self.bombear(lambda: i.inicio is not None)  # tras el fundido de entrada arranca el guion
        return i

    def test_es_una_ventana_sin_bordes_centrada_en_el_area_util(self):
        i = self.abrir()
        self.assertTrue(i.win.overrideredirect())
        l, t, r, b = theme.work_area(self.root)
        self.assertEqual(i.win.winfo_width(), round(CONTRATO["lienzo"]["ancho"] * i.k))
        self.assertAlmostEqual(i.win.winfo_x() + i.win.winfo_width() / 2, (l + r) / 2, delta=2)

    def test_pinta_el_instante_del_reloj_y_saltar_y_boton_estan_desde_el_primer_fotograma(self):
        i = self.abrir()
        textos = {i.canvas.itemcget(n, "text") for n in i.canvas.find_all() if i.canvas.type(n) == "text"}
        self.assertIn(ayuda.texto_intro("intro.pista"), textos)
        self.assertIn(ayuda.texto_intro("intro.saltar"), textos)
        self.ahora[0] = 2.4
        i._tic()
        self.assertEqual(i.canvas.itemcget(i._titulo, "text"), ayuda.texto_intro("intro.graba.titulo"))
        self.ahora[0] = 7.0
        i._tic()
        self.assertEqual(i.canvas.itemcget(i._boton_texto, "text"), ayuda.texto_intro("intro.comenzar"))
        self.assertEqual(i.canvas.itemcget(i._boton, "fill"), TEMAS["oscuro"][CONTRATO["boton"]["principal"]["fondo"]])

    def test_acaba_sola_al_terminar_el_guion_y_avisa_una_vez(self):
        i = self.abrir()
        self.ahora[0] = CONTRATO["duraciones_ms"]["total"] / 1000 + 0.01
        i._tic()
        self.bombear(lambda: i.terminada)
        self.assertEqual(self.fin, [1])
        self.assertFalse(i.win.winfo_exists())
        i.saltar()
        self.assertEqual(self.fin, [1], "no vuelve a avisar")

    def test_saltar_a_mitad_cancela_lo_pendiente(self):
        i = self.abrir()
        self.ahora[0] = 3.0
        i._tic()
        pendiente = i._tic_id
        i.saltar()
        self.bombear(lambda: i.terminada)
        self.assertEqual(self.fin, [1])
        self.assertTrue(pendiente is not None and i._cerrando)
        self.assertEqual(round(i.medida_ms), 3000)

    def disparar(self, evento):
        i = self.abrir()
        i.win.focus_force()
        self.root.update()
        if self.root.focus_get() is None:
            self.skipTest("Windows no dio el foco a la ventana de prueba")
        evento(i)
        self.bombear(lambda: i.terminada)
        self.assertEqual(self.fin, [1])

    def test_salta_con_cada_tecla(self):
        for tecla in (t for t in TECLAS_SALTO if t != "<KP_Enter>"):  # Tk no genera el del teclado numérico
            with self.subTest(tecla=tecla):
                self.disparar(lambda i: i.win.event_generate(tecla, when="now"))

    def test_salta_con_un_clic_en_cualquier_parte_y_con_el_boton(self):
        for x, y in ((10, 10), (600, 150), (680, 363)):  # esquina, ilustración y botón
            with self.subTest(x=x, y=y):
                self.disparar(lambda i: i.canvas.event_generate("<Button-1>", x=x, y=y, when="now"))

    def test_cerrar_la_ventana_tambien_salta(self):
        self.disparar(lambda i: i.win.tk.call(i.win.protocol("WM_DELETE_WINDOW")))

    def test_el_anillo_de_foco_usa_el_token_del_contrato(self):
        i = self.abrir()
        self.assertEqual(i.canvas.itemcget(i._anillo, "outline"), TEMAS["oscuro"][CONTRATO["boton"]["anillo_foco"]])


class TestVentanaReducida(TestVentanaDeLaIntroduccion):
    animaciones = intro.REDUCIDAS

    def test_solo_carga_el_logotipo_estatico(self):
        i = self.abrir()
        self.assertEqual(list(i._fotos), [0])
        self.assertEqual(i.canvas.coords(i._logo), [round(v * i.k) for v in CONTRATO["logotipo"]["centro_final"]])


class TestEnLaVentanaPrincipal(BaseVentana):
    """La primera vez, el menú «Más» y los casos en que no sale."""

    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, animacion, "modo", animacion.modo)
        animacion.modo = intro.COMPLETAS
        self.win._con_intro = True
        self.win.poll = lambda: None  # al volver a verse, <Map> reanudaría el sondeo de la sesión de mentira
    def esperar(self, condicion, limite=5.0):
        fin = time.time() + limite
        while not condicion() and time.time() < fin:
            self.root.update()
            time.sleep(0.01)
        self.assertTrue(condicion(), "no llegó lo esperado")

    def test_la_primera_vez_retira_la_ventana_y_no_se_ve_hasta_que_acaba(self):
        self.assertTrue(self.win._intro_primera_vez())
        self.assertEqual(self.root.state(), "withdrawn")
        self.assertIsNotNone(self.win._intro)
        self.esperar(lambda: self.win._intro.inicio is not None)
        self.win._intro.saltar()
        self.esperar(lambda: self.win._intro is None)
        self.assertEqual(self.root.state(), "normal", "al acabar sale la ventana principal")

    def test_intro_seen_se_guarda_y_la_segunda_vez_no_sale(self):
        self.assertFalse(json.loads(self.ruta.read_text(encoding="utf-8"))["intro_seen"])
        self.assertTrue(self.win._intro_primera_vez())
        self.assertTrue(json.loads(self.ruta.read_text(encoding="utf-8"))["intro_seen"], "persistido en config.json")
        self.win._intro.win.destroy()
        self.win._intro = None
        self.assertFalse(self.win._intro_primera_vez())
        self.assertIsNone(self.win._intro)

    def test_sin_fotogramas_se_omite_sin_error_y_la_ventana_se_ve(self):
        with tempfile.TemporaryDirectory() as vacio, patch.object(intro, "carpeta_assets", return_value=pathlib.Path(vacio)):
            self.assertFalse(self.win._intro_primera_vez())
        self.assertIsNone(self.win._intro)
        self.assertNotEqual(self.root.state(), "withdrawn")
        self.assertFalse(self.session.config.intro_seen, "no se vio: no se marca")

    def test_con_animaciones_ninguna_no_sale_y_no_se_marca(self):
        animacion.modo = self.session.config.animations = intro.NINGUNA
        self.assertFalse(self.win._intro_primera_vez())
        self.assertFalse(self.session.config.intro_seen)

    def test_una_falla_al_abrirla_no_impide_arrancar(self):
        with patch("recorder.ui.main_window.Introduccion", side_effect=RuntimeError("falla")):
            self.assertFalse(self.win._intro_primera_vez())
        self.assertNotEqual(self.root.state(), "withdrawn")

    def test_ver_introduccion_esta_en_mas_y_sale_aunque_ya_se_viera(self):
        self.session.config.intro_seen = True
        etiquetas = [self.win.menu_mas.entrycget(i, "label") for i in range(self.win.menu_mas.index("end") + 1)
                     if self.win.menu_mas.type(i) == "command"]
        self.assertIn(f"🎬 {ayuda.texto_intro('intro.ver')}", etiquetas)
        self.root.deiconify()
        self.win.ver_introduccion()
        self.assertIsNotNone(self.win._intro)
        self.win._intro.win.destroy()
        self.win._intro = None

    def test_ver_introduccion_con_ninguna_avisa(self):
        animacion.modo = intro.NINGUNA
        self.root.deiconify()
        self.win.ver_introduccion()
        self.assertIsNone(self.win._intro)
        self.assertIsNotNone(self.win._toast, ayuda.texto_intro("intro.sin_animaciones"))

    def test_sin_fotogramas_la_entrada_del_menu_queda_deshabilitada(self):
        with tempfile.TemporaryDirectory() as vacio, patch.object(intro, "carpeta_assets", return_value=pathlib.Path(vacio)):
            self.win._build_menu()
        entrada = next(i for i in range(self.win.menu_mas.index("end") + 1)
                       if self.win.menu_mas.type(i) == "command" and "intro" in self.win.menu_mas.entrycget(i, "label").lower())
        self.assertEqual(self.win.menu_mas.entrycget(entrada, "state"), "disabled")


if __name__ == "__main__":
    unittest.main()
