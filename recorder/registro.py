"""Registro de fallos: las excepciones que nadie atrapó, a un archivo que rota.

Instalado como ejecutable de ventana no hay consola: una excepción sin atrapar desaparece o sale en
un diálogo crudo de PyInstaller, y no queda rastro. Esto engancha `sys.excepthook`,
`threading.excepthook` y (desde la ventana) `report_callback_exception` de Tk a
`%LOCALAPPDATA%\\Recorder\\logs\\recorder.log` (1 MB × 3; ver rutas.carpeta_logs), y en la ventana
avisa con un cuadro de diálogo si no se pudo ni arrancar.

En la terminal no cambia nada que se vea: los ganchos anotan y después llaman a los de siempre, que
imprimen el traceback como hasta ahora. Desde el código el archivo no se crea hasta el primer fallo
(instalado se escribe una línea al arrancar, con la versión). Se registran solo excepciones, con
su traceback, y esa línea de arranque: nunca texto transcrito ni audio.

Solo biblioteca estándar al importar; tkinter se carga solo para el aviso de arranque fallido.
"""
import logging
import logging.handlers
import os
import pathlib
import sys
import threading
from typing import Optional

from . import __version__, rutas

NOMBRE_ARCHIVO = "recorder.log"
TAMANO_MAX = 1_000_000  # bytes por archivo antes de rotar
COPIAS = 3

_log = logging.getLogger("recorder.fallos")
_log.propagate = False  # que no acabe en el stderr de un logging ajeno
_manejador: Optional[logging.Handler] = None  # el archivo, mientras esté instalado
_ganchos_previos: dict = {}


def archivo_registro() -> pathlib.Path:
    return rutas.carpeta_logs() / NOMBRE_ARCHIVO


class _ArchivoRotatorio(logging.handlers.RotatingFileHandler):
    """Crea la carpeta al abrir el archivo (en el primer registro, no al instalar)."""

    def _open(self):
        os.makedirs(os.path.dirname(self.baseFilename), exist_ok=True)
        return super()._open()


def modo() -> str:
    return "instalado" if rutas.congelado() else "desde el código"


def anotar(contexto: str, exc_info) -> None:
    """Una excepción con su traceback en el registro, con la versión y el modo para situarla."""
    if _manejador is None:
        return
    try:
        _log.error("Recorder %s (%s): excepción sin atrapar %s", __version__, modo(), contexto, exc_info=exc_info)
    except Exception:  # ponytail: el registro de fallos no puede fallar él mismo
        pass


def _gancho_sys(tipo, valor, tb) -> None:
    anotar("en el hilo principal", (tipo, valor, tb))
    _ganchos_previos["sys"](tipo, valor, tb)


def _gancho_hilos(args) -> None:
    anotar(f"en el hilo «{getattr(args.thread, 'name', '?')}»", (args.exc_type, args.exc_value, args.exc_traceback))
    _ganchos_previos["threading"](args)


def instalar() -> pathlib.Path:
    """Engancha los dos ganchos al archivo rotatorio y devuelve su ruta. Repetirlo no duplica.

    Con `delay` el archivo (y su carpeta) se abre en el primer registro: desde el código no queda
    nada en disco hasta que algo falla. Si entonces no se puede escribir, logging lo dice por
    stderr y Recorder sigue: el registro nunca es motivo para no arrancar.
    """
    global _manejador
    ruta = archivo_registro()
    if _manejador is not None:
        return ruta
    manejador = _ArchivoRotatorio(ruta, maxBytes=TAMANO_MAX, backupCount=COPIAS, encoding="utf-8", delay=True)
    manejador.setFormatter(logging.Formatter("%(asctime)s  %(message)s"))
    _log.addHandler(manejador)
    _log.setLevel(logging.INFO)
    _manejador = manejador
    _ganchos_previos["sys"] = sys.excepthook
    _ganchos_previos["threading"] = threading.excepthook
    sys.excepthook = _gancho_sys
    threading.excepthook = _gancho_hilos
    if rutas.congelado():
        _log.info("Recorder %s (%s) arranca: %s", __version__, modo(), os.path.basename(sys.executable))
    return ruta


def desinstalar() -> None:
    """Deshace `instalar` (lo usan las pruebas): quita el archivo y devuelve los ganchos de antes."""
    global _manejador
    if _manejador is None:
        return
    sys.excepthook = _ganchos_previos.pop("sys", sys.__excepthook__)
    threading.excepthook = _ganchos_previos.pop("threading", threading.__excepthook__)
    _log.removeHandler(_manejador)
    _manejador.close()
    _manejador = None


def sumidero_sin_consola() -> None:
    """Sin consola (ejecutable de ventana, pythonw) `sys.stdout` y `sys.stderr` son None, y lo que
    escriba un tercero (la barra de progreso de tqdm al descargar el modelo) revienta con
    AttributeError: se les da un sumidero. Solo a los que sean None; en la terminal no toca nada.
    Llamar DESPUÉS de decidir ventana o terminal, que se decide por `sys.stdout is None`."""
    for nombre in ("stdout", "stderr"):
        if getattr(sys, nombre, None) is None:
            setattr(sys, nombre, open(os.devnull, "w", encoding="utf-8"))


def fallo_de_arranque(contexto: str, avisar: bool) -> None:
    """La excepción en curso no dejó ni abrir la ventana: al registro y, con `avisar` (no hay
    consola donde verla), un cuadro de diálogo con la ruta del registro."""
    anotar(contexto, sys.exc_info())
    if not avisar:
        return
    try:
        import tkinter as tk
        from tkinter import messagebox

        raiz = tk.Tk()
        raiz.withdraw()
        _tipo, valor, _tb = sys.exc_info()
        messagebox.showerror(
            "Recorder",
            f"Recorder no pudo arrancar {contexto}.\n\n{valor.__class__.__name__}: {valor}\n\n"
            f"El detalle queda en:\n{archivo_registro()}",
            parent=raiz,
        )
        raiz.destroy()
    except Exception:  # ponytail: sin Tk no hay dónde avisar; el registro ya lo tiene
        pass
