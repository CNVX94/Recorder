"""Lectura de una nota diaria de vuelta a estructura.

El original SIEMPRE se abre en modo lectura. Ningun punto de este modulo escribe sobre el.
"""

import dataclasses
import pathlib
import re
from typing import List, Optional

MIC = "\U0001F3A4"  # 🎤
CAM = "\U0001F4F8"  # 📸
PAUSE = "⏸"  # ⏸
PLAY = "▶"  # ▶
# La app escribe la flecha Unicode; se admite tambien "->" por si la nota se edito a mano.
ARROWS = r"(?:→|->)"

# - **10:20:08** texto            /  - **10:20:08** 🎤 texto
RE_ENTRY = re.compile(r"^- \*\*(\d{2}:\d{2}:\d{2})\*\*\s*(" + MIC + r")?\s*(.*)$")
# se admite sangria de 2 o 4 espacios:   - 📸 `clave` → ![](ruta)
RE_CAPTURE = re.compile(r"^\s+- " + CAM + r"\s*`([^`]*)`\s*" + ARROWS + r"\s*!\[\]\(([^)]*)\)")
# captura manual, que va en la propia linea de entrada
RE_MANUAL = re.compile(CAM + r"\s*captura manual\s*" + ARROWS + r"\s*!\[\]\(([^)]*)\)")
RE_MARKER = re.compile(r"^>\s*(" + PAUSE + r"|" + PLAY + r")\s*(\S+)\s*(\d{2}:\d{2}:\d{2})")
RE_TITLE = re.compile(r"^#\s+(.*)$")
# Un archivo derivado lleva este campo en su frontmatter.
RE_ORIGEN = re.compile(r"^origen:\s*(.+)$", re.M)


@dataclasses.dataclass
class Entry:
    """Una linea de la transcripcion."""

    stamp: str  # "HH:MM:SS"
    source: str  # "out" | "mic" | "pausa" | "captura"
    text: str
    captures: List[str] = dataclasses.field(default_factory=list)
    keywords: List[str] = dataclasses.field(default_factory=list)

    # Segundo de la ultima linea absorbida al unir; arranca en el propio.
    last_seconds: int = -1

    def __post_init__(self):
        if self.last_seconds < 0:
            self.last_seconds = self.seconds

    @property
    def seconds(self) -> int:
        h, m, s = (int(x) for x in self.stamp.split(":"))
        return h * 3600 + m * 60 + s


@dataclasses.dataclass
class Note:
    title: str
    entries: List[Entry]
    source_path: Optional[pathlib.Path] = None
    derived_from: Optional[str] = None  # si no es None, esta nota YA es una sintesis

    @property
    def is_derived(self) -> bool:
        return self.derived_from is not None


def parse_text(text: str, source_path: Optional[pathlib.Path] = None) -> Note:
    title = ""
    entries: List[Entry] = []
    derived = None

    m = RE_ORIGEN.search(text)
    if m:
        derived = m.group(1).strip()

    for line in text.splitlines():
        if not title and (m := RE_TITLE.match(line)):
            title = m.group(1).strip()
            continue

        if m := RE_CAPTURE.match(line):
            if entries:  # la captura cuelga de la ultima entrada leida
                kws = [k.strip() for k in m.group(1).split(",") if k.strip()]
                entries[-1].captures.append(m.group(2))
                entries[-1].keywords.extend(kws)
            continue

        if m := RE_MARKER.match(line):
            entries.append(Entry(stamp=m.group(3), source="pausa", text=f"{m.group(1)} {m.group(2)}"))
            continue

        if m := RE_ENTRY.match(line):
            stamp, mic, body = m.group(1), m.group(2), m.group(3).strip()
            if cap := RE_MANUAL.search(body):
                entries.append(
                    Entry(stamp=stamp, source="captura", text="captura manual", captures=[cap.group(1)])
                )
                continue
            entries.append(Entry(stamp=stamp, source="mic" if mic else "out", text=body))

    return Note(title=title, entries=entries, source_path=source_path, derived_from=derived)


def parse_file(path) -> Note:
    """Lee una nota del disco. Solo lectura, nunca abre en escritura."""
    path = pathlib.Path(path)
    return parse_text(path.read_text(encoding="utf-8"), source_path=path)
