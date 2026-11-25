"""La introducción animada en la ventana: la pantalla de bienvenida y «Ver introducción» de «Más».

Reproduce lo que describe el contrato (recorder/assets/intro/intro.json; el guion, con sus tiempos y
sus fundidos, es `recorder.intro.Guion`): una ventana sin bordes, centrada, con un lienzo de Canvas
donde se mueven los fotogramas del logotipo, los textos y las formas. Cada tic pinta el instante que
marca el reloj (el avance sale del reloj, como en `animacion.animar`), así que dura lo mismo en un
equipo lento. Los elementos se crean una vez y solo se tocan los que cambian.

Saltar (Esc, Enter, Espacio, clic o el botón) y llegar al final son lo mismo: se cancela lo pendiente,
la ventana se funde y recién entonces se llama a `al_terminar` (la ventana principal no se ve antes).
Con «animations» en «reducidas» solo hay fundidos y el logotipo es el fotograma estático; con
«ninguna» no se crea (lo decide `recorder.intro.debe_mostrarse`).
"""
import time
import tkinter as tk
from tkinter import font as tkfont
from typing import Callable, Dict, List, Optional

from PIL import Image, ImageTk

from .. import ayuda, intro
from . import animacion
from .theme import P, work_area

ANILLO_SEPARACION = 3  # unidades de diseño entre el botón y su anillo de foco
ANILLO_GROSOR = 2
TECLAS_SALTO = ("<Escape>", "<Return>", "<KP_Enter>", "<space>")
PESO_SEMIBOLD = "semibold"  # el valor del contrato que pide la variante Semibold de la familia


