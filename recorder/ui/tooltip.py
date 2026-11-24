"""Globo de ayuda (tooltip) para los controles de la ventana, con los textos de recorder/ayuda.py.

Aparece tras RETARDO_MS con el ratón encima o al llegar al control con el teclado (Tab); se va
al salir, al hacer clic, al perder el foco o con Esc. Entra con un fundido de opacidad que sigue
«animations» de config.json y nunca se sale del área útil del monitor. El globo es una ventana
sin marco que se crea al mostrarse y se destruye al ocultarse: mientras está a la vista,
`theme.aplicar_tema` lo repinta como a cualquier otro widget.
"""

import tkinter as tk
from typing import List, Optional, Tuple

from .. import ayuda
from .theme import P, work_area

RETARDO_MS = 450
ANCHO_PX = 320  # ancho del texto a 100 % de escala; se escala con la de Windows
SEPARACION = 6  # píxeles entre el globo y lo que señala
CURSOR_PX = 20  # alto aproximado del puntero: con el ratón, el globo va justo debajo de él
PASO_MS = 20
PASOS_FUNDIDO = {"completas": 6, "reducidas": 2, "ninguna": 0}  # ~120 ms, ~40 ms o sin fundido

animaciones = "completas"  # «animations» de config.json; la ventana principal lo pone al arrancar

Rect = Tuple[int, int, int, int]  # (izquierda, arriba, derecha, abajo) en coordenadas de pantalla


def posicion(ancla: Rect, tamano: Tuple[int, int], area: Rect) -> Tuple[int, int]:
    """Esquina superior izquierda del globo: debajo de `ancla` y alineado a su izquierda; si
    no cabe debajo, encima. Siempre dentro de `area` (el área útil del monitor)."""
    l, t, r, b = area
    ancho, alto = tamano
    x, y = ancla[0], ancla[3] + SEPARACION
    if y + alto > b:
        y = ancla[1] - SEPARACION - alto
    return max(l, min(x, r - ancho)), max(t, min(y, b - alto))


