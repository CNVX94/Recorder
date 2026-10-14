"""La entrada de `daily`: qué frontal se elige y cómo se reparten y cargan los subcomandos.

Sin audio, sin Whisper y sin ventana: la ventana y la grabación se sustituyen por funciones de
mentira, los comandos del contrato por un módulo escrito en un temporal, y `--recomendar` se
comprueba ejecutando recorder.py como script con la recomendación falseada. Nada toca el
config.json real ni las carpetas de notas.
"""

import io
import pathlib
import runpy
import subprocess
import sys
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from recorder.cli import app
from recorder.cli.consola import make_console
from recorder.config.hardware import HardwareProfile
from tests.test_session import PERFIL, ManagerDePrueba

RAIZ = pathlib.Path(__file__).resolve().parent.parent
RECORDER_PY = RAIZ / "recorder.py"

COMANDO_FALSO = textwrap.dedent('''
    """Un comando de mentira que cumple el contrato de recorder/cli/app.py."""
    NOMBRE = "falso"
    AYUDA = "hace de mentira lo que se le pida"
    llamadas = []

    def agregar_argumentos(parser):
        parser.add_argument("--n", type=int, default=1)

    def ejecutar(args, consola):
        llamadas.append((args.n, consola))
        consola.print(f"falso x{args.n}", markup=False)
        return 7
''')


