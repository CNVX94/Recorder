"""Modo VT de la consola de Windows: con él la consola clásica (conhost) entiende los colores reales.

Sin activarlo, rich la toma por una consola antigua (16 colores, ASCII). `activar` debe correr ANTES de
crear la primera `rich.Console`, porque rich recuerda lo que detectó. `restaurar` deja la consola como
estaba: el modo original, sin colores puestos y con el cursor visible, para que el prompt quede limpio.
"""
import atexit
import ctypes
import sys
from typing import Dict, Optional

BANDERA_VT = 0x0004  # ENABLE_VIRTUAL_TERMINAL_PROCESSING
SALIDAS = {"stdout": -11, "stderr": -12}  # STD_OUTPUT_HANDLE y STD_ERROR_HANDLE
LIMPIAR = "\x1b[0m\x1b[?25h"  # sin colores puestos y cursor visible

_originales: Dict[str, int] = {}  # modo original de cada salida que se tocó
_atexit_puesto = False


def _kernel32():
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetStdHandle.restype = ctypes.c_void_p
    k32.GetStdHandle.argtypes = [ctypes.c_ulong]
    k32.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    k32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    return k32


def _leer_modo(k32, manejador) -> Optional[int]:
    modo = ctypes.c_ulong()
    if not manejador or manejador == ctypes.c_void_p(-1).value or not k32.GetConsoleMode(manejador, ctypes.byref(modo)):
        return None  # salida redirigida o sin consola
    return modo.value


def activar() -> bool:
    """Activa el modo VT en la salida y en la de errores si son una consola de Windows. Devuelve
    si hay VT (ya lo tuviera o lo acabe de poner). Con cualquier fallo no cambia nada."""
    global _atexit_puesto
    if sys.platform != "win32":
        return False
    try:
        k32 = _kernel32()
        hay_vt = False
        for nombre, codigo in SALIDAS.items():
            manejador = k32.GetStdHandle(codigo)
            modo = _leer_modo(k32, manejador)
            if modo is None:
                continue
            if modo & BANDERA_VT:
                hay_vt = hay_vt or nombre == "stdout"
            elif k32.SetConsoleMode(manejador, modo | BANDERA_VT):
                _originales[nombre] = modo
                hay_vt = hay_vt or nombre == "stdout"
        if _originales and not _atexit_puesto:
            atexit.register(restaurar)
            _atexit_puesto = True
        return hay_vt
    except (OSError, AttributeError, ValueError):
        return False


def restaurar() -> None:
    """Deja la consola como estaba antes de `activar`; sin efecto si no tocó nada."""
    if not _originales:
        return
    try:
        k32 = _kernel32()
        for stream in (sys.stdout, sys.stderr):
            try:
                if stream is not None and stream.isatty():
                    stream.write(LIMPIAR)
                    stream.flush()
            except (OSError, ValueError):
                pass
        for nombre, modo in list(_originales.items()):
            k32.SetConsoleMode(k32.GetStdHandle(SALIDAS[nombre]), modo)
    except (OSError, AttributeError, ValueError):
        pass
    finally:
        _originales.clear()


def hay_vt() -> bool:
    """Si la salida estándar es una consola con VT activo (lo consulta tal cual está ahora)."""
    if sys.platform != "win32":
        return False
    try:
        k32 = _kernel32()
        modo = _leer_modo(k32, k32.GetStdHandle(SALIDAS["stdout"]))
    except (OSError, AttributeError, ValueError):
        return False
    return modo is not None and bool(modo & BANDERA_VT)
