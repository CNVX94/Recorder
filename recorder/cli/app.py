"""`daily` en la terminal: decide qué arrancar y reparte los subcomandos.

    daily                       graba: la pantalla en vivo (live.py)
    daily menu                  menú numerado con todo lo que se puede hacer (menu.py)
    daily ventana | --gui       la ventana de siempre
    daily config | calibrar | sintesis | recomendar [--aplicar]
    daily --ascii …             símbolos ASCII (en la consola clásica se detecta solo; esto lo fuerza)

Los subcomandos viven en módulos aparte con un contrato mínimo:

    NOMBRE = "config"                                   # nombre del subcomando
    AYUDA = "…"                                         # una línea: ayuda de argparse y etiqueta del menú
    def agregar_argumentos(parser: argparse.ArgumentParser) -> None
    def ejecutar(args: argparse.Namespace, consola: rich.console.Console) -> int

y se cargan por nombre desde `COMANDOS`: el que falte se omite sin ruido (la terminal arranca
aunque aún no esté todo), pero un módulo roto o al que le falte una dependencia sí avisa.
`recorder.py` y `python -m recorder` entran por `arrancar`, que elige ventana o terminal.
"""
import argparse
import importlib
import sys
from types import ModuleType
from typing import Dict, Optional, Sequence

from rich.console import Console

from .. import registro
from .consola import make_console

COMANDOS = (
    "recorder.cli.configurar",
    "recorder.cli.calibrar",
    "recorder.cli.sintesis",
    "recorder.cli.recomendar",
)


def cargar_comandos(nombres: Optional[Sequence[str]] = None) -> Dict[str, ModuleType]:
    """Los módulos de comando que existen, por su NOMBRE y en el orden de `COMANDOS`."""
    comandos: Dict[str, ModuleType] = {}
    for nombre in COMANDOS if nombres is None else nombres:
        try:
            modulo = importlib.import_module(nombre)
        except ModuleNotFoundError as e:
            if e.name != nombre:
                raise  # al módulo le falta una dependencia: eso no se calla
            continue  # aún no existe: se omite
        comandos[modulo.NOMBRE] = modulo
    return comandos


class _Formato(argparse.HelpFormatter):
    """La ayuda de argparse en español: "uso:" en vez de "usage:"."""

    def add_usage(self, usage, actions, groups, prefix=None):
        super().add_usage(usage, actions, groups, "uso: " if prefix is None else prefix)


def _nuevo_parser(factoria=argparse.ArgumentParser, ascii_suelto: bool = False, **kwargs) -> argparse.ArgumentParser:
    """Un parser con la ayuda en español. Con `ascii_suelto`, `--ascii` vale también después del
    subcomando (`daily config --ver --ascii`) sin pisar el que se puso delante."""
    parser = factoria(formatter_class=_Formato, add_help=False, **kwargs)
    parser._optionals.title = "opciones"
    parser.add_argument("-h", "--help", action="help", help="muestra esta ayuda y sale")
    if ascii_suelto:
        parser.add_argument("--ascii", action="store_true", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    return parser


def construir_parser(comandos: Dict[str, ModuleType]) -> argparse.ArgumentParser:
    parser = _nuevo_parser(
        prog="daily",
        description="Recorder desde la terminal. Sin comando, graba: transcribe en vivo a la nota de hoy.",
    )
    parser.add_argument("--ascii", action="store_true", help="símbolos ASCII (en la consola clásica se detecta solo)")
    parser.add_argument("--gui", action="store_true", help="abre la ventana en vez de usar la terminal")
    sub = parser.add_subparsers(dest="comando", metavar="comando", title="comandos")

    def subcomando(nombre: str, ayuda: str) -> argparse.ArgumentParser:
        return _nuevo_parser(sub.add_parser, ascii_suelto=True, name=nombre, help=ayuda, description=ayuda)

    subcomando("menu", "menú numerado con todo lo que se puede hacer")
    subcomando("ventana", "abre la ventana (igual que --gui)")
    for nombre, modulo in comandos.items():
        modulo.agregar_argumentos(subcomando(nombre, modulo.AYUDA))
    return parser


def ejecutar_comando(
    nombre: str,
    argv: Sequence[str] = (),
    consola: Optional[Console] = None,
    comandos: Optional[Dict[str, ModuleType]] = None,
) -> int:
    """Ejecuta un comando por su nombre con sus propios argumentos (así lo llama el menú).

    `KeyError` si no está cargado: el menú no ofrece lo que no hay.
    """
    modulo = (cargar_comandos() if comandos is None else comandos)[nombre]
    parser = _nuevo_parser(prog=f"daily {nombre}", description=modulo.AYUDA)
    modulo.agregar_argumentos(parser)
    return modulo.ejecutar(parser.parse_args(list(argv)), consola or make_console())


def abrir_ventana() -> int:
    """La ventana de siempre. Se importa aquí y no arriba: la terminal no carga tkinter.

    Sin consola (Recorder.exe, pythonw) se le da un sumidero a stdout/stderr, que son None, y si
    la ventana no llega ni a abrirse se avisa con un cuadro de diálogo que señala el registro de
    fallos: no hay terminal donde ver el traceback. Con consola, el fallo sale como siempre.
    """
    from ..ui.main_window import MainWindow

    sin_consola = sys.stdout is None
    if sin_consola:
        registro.sumidero_sin_consola()
    try:
        ventana = MainWindow()
    except Exception:
        if not sin_consola:
            raise
        registro.fallo_de_arranque("al abrir la ventana", avisar=True)
        return 1
    ventana.run()
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """`daily …` con consola: reparte según los argumentos. Devuelve el código de salida."""
    comandos = cargar_comandos()
    args = construir_parser(comandos).parse_args(argv)
    if args.gui or args.comando == "ventana":
        return abrir_ventana()
    consola = make_console(ascii_mode=True if args.ascii else None)
    if args.comando is None:
        from .live import grabar

        return grabar(consola=consola)
    if args.comando == "menu":
        from .menu import menu

        return menu(consola=consola, comandos=comandos)
    return comandos[args.comando].ejecutar(args, consola)


def arrancar(argv: Optional[Sequence[str]] = None) -> int:
    """Lo que ejecuta `daily` (recorder.py): la ventana si no hay consola (pythonw, un .exe de
    ventana no la tienen); si no, la terminal, que abre la ventana con --gui o `ventana`."""
    if sys.stdout is None:
        return abrir_ventana()
    return main(argv)
