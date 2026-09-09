"""Transformaciones puras sobre las entradas de una nota.

Ninguna toca el disco. Todas reciben una lista de Entry y devuelven otra nueva,
asi que se prueban sin audio, sin archivos y sin interfaz.

Sobre "quitar numeros": aqui solo se normaliza el andamiaje de marcas de tiempo.
Los numeros del propio texto (puertos, kilos, versiones) NO se tocan nunca:
en un daily tecnico son justo la informacion que hay que conservar.
"""

import dataclasses
from typing import List, Sequence, Tuple

from .parser import Entry

# Intervalos que ofrece la interfaz. 0 = no agrupar.
INTERVALS = [0, 5, 15, 30, 60]

# Al unir, dos lineas pertenecen al mismo turno de habla si casi no hay hueco entre ellas.
# Sin este limite, media hora de conversacion acaba en un solo parrafo ilegible.
MERGE_GAP_SEC = 45
MERGE_MAX_CHARS = 600


@dataclasses.dataclass
class DigestOptions:
    interval_min: int = 30  # 0 = sin agrupar
    merge: bool = True  # unir lineas seguidas del mismo hablante
    drop_short_words: int = 0  # descartar lineas con menos de N palabras (0 = ninguna)
    keep_captures: bool = True  # conservar las capturas incrustadas
    inline_stamps: bool = False  # conservar HH:MM:SS dentro de cada grupo

    def slug(self) -> str:
        """Sufijo del nombre de archivo. Describe el agrupamiento, que es la decision principal."""
        if not self.interval_min:
            return "sintesis"
        if self.interval_min >= 60 and self.interval_min % 60 == 0:
            return f"sintesis-{self.interval_min // 60}h"
        return f"sintesis-{self.interval_min}min"


def bucket_start(seconds: int, minutes: int) -> int:
    """Segundo en que empieza el tramo que contiene a `seconds`."""
    if minutes <= 0:
        return seconds
    size = minutes * 60
    return (seconds // size) * size


def hhmm(seconds: int) -> str:
    return f"{seconds // 3600 % 24:02d}:{seconds % 3600 // 60:02d}"


def group_by_interval(entries: Sequence[Entry], minutes: int) -> List[Tuple[str, List[Entry]]]:
    """Agrupa por tramos de reloj. Devuelve [(etiqueta, entradas), ...] en orden."""
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
    return grupos


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


def strip_captures(entries: Sequence[Entry]) -> List[Entry]:
    """Elimina las referencias a imagenes, dejando el texto intacto."""
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
    lineas que se acababan de tirar.
    """
    salida = drop_short(entries, opts.drop_short_words)
    if not opts.keep_captures:
        salida = strip_captures(salida)
    return salida
