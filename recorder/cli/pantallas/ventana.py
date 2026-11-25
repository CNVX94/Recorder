"""Ventana abierta: el cuadro fijo que enseña la terminal mientras la ventana gráfica ocupa el hilo principal.
No atiende el teclado (no hay nada que ofrecer, así que tampoco pie); al cerrar la ventana, Inicio recibe su aviso."""
from rich.text import Text

from ... import ayuda
from .base import Pantalla

SANGRIA = 2  # columnas de sangría del mensaje


class VentanaAbierta(Pantalla):
    titulo = "Ventana"
    TECLAS = ()

    def cuerpo(self, ancho, sitio):
        titulo, texto = ayuda.entrada("ventana_abierta")
        return [Text(), self.app.t((" " * SANGRIA + titulo, "bold")), *self.app.parrafo(
            [(" " * SANGRIA + texto, "tenue")], ancho, sangria=SANGRIA,
        )], 0
