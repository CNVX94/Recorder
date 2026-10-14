"""`daily menu`: un menú numerado con todo lo que se puede hacer desde la terminal.

Pensado para quien no recuerda los subcomandos: un título, una línea con dónde van las notas y
con qué calidad se transcribe, y las opciones numeradas con una descripción corta cada una,
alineadas. Se elige con un número y, salvo Grabar y la ventana (que son la sesión entera), se
vuelve al menú al terminar. Los comandos que aún no existen no se ofrecen y los números no
cambian. Ctrl+C o el fin de la entrada salen sin ruido. Mismo estilo que la pantalla en vivo
(consola de `consola.make_console`, símbolos por `presentar`).
"""
from types import ModuleType
from typing import Callable, Dict, List, Optional, Tuple

from rich.console import Console
from rich.text import Text

from ..config.manager import ConfigManager
from ..config.schema import AppConfig, describe_quality
from . import app
from .consola import make_console, presentar

# (número, etiqueta, acción, descripción). Los números no cambian aunque falte algo: así "5" es
# siempre lo mismo. La acción es un NOMBRE del contrato de app.py o una de las propias: grabar,
# ventana, salir. La descripción es la del menú, corta y de una línea; la AYUDA larga de cada
# comando queda para `daily -h`.
OPCIONES: Tuple[Tuple[str, str, str, str], ...] = (
    ("1", "Grabar", "grabar", "transcribe en vivo a la nota de hoy, aquí en la terminal"),
    ("2", "Opciones", "config", "carpetas, audio, capturas, calidad y motor"),
    ("3", "Calibrar", "calibrar", "filtros anti-alucinaciones, vocabulario y sandbox"),
    ("4", "Reagrupar nota", "sintesis", "copia de una nota ordenada por hora y por tramos (no resume)"),
    ("5", "Recomendación del equipo", "recomendar", "qué equipo se detecta y qué configuración conviene"),
    ("6", "Abrir la ventana", "ventana", "la interfaz gráfica"),
    ("0", "Salir", "salir", ""),
)
PROPIAS = ("grabar", "ventana", "salir")


def opciones_disponibles(comandos: Dict[str, ModuleType]) -> List[Tuple[str, str, str, str]]:
    """(número, etiqueta, acción, descripción) de lo que se puede ofrecer con los comandos cargados."""
    return [fila for fila in OPCIONES if fila[2] in PROPIAS or fila[2] in comandos]


def resumen(config: AppConfig, error: str = "") -> str:
    """La línea bajo el título: dónde van las notas y con qué calidad; o por qué no se pudo leer."""
    if error:
        return f"⚠ {error}"
    return f"notas en {config.notes_dir} · {describe_quality(config)}"


def menu(
    consola: Optional[Console] = None,
    entrada: Callable[[], str] = input,
    comandos: Optional[Dict[str, ModuleType]] = None,
    mgr: Optional[ConfigManager] = None,
) -> int:
    """El bucle del menú. `entrada` lee una línea y `mgr` la configuración (se inyectan en las pruebas)."""
    consola = consola or make_console()
    comandos = app.cargar_comandos() if comandos is None else comandos
    mgr = mgr or ConfigManager()

    def texto(*partes: Tuple[str, str]) -> Text:
        return Text.assemble(*[(presentar(t, consola), e) for t, e in partes])

    filas = opciones_disponibles(comandos)
    ancho = max(len(etiqueta) for _n, etiqueta, _a, _d in filas)
    try:
        while True:
            config = mgr.load()  # se relee en cada vuelta: Opciones puede haberla cambiado
            consola.print()
            consola.print(texto(("Recorder", "bold"), (" · ¿qué quieres hacer?", "tenue")))
            consola.print(texto((resumen(config, mgr.last_error), "error" if mgr.last_error else "tenue")), soft_wrap=True)
            consola.print()
            for numero, etiqueta, _accion, descripcion in filas:
                columna = (etiqueta.ljust(ancho) + "  ") if descripcion else etiqueta
                consola.print(texto((f"  {numero}  ", "acento"), (columna, "texto"), (descripcion, "tenue")), soft_wrap=True)
            consola.print(texto(("Opción: ", "tenue")), end="")
            try:
                eleccion = entrada().strip()
            except EOFError:
                consola.print()
                return 0
            accion = next((f[2] for f in filas if f[0] == eleccion), None)
            if accion is None:
                consola.print(texto((f"⚠ No hay opción «{eleccion}».", "error")))
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
