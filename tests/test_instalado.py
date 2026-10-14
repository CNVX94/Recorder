"""Recorder instalado (PyInstaller) sin compilarlo: `sys.frozen` y `sys._MEIPASS` falseados.

Lo que cambia instalado y aquí se comprueba: dónde va config.json (y la variable RECORDER_CONFIG),
dónde están los archivos del programa, cómo se relanza la consulta de Vulkan (el ejecutable de
consola con `--vulkan`, atendido por recorder.py antes de cargar nada), qué dicen los mensajes que
citan tools\\ y docs\\, el registro de fallos y la ventana sin consola. Nada toca el config.json
real, %APPDATA%\\Recorder ni %LOCALAPPDATA%\\Recorder: las carpetas de Windows se apuntan a un
temporal. Desde el código todo tiene que seguir exactamente igual, y eso también se comprueba.
"""

import io
import json
import os
import pathlib
import runpy
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from unittest import mock

from recorder import registro, rutas
from recorder.cli import app
from recorder.config import hardware as hw
from recorder.config.manager import ConfigManager
from recorder.config.options import quality_description
from recorder.config.schema import (
    QUALITY_PRESETS, AppConfig, preset_availability, recommend_config, startup_notices,
)
from recorder.engine.whispercpp import whispercpp_status
from tests.test_recommendation import RX, con_gpu, i5_9500

RAIZ = pathlib.Path(__file__).resolve().parent.parent
RECORDER_PY = RAIZ / "recorder.py"
SCRIPT_PS1 = RAIZ / "tools" / "instalar_whispercpp.ps1"
ORDEN_PS = "powershell -ExecutionPolicy Bypass -File "


