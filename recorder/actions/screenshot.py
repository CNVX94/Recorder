import ctypes
import ctypes.wintypes as wt
import datetime as dt
import pathlib
from typing import List, Optional, Tuple
from ..filters.normalizer import normalize

# Intentar habilitar DPI awareness por monitor para coincidencia exacta con Pillow
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass


def monitors() -> List[Tuple[int, int, int, int]]:
    """Devuelve los rectángulos (left, top, right, bottom) de cada monitor en píxeles físicos."""
    rects: List[Tuple[int, int, int, int]] = []
    try:
        proc = ctypes.WINFUNCTYPE(
            ctypes.c_int, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM
        )
        cb = proc(
            lambda h, d, p, l: (
                rects.append((p.contents.left, p.contents.top, p.contents.right, p.contents.bottom)),
                1,
            )[1]
        )
        ctypes.windll.user32.EnumDisplayMonitors(None, None, cb, 0)
    except Exception:
        pass
    return rects


def screen_labels() -> List[str]:
    """Etiquetas descriptivas para selección de monitor en la interfaz."""
    mons = monitors()
    return ["(todas las pantallas)"] + [
        f"Pantalla {i}: {r - l}×{b - t} en ({l}, {t})"
        for i, (l, t, r, b) in enumerate(mons, 1)
    ]


def take_screenshot(tag: str, caps_dir: str, screen_idx: int = 0) -> pathlib.Path:
    """Captura de pantalla multi-monitor y guarda el archivo PNG con marca de tiempo."""
    from PIL import ImageGrab

    d = pathlib.Path(caps_dir)
    d.mkdir(parents=True, exist_ok=True)
    clean_tag = normalize(tag).replace(" ", "-") or "captura"
    file_path = d / f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}_{clean_tag}.png"

    rects = monitors()
    bbox = rects[screen_idx - 1] if 0 < screen_idx <= len(rects) else None
    ImageGrab.grab(bbox=bbox, all_screens=True).save(file_path)
    return file_path
