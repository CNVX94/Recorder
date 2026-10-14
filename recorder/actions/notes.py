import datetime as dt
import os
import pathlib
import re
import shutil
import threading
from typing import Optional, Union

RE_IMG = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")  # ![](ruta) y también ![texto alternativo](ruta)


def md_ref(path: Union[str, pathlib.Path], notes_dir: Union[str, pathlib.Path]) -> str:
    """Ruta para incrustar en markdown: relativa a la carpeta de notas, absoluta si es otra unidad."""
    try:
        rel = os.path.relpath(path, notes_dir)
    except ValueError:
        rel = str(path)
    return rel.replace("\\", "/")


def rebase_links(text: str, old_dir: Union[str, pathlib.Path], new_dir: Union[str, pathlib.Path]) -> str:
    """Política pura: reescribe los `![](ruta)` (y `![alt](ruta)`) relativos para que sigan apuntando
    a la misma imagen cuando la nota pasa de `old_dir` a `new_dir`. Las capturas no se mueven; la
    ruta sí. El texto alternativo se conserva."""

    def rebase(m: "re.Match") -> str:
        alt, ref = m.group(1), m.group(2)
        if pathlib.PureWindowsPath(ref).is_absolute() or "://" in ref:
            return m.group(0)
        target = os.path.normpath(os.path.join(old_dir, ref))
        return f"![{alt}]({md_ref(target, new_dir)})"

    return RE_IMG.sub(rebase, text)


class NotesSession:
    """Gestiona el archivo Markdown de la sesión diaria con sincronización concurrente."""

    def __init__(self, notes_dir: Union[str, pathlib.Path], custom_name: Optional[str] = None):
        self.lock = threading.Lock()
        self.notes_dir = pathlib.Path(notes_dir)
        self.notes_dir.mkdir(parents=True, exist_ok=True)
        now = dt.datetime.now()
        filename = custom_name or f"daily_{now:%Y-%m-%d_%H-%M}.md"
        self.file_path = self.notes_dir / filename
        self._write_header(now)

    def _write_header(self, now: dt.datetime):
        with self.lock:
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(f"# Daily {now:%Y-%m-%d %H:%M}\n\n")

    def write_line(self, line: str):
        """Escribe una línea en el archivo de notas Markdown."""
        with self.lock:
            with open(self.file_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def move_notes(self, new_dir: Union[str, pathlib.Path]) -> pathlib.Path:
        """Cambia la carpeta de notas en caliente: mueve el .md de esta sesión.

        Las capturas se quedan donde están (caps_dir no cambia), así que los enlaces relativos
        ya escritos se reescriben para la nueva ubicación: antes se movía el .md sin más y todas
        sus imágenes quedaban rotas.
        """
        target_dir = pathlib.Path(new_dir)
        if target_dir == self.file_path.parent:
            return self.file_path
        target_dir.mkdir(parents=True, exist_ok=True)
        with self.lock:
            old_dir = self.file_path.parent
            new_file = target_dir / self.file_path.name
            shutil.move(str(self.file_path), str(new_file))
            text = new_file.read_text(encoding="utf-8")
            rebased = rebase_links(text, old_dir, target_dir)
            if rebased != text:
                new_file.write_text(rebased, encoding="utf-8")
            self.file_path = new_file
            self.notes_dir = target_dir
            return self.file_path
