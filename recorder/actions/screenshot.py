import ctypes
import ctypes.wintypes as wt
import datetime as dt
import pathlib
import re
from typing import List, Optional, Tuple
from ..filters.normalizer import normalize

# Intentar habilitar DPI awareness por monitor para coincidencia exacta con Pillow
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

Rect = Tuple[int, int, int, int]

# Constantes Win32 para capturar una ventana sin traerla al frente ni tocar el foco
PW_RENDERFULLCONTENT = 0x2  # PrintWindow: DWM dibuja la ventana completa aunque esté tapada
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x80  # ventanas auxiliares que no salen en la barra de tareas
DWMWA_EXTENDED_FRAME_BOUNDS = 9  # marco visible, sin el borde invisible de sombra de Win10/11
DWMWA_CLOAKED = 14  # ventanas UWP "fantasma": EnumWindows las lista pero no se ven en pantalla
BLACK_MAX = 10  # brillo máximo (0..255) por debajo del cual una captura se considera negra


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG), ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
    ]


def monitors() -> List[Rect]:
    """Devuelve los rectángulos (left, top, right, bottom) de cada monitor en píxeles físicos."""
    rects: List[Rect] = []
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


def windows() -> List[Tuple[int, str]]:
    """(hwnd, título) de las ventanas de aplicación abiertas, en orden Z (la activa primero).

    Quedan fuera las invisibles, las sin título, las de herramienta (WS_EX_TOOLWINDOW), las
    "cloaked" (fantasmas UWP como 'Configuración', que EnumWindows lista con tamaño de pantalla
    completa pero no existen en el escritorio) y el propio escritorio (clase Progman).
    Las minimizadas sí se listan: son aplicaciones reales que el usuario puede querer elegir.
    """
    u, dwm = ctypes.windll.user32, ctypes.windll.dwmapi
    found: List[Tuple[int, str]] = []

    def keep(h, _):
        n = u.GetWindowTextLengthW(h)
        if not n or not u.IsWindowVisible(h) or u.GetWindowLongW(h, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
            return 1
        cloaked, cls = ctypes.c_int(0), ctypes.create_unicode_buffer(32)
        dwm.DwmGetWindowAttribute(h, DWMWA_CLOAKED, ctypes.byref(cloaked), 4)
        u.GetClassNameW(h, cls, 32)
        if cloaked.value or cls.value == "Progman":
            return 1
        title = ctypes.create_unicode_buffer(n + 1)
        u.GetWindowTextW(h, title, n + 1)
        found.append((h, title.value))
        return 1

    try:
        u.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_int, wt.HWND, wt.LPARAM)(keep), 0)
    except Exception:
        pass
    return found


def window_titles() -> List[str]:
    """Títulos de las ventanas abiertas, para el selector de la interfaz."""
    return [t for _, t in windows()]


def app_name(title: str) -> str:
    """Nombre de aplicación de un título de ventana: el último tramo tras ' - ' o ' | '.

    'Chat | Equipo | Microsoft Teams' -> 'Microsoft Teams'; 'notas.txt - Bloc de notas' -> 'Bloc de notas'.
    """
    return re.split(r" [-|–—] ", title)[-1].strip() or title


def pick_window(wanted: str, titles: List[str]) -> Optional[str]:
    """Política pura: qué ventana abierta corresponde a la guardada en config, o None.

    1. Título exacto.
    2. Misma aplicación (mismo tramo final del título, sin distinguir mayúsculas): Teams cambia
       el título según el chat o la reunión activa, así que "Chat | Equipo | Microsoft Teams"
       guardado ayer debe valer hoy para "Reunión semanal | Microsoft Teams". Si hay varias
       ventanas de la misma aplicación gana la primera de `titles` (la más arriba en el orden Z).
    3. None: el llamador captura la pantalla configurada en su lugar.
    """
    if not wanted:
        return None
    if wanted in titles:
        return wanted
    app = app_name(wanted).casefold()
    return next((t for t in titles if app_name(t).casefold() == app), None)


