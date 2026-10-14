# -*- mode: python ; coding: utf-8 -*-
"""Receta de PyInstaller para Recorder: una carpeta `Recorder` (onedir) con dos ejecutables.

    Recorder.exe   sin consola: abre la ventana (recorder.cli.app.arrancar ve sys.stdout is None)
    daily.exe      con consola: `daily`, `daily menu`, `daily config`… y `--selftest`, `--recomendar`

Los dos salen del mismo análisis de recorder.py y comparten `_internal` (Python, dependencias y
datos), así que la carpeta no se duplica. La construye packaging\\build.ps1, que pasa --distpath
y --workpath fuera del repositorio; las rutas de aquí salen de SPECPATH (la carpeta del .spec),
por lo que da igual desde dónde se invoque.

Qué va dentro y qué no:
  - faster-whisper con su VAD (silero_vad_v6.onnx), ctranslate2, onnxruntime, tokenizers, av,
    PyAudioWPatch, Pillow, numpy, rich y tkinter (la ventana lo necesita: no excluirlo).
  - tools\\instalar_whispercpp.ps1, docs\\*.md, recorder\\assets\\* y config.example.json, con la
    misma ruta relativa que en el repositorio (el código los resuelve bajo sys._MEIPASS).
  - NO van los modelos de Whisper (se descargan al usarse, a la caché de Hugging Face), ni las
    DLL de CUDA (quien tenga NVIDIA instala CUDA/cuDNN aparte), ni whisper.cpp.
  - Se excluye hf_xet (9 MB, no carga congelado; huggingface_hub descarga por HTTP sin él).
  - UPX desactivado: comprime poco y dispara falsos positivos del antivirus.
"""
import os
import re
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

RAIZ = os.path.abspath(os.path.join(SPECPATH, os.pardir))  # noqa: F821 (SPECPATH lo define PyInstaller)
ICONO = os.path.join(RAIZ, "recorder", "assets", "recorder.ico")
NOMBRE_CARPETA = "Recorder"


def leer_version() -> str:
    """`__version__` de recorder/__init__.py sin importar el paquete (que arrastra numpy y PortAudio)."""
    with open(os.path.join(RAIZ, "recorder", "__init__.py"), encoding="utf-8") as f:
        encontrado = re.search(r'^__version__\s*=\s*"([^"]+)"', f.read(), re.M)
    if not encontrado:
        raise SystemExit("No se encontró __version__ en recorder/__init__.py")
    return encontrado.group(1)


VERSION = leer_version()


def version_numerica(texto: str):
    """"2.0.0" -> (2, 0, 0, 0): los cuatro enteros que pide el recurso VERSIONINFO de Windows."""
    partes = [int(p) for p in re.findall(r"\d+", texto)[:4]]
    return tuple(partes + [0] * (4 - len(partes)))


def info_version(nombre_archivo: str, descripcion: str) -> VSVersionInfo:
    """El recurso de versión que enseña el Explorador en Propiedades > Detalles."""
    numeros = version_numerica(VERSION)
    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=numeros,
            prodvers=numeros,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,  # VOS_NT_WINDOWS32
            fileType=0x1,  # VFT_APP
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo([
                StringTable(
                    "080A04B0",  # español (México), Unicode
                    [
                        StringStruct("CompanyName", "Recorder"),
                        StringStruct("FileDescription", descripcion),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", os.path.splitext(nombre_archivo)[0]),
                        StringStruct("OriginalFilename", nombre_archivo),
                        StringStruct("ProductName", "Recorder"),
                        StringStruct("ProductVersion", VERSION),
                    ],
                )
            ]),
            VarFileInfo([VarStruct("Translation", [0x080A, 1200])]),
        ],
    )


# Datos: el VAD de faster-whisper y los archivos del repositorio que el código busca por su ruta
# relativa (destino = misma carpeta que en el repo, colgando de _internal).
datas = collect_data_files("faster_whisper")  # faster_whisper/assets/silero_vad_v6.onnx
datas += [
    (os.path.join(RAIZ, "tools", "instalar_whispercpp.ps1"), "tools"),
    (os.path.join(RAIZ, "docs", "*.md"), "docs"),
    (os.path.join(RAIZ, "recorder", "assets", "*"), os.path.join("recorder", "assets")),
    (os.path.join(RAIZ, "config.example.json"), "."),
]

# Los subcomandos de la terminal (recorder.cli.configurar, calibrar, sintesis, recomendar) se
# cargan por nombre con importlib.import_module, que el análisis estático no ve: se declaran.
# collect_submodules importa el paquete, así que la raíz del repo tiene que estar en sys.path
# aunque se compile desde otra carpeta; si no, devuelve vacío sin avisar y faltan comandos.
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
hiddenimports = collect_submodules("recorder")
if "recorder.cli.configurar" not in hiddenimports:
    raise SystemExit("No se encontraron los subcomandos de recorder.cli: revisa que se pueda importar el paquete.")

a = Analysis(
    [os.path.join(RAIZ, "recorder.py")],
    pathex=[RAIZ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["hf_xet"],
    noarchive=False,
)
pyz = PYZ(a.pure)

comun = dict(
    exclude_binaries=True,  # onedir: los binarios van a la carpeta, no dentro del .exe
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    icon=ICONO,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

exe_ventana = EXE(
    pyz,
    a.scripts,
    [],
    name="Recorder",
    console=False,
    version=info_version("Recorder.exe", "Recorder: transcripción en vivo a notas Markdown"),
    **comun,
)

exe_terminal = EXE(
    pyz,
    a.scripts,
    [],
    name="daily",
    console=True,
    version=info_version("daily.exe", "Recorder desde la terminal (daily)"),
    **comun,
)

coll = COLLECT(
    exe_ventana,
    exe_terminal,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=NOMBRE_CARPETA,
)