class CasoInstalado(unittest.TestCase):
    """Un temporal que hace de `_internal`, de %APPDATA% y de %LOCALAPPDATA%; `congelar()` finge el exe."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = pathlib.Path(self.tmp.name)
        self.internal = self.raiz / "_internal"
        self.internal.mkdir()
        entorno = {"APPDATA": str(self.raiz / "appdata"), "LOCALAPPDATA": str(self.raiz / "localappdata")}
        mock.patch.dict(os.environ, entorno).start()
        os.environ.pop(rutas.VARIABLE_CONFIG, None)  # patch.dict lo devuelve al acabar
        self.addCleanup(mock.patch.stopall)

    def congelar(self, consola: bool = True):
        """Como dentro de Recorder.exe: `_internal` es el temporal y, si `consola`, daily.exe está al lado."""
        mock.patch.object(sys, "frozen", True, create=True).start()
        mock.patch.object(sys, "_MEIPASS", str(self.internal), create=True).start()
        mock.patch.object(sys, "executable", str(self.raiz / "Recorder.exe")).start()
        if consola:
            (self.raiz / "daily.exe").write_bytes(b"")


class TestRutas(CasoInstalado):
    def test_desde_el_codigo_todo_sigue_en_el_repositorio(self):
        self.assertFalse(rutas.congelado())
        self.assertEqual(rutas.ruta_config(), RAIZ / "config.json")
        self.assertEqual(ConfigManager().path, RAIZ / "config.json", "el ConfigManager por defecto es el de siempre")
        self.assertEqual(rutas.recurso("tools/instalar_whispercpp.ps1"), SCRIPT_PS1)
        self.assertTrue(rutas.recurso("docs/architecture.md").is_file())

    def test_instalado_config_en_appdata_y_recursos_en_internal(self):
        self.congelar()
        self.assertTrue(rutas.congelado())
        self.assertEqual(rutas.ruta_config(), self.raiz / "appdata" / "Recorder" / "config.json")
        self.assertEqual(ConfigManager().path, rutas.ruta_config())
        self.assertEqual(rutas.recurso("tools/instalar_whispercpp.ps1"), self.internal / "tools" / "instalar_whispercpp.ps1")
        self.assertEqual(rutas.recurso("recorder/assets/recorder.ico"), self.internal / "recorder" / "assets" / "recorder.ico")

    def test_la_carpeta_de_config_se_crea_al_guardar_no_antes(self):
        self.congelar()
        mgr = ConfigManager()
        cfg = mgr.load()
        self.assertTrue(mgr.first_run)
        self.assertFalse(mgr.path.parent.exists(), "importar y cargar no dejan rastro")
        mgr.save(cfg)
        self.assertTrue(mgr.path.is_file())
        self.assertEqual(mgr.path.parent, self.raiz / "appdata" / "Recorder")

    def test_recorder_config_manda_en_los_dos_modos(self):
        propio = self.raiz / "otro" / "mi_config.json"
        with mock.patch.dict(os.environ, {rutas.VARIABLE_CONFIG: str(propio)}):
            self.assertEqual(rutas.ruta_config(), propio)
            self.assertEqual(ConfigManager().path, propio)
            self.congelar()
            self.assertEqual(rutas.ruta_config(), propio)
        self.assertEqual(rutas.ruta_config(), self.raiz / "appdata" / "Recorder" / "config.json", "sin la variable, lo normal")

    def test_logs_en_localappdata_en_los_dos_modos(self):
        esperada = self.raiz / "localappdata" / "Recorder" / "logs"
        self.assertEqual(rutas.carpeta_logs(), esperada)
        self.congelar()
        self.assertEqual(rutas.carpeta_logs(), esperada)
        self.assertEqual(registro.archivo_registro(), esperada / "recorder.log")

    def test_sin_las_variables_de_windows_cae_bajo_el_perfil(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("APPDATA")
            os.environ.pop("LOCALAPPDATA")
            self.assertEqual(rutas.carpeta_datos(), pathlib.Path.home() / "AppData" / "Roaming" / "Recorder")
            self.assertEqual(rutas.carpeta_logs(), pathlib.Path.home() / "AppData" / "Local" / "Recorder" / "logs")

    def test_el_ejecutable_de_consola_si_esta_y_si_no_el_propio(self):
        self.congelar(consola=False)
        self.assertEqual(rutas.ejecutable_consola(), str(self.raiz / "Recorder.exe"))
        (self.raiz / "daily.exe").write_bytes(b"")
        self.assertEqual(rutas.ejecutable_consola(), str(self.raiz / "daily.exe"))


class TestMensajesConRutas(CasoInstalado):
    def test_desde_el_codigo_la_forma_corta_de_siempre(self):
        self.assertEqual(rutas.como_instalar_whispercpp(), "tools\\instalar_whispercpp.ps1")
        self.assertEqual(rutas.documento("gpu-amd-vulkan"), "docs/gpu-amd-vulkan.md")
        texto = "ver docs/rendimiento.md y docs/gpu-amd-vulkan.md"
        self.assertEqual(rutas.citar_documentos(texto), texto)
        self.assertIn("ejecuta tools\\instalar_whispercpp.ps1 (docs/gpu-amd-vulkan.md)", recommend_config(con_gpu(i5_9500(), RX)).reason)
        self.assertIn("(docs/gpu-amd-vulkan.md)", whispercpp_status("").text)

    def test_instalado_la_orden_completa_y_la_url_de_los_docs(self):
        self.congelar()
        script = self.internal / "tools" / "instalar_whispercpp.ps1"
        orden = f'{ORDEN_PS}"{script}"'
        url = "https://github.com/CNVX94/Recorder/blob/main/docs/gpu-amd-vulkan.md"
        self.assertEqual(rutas.como_instalar_whispercpp(), orden)
        self.assertEqual(rutas.documento("gpu-amd-vulkan"), url)

        perfil = con_gpu(i5_9500(), RX)
        rec = recommend_config(perfil)
        self.assertIn(f"ejecuta {orden} ({url}) y vuelve a pulsar", rec.reason)
        self.assertNotIn("tools\\instalar_whispercpp.ps1 ", rec.reason)
        self.assertIn(f"-Modelos large-v3-turbo", recommend_config(perfil, vulkan_large_ready=True).reason)
        self.assertIn(orden, recommend_config(perfil, vulkan_large_ready=True).reason)
        avisos = startup_notices(AppConfig(), perfil, rec)
        self.assertIn(f"ejecuta {orden} o indica la carpeta", avisos[0][0])
        self.assertIn(f"Ejecuta {orden} ({url})", whispercpp_status("", perfil).text)
        self.assertIn(url, whispercpp_status("").text)
        self.assertIn(url, preset_availability("extra", 0, False).reason)
        descripcion = quality_description("extra", ("x", 1, "cpu", "int8"), None, 1, False)
        self.assertIn(f"({url})", descripcion)
        self.assertNotIn("(docs/gpu-amd-vulkan.md)", descripcion)
        self.assertEqual(descripcion, rutas.citar_documentos(QUALITY_PRESETS["extra"].summary))


class TestSondaVulkan(CasoInstalado):
    def test_desde_el_codigo_el_interprete_base_con_este_archivo(self):
        python = getattr(sys, "_base_executable", "") or sys.executable
        self.assertEqual(hw.vulkan_probe_command(), [python, "-I", os.path.abspath(hw.__file__), "--vulkan"])

    def test_instalado_relanza_el_ejecutable_de_consola_solo_con_vulkan(self):
        self.congelar()
        self.assertEqual(hw.vulkan_probe_command(), [str(self.raiz / "daily.exe"), "--vulkan"])
        os.remove(self.raiz / "daily.exe")
        self.assertEqual(hw.vulkan_probe_command(), [str(self.raiz / "Recorder.exe"), "--vulkan"], "sin daily.exe, el propio")

    def test_instalado_lee_el_json_del_hijo_sin_ventana_y_con_tiempo_limite(self):
        self.congelar()
        hijo = mock.Mock(return_value=subprocess.CompletedProcess([], 0, 'capa ajena\nVULKAN_JSON {"devices": [{"n": 1}]}\n', ""))
        with mock.patch.object(hw.subprocess, "run", hijo):
            self.assertEqual(hw._run_vulkan_probe(), [{"n": 1}])
        (cmd,), kwargs = hijo.call_args
        self.assertEqual(cmd, [str(self.raiz / "daily.exe"), "--vulkan"])
        self.assertEqual(kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)
        self.assertEqual(kwargs["timeout"], hw.VULKAN_PROBE_TIMEOUT_SEC)
        self.assertTrue(kwargs["capture_output"])
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)

    def test_sonda_imprime_la_linea_y_un_fallo_va_en_el_json(self):
        with mock.patch.object(hw, "_vulkan_raw_devices", return_value=[{"name": "RX"}]), \
                mock.patch.object(sys, "stdout", io.StringIO()) as salida:
            self.assertEqual(hw.sonda_vulkan(), 0)
        self.assertEqual(json.loads(salida.getvalue()[len(hw.VULKAN_MARKER):]), {"devices": [{"name": "RX"}]})
        with mock.patch.object(hw, "_vulkan_raw_devices", side_effect=OSError("sin vulkan-1")), \
                mock.patch.object(sys, "stdout", io.StringIO()) as salida:
            self.assertEqual(hw.sonda_vulkan(), 0)
        self.assertEqual(json.loads(salida.getvalue()[len(hw.VULKAN_MARKER):]), {"error": "OSError: sin vulkan-1"})
        with mock.patch.object(hw, "_vulkan_raw_devices", return_value=[]), mock.patch.object(sys, "stdout", None):
            self.assertEqual(hw.sonda_vulkan(), 0, "sin stdout (ventana sin tuberías) no revienta")

    def correr_entrada(self, modulo: bool):
        """recorder.py o `python -m recorder` con --vulkan en este proceso; devuelve (código, salida)."""
        salida = io.StringIO()
        with mock.patch.object(sys, "argv", ["recorder.py", "--vulkan"]), \
                mock.patch.object(hw, "_vulkan_raw_devices", return_value=[]), \
                mock.patch.object(sys, "stdout", salida), \
                mock.patch.object(registro, "instalar") as instalar, \
                self.assertRaises(SystemExit) as ctx:
            if modulo:
                runpy.run_module("recorder", run_name="__main__")
            else:
                runpy.run_path(str(RECORDER_PY), run_name="__main__")
        instalar.assert_not_called()  # la consulta sale antes de tocar el registro o la terminal
        return ctx.exception.code, salida.getvalue()

    def test_recorder_py_y_python_m_recorder_atienden_vulkan(self):
        for modulo in (False, True):
            codigo, salida = self.correr_entrada(modulo)
            self.assertEqual(codigo, 0)
            self.assertEqual(salida.strip(), hw.VULKAN_MARKER + '{"devices": []}')

    def test_en_otro_proceso_la_consulta_no_carga_numpy_ni_rich_ni_tkinter(self):
        # Como el hijo real, pero con la enumeración de Vulkan falseada para no tocar el driver.
        guion = textwrap.dedent(f"""
            import runpy, sys
            import recorder.config.hardware as hw
            hw._vulkan_raw_devices = lambda: [{{"name": "falsa"}}]
            sys.argv = ["recorder.py", "--vulkan"]
            try:
                runpy.run_path({str(RECORDER_PY)!r}, run_name="__main__")
            except SystemExit as e:
                assert e.code == 0, e.code
            print("numpy" in sys.modules, "rich" in sys.modules, "tkinter" in sys.modules)
        """)
        res = subprocess.run([sys.executable, "-c", guion], cwd=RAIZ, capture_output=True, text=True, timeout=120)
        self.assertEqual(res.returncode, 0, res.stderr)
        lineas = res.stdout.strip().splitlines()
        self.assertEqual(lineas[0], hw.VULKAN_MARKER + '{"devices": [{"name": "falsa"}]}')
        self.assertEqual(lineas[-1], "False False False")


class TestRegistroDeFallos(CasoInstalado):
    def setUp(self):
        super().setUp()
        self.logs = self.raiz / "localappdata" / "Recorder" / "logs"
        self.archivo = self.logs / "recorder.log"
        # Los ganchos "de siempre" son de mentira: así se ve que se siguen llamando y no ensucian la salida
        self.sys_previo = mock.patch.object(sys, "excepthook", mock.Mock()).start()
        self.hilos_previo = mock.patch.object(threading, "excepthook", mock.Mock()).start()
        self.addCleanup(registro.desinstalar)

    def leer(self) -> str:
        return self.archivo.read_text(encoding="utf-8")

    def test_desde_el_codigo_no_escribe_nada_hasta_el_primer_fallo(self):
        self.assertEqual(registro.instalar(), self.archivo)
        self.assertFalse(self.logs.exists(), "ni la carpeta: daily no deja rastro si no falla nada")
        try:
            raise RuntimeError("boom")
        except RuntimeError:
            info = sys.exc_info()
        sys.excepthook(*info)
        texto = self.leer()
        self.assertIn("Recorder 2.0.0 (desde el código): excepción sin atrapar en el hilo principal", texto)
        self.assertIn("RuntimeError: boom", texto)
        self.assertIn("Traceback (most recent call last)", texto)
        self.sys_previo.assert_called_once_with(*info)

    def test_un_hilo_que_muere_queda_registrado_y_el_gancho_de_siempre_se_llama(self):
        registro.instalar()

        def muere():
            raise ValueError("en un hilo")

        hilo = threading.Thread(target=muere, name="captura-out")
        hilo.start()
        hilo.join()
        texto = self.leer()
        self.assertIn("en el hilo «captura-out»", texto)
        self.assertIn("ValueError: en un hilo", texto)
        self.hilos_previo.assert_called_once()

    def test_instalado_deja_una_linea_de_arranque_y_rota_a_1_mb_por_3(self):
        self.congelar()
        registro.instalar()
        self.assertEqual(self.leer().count("\n"), 1)
        self.assertIn("Recorder 2.0.0 (instalado) arranca: Recorder.exe", self.leer())
        self.assertEqual((registro._manejador.maxBytes, registro._manejador.backupCount), (1_000_000, 3))

    def test_instalar_dos_veces_no_duplica_y_desinstalar_devuelve_los_ganchos(self):
        registro.instalar()
        registro.instalar()
        self.assertEqual(len(registro._log.handlers), 1)
        self.assertIs(sys.excepthook, registro._gancho_sys)
        registro.desinstalar()
        self.assertIs(sys.excepthook, self.sys_previo)
        self.assertIs(threading.excepthook, self.hilos_previo)
        registro.anotar("ya desinstalado", (RuntimeError, RuntimeError("x"), None))
        self.assertFalse(self.archivo.exists(), "sin instalar, anotar no hace nada")

    def test_el_sumidero_solo_sustituye_los_flujos_que_son_none(self):
        real = sys.stdout
        registro.sumidero_sin_consola()
        self.assertIs(sys.stdout, real, "con consola no se toca nada")
        with mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None):
            registro.sumidero_sin_consola()
            self.assertIsNotNone(sys.stdout)
            self.assertIsNotNone(sys.stderr)
            print("a un sumidero", file=sys.stderr)  # lo que haría tqdm: no revienta
            sys.stdout.close()
            sys.stderr.close()

    def test_fallo_de_arranque_registra_y_sin_consola_avisa_con_la_ruta(self):
        registro.instalar()
        with mock.patch("tkinter.Tk") as tk_falso, mock.patch("tkinter.messagebox.showerror") as aviso:
            try:
                raise OSError("sin micrófono")
            except OSError:
                registro.fallo_de_arranque("al abrir la ventana", avisar=False)
                aviso.assert_not_called()
                registro.fallo_de_arranque("al abrir la ventana", avisar=True)
        texto = self.leer()
        self.assertEqual(texto.count("OSError: sin micrófono"), 2)
        self.assertIn("excepción sin atrapar al abrir la ventana", texto)
        aviso.assert_called_once()
        mensaje = aviso.call_args.args[1]
        self.assertIn("OSError: sin micrófono", mensaje)
        self.assertIn(str(self.archivo), mensaje)
        tk_falso.return_value.withdraw.assert_called_once()
        tk_falso.return_value.destroy.assert_called_once()


class TestVentanaSinConsola(CasoInstalado):
    """`arrancar` sin stdout abre la ventana y le da un sumidero a los flujos; un fallo al abrirla avisa."""

    def test_sin_stdout_abre_la_ventana_con_los_flujos_ya_utilizables(self):
        vistos = {}

        def run():
            vistos["stdout"], vistos["stderr"] = sys.stdout, sys.stderr

        ventana = mock.Mock()
        ventana.return_value.run.side_effect = run
        with mock.patch("recorder.ui.main_window.MainWindow", ventana), \
                mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None):
            self.assertEqual(app.arrancar(["menu"]), 0)
            sumideros = (sys.stdout, sys.stderr)
        ventana.assert_called_once_with()
        self.assertIsNotNone(vistos["stdout"], "tqdm y compañía ya tienen dónde escribir")
        self.assertIsNotNone(vistos["stderr"])
        for s in sumideros:
            s.close()

    def test_si_la_ventana_no_abre_sin_consola_se_registra_y_avisa(self):
        with mock.patch("recorder.ui.main_window.MainWindow", side_effect=RuntimeError("sin PortAudio")), \
                mock.patch.object(registro, "fallo_de_arranque") as fallo, \
                mock.patch.object(sys, "stdout", None), mock.patch.object(sys, "stderr", None):
            self.assertEqual(app.abrir_ventana(), 1)
            sumideros = (sys.stdout, sys.stderr)
        fallo.assert_called_once_with("al abrir la ventana", avisar=True)
        for s in sumideros:
            s.close()

    def test_con_consola_el_fallo_sale_como_siempre(self):
        with mock.patch("recorder.ui.main_window.MainWindow", side_effect=RuntimeError("sin PortAudio")), \
                mock.patch.object(registro, "fallo_de_arranque") as fallo, \
                self.assertRaises(RuntimeError):
            app.abrir_ventana()
        fallo.assert_not_called()


class TestIcono(CasoInstalado):
    def test_con_icono_se_aplica_a_la_raiz_y_sin_el_no_pasa_nada(self):
        import tkinter as tk

        from PIL import Image

        from recorder.ui import theme

        try:
            raiz = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"sin Tk: {e}")
        self.addCleanup(raiz.destroy)
        raiz.withdraw()
        icono = self.internal / "recorder" / "assets" / "recorder.ico"
        with mock.patch.object(raiz, "iconbitmap") as pone:
            theme.app_icon(raiz)  # desde el código: el icono del repo
            pone.assert_called_once_with(default=str(rutas.recurso(theme.ICONO)))
            pone.reset_mock()
            self.congelar()
            theme.app_icon(raiz)
            pone.assert_not_called()
            icono.parent.mkdir(parents=True)
            Image.new("RGBA", (16, 16), (249, 226, 175, 255)).save(icono, format="ICO")
            theme.app_icon(raiz)
            pone.assert_called_once_with(default=str(icono))
        theme.app_icon(raiz)  # de verdad, con el .ico recién hecho: Tk lo acepta


@unittest.skipIf(shutil.which("powershell") is None, "sin PowerShell")
class TestInstaladorWhisperCppSoloConfig(CasoInstalado):
    """`tools\\instalar_whispercpp.ps1 -SoloConfig`: solo el paso que escribe whispercpp_dir, sobre temporales."""

    def setUp(self):
        super().setUp()
        self.destino = self.raiz / "whispercpp"
        self.destino.mkdir()

    def correr(self, script: pathlib.Path, *args: str, **entorno: str) -> subprocess.CompletedProcess:
        env = {**os.environ, **entorno}  # el setUp ya quitó RECORDER_CONFIG del entorno de la prueba
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
             "-SoloConfig", "-Destino", str(self.destino), *args],
            capture_output=True, text=True, timeout=120, env=env, cwd=self.raiz,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        return res

    def whispercpp_dir(self, config: pathlib.Path) -> str:
        return os.path.normcase(json.loads(config.read_text(encoding="utf-8"))["whispercpp_dir"])

    def test_config_path_explicito_cambia_solo_esa_clave(self):
        config = self.raiz / "mi.json"
        config.write_text('{\n  "model": "small",\n  "whispercpp_dir": "C:\\\\viejo",\n  "vocab": "QA"\n}\n', encoding="utf-8")
        self.correr(SCRIPT_PS1, "-ConfigPath", str(config))
        self.assertEqual(self.whispercpp_dir(config), os.path.normcase(str(self.destino)))
        datos = json.loads(config.read_text(encoding="utf-8"))
        self.assertEqual((datos["model"], datos["vocab"]), ("small", "QA"))
        self.assertNotIn("\ufeff", config.read_text(encoding="utf-8"), "UTF-8 sin BOM, como escribe Recorder")

    def test_sin_config_path_desde_el_repositorio_honra_recorder_config(self):
        propio = self.raiz / "por_variable.json"
        propio.write_text('{"model": "small"}', encoding="utf-8")
        res = self.correr(SCRIPT_PS1, **{rutas.VARIABLE_CONFIG: str(propio)})
        self.assertEqual(self.whispercpp_dir(propio), os.path.normcase(str(self.destino)))
        self.assertIn(str(propio), res.stdout)
        self.assertFalse((RAIZ / "config.json.roto").exists())

    def test_copiado_fuera_del_repositorio_usa_appdata_recorder(self):
        # Como instalado: el script en _internal\tools, sin recorder.py al lado de su carpeta padre.
        copia = self.internal / "tools" / "instalar_whispercpp.ps1"
        copia.parent.mkdir(parents=True)
        shutil.copy(SCRIPT_PS1, copia)
        config = self.raiz / "appdata" / "Recorder" / "config.json"
        config.parent.mkdir(parents=True)
        config.write_text('{"model": "small"}', encoding="utf-8")
        res = self.correr(copia, APPDATA=str(self.raiz / "appdata"))
        self.assertEqual(self.whispercpp_dir(config), os.path.normcase(str(self.destino)))
        self.assertIn(str(config), res.stdout)

    def test_si_el_config_no_existe_no_lo_crea_y_dice_cual_seria(self):
        config = self.raiz / "appdata" / "Recorder" / "config.json"
        copia = self.internal / "tools" / "instalar_whispercpp.ps1"
        copia.parent.mkdir(parents=True)
        shutil.copy(SCRIPT_PS1, copia)
        res = self.correr(copia, APPDATA=str(self.raiz / "appdata"))
        self.assertFalse(config.exists())
        self.assertIn(f"Todavia no existe {config}", res.stdout)
        self.assertIn('"whispercpp_dir": "', res.stdout)


if __name__ == "__main__":
    unittest.main()
