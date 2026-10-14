"""Las preguntas que comparten los comandos de terminal: texto, lista numerada, sí/no y número.

Van sobre `rich.prompt` con la consola de `consola.make_console`. Todas devuelven lo elegido o
lanzan `Cancelado` cuando el usuario corta con Ctrl+C o cierra la entrada (Ctrl+Z en Windows),
para que cada comando termine igual: «Cancelado, no se guardó nada» y código 1. Leen con el
`input()` de Python a través de `Console.input`, así que las pruebas inyectan las respuestas
sustituyendo `builtins.input` (ver tests/test_cli_preguntas.py).
"""

from typing import Callable, Optional, Sequence, TypeVar

from rich.console import Console
from rich.markup import escape
from rich.prompt import Confirm, FloatPrompt, IntPrompt, InvalidResponse, Prompt

from .consola import presentar

VACIAR = "-"  # escrito solo en un campo de texto, lo deja vacío (Enter conserva lo que hay)
MARCA_ACTUAL = "▶"  # señala en una lista la opción que está guardada ahora (la que Enter conserva)
ANCHO_NUMERACION = 8  # lo que ocupan la marca y el número delante de cada opción de `elegir`

T = TypeVar("T")


class Cancelado(Exception):
    """El usuario cortó con Ctrl+C o cerró la entrada: el comando no guarda nada."""


# ------------------------------------------------------------------ texto para esta consola
def texto(consola: Console, s: str) -> str:
    """`s` tal como lo pinta esta consola: en la clásica (conhost), sin emoji ni bloques; en las
    demás, con los símbolos que no pisan el espacio siguiente (`consola.presentar`)."""
    return presentar(s, consola)


def imprimir(consola: Console, s: str = "", **kwargs) -> None:
    """`consola.print` pasando el texto por `texto`. Lo que venga del usuario debe ir con `escape`."""
    consola.print(texto(consola, s), **kwargs)


def contar(n: int, uno: str, varios: str) -> str:
    """"1 frase", "3 frases"."""
    return f"{n} {uno if n == 1 else varios}"


# ------------------------------------------------------------------ preguntas de rich en español
class _Texto(Prompt):
    prompt_suffix = ": "


class _Entero(IntPrompt):
    prompt_suffix = ": "
    validate_error_message = "[error]Escribe un número entero.[/]"


class _Decimal(FloatPrompt):
    prompt_suffix = ": "
    validate_error_message = "[error]Escribe un número, p. ej. 0.45.[/]"

    def process_response(self, value: str) -> float:
        return super().process_response(value.replace(",", "."))  # 0,45 también vale


class _SiNo(Confirm):
    prompt_suffix = ": "
    choices = ["s", "n"]
    validate_error_message = "[error]Responde s o n.[/]"

    def process_response(self, value: str) -> bool:
        v = value.strip().lower()
        if v in ("s", "si", "sí", "y", "yes"):
            return True
        if v in ("n", "no"):
            return False
        raise InvalidResponse(self.validate_error_message)


def _leer(pregunta: Callable[[], T]) -> T:
    """Hace una pregunta convirtiendo Ctrl+C y el fin de la entrada en `Cancelado`."""
    try:
        return pregunta()
    except (KeyboardInterrupt, EOFError):
        raise Cancelado() from None


# ------------------------------------------------------------------ las preguntas
def leer_linea(consola: Console, indicador: str) -> str:
    """Una línea tal cual (sin recortar), con el indicador dado; para bucles como el sandbox."""
    return _leer(lambda: consola.input(texto(consola, indicador)))


def preguntar_texto(consola: Console, etiqueta: str, actual: str = "", ayuda: str = "") -> str:
    """Pide un texto enseñando el valor actual: Enter lo conserva y «-» lo deja vacío."""
    if ayuda:
        imprimir(consola, f"  [tenue]{ayuda}[/]")
    respuesta = _leer(
        lambda: _Texto.ask(texto(consola, etiqueta), console=consola, default=actual, show_default=bool(actual))
    ).strip()
    return "" if respuesta == VACIAR else respuesta


def elegir(
    consola: Console,
    etiqueta: str,
    opciones: Sequence[str],
    actual: Optional[int] = None,
    detalles: Optional[Sequence[str]] = None,
    cabecera: str = "",
) -> int:
    """Lista numerada; devuelve el índice elegido. `actual` va marcado y Enter lo conserva.

    `detalles`, si se da, es una nota tenue por opción (p. ej. su valor de ahora); `cabecera`,
    una línea tenue sobre las opciones, alineada con ellas (los títulos de columna de un listado).
    """
    imprimir(consola, f"[acento]{etiqueta}[/]")
    if cabecera:
        imprimir(consola, f"{' ' * ANCHO_NUMERACION}[tenue]{escape(cabecera)}[/]")
    for i, opcion in enumerate(opciones):
        marca = MARCA_ACTUAL if i == actual else " "
        detalle = f"  [tenue]{escape(detalles[i])}[/]" if detalles and detalles[i] else ""
        imprimir(consola, f"  {marca} {i + 1:>2}  {escape(opcion)}{detalle}")
    while True:
        if actual is None:
            n = _leer(lambda: _Entero.ask("Número", console=consola))
        else:
            n = _leer(lambda: _Entero.ask("Número", console=consola, default=actual + 1))
        if 1 <= n <= len(opciones):
            return n - 1
        imprimir(consola, f"[error]Elige un número entre 1 y {len(opciones)}.[/]")


def confirmar(consola: Console, pregunta: str, por_defecto: bool = True) -> bool:
    """Sí o no; Enter responde `por_defecto`."""
    return _leer(lambda: _SiNo.ask(texto(consola, pregunta), console=consola, default=por_defecto))


def preguntar_entero(
    consola: Console, etiqueta: str, actual: int, minimo: int, maximo: int, ayuda: str = ""
) -> int:
    """Un entero entre `minimo` y `maximo`; Enter conserva `actual`."""
    if ayuda:
        imprimir(consola, f"  [tenue]{ayuda}[/]")
    while True:
        n = _leer(lambda: _Entero.ask(texto(consola, etiqueta), console=consola, default=actual))
        if minimo <= n <= maximo:
            return n
        imprimir(consola, f"[error]Debe estar entre {minimo} y {maximo}.[/]")


def preguntar_decimal(
    consola: Console, etiqueta: str, actual: float, minimo: float, maximo: float, paso: float
) -> float:
    """Un decimal entre `minimo` y `maximo`, redondeado a los decimales de `paso`; Enter conserva `actual`."""
    decimales = len(str(paso).split(".")[1]) if "." in str(paso) else 0
    while True:
        v = _leer(lambda: _Decimal.ask(texto(consola, etiqueta), console=consola, default=actual))
        if minimo <= v <= maximo:
            return round(v, decimales)
        imprimir(consola, f"[error]Debe estar entre {minimo} y {maximo}.[/]")
