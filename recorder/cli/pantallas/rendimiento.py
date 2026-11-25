"""Rendimiento: el motor que se usaría y lo que gasta el equipo ahora, con barras y tendencia. Desde el menú no
hay ninguna grabación en curso: las cifras son las del equipo entero (`Muestreador` sin transcriptor), que es lo
que dice si hay margen antes de grabar."""
import collections
from typing import Deque, Dict, Optional

from rich.text import Text

from ... import ayuda
from ...config.hardware import peek_hardware
from ...metricas import INTERVALO as INTERVALO_METRICAS
from .base import HISTORIA, Pantalla, barra, motor_previsto, tendencia


class Rendimiento(Pantalla):
    titulo = "Rendimiento"
    SERIES = (("cpu", "CPU del equipo"), ("gpu", "GPU del equipo"))

    def __init__(self, terminal):
        super().__init__(terminal)
        self.muestreo = terminal.nuevo_muestreador()
        self.muestreo.iniciar()
        self.desde = terminal.reloj()
        self.ultima: Optional[float] = None
        self.historia: Dict[str, Deque[Optional[float]]] = {s: collections.deque(maxlen=HISTORIA) for s, _t in self.SERIES}

    def al_salir(self):
        self.muestreo.parar()

    def ayuda(self):
        return ayuda.linea("menu_rendimiento"), "tenue"

    def _anotar(self, valores: Dict[str, Optional[float]]) -> None:
        ahora = self.app.reloj()
        if self.ultima is None or ahora - self.ultima >= INTERVALO_METRICAS:
            self.ultima = ahora
            for serie, valor in valores.items():
                self.historia[serie].append(valor)

    def cuerpo(self, ancho, sitio):
        t, m = self.app.t, self.muestreo.foto()
        valores = {"cpu": m.cpu_sistema, "gpu": m.gpu_sistema}
        if any(v is not None for v in valores.values()):
            self._anotar(valores)
        lineas = [t(("No hay ninguna grabación en curso: las cifras son del equipo entero.", "tenue"))]
        hw = peek_hardware()
        if hw is None:
            lineas.append(self.app.spinner(ayuda.linea("terminal_detectando_equipo").rstrip(".") + "…"))
        else:
            motor = motor_previsto(self.app.config, hw)
            lineas.append(t(("Motor que se usaría: ", "tenue"), (motor.texto, "texto")))
            if motor.caida:
                lineas += self.app.parrafo([(f"⚠ {motor.caida}", "error")], ancho)
        lineas.append(Text())
        if all(v is None for v in valores.values()) and self.app.reloj() - self.desde < 3 * INTERVALO_METRICAS:
            lineas.append(self.app.spinner("midiendo…"))  # el primer % llega con la segunda muestra
            return lineas, 0
        etiqueta = max(len(titulo) for _s, titulo in self.SERIES) + 2
        celdas = max(10, min(30, (ancho - etiqueta - 9) // 2))
        for serie, titulo in self.SERIES:
            v = valores[serie]
            lleno, vacio = barra(v or 0.0, celdas)
            lineas.append(t(
                (titulo.ljust(etiqueta), "texto"), (lleno, "acento"), (vacio, "borde"),
                (f"{'n/d' if v is None else f'{v:.0f} %':>6}  ", "texto"),
                (tendencia(self.historia[serie], ancho - etiqueta - celdas - 8, self.app.juego), "mic"),
            ))
        return lineas, 0
