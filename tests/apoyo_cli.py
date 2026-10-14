"""Apoyo para probar los comandos de terminal: consola en memoria, respuestas guionizadas y argumentos.

Los comandos leen con el `input()` de Python (a través de `Console.input`), así que `respuestas`
lo sustituye por una lista de lo que el usuario teclearía; agotada, la entrada se cierra como con
Ctrl+Z, y el comando debe cancelar sin guardar.
"""

import argparse
import builtins
import contextlib
import io
from typing import Callable, Tuple
from unittest import mock

from rich.console import Console

from recorder.cli.consola import make_console


def consola_de_prueba(ascii_mode: bool = False) -> Tuple[Console, io.StringIO]:
    """Una consola de Recorder que escribe en memoria, ancha para que las tablas no partan rutas."""
    buf = io.StringIO()
    return make_console(ascii_mode=ascii_mode, file=buf, width=160), buf


@contextlib.contextmanager
def respuestas(*lineas: str):
    """Lo que el usuario teclearía, en orden. Una respuesta de más pedida = EOF (Ctrl+Z)."""
    pendientes = iter(lineas)

    def teclear(_prompt: str = "") -> str:
        try:
            return next(pendientes)
        except StopIteration:
            raise EOFError

    with mock_input(teclear):
        yield


@contextlib.contextmanager
def mock_input(fn: Callable[..., str]):
    """Sustituye el `input()` de Python, que es lo que lee `Console.input`."""
    with mock.patch.object(builtins, "input", fn):
        yield


def argumentos(modulo, *argv: str) -> argparse.Namespace:
    """Los argumentos de un comando como los dejaría el despachador (sin argv = los del menú)."""
    parser = argparse.ArgumentParser(prog=modulo.NOMBRE, description=modulo.AYUDA)
    modulo.agregar_argumentos(parser)
    return parser.parse_args(argv)


def solo_ascii(salida: str) -> bool:
    """Si la salida no trae emoji ni bloques (lo que la consola clásica pinta mal); acentos y «·» sí."""
    return all(ord(c) < 0x2000 or c in "–—·" for c in salida)
