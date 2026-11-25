import ctypes
import ctypes.wintypes as wt
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

from .. import paleta
from ..rutas import recurso
from . import animacion

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
    ventana padre y se centra ahí. Queda redimensionable por si aun así no cabe. Como toda ventana
    pasa por aquí al abrirse, aquí recibe también la barra de título del tema y, la primera vez,
    el fundido de entrada (reajustarla después, como «Ampliar» de Reagrupar, no la vuelve a fundir).
    """
    primera = not getattr(win, "_ajustada", False)
    if primera:
        win._ajustada = True
        animacion.preparar_entrada(win)  # antes de update_idletasks, que es lo que la muestra
    win.update_idletasks()
    k = win.tk.call("tk", "scaling") / (96 / 72)  # 1.0 a 100 %, 1.25 a 125 %...
    l, t, r, b = work_area(win.master or win)
    chrome = int(40 * k)  # barra de título y bordes que Tk no cuenta en geometry
    w = min(max(int(w * k), win.winfo_reqwidth()), r - l - 16)
    h = min(max(int(h * k), win.winfo_reqheight()), b - t - chrome)
    x, y = l + (r - l - w) // 2, t + max(0, (b - t - h - chrome) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")
    win.resizable(True, True)
    barra_titulo(win)
    if primera:
        animacion.entrar(win)
    return w, h  # el tamaño puesto: hasta el próximo sondeo de Tk, winfo_width aún da el de antes


# La paleta activa (tokens de recorder/paleta.py). Los widgets leen `P.fondo`, `P.texto`... al
# crearse o repintarse; `aplicar_tema` la cambia en el sitio, así que nadie guarda una copia vieja.
P = SimpleNamespace(**paleta.TEMAS[paleta.POR_DEFECTO])

# Estilos compartidos; `_estilos` los rehace en el sitio con la paleta activa.
BTN_STYLE: dict = {}
ENTRY_STYLE: dict = {}
LABEL_STYLE: dict = {}
HEADER_STYLE: dict = {}


def _estilos():
    BTN_STYLE.update(
        bg=P.superficie, fg=P.texto, relief="flat", activebackground=P.acento,
        activeforeground=P.texto_sobre_acento, padx=10, font=("Segoe UI", 10),
    )
    # El contorno (borde, foco al escribir) marca dónde está el campo: el relleno solo no llega a 3:1.
    ENTRY_STYLE.update(
        bg=P.superficie, fg=P.texto, insertbackground=P.texto, relief="flat", font=("Segoe UI", 10),
        highlightthickness=1, highlightbackground=P.borde, highlightcolor=P.foco,
    )
    LABEL_STYLE.update(bg=P.fondo, fg=P.texto_tenue, font=("Segoe UI", 9))
    HEADER_STYLE.update(bg=P.fondo, fg=P.texto, font=("Segoe UI Semibold", 11))


_estilos()

# Opciones de color de los widgets de Tk que `aplicar_tema` revisa (los alias bg/fg no hacen falta).
OPCIONES_COLOR = (
    "background", "foreground", "activebackground", "activeforeground", "selectcolor",
    "insertbackground", "buttonbackground", "highlightbackground", "highlightcolor", "troughcolor",
    "selectbackground", "selectforeground", "disabledforeground", "readonlybackground",
)
ESTILOS_TTK = ("Digest.Vertical.TScrollbar",)  # estilos ttk con colores de la paleta


def aplicar_tema(raiz, nombre: str, transicion_ms: int = 0) -> str:
    """Pone el tema `nombre` (de config «theme») en caliente y devuelve el que se pinta.

    Es el único punto que cambia el tema: cambia la paleta y los estilos y repinta `raiz` con todo
    lo que cuelga de ella, diálogos abiertos incluidos, sustituyendo cada color del tema anterior
    por el del mismo token (los tokens con el mismo color coinciden en todos los temas, ver
    paleta.py). Los diálogos que se abran después ya leen la paleta nueva.

    Con `transicion_ms`, cada color va del viejo al nuevo en un fundido cruzado (si «animations»
    lo permite); la paleta, los estilos y la barra de título cambian ya. Un fundido a medias se
    completa antes de empezar otro: un color intermedio no se reconocería al sustituir.
    """
    animacion.cancelar(raiz, "tema", completar=True)
    resuelto = paleta.resolver(nombre)
    nuevo = paleta.TEMAS[resuelto]
    cambio = {color: nuevo[token] for token, color in vars(P).items()}
    vars(P).update(nuevo)
    _estilos()
    estilo = ttk.Style(raiz)
    for nombre_estilo in ESTILOS_TTK:
        viejos = estilo.configure(nombre_estilo) or {}
        nuevos = {op: cambio[str(v)] for op, v in viejos.items() if str(v) in cambio}
        if nuevos:
            estilo.configure(nombre_estilo, **nuevos)
    pendientes = []  # (configurar, {opción: (color viejo, color nuevo)})
    _repintar(raiz, cambio, pendientes)

    def paso(v):
        for configurar, opciones in pendientes:
            try:
                configurar(**{op: animacion.mezclar(a, b, v) for op, (a, b) in opciones.items()})
            except tk.TclError:
                pass  # un diálogo que se cerró a mitad del fundido

    animacion.animar(raiz, "tema", transicion_ms, paso)
    return resuelto


def _repintar(w, cambio: dict, pendientes: list):
    opciones = {}
    for op in OPCIONES_COLOR:
        try:
            valor = str(w.cget(op))
        except tk.TclError:
            continue  # este widget no tiene esa opción
        if valor in cambio and cambio[valor] != valor:
            opciones[op] = (valor, cambio[valor])
    if opciones:
        pendientes.append((w.configure, opciones))
    if isinstance(w, tk.Text):
        for tag in w.tag_names():
            tag_opciones = {}
            for op in ("foreground", "background"):
                valor = str(w.tag_cget(tag, op))
                if valor in cambio and cambio[valor] != valor:
                    tag_opciones[op] = (valor, cambio[valor])
            if tag_opciones:
                pendientes.append((lambda _t=tag, _w=w, **o: _w.tag_configure(_t, **o), tag_opciones))
    if isinstance(w, (tk.Tk, tk.Toplevel)):
        barra_titulo(w)
    elif isinstance(w, tk.Scrollbar):
        scroll_nativo(w)
    for hijo in w.winfo_children():
        _repintar(hijo, cambio, pendientes)


HOVER_MS = 120


def con_anillo(padre, crear):
    """`crear(marco)` dentro de un marco de 2 px que toma el color de foco (>= 3:1 sobre el fondo)
    mientras el control tiene el foco del teclado; devuelve el control (el marco es su `master`).

    Tk en Windows marca el foco de botones y etiquetas solo con el punteado nativo: no pinta
    `highlightcolor` (Entry y Text sí). El anillo es, por eso, el fondo de este marco.
    """
    marco = tk.Frame(padre, bg=P.fondo, padx=2, pady=2)
    control = crear(marco)
    control.pack(fill="both", expand=True)
    control.bind("<FocusIn>", lambda _e: marco.configure(bg=P.foco), add="+")
    control.bind("<FocusOut>", lambda _e: marco.configure(bg=P.fondo), add="+")
    return control


def boton_vivo(boton: tk.Button, reposo: str = "superficie", encima: str = "superficie_elevada") -> tk.Button:
    """Transición de color al pasar el ratón y al soltar el clic (los tokens de la paleta en
    reposo y encima). Mientras se pulsa, Windows pinta `activebackground` (el acento); al soltar,
    el color vuelve de medio acento al de encima en vez de saltar."""
    def ir(desde: str, token: str):
        hasta = getattr(P, token)
        animacion.animar(boton, "color", HOVER_MS, lambda v: boton.configure(bg=animacion.mezclar(desde, hasta, v)))

    def soltar(_e):
        # Soltado fuera (se arrastró el ratón): vuelve al reposo, no se queda resaltado
        dentro = boton.winfo_containing(*boton.winfo_pointerxy()) is boton
        ir(animacion.mezclar(getattr(P, encima), P.acento, 0.5), encima if dentro else reposo)

    boton.bind("<Enter>", lambda _e: ir(str(boton.cget("bg")), encima), add="+")
    boton.bind("<Leave>", lambda _e: ir(str(boton.cget("bg")), reposo), add="+")
    boton.bind("<ButtonRelease-1>", soltar, add="+")
    return boton


DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # Windows 10 20H1 en adelante
SWP_REFRESCAR_MARCO = 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED


def barra_titulo(win):
    """Barra de título oscura o clara según la paleta activa. Si Windows no lo admite, se queda la suya."""
    try:
        win.update_idletasks()  # que exista el marco de Windows de la ventana
        hwnd = int(win.wm_frame(), 16)
        oscura = ctypes.c_int(paleta.es_oscuro(vars(P)))
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(oscura), ctypes.sizeof(oscura)
        )
        ctypes.windll.user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, SWP_REFRESCAR_MARCO)  # repinta ya, no al pasar el ratón
    except Exception:
        pass


def scroll_nativo(barra):
    """La barra de desplazamiento de Tk es la de Windows y no admite colores: se le pone el tema
    oscuro o claro del Explorador, para que no quede un bloque blanco en el tema oscuro."""
    try:
        tema = "DarkMode_Explorer" if paleta.es_oscuro(vars(P)) else "Explorer"
        ctypes.windll.uxtheme.SetWindowTheme(barra.winfo_id(), tema, None)
    except Exception:
        pass
