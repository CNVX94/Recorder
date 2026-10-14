"""Lo que una interfaz necesita para ofrecer una sintesis, sin Tkinter.

La ventana «Sintesis de notas» y el comando `daily sintesis` hacen lo mismo con distinta cara:
listar las notas originales, traducir las decisiones del usuario a `DigestOptions`, ensenar la
vista previa con sus cifras y, al confirmar, escribir (`writer.write_digest`). Aqui va la parte
comun. Nada de esto escribe en disco: el original solo se lee.
"""

import dataclasses
import datetime as dt
import pathlib
from typing import Dict, Optional

from .transforms import DigestOptions
from .writer import build_digest

# Como se nombra cada uno de los INTERVALS que ofrece la interfaz.
INTERVAL_LABELS: Dict[int, str] = {0: "Sin agrupar", 5: "Cada 5 min", 15: "Cada 15 min", 30: "Cada 30 min", 60: "Cada hora"}
MIN_WORDS = 4  # «Descartar lineas de menos de N palabras»

# Cabecera del listado de originales, alineada con `note_row`.
NOTE_HEADER = f"{'archivo':<32}{'fecha':<12}{'hora':<8}{'tamaño':>9}"


def digest_options(
    interval_min: int,
    merge: bool = True,
    strip_stamps: bool = True,
    keep_captures: bool = True,
    drop_short: bool = False,
) -> DigestOptions:
    """Traduce las decisiones de la interfaz a `DigestOptions`.

    `strip_stamps` solo cuenta al agrupar: sin agrupar, la marca de tiempo es lo unico que ordena
    y se conserva siempre. `drop_short` descarta las lineas de menos de MIN_WORDS palabras.
    """
    return DigestOptions(
        interval_min=interval_min,
        merge=merge,
        drop_short_words=MIN_WORDS if drop_short else 0,
        keep_captures=keep_captures,
        inline_stamps=not strip_stamps or not interval_min,
    )


@dataclasses.dataclass(frozen=True)
class DigestPreview:
    """La sintesis generada en memoria y sus cifras, para ensenarla antes de confirmar."""

    markdown: str
    source_lines: int  # lineas del original
    blocks: int  # encabezados «## » (tramos)
    lines: int
    kb: int

    def stats(self) -> str:
        return f"{self.source_lines} líneas → {self.blocks} bloques · {self.lines} líneas · ~{self.kb} KB"


def preview_digest(source_path, opts: DigestOptions, now: Optional[dt.datetime] = None) -> DigestPreview:
    """Genera la sintesis sin escribirla, con sus cifras. Lanza lo mismo que `build_digest`."""
    src = pathlib.Path(source_path)
    md = build_digest(src, opts, now=now)
    lineas = md.splitlines()
    return DigestPreview(
        markdown=md,
        source_lines=len(src.read_text(encoding="utf-8").splitlines()),
        blocks=sum(1 for l in lineas if l.startswith("## ")),
        lines=len(lineas),
        kb=len(md) // 1024,
    )


def note_row(path, active_name: Optional[str] = None) -> str:
    """Una fila del listado de originales: nombre, fecha, hora, tamano y si es la nota en curso."""
    p = pathlib.Path(path)
    m = dt.datetime.fromtimestamp(p.stat().st_mtime)
    marca = " ● en curso" if p.name == active_name else ""
    kb = f"{p.stat().st_size / 1024:.0f} KB"
    return f"{p.name:<32}{m:%d/%m/%Y}  {m:%H:%M}  {kb:>9}{marca}"