class Introduccion:
    """La ventana de la introducción. `mostrar()` la abre; `al_terminar()` se llama cuando ya se fue."""

    def __init__(
        self,
        raiz: tk.Misc,
        contrato: dict,
        animaciones: str,
        al_terminar: Optional[Callable[[], None]] = None,
        reloj: Callable[[], float] = time.monotonic,
    ):
        self.raiz = raiz
        self.c = contrato
        self.al_terminar = al_terminar
        self._reloj = reloj
        self.guion = intro.Guion(contrato, animaciones == intro.REDUCIDAS, animacion.CORTO_MS)
        self.k = raiz.tk.call("tk", "scaling") / (96 / 72)  # 1.0 a 100 %, 1.25 a 125 %…
        self.terminada = False
        self.inicio: Optional[float] = None  # cuándo arrancó el guion (tras el fundido de entrada)
        self.medida_ms: Optional[float] = None  # lo que duró el guion, para medirlo
        self._tic_id: Optional[str] = None
        self._cerrando = False
        self._cache: Dict[tuple, object] = {}
        self._fotos: Dict[int, ImageTk.PhotoImage] = {}
        self._construir()

    # ------------------------------------------------------------------ construcción
    def _u(self, unidades: float) -> int:
        """Unidades de diseño a píxeles con la escala de la pantalla."""
        return round(unidades * self.k)

    def _color(self, token: str) -> str:
        return getattr(P, token)

    def _fuente(self, estilo: dict) -> tkfont.Font:
        """La familia preferida que haya, en su variante Semibold si el contrato la pide y existe."""
        presentes = set(tkfont.families(self.win))
        familia = next((f for f in self.c["tipografia"]["familias"] if f in presentes), "TkDefaultFont")
        peso = "normal"
        if estilo.get("peso") == PESO_SEMIBOLD:
            if f"{familia} Semibold" in presentes:
                familia = f"{familia} Semibold"
            else:
                peso = "bold"
        return tkfont.Font(root=self.win, family=familia, size=estilo["puntos"], weight=peso)

    def _construir(self) -> None:
        c, lienzo = self.c, self.c["lienzo"]
        self.win = win = tk.Toplevel(self.raiz, bg=self._color(lienzo["color"]))
        win.withdraw()  # se coloca y se pinta antes de verse
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        ancho, alto = self._u(lienzo["ancho"]), self._u(lienzo["alto"])
        l, t, r, b = work_area(self.raiz)
        win.geometry(f"{ancho}x{alto}+{l + (r - l - ancho) // 2}+{t + (b - t - alto) // 2}")
        self.canvas = tk.Canvas(win, width=ancho, height=alto, bg=self._color(lienzo["color"]),
                                highlightthickness=0, takefocus=0)
        self.canvas.pack()

        tipo, disp, ilu = c["tipografia"], c["disposicion"], c["ilustracion"]
        self._fuentes = {nombre: self._fuente(estilo) for nombre, estilo in tipo.items() if isinstance(estilo, dict)}
        ox, oy = disp["ilustracion"]["origen"]
        self._origen = (ox, oy)

        eq = ilu["equipo"]
        self._equipo = self.canvas.create_rectangle(0, 0, 0, 0, width=self._u(eq["grosor"]), state="hidden")
        self._base = self.canvas.create_line(0, 0, 0, 0, width=self._u(eq["grosor_base"]), state="hidden")
        cap = ilu["captura"]
        self._captura = self.canvas.create_rectangle(0, 0, 0, 0, width=1, state="hidden")
        self._franja = self.canvas.create_rectangle(0, 0, 0, 0, width=0, state="hidden")
        self._trazos: List[int] = [
            self.canvas.create_rectangle(0, 0, 0, 0, width=0, state="hidden") for _ in ilu["lineas"]["trazos"]
        ]

        self._rotulo = self.canvas.create_text(
            self._u(disp["rotulo"]["centro"][0]), self._u(disp["rotulo"]["centro"][1]), anchor="center",
            font=self._fuentes["rotulo"], state="hidden")
        self._titulo = self.canvas.create_text(
            self._u(disp["titulo"]["origen"][0]), self._u(disp["titulo"]["origen"][1]), anchor="nw",
            font=self._fuentes["titulo"], state="hidden")
        self._subtitulo = self.canvas.create_text(
            self._u(disp["subtitulo"]["origen"][0]), self._u(disp["subtitulo"]["origen"][1]), anchor="nw",
            font=self._fuentes["subtitulo"], state="hidden")

        # «Saltar» y la pista de teclas están desde el primer fotograma y no se mueven ni se funden.
        self.canvas.create_text(
            self._u(disp["pista"]["origen"][0]), self._u(disp["pista"]["origen"][1]), anchor="w",
            text=ayuda.texto_intro("intro.pista"), font=self._fuentes["pista"],
            fill=self._color(tipo["pista"]["color"]))
        x0, y0, x1, y1 = (self._u(v) for v in disp["boton"]["caja"])
        a = self._u(ANILLO_SEPARACION)
        self._anillo = self.canvas.create_rectangle(
            x0 - a, y0 - a, x1 + a, y1 + a, outline=self._color(c["boton"]["anillo_foco"]), width=self._u(ANILLO_GROSOR))
        self._boton = self.canvas.create_rectangle(x0, y0, x1, y1, width=1)
        self._boton_texto = self.canvas.create_text((x0 + x1) // 2, (y0 + y1) // 2, anchor="center",
                                                    font=self._fuentes["boton"])
        self._logo = self.canvas.create_image(0, 0)  # el último: va por encima de todo
        self._cargar_logotipo()

        self.canvas.bind("<Button-1>", lambda _e: self.saltar())
        for tecla in TECLAS_SALTO:
            win.bind(tecla, lambda _e: self.saltar())
        win.protocol("WM_DELETE_WINDOW", self.saltar)

    def _cargar_logotipo(self) -> None:
        """Reduce cada fotograma una sola vez, al cargar, a los píxeles que ocupa en pantalla."""
        logo = self.c["logotipo"]
        lado = self._u(logo["lado"])
        numeros = [0] if self.guion.reducido else [0, *range(1, logo["fotogramas"] + 1)]
        for n in numeros:
            archivo = logo["estatico"] if n == 0 else logo["patron"].format(n=n)
            with Image.open(intro.ruta_asset(archivo)) as hoja:
                hoja = hoja.convert("RGBA")
                if hoja.width != lado:
                    hoja = hoja.resize((lado, lado), Image.LANCZOS)
                self._fotos[n] = ImageTk.PhotoImage(hoja, master=self.win)

    # ------------------------------------------------------------------ pintar
    def _config(self, item: int, **opciones) -> None:
        """`itemconfigure` solo de lo que cambió: en cada tic casi todo sigue igual."""
        clave = (item, "cfg")
        previo = self._cache.setdefault(clave, {})
        cambios = {k: v for k, v in opciones.items() if previo.get(k) != v}
        if cambios:
            self.canvas.itemconfigure(item, **cambios)
            previo.update(cambios)

    def _coords(self, item: int, *valores: float) -> None:
        pixeles = tuple(self._u(v) for v in valores)
        if self._cache.get((item, "xy")) != pixeles:
            self.canvas.coords(item, *pixeles)
            self._cache[(item, "xy")] = pixeles

    def _tinta(self, token: str, opacidad: float) -> str:
        """El color de `token` a esa opacidad sobre el fondo del lienzo (no hay transparencia por elemento)."""
        return animacion.mezclar(self._color(self.c["lienzo"]["color"]), self._color(token), opacidad)

    def _visible(self, item: int, opacidad: float, **opciones) -> None:
        self._config(item, state="normal" if opacidad > 0 else "hidden", **opciones)

    def _pintar(self, t: float) -> None:
        e = self.guion.estado(t)
        c, ilu, disp, tipo = self.c, self.c["ilustracion"], self.c["disposicion"], self.c["tipografia"]
        ox, oy = self._origen

        eq = ilu["equipo"]
        x0, y0, x1, y1 = eq["pantalla"]
        self._coords(self._equipo, ox + x0, oy + y0, ox + x1, oy + y1)
        self._visible(self._equipo, e.equipo, outline=self._tinta(eq["color"], e.equipo))
        x0, y0, x1, y1 = eq["base"]
        self._coords(self._base, ox + x0, oy + y0, ox + x1, oy + y1)
        self._visible(self._base, e.base, fill=self._tinta(eq["color"], e.base))

        fondo = self._color(c["lienzo"]["color"])
        for item, trazo in zip(self._trazos, e.trazos):
            self._coords(item, ox + trazo.x, oy + trazo.y - trazo.alto / 2, ox + trazo.x + trazo.ancho, oy + trazo.y + trazo.alto / 2)
            onda, linea, nota = (self._color(token) for token in trazo.tokens)
            color = animacion.mezclar(animacion.mezclar(onda, linea, trazo.teñido), nota, trazo.en_nota)
            self._config(item, state="normal", fill=animacion.mezclar(fondo, color, trazo.opacidad))

        cap = ilu["captura"]
        x0, y0, x1, y1 = cap["caja"]
        self._coords(self._captura, ox + x0, oy + y0, ox + x1, oy + y1)
        self._visible(self._captura, e.captura, fill=self._tinta(cap["fondo"], e.captura),
                      outline=self._tinta(cap["borde"], e.captura))
        x0, y0, x1, y1 = cap["franja"]
        self._coords(self._franja, ox + x0 + 1, oy + y0 + 1, ox + x1 - 1, oy + y1)
        self._visible(self._franja, e.captura, fill=self._tinta(cap["color_franja"], e.captura))

        self._visible(self._rotulo, e.rotulo, text=ayuda.texto_intro("intro.nombre"),
                      fill=self._tinta(tipo["rotulo"]["color"], e.rotulo))
        for item, elemento, (clave, opacidad) in (
            (self._titulo, "titulo", e.titulo), (self._subtitulo, "subtitulo", e.subtitulo),
        ):
            self._visible(item, opacidad if clave else 0, text=ayuda.texto_intro(clave) if clave else "",
                          fill=self._tinta(tipo[elemento]["color"], opacidad))

        sec, pri = c["boton"]["secundario"], c["boton"]["principal"]
        mezcla = lambda campo: animacion.mezclar(self._color(sec[campo]), self._color(pri[campo]), e.boton)  # noqa: E731
        self._config(self._boton, fill=mezcla("fondo"), outline=mezcla("borde"))
        self._config(self._boton_texto, fill=mezcla("texto"),
                     text=ayuda.texto_intro((pri if e.boton >= 0.5 else sec)["rotulo"]))

        self._coords(self._logo, *e.logo_centro)
        self._config(self._logo, image=self._fotos[e.logo])

    # ------------------------------------------------------------------ vida
    def mostrar(self) -> None:
        """La abre con el fundido de siempre; el guion arranca al terminar de entrar."""
        self._pintar(0)
        animacion.preparar_entrada(self.win)
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        animacion.animar(self.win, "alfa", animacion.ENTRADA_MS, lambda v: self.win.attributes("-alpha", v),
                         fin=self._empezar)

    def _empezar(self) -> None:
        if self._cerrando:
            return
        self.inicio = self._reloj()
        self._tic()

    def _tic(self) -> None:
        if self._cerrando or self.inicio is None:
            return
        t = (self._reloj() - self.inicio) * 1000
        try:
            self._pintar(min(t, self.guion.total_ms))
            if t < self.guion.total_ms:
                self._tic_id = self.win.after(animacion.PASO_MS, self._tic)
                return
        except tk.TclError:
            return  # la ventana se destruyó a mitad (se cerró la aplicación)
        self.saltar()

    def saltar(self) -> None:
        """Termina ya: cancela lo pendiente, funde la ventana y avisa. Llegar al final hace lo mismo."""
        if self._cerrando:
            return
        self._cerrando = True
        if self.inicio is not None:
            self.medida_ms = (self._reloj() - self.inicio) * 1000
        try:
            if self._tic_id is not None:
                self.win.after_cancel(self._tic_id)
            animacion.cancelar(self.win, "alfa")
            animacion.cerrar(self.win, fin=self._irse)
        except tk.TclError:
            self._irse()

    def _irse(self) -> None:
        # No se destruye desde un `after` de la propia ventana (es de donde llega el último tic del
        # fundido): Tk intentaría limpiar el comando de un widget que ya no existe.
        try:
            self.raiz.after(0, self._destruir)
        except tk.TclError:
            self._destruir()

    def _destruir(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        self.terminada = True
        if self.al_terminar:
            self.al_terminar()
