"""`daily menu`: un menú numerado con todo lo que se puede hacer desde la terminal.

Pensado para quien no recuerda los subcomandos: se elige con un número y, salvo Grabar y la
ventana (que son la sesión entera), se vuelve al menú al terminar. Los comandos que aún no
existen no se ofrecen. Ctrl+C o el fin de la entrada salen sin ruido.
"""
from types import ModuleType
from typing import Callable, Dict, List, Optional, Tuple

from rich.console import Console
from rich.text import Text

from . import app
from .consola import asciify, make_console

# (número, etiqueta, acción). Los números no cambian aunque falte algo: así "5" es siempre lo mismo.
# La acción es un NOMBRE del contrato de app.py o una de las propias: grabar, ventana, salir.
OPCIONES: Tuple[Tuple[str, str, str], ...] = (
    ("1", "Grabar", "grabar"),
    ("2", "Opciones", "config"),
    ("3", "Calibrar", "calibrar"),
    ("4", "Reagrupar nota", "sintesis"),
    ("5", "Recomendación del equipo", "recomendar"),
    ("6", "Abrir la ventana", "ventana"),
    ("0", "Salir", "salir"),
)
PROPIAS = {
    "grabar": "transcribe en vivo a la nota de hoy, aquí en la terminal",
    "ventana": "la interfaz gráfica de siempre",
    "salir": "",
}


def opciones_disponibles(comandos: Dict[str, ModuleType]) -> List[Tuple[str, str, str, str]]:
    """(número, etiqueta, acción, ayuda) de lo que se puede ofrecer con los comandos cargados."""
    filas = []
    for numero, etiqueta, accion in OPCIONES:
        if accion in PROPIAS:
            filas.append((numero, etiqueta, accion, PROPIAS[accion]))
        elif accion in comandos:
            filas.append((numero, etiqueta, accion, comandos[accion].AYUDA))
    return filas


def menu(
    consola: Optional[Console] = None,
    entrada: Callable[[], str] = input,
    comandos: Optional[Dict[str, ModuleType]] = None,
) -> int:
    """El bucle del menú. `entrada` lee una línea (se inyecta en las pruebas)."""
    consola = consola or make_console()
    comandos = app.cargar_comandos() if comandos is None else comandos
    ascii_mode = getattr(consola, "ascii_mode", False)

    def texto(t: str) -> str:
        return asciify(t) if ascii_mode else t

    filas = opciones_disponibles(comandos)
    try:
        while True:
            consola.print()
            consola.print(Text(texto("Recorder · ¿qué quieres hacer?"), style="bold"))
            for numero, etiqueta, _accion, ayuda in filas:
                consola.print(Text.assemble(
                    (f"  {numero}  ", "acento"), (texto(etiqueta), "texto"), (f"   {texto(ayuda)}" if ayuda else "", "tenue"),
                ))
            consola.print(Text(texto("Opción: "), style="tenue"), end="")
            try:
                eleccion = entrada().strip()
            except EOFError:
                consola.print()
                return 0
            accion = next((f[2] for f in filas if f[0] == eleccion), None)
            if accion is None:
                consola.print(Text(texto(f"No hay opción «{eleccion}»."), style="error"))
                continue
            if accion == "salir":
                return 0
            if accion == "grabar":
                from .live import grabar

                return grabar(consola=consola)
            if accion == "ventana":
                return app.abrir_ventana()
            app.ejecutar_comando(accion, (), consola, comandos)
    except KeyboardInterrupt:
        consola.print()
        return 0
