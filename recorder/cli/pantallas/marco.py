"""El reparto del cuadro de una pantalla (docs/terminal-especificacion.md, sección 1): funciones puras,
sin rich, para que se prueben con números.

De arriba abajo: cabecera, regla, ruta, cuerpo, ayuda, aviso y pie. El cuerpo recibe lo que quede; si
sobra espacio, hay una línea de respiro bajo el cuerpo y otra sobre él.
"""
from typing import List, Tuple

from .base import Teclas, recorte

MARGEN = 1  # columnas en blanco a cada lado
ANCHO_MINIMO, ALTO_MINIMO = 60, 24  # por debajo no se pinta ninguna pantalla
ANCHO_AYUDA_DOS, ANCHO_AYUDA_TRES = 92, 74  # desde aquí la ayuda ocupa 2 líneas, desde aquí 3, y por debajo 4
RESPIRO_ABAJO, RESPIRO_ARRIBA = 12, 15  # el espacio libre desde el que sale cada línea de respiro
ANCHO_DOS_COLUMNAS = 96  # desde aquí el Inicio enseña su ficha a la derecha de la lista
ALTO_AVISO = 1  # la región de aviso se reserva siempre
ALTO_PIE = 1
SANGRIA_LISTA = 4  # las marcas «↑ N más arriba» / «↓ N más abajo» van sangradas
TECLA_AYUDA = "?"


def alto_ayuda(ancho: int) -> int:
    """Las líneas que se reservan a la explicación de lo elegido: fijas para cada ancho, para que el
    cuerpo no salte al mover la selección."""
    return 2 if ancho >= ANCHO_AYUDA_DOS else 3 if ancho >= ANCHO_AYUDA_TRES else 4


def respiros(libre: int) -> Tuple[int, int]:
    """(líneas en blanco sobre el cuerpo, bajo el cuerpo) con `libre` líneas para cuerpo y respiros."""
    abajo = 1 if libre >= RESPIRO_ABAJO else 0
    arriba = 1 if libre - abajo >= RESPIRO_ARRIBA else 0
    return arriba, abajo


def demasiado_pequena(ancho: int, alto: int) -> bool:
    return ancho < ANCHO_MINIMO or alto < ALTO_MINIMO


def pie_que_cabe(teclas: Teclas, cabe, mas: Tuple[str, str]) -> List[Tuple[str, str]]:
    """Las teclas del pie que caben, en orden de prioridad. `cabe(teclas)` dice si una lista cabe en una
    línea. Si no caben todas se quitan las últimas y, si la lista tenía «?», se añade «[?] Más»."""
    teclas = list(teclas)
    if cabe(teclas):
        return teclas
    con_ayuda = any(t == TECLA_AYUDA for t, _ in teclas)
    resto = [t for t in teclas if t[0] != TECLA_AYUDA]
    while resto and not cabe(resto + ([mas] if con_ayuda else [])):
        resto.pop()
    return resto + ([mas] if con_ayuda else [])


def desde(n: int, arriba: int, sitio: int) -> Tuple[range, int, int]:
    """Como `ventana`, pero para un texto que se recorre desde una línea (`arriba`) en vez de seguir una fila
    elegida: (líneas visibles, cuántas quedan arriba, cuántas abajo). `arriba` se ajusta para no pasar del
    final; lo que queda arriba es la primera línea que vale. Las líneas de «↑ N más arriba» y
    «↓ N más abajo» salen de `sitio` cuando hay algo oculto por ese lado."""
    if n <= sitio:
        return range(n), 0, 0
    arriba = max(0, min(arriba, n - (sitio - 1)))  # en el final solo hace falta el marcador de arriba
    filas = max(1, sitio - (1 if arriba else 0))
    if arriba + filas < n:
        filas = max(1, filas - 1)
    return range(arriba, min(n, arriba + filas)), arriba, max(0, n - arriba - filas)


def ventana(n: int, foco: int, sitio: int) -> Tuple[range, int, int]:
    """(filas visibles, cuántas quedan arriba, cuántas abajo) de una lista de `n` filas en `sitio` líneas.
    Si no cabe, la primera y la última línea visibles se reservan a «↑ N más arriba» y «↓ N más abajo»
    cuando hay algo oculto por ese lado, y `foco` queda siempre a la vista."""
    if n <= sitio:
        return range(n), 0, 0
    filas = recorte(n, foco, max(1, sitio - 1))
    if filas.start > 0 and filas.stop < n:
        filas = recorte(n, foco, max(1, sitio - 2))
    return filas, filas.start, n - filas.stop

