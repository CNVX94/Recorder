import ctypes
import ctypes.wintypes as wt

from ..rutas import recurso

ICONO = "recorder/assets/recorder.ico"  # lo añade el empaquetado; desde el código puede no estar


def app_icon(root):
    """Pone el icono de Recorder a la ventana raíz y, con `default`, a todos los diálogos que abra.
    Si el archivo no está (desde el código) o Tk no lo acepta, no pasa nada."""
    icono = recurso(ICONO)
    if not icono.is_file():
        return
    try:
        root.iconbitmap(default=str(icono))
    except Exception:
        pass


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]


def work_area(win):
    """(left, top, right, bottom) del área útil (sin barra de tareas) del monitor donde está `win`."""
    try:
        info = _MONITORINFO(cbSize=ctypes.sizeof(_MONITORINFO))
        mon = ctypes.windll.user32.MonitorFromWindow(win.winfo_id(), 2)  # MONITOR_DEFAULTTONEAREST
        ctypes.windll.user32.GetMonitorInfoW(mon, ctypes.byref(info))
        r = info.rcWork
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()


def fit_window(win, w: int, h: int):
    """Da a `win` el tamaño de diseño `w`×`h` (pensado a 100 % de escala) sin salirse de la pantalla.

    El proceso es DPI-aware (ver actions/screenshot.py): Tk agranda las fuentes con la escala de
    Windows pero `geometry` va en píxeles físicos, así que un tamaño fijo recorta el contenido a
    125 % o en pantallas pequeñas (monitores virtuales de streaming de 1366×768). Se escala el
    tamaño, se usa el que pide el contenido si es mayor, se limita al área útil del monitor de la
    ventana padre y se centra ahí. Queda redimensionable por si aun así no cabe.
    """
    win.update_idletasks()
    k = win.tk.call("tk", "scaling") / (96 / 72)  # 1.0 a 100 %, 1.25 a 125 %...
    l, t, r, b = work_area(win.master or win)
    chrome = int(40 * k)  # barra de título y bordes que Tk no cuenta en geometry
    w = min(max(int(w * k), win.winfo_reqwidth()), r - l - 16)
    h = min(max(int(h * k), win.winfo_reqheight()), b - t - chrome)
    x, y = l + (r - l - w) // 2, t + max(0, (b - t - h - chrome) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.resizable(True, True)


BG = "#1e1e2e"
PANEL = "#313244"
FG = "#cdd6f4"
DIM = "#7f849c"
ACC = "#f9e2af"
MIC = "#89b4fa"
ERR = "#f38ba8"
SUCCESS = "#a6e3a1"
BORDER = "#45475a"

BTN_STYLE = {
    "bg": PANEL,
    "fg": FG,
    "relief": "flat",
    "activebackground": ACC,
    "activeforeground": BG,
    "padx": 10,
    "font": ("Segoe UI", 10),
}

ENTRY_STYLE = {
    "bg": PANEL,
    "fg": FG,
    "insertbackground": FG,
    "relief": "flat",
    "font": ("Segoe UI", 10),
}

LABEL_STYLE = {
    "bg": BG,
    "fg": DIM,
    "font": ("Segoe UI", 9),
}

HEADER_STYLE = {
    "bg": BG,
    "fg": FG,
    "font": ("Segoe UI Semibold", 11),
}
