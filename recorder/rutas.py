"""Dónde está cada cosa: desde el código o instalado (PyInstaller), con una sola respuesta.

Desde el código todo vive en el repositorio: `config.json` en la raíz, `tools/`, `docs/`. Instalado
(`Recorder.exe` y `daily.exe` en `%LOCALAPPDATA%\\Programs\\Recorder`, de solo lectura en espíritu)
los archivos que acompañan al programa están en `_internal` (`sys._MEIPASS`) y lo que el usuario
escribe va a sus carpetas: la configuración a `%APPDATA%\\Recorder` y el registro de fallos a
`%LOCALAPPDATA%\\Recorder\\logs`. `RECORDER_CONFIG` apunta a otro config.json (pruebas, uso portable).

Solo biblioteca estándar: lo importan la configuración, la detección del equipo y la terminal, y
ninguno de ellos carga tkinter. Nada de aquí crea carpetas: las crea quien escribe (`ConfigManager.save`,
el registro) para que importar no deje rastro.
"""
import os
import pathlib
import re
import sys

NOMBRE_APP = "Recorder"
VARIABLE_CONFIG = "RECORDER_CONFIG"  # otro config.json: pruebas, uso portable, varias configuraciones
EJECUTABLE_CONSOLA = "daily.exe"  # el ejecutable de consola instalado junto al de ventana (Recorder.exe)
REPOSITORIO_DOCS = "https://github.com/CNVX94/Recorder/blob/main/docs"


def congelado() -> bool:
    """True dentro de un ejecutable de PyInstaller; False desde el código (`python recorder.py`, daily)."""
    return bool(getattr(sys, "frozen", False))


def raiz_recursos() -> pathlib.Path:
    """La carpeta con los archivos que acompañan al programa (`tools/`, `docs/`, `recorder/assets/`):
    la raíz del repositorio desde el código; instalado, `_internal` (`sys._MEIPASS`)."""
    if congelado():
        return pathlib.Path(getattr(sys, "_MEIPASS", None) or pathlib.Path(sys.executable).parent)
    return pathlib.Path(__file__).resolve().parent.parent


def recurso(relativa: str) -> pathlib.Path:
    """Ruta absoluta de un archivo del programa a partir de su ruta relativa al repositorio, con `/`
    (`recurso("tools/instalar_whispercpp.ps1")`). Vale igual desde el código e instalado."""
    return raiz_recursos().joinpath(*relativa.split("/"))


def _carpeta_windows(variable: str, *por_defecto: str) -> pathlib.Path:
    """%APPDATA% o %LOCALAPPDATA%; si la variable no está (raro), la ruta habitual bajo el perfil."""
    valor = os.environ.get(variable)
    return pathlib.Path(valor) if valor else pathlib.Path.home().joinpath(*por_defecto)


def carpeta_datos() -> pathlib.Path:
    """Instalado, donde se guarda lo del usuario: `%APPDATA%\\Recorder` (itinerante, como su config)."""
    return _carpeta_windows("APPDATA", "AppData", "Roaming") / NOMBRE_APP


def carpeta_logs() -> pathlib.Path:
    """El registro de fallos, en los dos modos: `%LOCALAPPDATA%\\Recorder\\logs` (local, no itinerante)."""
    return _carpeta_windows("LOCALAPPDATA", "AppData", "Local") / NOMBRE_APP / "logs"


def ruta_config() -> pathlib.Path:
    """El config.json que usa Recorder, decidido en cada llamada (no al importar).

    1. `RECORDER_CONFIG`, si está definida.
    2. Desde el código, `config.json` en la raíz del repositorio: lo de siempre.
    3. Instalado, `%APPDATA%\\Recorder\\config.json`; la carpeta se crea al guardar.
    """
    propia = os.environ.get(VARIABLE_CONFIG, "").strip()
    if propia:
        return pathlib.Path(propia)
    if congelado():
        return carpeta_datos() / "config.json"
    return raiz_recursos() / "config.json"


def ejecutable_consola() -> str:
    """Instalado, con qué relanzar Recorder en otro proceso para leer lo que imprime: `daily.exe`
    (consola) junto al ejecutable que corre, si está; si no, el propio `sys.executable`.

    Un hijo de ventana al que se le dan tuberías también escribe en ellas, pero el de consola es el
    camino sin sorpresas. Desde el código no se usa: ahí se relanza el intérprete.
    """
    actual = pathlib.Path(sys.executable)
    consola = actual.with_name(EJECUTABLE_CONSOLA)
    return str(consola if consola.is_file() else actual)


# ------------------------------------------------------------------ cómo citar rutas en los mensajes
def como_instalar_whispercpp() -> str:
    """Cómo lanzar tools/instalar_whispercpp.ps1 en un mensaje al usuario.

    Desde el código basta la ruta relativa de siempre; instalado, el script va empaquetado en
    `_internal\\tools` y se da la orden completa, porque `.ps1` no se ejecuta con doble clic.
    """
    if congelado():
        return f'powershell -ExecutionPolicy Bypass -File "{recurso("tools/instalar_whispercpp.ps1")}"'
    return "tools\\instalar_whispercpp.ps1"


def documento(nombre: str) -> str:
    """Cómo citar `docs/<nombre>.md`: relativo desde el código; instalado, su URL en GitHub (los
    documentos también van en `_internal\\docs`, pero la URL se lee y se abre mejor)."""
    if congelado():
        return f"{REPOSITORIO_DOCS}/{nombre}.md"
    return f"docs/{nombre}.md"


_CITA_DOC = re.compile(r"docs/([A-Za-z0-9-]+)\.md")


def citar_documentos(texto: str) -> str:
    """`documento()` sobre un texto ya escrito: cada `docs/<nombre>.md` pasa por él. Para los textos
    fijos (los resúmenes de los presets) que se escriben una vez al importar; desde el código no
    cambia nada."""
    return _CITA_DOC.sub(lambda m: documento(m.group(1)), texto)
