"""Panel de rendimiento de la ventana: lo que trae `StatusSnapshot.metricas` (recorder/metricas.py)
con una sparkline de los últimos ~2 minutos por dato.

`Historial`, `textos` y `puntos` son lógica pura (se prueban sin Tk). La ventana anota una muestra
en el historial cada metricas.INTERVALO s aunque el panel esté plegado (un append, para que al
abrirlo ya haya curva); el panel solo se redibuja si está a la vista: las etiquetas cuando su
texto cambia y las sparklines cuando llega una muestra nueva o cambia su ancho.
"""

import collections
import time
import tkinter as tk
from typing import Callable, Deque, Dict, List, Optional, Sequence

from .. import metricas
from ..metricas import Metricas, factor, na
from .theme import BTN_STYLE, P, boton_vivo, con_anillo
from .tooltip import con_ayuda

HISTORIA_S = 120
MUESTRAS = int(HISTORIA_S / metricas.INTERVALO)

# (dato, título, clave de ayuda, techo mínimo del eje). El eje va de 0 al mayor valor o al techo
# si es más, para que el ruido de un valor bajo no parezca una montaña; la RAM (None) va de su
# mínimo a su máximo, porque apenas se mueve una vez cargado el modelo.
SERIES = (
    ("velocidad", "Velocidad", "rend_velocidad", 2.0),
    ("cpu", "CPU", "rend_cpu", 10.0),
    ("gpu", "GPU", "rend_gpu", 10.0),
    ("ram", "RAM", "rend_ram", None),
    ("cola", "Cola", "cola", 3.0),
    ("atraso", "Atraso", "atraso", 30.0),
)
COLUMNAS = {"amplio": 6, "compacto": 3, "estrecho": 2}  # celdas por fila según el punto de corte


class Historial:
    """Las últimas MUESTRAS lecturas de cada dato (None = sin dato), una cada `intervalo` s."""

    def __init__(self, n: int = MUESTRAS, intervalo: float = metricas.INTERVALO, reloj=time.monotonic):
        self.series: Dict[str, Deque[Optional[float]]] = {s[0]: collections.deque(maxlen=n) for s in SERIES}
        self.intervalo, self._reloj = intervalo, reloj
        self._ultima: Optional[float] = None
        self.version = 0  # sube con cada muestra: el panel redibuja si cambió

    def anotar(self, m: Optional[Metricas]) -> bool:
        """Guarda `m` si pasó un intervalo desde la última; True si la guardó. El sondeo de la
        ventana llega cada 200 ms y el muestreo cambia cada 2 s: el resto se descarta."""
        ahora = self._reloj()
        if m is None or (self._ultima is not None and ahora - self._ultima < self.intervalo):
            return False
        self._ultima = ahora
        for clave, valor in (
            ("velocidad", m.velocidad), ("cpu", m.cpu_proceso), ("gpu", m.gpu_proceso),
            ("ram", m.ram_mb), ("cola", float(m.cola)), ("atraso", m.atraso_s),
        ):
            self.series[clave].append(valor)
        self.version += 1
        return True


def _con_equipo(proceso: Optional[float], sistema: Optional[float]) -> str:
    if proceso is None and sistema is None:
        return "n/d"
    return f"{na(proceso)} (equipo {na(sistema)})"


def textos(m: Optional[Metricas]) -> Dict[str, str]:
    """Lo que dice cada etiqueta del panel para la foto `m` (None mientras arranca)."""
    if m is None:
        return {"motor": "Cargando modelo…", **{s[0]: "n/d" for s in SERIES}}
    return {
        "motor": m.motor.texto if m.motor else "Cargando modelo…",
        "velocidad": factor(m.velocidad) if m.velocidad is not None else "n/d",
        "cpu": _con_equipo(m.cpu_proceso, m.cpu_sistema),
        "gpu": _con_equipo(m.gpu_proceso, m.gpu_sistema),
        "ram": na(m.ram_mb, "{:.0f} MB"),
        "cola": str(m.cola),
        "atraso": f"{m.atraso_s:.0f} s",
    }


def puntos(valores: Sequence[Optional[float]], ancho: int, alto: int, techo: Optional[float] = None,
           n: int = MUESTRAS, margen: int = 2) -> List[float]:
    """Coordenadas (x0, y0, x1, y1…) de la sparkline en un lienzo de `ancho`×`alto`.

    La última muestra va en el borde derecho y cada una ocupa 1/(n-1) del ancho, así la curva
    entra por la derecha y no se estira mientras se llena el historial. Los None se saltan; con
    menos de dos valores no hay línea ([]). Escala: ver SERIES.
    """
    hay = [(i, v) for i, v in enumerate(valores) if v is not None]
    if len(hay) < 2:
        return []
    vs = [v for _, v in hay]
    bajo, alto_v = (min(vs), max(vs)) if techo is None else (0.0, max(techo, max(vs)))
    rango = (alto_v - bajo) or 1.0
    paso = (ancho - 2 * margen) / max(1, n - 1)
    hueco = n - len(valores)
    coords: List[float] = []
    for i, v in hay:
        coords += [margen + (hueco + i) * paso, alto - margen - (v - bajo) / rango * (alto - 2 * margen)]
    return coords