class BaseComandos(unittest.TestCase):
    """Deja módulos de comando en un temporal importable y los retira al acabar."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        sys.path.insert(0, self.tmp.name)
        self.addCleanup(sys.path.remove, self.tmp.name)
        self.escribir("comando_falso_recorder", COMANDO_FALSO)
        self.escribir("comando_sin_dependencia_recorder", "import dependencia_que_no_existe_xyz\nNOMBRE = 'x'\n")
        self.escribir("comando_roto_recorder", "raise RuntimeError('roto')\n")

    def escribir(self, nombre, contenido):
        (pathlib.Path(self.tmp.name) / f"{nombre}.py").write_text(contenido, encoding="utf-8")
        self.addCleanup(sys.modules.pop, nombre, None)

    def consola(self):
        return make_console(ascii_mode=False, file=io.StringIO())


class TestContrato(BaseComandos):
    def test_carga_los_que_existen_y_omite_los_que_faltan(self):
        comandos = app.cargar_comandos(("recorder.cli.no_existe_aun", "comando_falso_recorder", "recorder.cli.recomendar"))
        self.assertEqual(list(comandos), ["falso", "recomendar"], "en el orden de la tupla, por NOMBRE")
        self.assertEqual(comandos["falso"].AYUDA, "hace de mentira lo que se le pida")

    def test_un_modulo_al_que_le_falta_una_dependencia_no_se_calla(self):
        with self.assertRaises(ModuleNotFoundError) as ctx:
            app.cargar_comandos(("comando_sin_dependencia_recorder",))
        self.assertEqual(ctx.exception.name, "dependencia_que_no_existe_xyz")

    def test_un_modulo_roto_no_se_calla(self):
        with self.assertRaises(RuntimeError):
            app.cargar_comandos(("comando_roto_recorder",))

    def test_ejecutar_comando_por_nombre_con_sus_argumentos(self):
        comandos = app.cargar_comandos(("comando_falso_recorder",))
        consola = self.consola()
        self.assertEqual(app.ejecutar_comando("falso", ["--n", "3"], consola, comandos), 7)
        self.assertEqual(comandos["falso"].llamadas, [(3, consola)])
        self.assertEqual(consola.file.getvalue(), "falso x3\n")
        with self.assertRaises(KeyError):
            app.ejecutar_comando("no_cargado", (), consola, comandos)

    def test_el_subcomando_llega_por_argparse_hasta_el_modulo(self):
        consola = self.consola()
        with patch.object(app, "COMANDOS", ("comando_falso_recorder",)), patch.object(app, "make_console", return_value=consola):
            self.assertEqual(app.main(["falso", "--n", "2"]), 7)
            self.assertEqual(sys.modules["comando_falso_recorder"].llamadas[-1], (2, consola))
            ayuda = io.StringIO()
            with patch.object(sys, "stdout", ayuda), self.assertRaises(SystemExit) as ctx:
                app.main(["-h"])
        self.assertEqual(ctx.exception.code, 0)
        for palabra in ("menu", "ventana", "falso", "hace de mentira", "--ascii", "--gui"):
            self.assertIn(palabra, ayuda.getvalue())


class TestEleccionDeFrontal(unittest.TestCase):
    def setUp(self):
        self.ventana = patch.object(app, "abrir_ventana", return_value=0).start()
        self.addCleanup(patch.stopall)
        self.grabar = patch("recorder.cli.live.grabar", return_value=0).start()
        self.menu = patch("recorder.cli.menu.menu", return_value=0).start()

    def test_sin_argumentos_graba_en_la_terminal(self):
        self.assertEqual(app.arrancar([]), 0)
        self.grabar.assert_called_once()
        consola = self.grabar.call_args.kwargs["consola"]
        self.assertIsInstance(consola.ascii_mode, bool, "sin --ascii lo decide la consola (detect_legacy_windows)")
        self.ventana.assert_not_called()

    def test_ascii_se_fuerza_con_la_opcion(self):
        app.main(["--ascii"])
        self.assertTrue(self.grabar.call_args.kwargs["consola"].ascii_mode)

    def test_gui_y_ventana_abren_la_ventana(self):
        self.assertEqual(app.main(["--gui"]), 0)
        self.assertEqual(app.main(["ventana"]), 0)
        self.assertEqual(self.ventana.call_count, 2)
        self.grabar.assert_not_called()

    def test_sin_consola_se_abre_la_ventana_sin_mirar_argumentos(self):
        with patch.object(sys, "stdout", None):
            self.assertEqual(app.arrancar(["menu"]), 0)
        self.ventana.assert_called_once()
        self.menu.assert_not_called()

    def test_menu(self):
        self.assertEqual(app.main(["menu"]), 0)
        self.menu.assert_called_once()
        self.assertIn("recomendar", self.menu.call_args.kwargs["comandos"])


class TestRecorderPy(unittest.TestCase):
    """recorder.py como script: --recomendar sigue igual y la terminal no carga tkinter."""

    def correr(self, *argv):
        # El registro de fallos no se instala en el proceso de las pruebas (cambiaría sys.excepthook)
        with patch.object(sys, "argv", ["recorder.py", *argv]), patch("recorder.registro.instalar") as registro, \
                self.assertRaises(SystemExit) as ctx:
            runpy.run_path(str(RECORDER_PY), run_name="__main__")
        registro.assert_called_once_with()
        return ctx.exception.code

    def test_recomendar_sigue_funcionando_con_y_sin_aplicar(self):
        with patch("recorder.cli.recomendar.recomendar", return_value=3) as rec:
            self.assertEqual(self.correr("--recomendar"), 3)
            self.assertEqual(self.correr("--recomendar", "--aplicar"), 3)
        self.assertEqual([c.args for c in rec.call_args_list], [(False,), (True,)])

    def test_sin_argumentos_entra_por_la_terminal(self):
        with patch("recorder.cli.app.arrancar", return_value=5) as arrancar:
            self.assertEqual(self.correr(), 5)
        arrancar.assert_called_once_with()

    def test_la_terminal_no_carga_tkinter(self):
        # En otro proceso: en este ya lo cargaron las pruebas de la ventana
        guion = textwrap.dedent(f"""
            import runpy, sys
            sys.argv = ["recorder.py", "--help"]
            try:
                runpy.run_path({str(RECORDER_PY)!r}, run_name="__main__")
            except SystemExit as e:
                assert e.code == 0, e.code
            import recorder.cli.live, recorder.cli.menu, recorder.cli.recomendar
            print("tkinter" in sys.modules, "recorder.ui" in sys.modules)
        """)
        res = subprocess.run([sys.executable, "-c", guion], cwd=RAIZ, capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip().splitlines()[-1], "False False", res.stdout)


class TestRecomendar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        raiz = pathlib.Path(self.tmp.name)
        self.mgr = ManagerDePrueba(raiz / "config.json", raiz)
        patch("recorder.config.hardware.detect_hardware", return_value=HardwareProfile(**PERFIL)).start()
        patch("recorder.config.hardware._cache", None).start()  # que otra prueba no deje su perfil
        self.addCleanup(patch.stopall)

    def test_imprime_equipo_y_recomendacion_y_con_aplicar_la_guarda(self):
        from recorder.cli.recomendar import recomendar

        consola = make_console(ascii_mode=False, file=io.StringIO())
        self.assertEqual(recomendar(False, consola, self.mgr), 0)
        salida = consola.file.getvalue()
        self.assertIn("Equipo:      Intel Core i5-9500", salida)
        self.assertIn("Recomendado: Media (small, haz 5, CPU, int8, 5 hilos) [", salida)
        self.assertIn("Motivo:", salida)
        self.assertFalse(self.mgr.path.exists(), "sin --aplicar no se escribe nada")

        self.assertEqual(recomendar(True, consola, self.mgr), 0)
        self.assertIn(f"Aplicado en {self.mgr.path}", consola.file.getvalue())
        self.assertTrue(self.mgr.path.exists())
        self.assertEqual(self.mgr.load().cpu_threads, 5)

    def test_en_ascii_no_salen_emoji(self):
        from recorder.cli.recomendar import recomendar

        consola = make_console(ascii_mode=True, file=io.StringIO())
        recomendar(False, consola, self.mgr)
        self.assertFalse([c for c in consola.file.getvalue() if ord(c) >= 0x2000])


if __name__ == "__main__":
    unittest.main()
