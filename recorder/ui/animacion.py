"""Movimiento de la interfaz con `after` de Tk: sin hilos, sin dependencias y sin tocar la paleta.

Todo pasa por `animar`: llama a `paso(v)` con v de 0 a 1 (tras la curva, ease-out por defecto)
como mucho cada PASO_MS (~60 fps). El avance sale del reloj y no de contar pasos, así que un tic
que llega tarde salta adelante en vez de alargar la animación. Cada animación lleva una clave por
widget («alfa», «color», «tema»…): empezar otra con la misma clave cancela la anterior, de modo
que nunca se acumulan dos sobre la misma propiedad. `cancelar` la deja donde esté o, con
`completar`, la lleva al final.

«animations» de config.json (en `modo`; lo pone la ventana al arrancar) decide cuánto dura cada
cosa: «completas», lo pedido; «reducidas», solo fundidos y de CORTO_MS como mucho (lo continuo,
como el pulso del indicador, se queda quieto); «ninguna», cambios instantáneos.
"""

import math
import time
import tkinter as tk

PASO_MS = 16  # ~60 fps como mucho
CORTO_MS = 120  # techo de cualquier fundido con «reducidas»
ENTRADA_MS = 180  # fundido al abrir una ventana o un diálogo
SALIDA_MS = 140  # y al cerrarlo

modo = "completas"  # «animations» de config.json


def ease_out(t: float) -> float:
    """Cúbica que arranca rápida y frena al final."""
    return 1 - (1 - t) ** 3


def mezclar(a: str, b: str, t: float) -> str:
    """El color entre "#rrggbb" `a` (t=0) y `b` (t=1). Los extremos devuelven el color tal cual,
    para que `theme.aplicar_tema` los reconozca después."""
    if t <= 0:
        return a
    if t >= 1:
        return b
    if len(a) != 7 or len(b) != 7:  # un nombre de color de Tk: sin mezcla, salta a mitad
        return b if t >= 0.5 else a
    ca = (int(a[i:i + 2], 16) for i in (1, 3, 5))
    cb = (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def duracion(ms: int, fundido: bool = True) -> int:
    """Cuánto dura de verdad una animación de `ms` con el `modo` actual; 0 = instantánea."""
    if modo == "ninguna":
        return 0
    if modo == "reducidas":
        return min(ms, CORTO_MS) if fundido else 0
    return ms


def _pendientes(widget) -> dict:
    return widget.__dict__.setdefault("_animaciones", {})


def cancelar(widget, clave: str, completar: bool = False) -> None:
    """Para la animación `clave` de `widget`, si hay una; con `completar`, la deja en su final."""
    pendiente = _pendientes(widget).pop(clave, None)
    if pendiente is None:
        return
    after_id, paso, fin = pendiente
    try:
        widget.after_cancel(after_id)
        if completar:
            paso(1.0)
    except tk.TclError:
        return  # el widget ya no existe
    if completar and fin:
        fin()


def animar(widget, clave: str, ms: int, paso, *, fin=None, curva=ease_out, fundido: bool = True,
           cada_ms: int = PASO_MS, reloj=None) -> None:
    """Llama a `paso(curva(t))` con t de 0 a 1 a lo largo de `ms` y después a `fin()`.

    Cancela antes la animación `clave` que tuviera `widget`. Con duración 0 («ninguna») llama una
    sola vez a `paso(1.0)` y a `fin()`, sin `after`. `fundido=False` marca lo que no es un
    fundido de color u opacidad: con «reducidas» también es instantáneo.
    """
    cancelar(widget, clave)
    ms = duracion(ms, fundido)
    reloj = reloj or time.monotonic
    inicio = reloj()

    def tic():
        t = 1.0 if ms <= 0 else min(1.0, (reloj() - inicio) * 1000 / ms)
        try:
            paso(curva(t))
            if t < 1.0:
                _pendientes(widget)[clave] = (widget.after(cada_ms, tic), paso, fin)
                return
        except tk.TclError:
            pass  # el widget se destruyó a mitad: no queda nada que animar
        _pendientes(widget).pop(clave, None)
        if fin:
            try:
                fin()
            except tk.TclError:
                pass

    tic()


def latir(widget, clave: str, periodo_ms: int, paso, *, cada_ms: int = 66, reloj=None) -> None:
    """Pulso continuo y suave hasta `cancelar`: `paso(v)` con v que sube de 0 a 1 y vuelve (coseno)
    cada `periodo_ms`. Es movimiento, no un fundido: con «reducidas» o «ninguna» se queda en v=0.
    ~15 fps bastan para un pulso lento y cuestan una décima parte que 60."""
    cancelar(widget, clave)
    if not duracion(periodo_ms, fundido=False):
        paso(0.0)
        return
    reloj = reloj or time.monotonic
    inicio = reloj()

    def tic():
        fase = ((reloj() - inicio) * 1000 % periodo_ms) / periodo_ms
        try:
            paso((1 - math.cos(2 * math.pi * fase)) / 2)
            _pendientes(widget)[clave] = (widget.after(cada_ms, tic), paso, None)
        except tk.TclError:
            _pendientes(widget).pop(clave, None)

    tic()


# ---------------------------------------------------------------------------- ventanas


def preparar_entrada(win) -> None:
    """Transparente antes de verse, para que `entrar` la haga aparecer sin un fogonazo."""
    if duracion(ENTRADA_MS):
        win.attributes("-alpha", 0.0)


def entrar(win) -> None:
    """Fundido de entrada de una ventana (la principal, un diálogo, un toast)."""
    if duracion(ENTRADA_MS):
        animar(win, "alfa", ENTRADA_MS, lambda v: win.attributes("-alpha", v))


def cerrar(win, fin=None) -> None:
    """Cierra `win` con un fundido de salida y llama a `fin` (por defecto, `win.destroy`).

    Mientras se funde ya no recibe clics (un segundo «Guardar» no guarda dos veces) ni retiene el
    foco de la aplicación. Sin animaciones, o si no se ve (las pruebas la tienen oculta), se
    cierra al momento, como antes.
    """
    fin = fin or win.destroy
    try:
        visible = bool(win.winfo_viewable())
    except tk.TclError:
        visible = False
    if not duracion(SALIDA_MS) or not visible:
        cancelar(win, "alfa")
        fin()
        return
    try:
        win.grab_release()
        win.attributes("-disabled", True)
        desde = float(win.attributes("-alpha"))
    except tk.TclError:
        desde = 1.0
    animar(win, "alfa", SALIDA_MS, lambda v: win.attributes("-alpha", desde * (1 - v)), fin=fin)