def find_window(wanted: str) -> Optional[int]:
    """hwnd de la ventana configurada, o None si no hay ninguna abierta que corresponda.

    Las minimizadas cuentan como no disponibles: PrintWindow devuelve basura con ellas
    (un rectángulo de 160×28 gris) y restaurarlas robaría el foco al usuario.
    """
    if not wanted:
        return None
    u = ctypes.windll.user32
    open_ = [(h, t) for h, t in windows() if not u.IsIconic(h)]
    title = pick_window(wanted, [t for _, t in open_])
    return next((h for h, t in open_ if t == title), None)


def window_rect(hwnd: int) -> Rect:
    """Marco visible de la ventana en píxeles físicos (sin el borde invisible de sombra de Win10/11)."""
    r = wt.RECT()
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(r), ctypes.sizeof(r)
    )
    if hr != 0:  # sin DWM vale el rectángulo clásico
        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def is_black(img) -> bool:
    """True si la imagen es (casi) negra: ningún píxel supera BLACK_MAX de brillo."""
    return img.convert("L").getextrema()[1] < BLACK_MAX


def grab_window(hwnd: int):
    """Imagen (PIL) de la ventana aunque esté tapada por otras, o None si sale negra.

    Usa PrintWindow con PW_RENDERFULLCONTENT: la ventana se dibuja en un bitmap en memoria
    sin traerla al frente ni tocar el foco. Comprobado en Windows 11 con Teams (WebView2),
    el Explorador y Tk, tapadas por otras ventanas: sale su contenido real. Sin esa bandera
    Teams sale negro. Algunas ventanas no se dejan dibujar así y devuelven negro puro;
    entonces se devuelve None y el llamador decide el plan B.
    """
    from PIL import Image

    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    r = wt.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    w, h = r.right - r.left, r.bottom - r.top
    if w <= 0 or h <= 0:
        return None
    hdc = u.GetDC(None)
    mem = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, w, h)
    g.SelectObject(mem, bmp)
    u.PrintWindow(hwnd, mem, PW_RENDERFULLCONTENT)
    info = _BITMAPINFOHEADER(
        biSize=ctypes.sizeof(_BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32
    )
    buf = ctypes.create_string_buffer(w * h * 4)
    g.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(info), 0)
    g.DeleteObject(bmp)
    g.DeleteDC(mem)
    u.ReleaseDC(None, hdc)
    img = Image.frombytes("RGB", (w, h), buf.raw, "raw", "BGRX", 0, 1)
    # PrintWindow deja negro el borde invisible (~8 px) que rodea a las ventanas: se recorta
    l, t, rr, b = window_rect(hwnd)
    img = img.crop((l - r.left, t - r.top, rr - r.left, b - r.top))
    return None if is_black(img) else img


def take_screenshot(tag: str, caps_dir: str, screen_idx: int = 0, window: str = "") -> pathlib.Path:
    """Captura y guarda un PNG con marca de tiempo; devuelve su ruta.

    Objetivo, por prioridad:
    1. `window` (título de una ventana de aplicación) si está abierta y no minimizada: se dibuja
       con PrintWindow aunque esté tapada. Si PrintWindow la devuelve negra, se recorta lo que
       haya visible en su zona de pantalla (puede ser otra ventana encima; es el mejor plan B).
    2. `screen_idx`: 0 = todas las pantallas, n = monitor n. También es el plan B cuando la
       ventana configurada no existe, está minimizada o falla cualquier llamada Win32:
       una captura nunca revienta al transcriptor.
    """
    from PIL import ImageGrab

    d = pathlib.Path(caps_dir)
    d.mkdir(parents=True, exist_ok=True)
    clean_tag = normalize(tag).replace(" ", "-") or "captura"
    file_path = d / f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}_{clean_tag}.png"

    img = None
    try:
        hwnd = find_window(window)
        if hwnd:
            img = grab_window(hwnd)
            if img is None:  # ventana que PrintWindow no sabe dibujar: lo visible en su rectángulo
                img = ImageGrab.grab(bbox=window_rect(hwnd), all_screens=True)
    except Exception:
        img = None  # ponytail: cualquier fallo Win32 degrada a captura de pantalla, no se propaga
    if img is None:
        rects = monitors()
        bbox = rects[screen_idx - 1] if 0 < screen_idx <= len(rects) else None
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
    img.save(file_path)
    return file_path
