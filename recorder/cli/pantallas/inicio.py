"""Inicio: el menú. ↑/↓ (o j/k) mueven, Enter abre y los números son atajos. Las filas no llevan descripción (la
dice la línea de ayuda de la elegida); a la derecha, desde ANCHO_DOS_COLUMNAS, la ficha «Próxima grabación»
con el equipo, y debajo de la lista, resumida, si no. Las pantallas se abren por el registro (registro.py); grabar
y la ventana las atiende la terminal (terminal.py)."""
from typing import List, Optional, Tuple

from rich.cells import cell_len
from rich.text import Text

from ... import ayuda
from ...config.hardware import describe_hardware
from ...config.schema import AppConfig, describe_quality
from ...metricas import MotorEfectivo
from ..menu import opciones_disponibles
from ..teclas import ENTER
from . import registro
from .base import Pantalla, mover, pie
from .componentes import recortar_por_el_medio
from .marco import ANCHO_DOS_COLUMNAS, MARGEN
from .ventana import VentanaAbierta

# Las pantallas propias del inicio, entre lo del menú numerado y Salir (la descripción ya no se enseña).
EXTRA = (
    ("7", "Rendimiento", "rendimiento", ""),
    ("8", "Ayuda", "ayuda", ""),
)
SOLO_WINDOWS = ("grabar", "ventana")  # necesitan WASAPI (y la ventana, la sesión entera)
SEPARADOR = " │ "  # entre la lista y la ficha
HUECO_LISTA = 4  # columnas entre la etiqueta más larga y el separador
ANCHO_FICHA_MIN = 36  # columnas mínimas de la ficha a la derecha; con menos, va debajo
SANGRIA_FICHA = 2
HUECO_FICHA = 2  # entre la etiqueta de la ficha y su valor
SEPARADOR_PARTES = " · "
ETIQUETA_MIC = "Mic"  # «Escucha  Altavoces · Mic: portátil» en la ficha resumida


def calidad_corta(config: AppConfig) -> str:
    """«Media» de «Calidad Media · CPU»: el preset, sin dónde corre (eso va en «Se usará»)."""
    return describe_quality(config).split(SEPARADOR_PARTES)[0].removeprefix("Calidad ")


def _valor(clave: str, **datos) -> str:
    return ayuda.entrada(clave)[0].format(**datos)


def micro_texto(config: AppConfig) -> str:
    return (config.mic_dev or _valor("inicio_predeterminado")) if config.mic else _valor("inicio_apagado")


def capturas_texto(config: AppConfig) -> str:
    """Qué se fotografía y con qué palabras clave: «todas las pantallas · al oír bloqueo, error, demo»."""
    if config.captures == "off":
        return _valor("inicio_sin_capturas")
    que = config.window or (_valor("inicio_pantalla", n=config.screen) if config.screen else _valor("inicio_todas_pantallas"))
    palabras = ", ".join(k for k in config.keywords if k.strip())
    return que + (SEPARADOR_PARTES + _valor("inicio_al_oir", palabras=palabras) if palabras else "")


def filas_ficha(config: AppConfig, motor: Optional[MotorEfectivo], nota: str, completa: bool) -> List[Tuple[str, str]]:
    """(etiqueta, valor) de «Próxima grabación»: lo que usaría una grabación que empezara ahora. La completa
    (a la derecha de la lista) lleva todo; la resumida (debajo), lo esencial en tres filas."""
    donde = motor.donde if motor else _valor("terminal_detectando_equipo").lower()
    escucha = config.out_dev or _valor("inicio_predeterminado")
    if not completa:
        return [
            (_valor("inicio_nota"), nota),
            (_valor("inicio_calidad"), calidad_corta(config) + SEPARADOR_PARTES + donde),
            (_valor("inicio_escucha"), escucha + SEPARADOR_PARTES + f"{ETIQUETA_MIC}: {micro_texto(config)}"),
        ]
    return [
        (_valor("inicio_nota"), nota),
        (_valor("inicio_carpeta"), config.notes_dir),
        (_valor("inicio_calidad"), calidad_corta(config)),
        (_valor("inicio_motor"), donde),
        (_valor("inicio_escucha"), escucha),
        (_valor("inicio_micro"), micro_texto(config)),
        (_valor("inicio_capturas"), capturas_texto(config)),
    ]

