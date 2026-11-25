"""Las teclas de la terminal sin bloquear, en Windows y en Linux/macOS, con nombres comunes.

`teclado()` da, dentro de un `with`, una función que devuelve la tecla pulsada o None si no hay
ninguna esperando. Las especiales llegan con su nombre (ARRIBA, ABAJO, IZQUIERDA, DERECHA,
INICIO, FIN, SUPR, REPAG, AVPAG, ENTER, ESC, TAB, RETROCESO); el resto, como su carácter (el
espacio, como ESPACIO).

- Windows: msvcrt. Las flechas, Inicio, Fin, Supr, RePág y AvPág llegan como un prefijo \\xe0 o
  \\x00 y un código; las demás especiales (F1…) se consumen y se ignoran.
- Linux/macOS: la terminal pasa a modo cbreak (sin eco ni esperar a Enter; Ctrl+C sigue siendo
  SIGINT) y se lee lo que haya con select. Las flechas son ESC [ A…D (o ESC O A…D); un ESC sin
  nada detrás en ESPERA_ESC segundos es la tecla Esc. Inicio y Fin son ESC [ H / F (o ESC [ 1 ~ y
  ESC [ 4 ~) y Supr, RePág y AvPág, ESC [ 3 ~, 5 ~ y 6 ~. Al salir del `with` la terminal se restaura
  siempre, también si salta una excepción o Ctrl+C. Con la entrada redirigida no hay teclas.

Los decodificadores son puros y se prueban con secuencias guionizadas (tests/test_cli_teclas.py).
"""
import codecs
import contextlib
import os
import select
import sys
from typing import Callable, Iterator, Optional, Tuple

if os.name == "nt":
    import msvcrt

ARRIBA, ABAJO, IZQUIERDA, DERECHA = "arriba", "abajo", "izquierda", "derecha"
INICIO, FIN, SUPR, REPAG, AVPAG = "inicio", "fin", "supr", "repag", "avpag"
ENTER, ESC, TAB, RETROCESO = "enter", "esc", "tab", "retroceso"
ESPACIO = " "  # llega como su carácter: en un campo de texto es texto y en un interruptor, alternar
CTRL_C = "\x03"  # lo que el manejador de SIGINT de la pantalla en vivo mete en su cola de teclas
ESPERA_ESC = 0.05  # s que se espera tras un ESC suelto por el resto de una secuencia

SIMPLES = {"\r": ENTER, "\n": ENTER, "\t": TAB, "\x08": RETROCESO, "\x7f": RETROCESO, "\x1b": ESC}
WINDOWS = {  # el código tras \x00 o \xe0
    "H": ARRIBA, "P": ABAJO, "K": IZQUIERDA, "M": DERECHA, "G": INICIO, "O": FIN, "S": SUPR, "I": REPAG, "Q": AVPAG,
}
POSIX = {"A": ARRIBA, "B": ABAJO, "C": DERECHA, "D": IZQUIERDA, "H": INICIO, "F": FIN}  # el final de ESC [ X o ESC O X
POSIX_VIRGULILLA = {"1": INICIO, "7": INICIO, "4": FIN, "8": FIN, "3": SUPR, "5": REPAG, "6": AVPAG}  # ESC [ n ~

Lector = Callable[[], Optional[str]]


def decodificar_windows(ch: str, segundo: Callable[[], str]) -> Optional[str]:
    """La tecla de un carácter de msvcrt.getwch; `segundo` lee el código de una especial."""
    if ch in ("\x00", "\xe0"):
        return WINDOWS.get(segundo())
    return SIMPLES.get(ch, ch)


def decodificar_posix(datos: str) -> Tuple[Optional[str], str]:
    """(la primera tecla de `datos`, lo que sobra). Una secuencia de escape que no es una flecha
    (Ctrl+flecha, F1…) da None y se consume entera; un ESC seguido de otra cosa es Esc."""
    if not datos:
        return None, ""
    if datos[0] != "\x1b" or len(datos) == 1:
        return SIMPLES.get(datos[0], datos[0]), datos[1:]
    if datos[1] not in "[O":
        return ESC, datos[1:]
    fin = 2  # tras ESC [ pueden ir parámetros (1;5) hasta el carácter final (@ a ~)
    while fin < len(datos) and not "@" <= datos[fin] <= "~":
        fin += 1
    if fin == len(datos):
        return None, ""  # secuencia cortada: se descarta
    if datos[fin] == "~":
        tecla = POSIX_VIRGULILLA.get(datos[2:fin])
    else:
        tecla = POSIX.get(datos[fin]) if fin == 2 else None
    return tecla, datos[fin + 1:]


def leer_windows() -> Optional[str]:
    if not msvcrt.kbhit():
        return None
    return decodificar_windows(msvcrt.getwch(), msvcrt.getwch)


class LectorPosix:
    """Lee sin bloquear del descriptor `fd`. `leer` y `listo(espera)` se inyectan en las pruebas."""

    def __init__(self, fd: int, leer: Callable[[int, int], bytes] = os.read, listo: Optional[Callable[[float], bool]] = None):
        self.fd = fd
        self._leer = leer
        self._listo = listo or (lambda espera: bool(select.select([fd], [], [], espera)[0]))
        self._utf8 = codecs.getincrementaldecoder("utf-8")("replace")  # una ñ puede llegar partida
        self._pendiente = ""  # lo leído que aún no se entregó (varias teclas de golpe, un pegado)

    def _leer_lo_que_haya(self) -> str:
        return self._utf8.decode(self._leer(self.fd, 64))

    def __call__(self) -> Optional[str]:
        if not self._pendiente:
            if not self._listo(0):
                return None
            self._pendiente = self._leer_lo_que_haya()
        if self._pendiente == "\x1b" and self._listo(ESPERA_ESC):
            self._pendiente += self._leer_lo_que_haya()  # el resto de una flecha, si lo era
        tecla, self._pendiente = decodificar_posix(self._pendiente)
        return tecla


@contextlib.contextmanager
def modo_cbreak(fd: int, termios, tty) -> Iterator[None]:
    """La terminal en cbreak mientras dura el `with`; restaurada al salir pase lo que pase."""
    antes = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, antes)


@contextlib.contextmanager
def teclado() -> Iterator[Lector]:
    """El lector de teclas de esta plataforma, con la terminal preparada mientras dura el `with`."""
    if os.name == "nt":
        yield leer_windows
        return
    if sys.stdin is None or not sys.stdin.isatty():
        yield lambda: None  # entrada redirigida: no hay teclado
        return
    import termios
    import tty

    fd = sys.stdin.fileno()
    with modo_cbreak(fd, termios, tty):
        yield LectorPosix(fd)
