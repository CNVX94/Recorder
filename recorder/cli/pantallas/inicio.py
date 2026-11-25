"""Inicio: el menú. ↑/↓ (o j/k) mueven, Enter abre y los números son atajos. Las pantallas se abren por el
registro (registro.py); lo demás (grabar, la ventana, Calibrar…) usa la terminal entera y se ejecuta fuera."""
from ... import ayuda
from ..menu import opciones_disponibles
from ..teclas import ENTER
from . import registro
from .base import Pantalla, mover

# Las pantallas propias del inicio, entre lo del menú numerado y Salir.
EXTRA = (
    ("7", "Rendimiento", "rendimiento", "motor que se usaría y lo que gasta el equipo"),
    ("8", "Ayuda", "ayuda", "teclas y glosario"),
)
SOLO_WINDOWS = ("grabar", "ventana")  # necesitan WASAPI (y la ventana, la sesión entera)


class Inicio(Pantalla):
    titulo = "Inicio"
    TECLAS = (("Enter", "abrir"), ("Esc", "salir"), ("?", "ayuda"), ("t", "tema"))
    cabecera_completa = True

    def __init__(self, terminal):
        super().__init__(terminal)
        disponibles = opciones_disponibles(terminal.comandos)
        self.filas = [f for f in disponibles if f[2] != "salir"] + list(EXTRA) + [f for f in disponibles if f[2] == "salir"]
        self.ancho = max(len(f[1]) for f in self.filas)
        self.sel = 0

    def apagada(self, accion: str) -> bool:
        return accion in SOLO_WINDOWS and not self.app.windows

    def cuerpo(self, ancho, sitio):
        lineas = []
        for i, (numero, etiqueta, accion, descripcion) in enumerate(self.filas):
            elegida, apagada = i == self.sel, self.apagada(accion)
            estilo = "tenue" if apagada else "elegido" if elegida else "texto"
            partes = (
                ("▶" if elegida else " ", "acento"), (f" {numero}  ", "tenue" if apagada else "acento"),
                (etiqueta.ljust(self.ancho) + "  ", estilo), ("(solo Windows)" if apagada else descripcion, "tenue"),
            )
            lineas.append(self.app.t_fila(*partes) if elegida else self.app.t(*partes))
        return lineas, self.sel

    def ayuda(self):
        accion = self.filas[self.sel][2]
        return ayuda.linea("solo_windows" if self.apagada(accion) else "menu_" + accion), "tenue"

    def tecla(self, k):
        movida = mover(self.sel, len(self.filas), k)
        if movida is not None:
            self.sel = movida
        elif k == ENTER:
            self.abrir(self.filas[self.sel][2])
        elif any(f[0] == k for f in self.filas):  # los números siguen siendo atajos
            self.sel = next(i for i, f in enumerate(self.filas) if f[0] == k)
            self.abrir(self.filas[self.sel][2])
        else:
            return False
        return True

    def abrir(self, accion: str) -> None:
        clase = registro.clase_de(accion)
        if self.apagada(accion):
            self.app.avisar(f"⚠ {ayuda.entrada('solo_windows')[0]}: no se puede aquí.", "error")
        elif accion == "salir":
            self.app.salir()
        elif clase is not None:
            self.app.abrir(clase(self.app))
        else:
            self.app.salir(accion)  # grabar, la ventana y los comandos usan la terminal entera