class Inicio(Pantalla):
    titulo = "Inicio"

    def __init__(self, terminal):
        super().__init__(terminal)
        disponibles = opciones_disponibles(terminal.comandos)
        self.filas = [f for f in disponibles if f[2] != "salir"] + list(EXTRA) + [f for f in disponibles if f[2] == "salir"]
        self.ancho = max(len(f[1]) for f in self.filas)
        self.sel = 0

    def apagada(self, accion: str) -> bool:
        return accion in SOLO_WINDOWS and not self.app.windows

    def teclas(self):
        directas = [f[0] for f in self.filas if f[0] != "0"]
        return pie(
            ("↑↓", "mover"), ("Enter", "abrir"), ("Esc", "salir"),
            (f"{min(directas)}-{max(directas)}", "abrir_directo"), ("?", "ayuda"), ("t", "tema"),
        )

    # ------------------------------------------------------------ lista y ficha
    def _lista(self, ancho: int) -> List[Text]:
        """Las filas, cada una en `ancho` columnas (la elegida con su fondo hasta el borde)."""
        lineas = []
        with self.app.con_ancho(ancho):
            for i, (numero, etiqueta, accion, _descripcion) in enumerate(self.filas):
                elegida, apagada = i == self.sel, self.apagada(accion)
                estilo = "tenue" if apagada else "elegido" if elegida else "texto"
                partes = (
                    ("▶" if elegida else " ", "acento"), (f" {numero}  ", "tenue" if apagada else "acento"),
                    (etiqueta, estilo), ("  (solo Windows)" if apagada else "", "tenue"),
                )
                linea = self.app.t_fila(*partes) if elegida else self.app.t(*partes)
                linea.pad_right(max(0, ancho - cell_len(linea.plain)))
                lineas.append(linea)
        return lineas

    def _ficha(self, ancho: int, completa: bool, con_equipo: bool = True) -> List[Text]:
        """«Próxima grabación» (y «Equipo» en la completa, si `con_equipo`) en `ancho` columnas."""
        app = self.app
        filas = filas_ficha(app.config, app.motor, app.nota, completa)
        columna = max(cell_len(etiqueta) for etiqueta, _valor_ in filas)
        valor_ancho = max(1, ancho - SANGRIA_FICHA - columna - HUECO_FICHA)
        carpeta = _valor("inicio_carpeta")
        lineas: List[Text] = []
        with app.con_ancho(ancho):
            lineas.append(app.t((_valor("inicio_proxima"), "bold")))
            for etiqueta, valor in filas:
                if etiqueta == carpeta:  # una ruta se recorta por el medio, que es donde está lo que la distingue
                    valor = recortar_por_el_medio(valor, valor_ancho, app.elidido)
                lineas.append(app.t((" " * SANGRIA_FICHA + etiqueta.ljust(columna) + " " * HUECO_FICHA, "tenue"), (valor, "texto")))
            if completa and con_equipo:
                lineas += [Text(), app.t((_valor("inicio_equipo"), "bold"))]
                if app.equipo is None:
                    lineas.append(app.spinner(ayuda.linea("terminal_detectando_equipo").rstrip(".") + "…"))
                else:
                    lineas += app.parrafo([(" " * SANGRIA_FICHA + describe_hardware(app.equipo), "tenue")], ancho, sangria=SANGRIA_FICHA)
        return lineas

    def cuerpo(self, ancho, sitio):
        ancho_lista = 1 + 1 + max(len(f[0]) for f in self.filas) + 2 + self.ancho + HUECO_LISTA
        derecha = ancho - ancho_lista - len(SEPARADOR)
        if ancho + 2 * MARGEN >= ANCHO_DOS_COLUMNAS and derecha >= ANCHO_FICHA_MIN:
            lista = self._lista(ancho_lista)
            ficha = self._ficha(derecha, True)
            if len(ficha) > max(sitio, len(lista)):  # no cabe: lo primero que se quita es «Equipo»
                ficha = self._ficha(derecha, True, con_equipo=False)
            separador = self.app.t((SEPARADOR, "borde"))
            lineas = []
            for i in range(max(len(lista), len(ficha))):
                izquierda = lista[i] if i < len(lista) else Text(" " * ancho_lista)
                lineas.append(izquierda + separador + (ficha[i] if i < len(ficha) else Text()))
            return lineas, self.sel
        lista = self._lista(ancho)
        ficha = self._ficha(ancho, False)
        if len(lista) + 1 + len(ficha) <= sitio:  # debajo de la lista, si cabe entera; si no, no se enseña
            return lista + [Text()] + ficha, self.sel
        return lista, self.sel
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
        elif accion == "grabar":
            self.app.salir(accion)  # la grabación abre su propia pantalla completa y devuelve aquí con su resumen
        elif accion == "ventana":
            self.app.esperar(VentanaAbierta(self.app), self._abrir_ventana)
        elif clase is not None:
            self.app.abrir(clase(self.app))

    def _abrir_ventana(self) -> Tuple[str, str]:
        """La ventana gráfica, hasta que se cierra; el aviso con que se vuelve."""
        from .. import app as despacho  # aquí y no arriba: app.py importa este paquete al abrir el menú

        try:
            codigo = despacho.abrir_ventana()
        except Exception as e:
            return "⚠ " + ayuda.linea("ventana_no_abre").format(motivo=f"{e.__class__.__name__}: {e}"), "error"
        if codigo:
            return "⚠ " + ayuda.linea("ventana_no_abre").format(motivo=codigo), "error"
        return "✔ " + ayuda.linea("ventana_cerrada"), "ok"
