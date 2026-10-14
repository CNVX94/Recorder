"""Transformaciones puras sobre las entradas de una nota.

Ninguna toca el disco. Todas reciben una lista de Entry y devuelven otra nueva,
asi que se prueban sin audio, sin archivos y sin interfaz.

Sobre "quitar numeros": aqui solo se normaliza el andamiaje de marcas de tiempo.
Los numeros del propio texto (puertos, kilos, versiones) NO se tocan nunca:
en un daily tecnico son justo la informacion que hay que conservar.
"""

import dataclasses
from typing import List, Sequence, Tuple

from ..filters.echo import strip_prompt_echo
from .parser import Entry

# Intervalos que ofrece la interfaz. 0 = no agrupar.
INTERVALS = [0, 5, 15, 30, 60]

# Al unir, dos lineas pertenecen al mismo turno de habla si casi no hay hueco entre ellas.
# Sin este limite, media hora de conversacion acaba en un solo parrafo ilegible.
MERGE_GAP_SEC = 45
MERGE_MAX_CHARS = 600
HALF_DAY = 12 * 3600
DAY = 24 * 3600


@dataclasses.dataclass
class DigestOptions:
    interval_min: int = 30  # 0 = sin agrupar
    merge: bool = True  # unir lineas seguidas del mismo hablante
    drop_short_words: int = 0  # descartar lineas con menos de N palabras (0 = ninguna)
    keep_captures: bool = True  # False = texto puro: ni imagen, ni "📸 `clave` →", ni captura manual
    inline_stamps: bool = False  # HH:MM:SS por linea; si no, [HH:MM] por parrafo
    drop_echo: bool = False  # quitar el eco del vocabulario ("Terminos.", listas del prompt)
    vocab: str = ""  # el vocabulario con que se grabo, para reconocer su eco

    def slug(self) -> str:
        """Sufijo del nombre de archivo. Dice lo que hace (reagrupar), no lo que no hace (resumir)."""
        if not self.interval_min:
            return "reagrupada"
        if self.interval_min >= 60 and self.interval_min % 60 == 0:
            return f"reagrupada-{self.interval_min // 60}h"
        return f"reagrupada-{self.interval_min}min"


