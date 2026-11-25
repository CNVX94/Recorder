"""Ayuda: las teclas de las pantallas y de la grabación, y el glosario de recorder/ayuda.py."""
from rich.text import Text

from ... import ayuda as textos
from ..teclas import ABAJO, ARRIBA, AVPAG, FIN, INICIO, REPAG
from .base import Pantalla

# Las teclas de las pantallas, en el orden en que se enseñan (su texto sale de recorder/ayuda.py).
ATAJOS = (
    "atajo_mover", "atajo_extremos", "atajo_pagina", "atajo_abrir", "atajo_cambiar", "atajo_volver",
    "atajo_numeros", "atajo_guardar", "atajo_tema", "atajo_ayuda", "atajo_ctrl_c",
)
TECLAS_GRABACION = "pcraoq"
COLUMNA_TECLAS = 14


class Ayuda(Pantalla):
    titulo = "Ayuda"
    TECLAS = (("↑↓", "desplazar"), ("RePág/AvPág", "pagina"), ("Esc", "volver"), ("t", "tema"))
    abre_ayuda = False
    sitio = 10  # las líneas que cabían la última vez: lo que mide una página

    def __init__(self, terminal):
        super().__init__(terminal)
        self.arriba = 0  # la primera línea a la vista

    def ayuda(self):
        return textos.linea("menu_ayuda"), "tenue"

    def tecla(self, k):
        if k in (ARRIBA, "k"):
            self.arriba = max(0, self.arriba - 1)
        elif k in (ABAJO, "j"):
            self.arriba += 1  # el tope se pone al pintar, cuando se sabe cuánto cabe
        elif k == INICIO:
            self.arriba = 0
        elif k == FIN:
            self.arriba = 10 ** 6
        elif k in (REPAG, AVPAG):
            self.arriba = max(0, self.arriba + (self.sitio - 1) * (1 if k == AVPAG else -1))
        else:
            return False
        return True

    def cuerpo(self, ancho, sitio):
        self.sitio = sitio
        t, parrafo = self.app.t, self.app.parrafo
        lineas = [t((textos.entrada("ayuda_teclas")[0], "bold"))]
        for clave in ATAJOS:
            tecla, que = textos.entrada(clave)
            lineas.append(t((f"  {self.app.presentar(tecla):<{COLUMNA_TECLAS}}", "acento"), (que, "texto")))
        lineas += [Text(), t((textos.entrada("ayuda_teclas_grabacion")[0], "bold"))]
        for k in TECLAS_GRABACION:
            titulo, texto = textos.entrada(f"tecla_{k}")
            lineas += parrafo([(f"  [{k}] {titulo}: ", "acento"), (texto, "tenue")], ancho, sangria=6)
        lineas += [Text(), t((textos.entrada("ayuda_glosario")[0], "bold"))]
        for titulo, texto in textos.GLOSARIO.values():
            lineas += parrafo([(f"  {titulo}: ", "acento"), (texto, "tenue")], ancho)
        self.arriba = min(self.arriba, max(0, len(lineas) - sitio))
        return lineas[self.arriba:self.arriba + sitio], 0

