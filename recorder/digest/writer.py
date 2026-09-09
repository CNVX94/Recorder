"""Generacion de sintesis a partir de una nota diaria.

Garantia central del modulo: **la nota original nunca se modifica**. Solo se lee.
Cada sintesis es un archivo nuevo, con nombre distinto, que ademas guarda en su
cabecera de que original salio. Como las sintesis pierden informacion (agrupar por
hora impide volver a partir por minutos), este modulo se niega a derivar desde otra
sintesis y te remite al original.
"""

import datetime as dt
import pathlib
from typing import List, Optional

from .parser import CAM, MIC, Note, parse_file
from .transforms import DigestOptions, apply_all, group_by_interval, merge_consecutive

SEP = "_sintesis"  # marca en el nombre que el archivo es derivado
AVISO = (
    "Sintesis derivada y con perdida de detalle. "
    "Para otro agrupamiento, regenera desde el origen; no desde este archivo."
)


class DerivedSourceError(Exception):
    """Se intento derivar desde una sintesis en vez de desde el original."""


class WouldOverwriteSourceError(Exception):
    """El destino calculado coincide con el archivo de origen."""


def is_digest(path) -> bool:
    """Un archivo es sintesis si su cabecera declara un origen."""
    try:
        head = pathlib.Path(path).read_text(encoding="utf-8")[:400]
    except OSError:
        return False
    return "origen:" in head


def list_originals(notes_dir) -> List[pathlib.Path]:
    """Notas originales de la carpeta, de mas reciente a mas antigua. Excluye sintesis."""
    d = pathlib.Path(notes_dir)
    if not d.is_dir():
        return []
    notas = [p for p in d.glob("*.md") if SEP not in p.stem and not is_digest(p)]
    return sorted(notas, key=lambda p: p.stat().st_mtime, reverse=True)


def digest_path(source_path, opts: DigestOptions) -> pathlib.Path:
    """Ruta base del clon. Mismo directorio que el original, para que las rutas de las capturas sigan siendo validas."""
    p = pathlib.Path(source_path)
    return p.with_name(f"{p.stem}_{opts.slug()}{p.suffix}")


def unique_digest_path(source_path, opts: DigestOptions, limit: int = 99) -> pathlib.Path:
    """Como digest_path, pero numerando si ya existe. Nunca devuelve un archivo que haya que sobrescribir."""
    base = digest_path(source_path, opts)
    if not base.exists():
        return base
    for n in range(2, limit + 1):
        cand = base.with_name(f"{base.stem} ({n}){base.suffix}")
        if not cand.exists():
            return cand
    raise FileExistsError(f"demasiadas sintesis con el nombre {base.name}")


def _describe(opts: DigestOptions) -> str:
    partes = ["sin agrupar" if not opts.interval_min else f"tramos de {opts.interval_min} min"]
    if opts.merge:
        partes.append("lineas seguidas unidas")
    if opts.drop_short_words:
        partes.append(f"descartadas lineas de menos de {opts.drop_short_words} palabras")
    if not opts.keep_captures:
        partes.append("sin capturas")
    if opts.inline_stamps:
        partes.append("con marca de tiempo por linea")
    return ", ".join(partes)


def render(note: Note, opts: DigestOptions, source_name: str, now: Optional[dt.datetime] = None) -> str:
    """Convierte una nota ya transformada en Markdown."""
    now = now or dt.datetime.now()
    out = [
        "---",
        f"origen: {source_name}",
        f"generado: {now:%Y-%m-%d %H:%M}",
        f"agrupacion: {opts.interval_min} min" if opts.interval_min else "agrupacion: ninguna",
        f"opciones: {_describe(opts)}",
        f"aviso: {AVISO}",
        "---",
        "",
        f"# {note.title or source_name}" + (f" - sintesis {opts.interval_min} min" if opts.interval_min else " - sintesis"),
        "",
    ]

    entradas = apply_all(note.entries, opts)
    for etiqueta, grupo in group_by_interval(entradas, opts.interval_min):
        if opts.merge:  # unir dentro del tramo, nunca a traves de tramos
            grupo = merge_consecutive(grupo)
        if etiqueta:
            out.append(f"## {etiqueta}")
            out.append("")
        for e in grupo:
            if e.source == "pausa":
                out.append(f"> {e.text} {e.stamp}")
                out.append("")
                continue
            marca = f"**{e.stamp}** " if (opts.inline_stamps or not opts.interval_min) else ""
            voz = f"{MIC} " if e.source == "mic" else ""
            out.append(f"- {marca}{voz}{e.text}".rstrip())
            for c in e.captures:
                claves = ", ".join(dict.fromkeys(e.keywords)) or "captura"
                out.append(f"  - {CAM} `{claves}` → ![]({c})")
        out.append("")

    return "\n".join(out).rstrip() + "\n"


def build_digest(source_path, opts: DigestOptions, now: Optional[dt.datetime] = None) -> str:
    """Lee el original y devuelve el Markdown de la sintesis, sin escribir nada."""
    src = pathlib.Path(source_path)
    note = parse_file(src)
    if note.is_derived:
        raise DerivedSourceError(
            f"'{src.name}' ya es una sintesis de '{note.derived_from}'. "
            "Genera siempre desde el original: agrupar es una operacion con perdida."
        )
    return render(note, opts, src.name, now=now)


def write_digest(source_path, opts: DigestOptions, now: Optional[dt.datetime] = None) -> pathlib.Path:
    """Escribe la sintesis en un archivo nuevo y devuelve su ruta. El original no se toca."""
    src = pathlib.Path(source_path)
    contenido = build_digest(src, opts, now=now)
    destino = unique_digest_path(src, opts)  # nunca sobrescribe una sintesis anterior
    if destino.resolve() == src.resolve():
        raise WouldOverwriteSourceError(f"el destino coincide con el origen: {src}")
    destino.write_text(contenido, encoding="utf-8")
    return destino