def bucket_start(seconds: int, minutes: int) -> int:
    """Segundo en que empieza el tramo que contiene a `seconds`."""
    if minutes <= 0:
        return seconds
    size = minutes * 60
    return (seconds // size) * size


def hhmm(seconds: int) -> str:
    return f"{seconds // 3600 % 24:02d}:{seconds % 3600 // 60:02d}"


def sort_by_time(entries: Sequence[Entry]) -> List[Entry]:
    """Ordena por hora, estable. La nota se escribe en orden de transcripcion, no de habla.

    Con cola, una frase de las 17:53:06 se escribe despues del marcador de pausa de las 17:53:25
    (la pausa se anota al pulsar; la frase, al terminar de transcribirla). La clave es relativa a
    la primera entrada para que una reunion que cruza la medianoche no se parta en dos.
    """
    if not entries:
        return []
    base = entries[0].seconds
    return sorted(entries, key=lambda e: (e.seconds - base + HALF_DAY) % DAY)


def group_by_interval(entries: Sequence[Entry], minutes: int) -> List[Tuple[str, List[Entry]]]:
    """Agrupa por tramos de reloj. Devuelve [(etiqueta, entradas), ...] en orden.

    Un tramo con solo marcadores (pausas, avisos) no es un tramo: sus marcadores van al tramo
    anterior (o al siguiente, si no lo hay). Antes, dos pausas pulsadas al cerrar la reunion
    creaban un "## 20:00 - 21:00" vacio.
    """
    if minutes <= 0:
        return [("", list(entries))]
    grupos: List[Tuple[str, List[Entry]]] = []
    for e in entries:
        ini = bucket_start(e.seconds, minutes)
        etiqueta = f"{hhmm(ini)} - {hhmm(ini + minutes * 60)}"
        if grupos and grupos[-1][0] == etiqueta:
            grupos[-1][1].append(e)
        else:
            grupos.append((etiqueta, [e]))

    salida: List[Tuple[str, List[Entry]]] = []
    sueltos: List[Entry] = []  # marcadores antes del primer tramo con contenido
    for etiqueta, grupo in grupos:
        if all(e.source == "pausa" for e in grupo):
            (salida[-1][1] if salida else sueltos).extend(grupo)
        else:
            salida.append((etiqueta, sueltos + grupo))
            sueltos = []
    if sueltos:  # la nota solo tiene marcadores
        salida.append((grupos[0][0], sueltos))
    return salida


def merge_consecutive(
    entries: Sequence[Entry],
    max_gap_sec: int = MERGE_GAP_SEC,
    max_chars: int = MERGE_MAX_CHARS,
) -> List[Entry]:
    """Une lineas seguidas de la misma fuente que pertenecen al mismo turno de habla.

    Solo une si el hueco entre ambas es pequeno y el parrafo resultante no se dispara.
    Una entrada que lleva captura nunca se funde con la vecina, para que la imagen
    quede pegada al texto que la disparo y no se apile al final del bloque.
    """
    salida: List[Entry] = []
    for e in entries:
        previa = salida[-1] if salida else None
        unible = (
            previa is not None
            and previa.source == e.source
            and e.source in ("out", "mic")
            and not previa.captures
            and not e.captures
            and 0 <= e.seconds - previa.last_seconds <= max_gap_sec
            and len(previa.text) + len(e.text) + 1 <= max_chars
        )
        if unible:
            previa.text = f"{previa.text} {e.text}".strip()
            previa.keywords.extend(e.keywords)
            previa.last_seconds = e.seconds
        else:
            nueva = Entry(
                stamp=e.stamp,
                source=e.source,
                text=e.text,
                captures=list(e.captures),
                keywords=list(e.keywords),
            )
            nueva.last_seconds = e.seconds
            salida.append(nueva)
    return salida


def drop_short(entries: Sequence[Entry], min_words: int) -> List[Entry]:
    """Quita el relleno corto ("Si, si, si.", "A ver.") contando palabras.

    Nunca descarta una entrada que lleve captura ni un marcador de pausa:
    ahi el valor no esta en el texto.
    """
    if min_words <= 0:
        return list(entries)
    return [
        e
        for e in entries
        if len(e.text.split()) >= min_words or e.captures or e.source not in ("out", "mic")
    ]


def drop_echo(entries: Sequence[Entry], vocab: str) -> List[Entry]:
    """Quita el eco del vocabulario (filters/echo.py) de las lineas habladas.

    Una linea que era solo eco desaparece, salvo que lleve captura (como en drop_short).
    """
    salida = []
    for e in entries:
        if e.source not in ("out", "mic"):
            salida.append(e)
            continue
        texto = strip_prompt_echo(e.text, vocab)
        if texto or e.captures:
            salida.append(dataclasses.replace(e, text=texto, captures=list(e.captures), keywords=list(e.keywords)))
    return salida


def strip_captures(entries: Sequence[Entry]) -> List[Entry]:
    """Texto puro: quita las imagenes y con ellas su indicador ("📸 `clave` → ...", "tardia") y las
    entradas de captura manual. El texto hablado queda intacto."""
    salida = []
    for e in entries:
        if e.source == "captura":
            continue
        salida.append(
            Entry(stamp=e.stamp, source=e.source, text=e.text, captures=[], keywords=list(e.keywords))
        )
    return salida


def apply_all(entries: Sequence[Entry], opts: DigestOptions) -> List[Entry]:
    """Filtros que no dependen del agrupamiento.

    Unir NO se hace aqui: depende del tramo, asi que se aplica dentro de cada
    grupo en el renderizado. Descartar va primero para que unir no resucite
    lineas que se acababan de tirar. Quitar imagenes va antes que descartar: una
    linea corta o de eco se salva por llevar captura, y sin captura ya no tiene por que.
    """
    salida = sort_by_time(entries)
    if not opts.keep_captures:
        salida = strip_captures(salida)
    if opts.drop_echo:
        salida = drop_echo(salida, opts.vocab)
    return drop_short(salida, opts.drop_short_words)
