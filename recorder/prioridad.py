"""Prioridad de Recorder frente a los demás programas de Windows.

Solo dos: «normal» (lo de siempre) y «inferior» (por debajo de lo normal), que deja el procesador a
Teams cuando la videollamada lo pide y a Recorder le toca lo que sobre. Nunca «alta» ni «tiempo real»:
le quitarían procesador a la videollamada, que es peor que una cola que crece (docs/rendimiento.md, 3.7).

Se aplica a todo el proceso (los hilos de CTranslate2 nacen con la clase del proceso, y el
whisper-server que se lance después la hereda). La pone el transcriptor al cargar el modelo, es decir,
al empezar cada sesión: un cambio en Opciones vale desde la siguiente.
"""
import ctypes
from typing import Optional

from .config.schema import DEFAULT_PRIORITY, PRIORITIES

NORMAL_PRIORITY_CLASS = 0x00000020
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
CLASES = {"normal": NORMAL_PRIORITY_CLASS, "inferior": BELOW_NORMAL_PRIORITY_CLASS}
assert tuple(CLASES) == PRIORITIES


def clase_de(nombre: str) -> int:
    """La clase de prioridad de Windows de `nombre`; un valor desconocido es «normal»."""
    return CLASES.get(nombre, CLASES[DEFAULT_PRIORITY])


def aplicar(nombre: str, establecer=None) -> bool:
    """Pone la prioridad `nombre` al proceso actual. True si Windows la aceptó; fuera de Windows, o si no
    deja, False y todo sigue como estaba (no es motivo para no transcribir). `establecer(clase)` se inyecta
    en las pruebas para no tocar la prioridad real."""
    clase = clase_de(nombre)
    try:
        if establecer is not None:
            return bool(establecer(clase))
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        return bool(k32.SetPriorityClass(k32.GetCurrentProcess(), clase))
    except (OSError, AttributeError):
        return False


def ajustar(nombre: str) -> bool:
    """Lo que hace el transcriptor al empezar una sesión: «inferior» la pone; «normal» solo deshace una
    «inferior» anterior y no toca un proceso que arrancó con otra clase (p. ej. lanzado a mano con
    `start /low`). True si no había nada que cambiar o se cambió."""
    if nombre == DEFAULT_PRIORITY and actual() != "inferior":
        return True
    return aplicar(nombre)


def actual() -> Optional[str]:
    """«normal», «inferior» o None (otra clase, o no se pudo leer): la prioridad que tiene el proceso ahora."""
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetCurrentProcess.restype = ctypes.c_void_p
        k32.GetPriorityClass.argtypes = [ctypes.c_void_p]
        clase = k32.GetPriorityClass(k32.GetCurrentProcess())
    except (OSError, AttributeError):
        return None
    return next((n for n, c in CLASES.items() if c == clase), None)