class Tooltip:
    """La ayuda de un control: una o varias claves de recorder/ayuda.py, más su atajo si lo tiene."""

    def __init__(self, widget: tk.Widget, *claves: str, atajo: str = ""):
        for clave in claves:
            ayuda.entrada(clave)  # una clave sin texto falla al construir la ventana, no al pasar el ratón
        self.widget, self.claves, self.atajo = widget, claves, atajo
        self._espera: Optional[str] = None
        self._globo: Optional[tk.Toplevel] = None
        self._esc: Optional[str] = None
        self._por_raton = False
        self._clic = False  # el foco que llega por un clic no muestra el globo (solo el del teclado)
        widget.tooltip = self  # las pruebas recorren los controles y miran qué ayuda llevan
        # Los clics van por botón (<Button-1>, no <ButtonPress>): en Tk solo salta la vinculación
        # más concreta, y un <Button-1> propio del control (el clic de los medidores) taparía otra genérica.
        for evento, accion in (
            ("<Enter>", self._al_entrar), ("<FocusIn>", self._al_enfocar), ("<Leave>", self.ocultar),
            ("<FocusOut>", self._al_desenfocar), ("<Button-1>", self._al_pulsar), ("<Button-3>", self._al_pulsar),
            ("<Destroy>", self.ocultar),
        ):
            widget.bind(evento, accion, add="+")

    def bloques(self) -> List[Tuple[str, str]]:
        """(título, explicación) de cada clave; el atajo, si lo hay, va junto al primer título."""
        bloques = [ayuda.entrada(clave) for clave in self.claves]
        if self.atajo:
            titulo, explicacion = bloques[0]
            bloques[0] = (f"{titulo}  ·  {self.atajo}", explicacion)
        return bloques

    def texto(self) -> str:
        """Lo que dice el globo, en texto plano."""
        return "\n\n".join(f"{t}\n{e}" for t, e in self.bloques())

    # ------------------------------------------------------------------ eventos
    def _al_entrar(self, _evento=None):
        self._programar(por_raton=True)

    def _al_enfocar(self, _evento=None):
        if self._clic:
            self._clic = False
            return
        self._programar(por_raton=False)

    def _al_desenfocar(self, _evento=None):
        self._clic = False
        self.ocultar()

    def _al_pulsar(self, _evento=None):
        self._clic = True
        self.ocultar()

    def _programar(self, por_raton: bool):
        self.ocultar()
        self._por_raton = por_raton
        self._espera = self.widget.after(RETARDO_MS, self.mostrar)

    # ------------------------------------------------------------------ globo
    def mostrar(self):
        self._espera = None
        if self._globo is not None or not self.widget.winfo_viewable():
            return
        k = self.widget.tk.call("tk", "scaling") / (96 / 72)  # 1.0 a 100 %, 1.25 a 125 %...
        globo = tk.Toplevel(self.widget, bg=P.tooltip_fondo, highlightthickness=1, highlightbackground=P.borde)
        globo.withdraw()  # se coloca antes de verse, para que no aparezca un instante en otro sitio
        globo.wm_overrideredirect(True)
        globo.attributes("-topmost", True)
        bloques = self.bloques()
        for i, (titulo, explicacion) in enumerate(bloques):
            ultimo = i == len(bloques) - 1
            for texto, fuente, margen in (
                (titulo, ("Segoe UI Semibold", 9), (6, 0)),
                (explicacion, ("Segoe UI", 9), (0, 6 if ultimo else 0)),
            ):
                tk.Label(
                    globo, text=texto, bg=P.tooltip_fondo, fg=P.tooltip_texto, font=fuente,
                    wraplength=int(ANCHO_PX * k), justify="left", anchor="w",
                ).pack(fill="x", padx=8, pady=margen)
        globo.update_idletasks()
        if self._por_raton:
            px, py = self.widget.winfo_pointerxy()
            ancla = (px, py, px, py + int(CURSOR_PX * k))
        else:
            x0, y0 = self.widget.winfo_rootx(), self.widget.winfo_rooty()
            ancla = (x0, y0, x0 + self.widget.winfo_width(), y0 + self.widget.winfo_height())
        x, y = posicion(ancla, (globo.winfo_reqwidth(), globo.winfo_reqheight()), work_area(self.widget))
        globo.geometry(f"+{x}+{y}")
        pasos = PASOS_FUNDIDO.get(animaciones, 0)
        if pasos:
            globo.attributes("-alpha", 0.0)
        globo.deiconify()
        self._globo = globo
        self._esc = self.widget.winfo_toplevel().bind("<Escape>", self.ocultar, add="+")
        if pasos:
            self._fundir(globo, 1, pasos)

    def _fundir(self, globo: tk.Toplevel, paso: int, pasos: int):
        if globo is not self._globo:
            return  # se ocultó (o ya hay otro) a mitad del fundido
        globo.attributes("-alpha", paso / pasos)
        if paso < pasos:
            globo.after(PASO_MS, self._fundir, globo, paso + 1, pasos)

    def ocultar(self, _evento=None):
        try:
            if self._espera is not None:
                self.widget.after_cancel(self._espera)
            if self._esc is not None:
                self.widget.winfo_toplevel().unbind("<Escape>", self._esc)
            if self._globo is not None:
                self._globo.destroy()
        except tk.TclError:
            pass  # la ventana ya se está cerrando: no queda nada que ocultar
        self._espera = self._esc = self._globo = None


def con_ayuda(widget: tk.Widget, *claves: str, atajo: str = "") -> tk.Widget:
    """Pone a `widget` el globo con las claves de recorder/ayuda.py y lo devuelve (para encadenar .pack/.grid)."""
    Tooltip(widget, *claves, atajo=atajo)
    return widget