class PanelRendimiento(tk.Frame):
    """El panel plegable. `actualizar` lo llama la ventana en cada sondeo mientras se ve."""

    def __init__(self, master, historial: Historial, al_cerrar: Callable[[], None], atajo: str = ""):
        super().__init__(master, bg=P.fondo, highlightthickness=1, highlightbackground=P.borde)
        self.historial = historial
        k = self.tk.call("tk", "scaling") / (96 / 72)
        self._pintado: Dict[tk.Widget, dict] = {}
        self._version = -1

        cabecera = tk.Frame(self, bg=P.fondo)
        cabecera.grid(row=0, column=0, columnspan=6, sticky="ew", padx=10, pady=(6, 2))
        tk.Label(cabecera, text="Rendimiento", bg=P.fondo, fg=P.texto, font=("Segoe UI Semibold", 10)).pack(side="left")
        self.lbl_motor = tk.Label(cabecera, text="", bg=P.fondo, fg=P.texto_tenue, font=("Segoe UI", 9), anchor="w")
        self.lbl_motor.pack(side="left", fill="x", expand=True, padx=(10, 6))
        con_ayuda(self.lbl_motor, "rend_motor")
        cerrar = con_anillo(cabecera, lambda marco: tk.Button(marco, text="✕", command=al_cerrar, **{**BTN_STYLE, "padx": 6}))
        con_ayuda(boton_vivo(cerrar), "rendimiento", atajo=atajo)
        cerrar.master.pack(side="right")

        self.valores: Dict[str, tk.Label] = {}
        self.lineas: Dict[str, tuple] = {}  # dato -> (lienzo, línea)
        self.celdas = []
        for clave, titulo, ayuda, _techo in SERIES:
            celda = tk.Frame(self, bg=P.fondo)
            nombre = tk.Label(celda, text=titulo, bg=P.fondo, fg=P.texto_tenue, font=("Segoe UI", 9), anchor="w")
            valor = tk.Label(celda, text="n/d", bg=P.fondo, fg=P.texto, font=("Segoe UI Semibold", 10), anchor="w")
            lienzo = tk.Canvas(celda, width=1, height=int(26 * k), bg=P.fondo, highlightthickness=0)
            linea = lienzo.create_line(0, 0, 0, 0, fill=P.foco, width=max(1, round(1.5 * k)), state="hidden")
            lienzo.bind("<Configure>", lambda _e: self._redibujar(forzar=True))
            for w in (nombre, valor, lienzo):
                w.pack(fill="x")
                con_ayuda(w, ayuda)
            self.valores[clave], self.lineas[clave] = valor, (lienzo, linea)
            self.celdas.append(celda)
        self.columnas(COLUMNAS["amplio"])

    def columnas(self, n: int) -> None:
        """Reparte las celdas en filas de `n` (según el punto de corte de la ventana)."""
        for c in range(len(SERIES)):
            self.columnconfigure(c, weight=1 if c < n else 0, uniform="celda" if c < n else "")
        for i, celda in enumerate(self.celdas):
            celda.grid(row=1 + i // n, column=i % n, sticky="ew", padx=10, pady=(2, 8))

    def _poner(self, lbl: tk.Label, **opts) -> None:
        if self._pintado.get(lbl) != opts:
            lbl.configure(**opts)
            self._pintado[lbl] = opts

    def actualizar(self, m: Optional[Metricas]) -> None:
        """Etiquetas que cambiaron y, si hubo muestra nueva, las sparklines."""
        t = textos(m)
        self._poner(self.lbl_motor, text=t["motor"])
        lento = m is not None and m.velocidad is not None and m.velocidad < 1
        for clave, lbl in self.valores.items():
            self._poner(lbl, text=t[clave], fg=P.error if clave == "velocidad" and lento else P.texto)
        self._redibujar()

    def repintar(self) -> None:
        """Tras un cambio de tema: los colores de las líneas no los ve `theme.aplicar_tema`."""
        self._pintado.clear()
        self._redibujar(forzar=True)

    def _redibujar(self, forzar: bool = False) -> None:
        if not forzar and self.historial.version == self._version:
            return
        self._version = self.historial.version
        for clave, _titulo, _ayuda, techo in SERIES:
            lienzo, linea = self.lineas[clave]
            ancho, alto = lienzo.winfo_width(), lienzo.winfo_height()
            coords = puntos(self.historial.series[clave], ancho, alto, techo) if ancho > 10 else []
            if coords:
                lienzo.coords(linea, *coords)
                lienzo.itemconfigure(linea, state="normal", fill=P.foco)
            else:
                lienzo.itemconfigure(linea, state="hidden")
