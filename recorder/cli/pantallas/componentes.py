"""Los componentes que comparten las pantallas (docs/terminal-especificacion.md, sección 4).

Cada uno guarda su estado, atiende las teclas que le tocan (`tecla` devuelve si la atendió) y dice cómo
se pinta con trozos (texto, estilo) o líneas de rich: el color sale de la paleta por el nombre del estilo
y los símbolos de siempre son los del juego completo; `Terminal.t` los pasa al juego activo.

- CampoTexto: texto con cursor (←→, Inicio, Fin, Retroceso, Supr).
- Interruptor: sí / no.
- Numerico: un número con paso y rango.
- ListaAjustes: filas con rótulos de sección, columna de etiquetas y marca de la elegida.
- ListaSeleccion y Confirmacion: subpantallas (se abren con `Terminal.abrir`).
- VistaPrevia: texto desplazable por páginas.
- estado_vacio y estado_error: una línea que dice qué hacer.
"""
import dataclasses
from typing import Callable, List, Sequence, Tuple

from rich.cells import cell_len
from rich.text import Text

from ... import ayuda
from ..consola import ELIDIDO, JUEGO_ASCII
from ..teclas import AVPAG, DERECHA, ENTER, ESPACIO, FIN, INICIO, IZQUIERDA, REPAG, RETROCESO, SUPR
from .base import Pantalla, mover, pie

SANGRIA_FILA = 4  # columnas de la marca de fila y el hueco hasta la etiqueta (2 sin rótulos de sección)
SANGRIA_ROTULO = 2
HUECO_VALOR = 2  # entre la columna de etiquetas y el valor
ANCHO_MINIMO_VENTANA = 8  # lo mínimo que tiene sentido enseñar de un texto con cursor
CURSOR = "▌"
ENTRADA_TEXTO = "› "
PASO_PAGINA_MIN = 1


# ------------------------------------------------------------------ campo de texto
class CampoTexto:
    """Un texto con el cursor en `cursor` (0 a len(texto))."""

    def __init__(self, texto: str = ""):
        self.texto = texto
        self.cursor = len(texto)

    def tecla(self, k: str) -> bool:
        """Edita con `k`: True si la atendió (↑↓, Enter y Esc son de quien lo use)."""
        t, c = self.texto, self.cursor
        if k == IZQUIERDA:
            self.cursor = max(0, c - 1)
        elif k == DERECHA:
            self.cursor = min(len(t), c + 1)
        elif k == INICIO:
            self.cursor = 0
        elif k == FIN:
            self.cursor = len(t)
        elif k == RETROCESO:
            if c:
                self.texto, self.cursor = t[:c - 1] + t[c:], c - 1
        elif k == SUPR:
            self.texto = t[:c] + t[c + 1:]
        elif len(k) == 1 and k.isprintable():
            self.texto, self.cursor = t[:c] + k + t[c:], c + 1
        else:
            return False
        return True

    def partes(self, ancho: int, elidido: str = ELIDIDO) -> List[Tuple[str, str]]:
        """«› antes▌después» en `ancho` celdas; si no cabe, una ventana que mantiene el cursor a la vista
        con `elidido` («…», o «...» en ASCII) en el lado cortado."""
        disponible = max(ANCHO_MINIMO_VENTANA, ancho - len(ENTRADA_TEXTO))
        antes, despues, c = self.texto[:self.cursor], self.texto[self.cursor:], self.cursor
        total = len(self.texto) + 1
        if total > disponible:
            completo = antes + CURSOR + despues
            inicio = max(0, min(c - disponible // 2, total - disponible))
            fin = inicio + disponible
            antes, despues = completo[inicio:c], completo[c + 1:fin]
            if inicio > 0:
                antes = elidido + antes[len(elidido):]
            if fin < total:
                despues = despues[:len(despues) - len(elidido)] + elidido
        return [(ENTRADA_TEXTO, "acento"), (antes, "texto"), (CURSOR, "acento"), (despues, "texto")]


# ------------------------------------------------------------------ interruptor
class Interruptor:
    def __init__(self, valor: bool):
        self.valor = valor

    def alternar(self) -> bool:
        self.valor = not self.valor
        return self.valor

    def tecla(self, k: str) -> bool:
        if k in (ESPACIO, ENTER, IZQUIERDA, DERECHA):
            self.alternar()
            return True
        return False

    def partes(self, juego: str) -> List[Tuple[str, str]]:
        """«● sí» en `ok` o «○ no» en `tenue` (en ASCII, «[x] sí» y «[ ] no»)."""
        ascii_ = juego == JUEGO_ASCII
        if self.valor:
            return [("[x]" if ascii_ else "●", "ok"), (" " + ayuda.entrada("terminal_si")[0], "texto")]
        return [("[ ]" if ascii_ else "○", "tenue"), (" " + ayuda.entrada("terminal_no")[0], "tenue")]


# ------------------------------------------------------------------ numérico
def coma(numero: float, decimales: int) -> str:
    """0.6 → «0,60»: la coma decimal al mostrar."""
    return f"{numero:.{decimales}f}".replace(".", ",")


class Numerico:
    """Un número entre `minimo` y `maximo` que se mueve de `paso` en `paso` (sin dar la vuelta)."""

    def __init__(self, valor: float, minimo: float, maximo: float, paso: float, decimales: int = 2):
        self.minimo, self.maximo, self.paso, self.decimales = minimo, maximo, paso, decimales
        self.valor = self._dentro(valor)

    def _dentro(self, valor: float) -> float:
        return round(min(self.maximo, max(self.minimo, valor)), self.decimales)

    def mover(self, sentido: int) -> float:
        self.valor = self._dentro(self.valor + sentido * self.paso)
        return self.valor

    def tecla(self, k: str) -> bool:
        if k in (IZQUIERDA, DERECHA):
            self.mover(-1 if k == IZQUIERDA else 1)
            return True
        return False

    def texto(self) -> str:
        return coma(self.valor, self.decimales)

    def aceptar(self, texto: str) -> bool:
        """Pone el número escrito (con coma o punto) si es uno y cae dentro del rango; si no, lo deja como estaba."""
        try:
            numero = float(texto.strip().replace(",", "."))
        except ValueError:
            return False
        if not self.minimo <= numero <= self.maximo:
            return False
        self.valor = self._dentro(numero)
        return True

    def partes(self, elegido: bool = True) -> List[Tuple[str, str]]:
        """«‹ 0,60 ›»; las flechas solo en la fila elegida."""
        if not elegido:
            return [(self.texto(), "tenue")]
        return [("‹ ", "acento"), (self.texto(), "texto"), (" ›", "acento")]


# ------------------------------------------------------------------ recorte de rutas
def recortar_por_el_medio(texto: str, ancho: int, elidido: str = ELIDIDO) -> str:
    """`texto` en `ancho` celdas conservando el principio (un tercio) y el final, que es lo que distingue:
    «C:\\Users…\\Dailies\\capturas»."""
    if cell_len(texto) <= ancho:
        return texto
    if ancho <= len(elidido):
        return texto[:ancho]
    cabeza = max(1, (ancho - len(elidido)) // 3)
    cola = ancho - len(elidido) - cabeza
    return texto[:cabeza] + elidido + texto[len(texto) - cola:]


# ------------------------------------------------------------------ lista de ajustes
@dataclasses.dataclass
class Fila:
    """Una fila de una lista de ajustes. `seccion` es el rótulo que se pinta justo encima."""

    etiqueta: str
    clave: str = ""  # la clave de ayuda de lo que explica
    dato: object = None  # lo que quiera guardar quien la usa
    seccion: str = ""


class ListaAjustes:
    """Filas con rótulos de sección: la etiqueta en una columna y el valor al lado. ↑↓ (o j k) mueven dando
    la vuelta; Inicio y Fin van a la primera y la última; RePág y AvPág, una página. Los rótulos no se eligen."""

    def __init__(self, filas: Sequence[Fila], sel: int = 0):
        self.filas = list(filas)
        self.sel = min(sel, max(0, len(self.filas) - 1))
        self.sitio = 10  # líneas que había la última vez que se pintó: lo que mide una página

    @property
    def actual(self) -> Fila:
        return self.filas[self.sel]

    def tecla(self, k: str) -> bool:
        n = len(self.filas)
        if not n:
            return False
        movida = mover(self.sel, n, k)
        if movida is not None:
            self.sel = movida
        elif k == INICIO:
            self.sel = 0
        elif k == FIN:
            self.sel = n - 1
        elif k in (REPAG, AVPAG):
            pagina = max(PASO_PAGINA_MIN, self.sitio - 1)
            self.sel = min(n - 1, max(0, self.sel + (pagina if k == AVPAG else -pagina)))
        else:
            return False
        return True

    def lineas(self, app, valor, ancho: int, sitio: int) -> Tuple[List[Text], int]:
        """(líneas, la de la fila elegida). `valor(fila, es_la_elegida, ancho)` da los trozos del valor
        de una fila (vacío si es una acción) y `ancho` es lo que le queda en la línea."""
        self.sitio = sitio
        etiquetas = [app.presentar(f.etiqueta) for f in self.filas]
        columna = max((cell_len(e) for e in etiquetas), default=0)
        con_secciones = any(f.seccion for f in self.filas)
        sangria = SANGRIA_FILA if con_secciones else SANGRIA_FILA - SANGRIA_ROTULO
        lineas, foco = [], 0
        for i, (fila, etiqueta) in enumerate(zip(self.filas, etiquetas)):
            if fila.seccion:
                lineas.append(app.t((" " * SANGRIA_ROTULO + fila.seccion, "bold")))
            elegida = i == self.sel
            hueco = " " * (sangria - 1)
            libre = max(0, ancho - sangria - columna - HUECO_VALOR)
            valores = valor(fila, elegida, libre)
            relleno = " " * (columna - cell_len(etiqueta) + HUECO_VALOR) if valores else ""
            partes = [
                ("▶" if elegida else " ", "acento"), (hueco + etiqueta + relleno, "elegido" if elegida else "texto"), *valores,
            ]
            if elegida:
                foco = len(lineas)
            lineas.append(app.t_fila(*partes) if elegida else app.t(*partes))
        return lineas, foco


# ------------------------------------------------------------------ subpantallas
class ListaSeleccion(Pantalla):
    """Elegir un valor de una lista: sube con ↑↓, elige con Enter o con su número (1-9); Esc vuelve sin
    cambiar. Abre con la fila en lo actual. `al_elegir(valor)` recibe lo elegido y la pantalla se cierra."""

    NUMEROS = "123456789"
    TECLAS = (
        ("Enter", "elegir"), ("Esc", "volver_sin_cambiar"), ("↑↓", "mover"), ("1-9", "directo"), ("?", "ayuda"),
    )

    def __init__(
        self, terminal, titulo: str, opciones: Sequence[Tuple[str, object]], actual: object,
        al_elegir: Callable[[object], None], clave_ayuda: str = "opciones_lista",
    ):
        super().__init__(terminal)
        self.titulo, self.opciones, self.al_elegir, self.clave_ayuda = titulo, list(opciones), al_elegir, clave_ayuda
        self.actual = actual
        self.lista = ListaAjustes([Fila(etiqueta, dato=valor) for etiqueta, valor in self.opciones])
        self.lista.sel = next((i for i, (_e, v) in enumerate(self.opciones) if v == actual), 0)

    def teclas(self):
        n = min(len(self.opciones), len(self.NUMEROS))
        pares = [(t if t != "1-9" else f"1-{n}", c) for t, c in self.TECLAS]
        return pie(*(pares if n > 1 else [p for p in pares if p[1] != "directo"]))

    def ayuda(self):
        return ayuda.linea(self.clave_ayuda), "tenue"

    def cuerpo(self, ancho, sitio):
        if not self.opciones:
            return estado_vacio(self.app, "terminal_sin_opciones"), 0
        t = self.app.t
        lineas, foco = [], 0
        for i, (etiqueta, valor) in enumerate(self.opciones):
            elegida = i == self.lista.sel
            numero = f"{i + 1}" if i < len(self.NUMEROS) else " "
            partes = [
                ("▶" if elegida else " ", "acento"), (f" {numero}  ", "acento"),
                (etiqueta, "elegido" if elegida else "texto"),
                (("  " + ayuda.entrada("terminal_actual")[0]) if valor == self.actual else "", "tenue"),
            ]
            if elegida:
                foco = len(lineas)
            lineas.append(self.app.t_fila(*partes) if elegida else t(*partes))
        self.lista.sitio = sitio
        return lineas, foco

    def tecla(self, k):
        if not self.opciones:
            return False
        if self.lista.tecla(k):
            return True
        if k == ENTER:
            self._elegir(self.lista.sel)
        elif k in self.NUMEROS and int(k) <= len(self.opciones):
            self._elegir(int(k) - 1)
        else:
            return False
        return True

    def _elegir(self, i: int) -> None:
        self.app.volver()
        self.al_elegir(self.opciones[i][1])


class Confirmacion(Pantalla):
    """«Antes → después» de lo que cambia, antes de guardar. Enter lo confirma (`al_confirmar`) y Esc
    vuelve a seguir editando. Si una fila no cabe en una línea, todas pasan a dos."""

    TECLAS = (("Enter", "guardar"), ("Esc", "seguir_editando"))
    SEPARADOR = "  →  "

    def __init__(
        self, terminal, filas: Sequence[Tuple[str, str, str]], al_confirmar: Callable[[], None],
        titulo: str = "", encabezado: str = "", clave_ayuda: str = "terminal_confirmar",
        marca: Tuple[str, str] = ("", "tenue"),
    ):
        super().__init__(terminal)
        self.filas, self.al_confirmar, self.encabezado, self.clave_ayuda = list(filas), al_confirmar, encabezado, clave_ayuda
        self.titulo = titulo or ayuda.entrada("pie_guardar")[0]
        self._marca = marca

    def marca(self):
        return self._marca

    def ayuda(self):
        return ayuda.linea(self.clave_ayuda), "tenue"

    def cuerpo(self, ancho, sitio):
        t = self.app.t
        lineas = [t((self.encabezado, "tenue")), Text()] if self.encabezado else []
        pr = self.app.presentar
        columna = max((cell_len(pr(e)) for e, _a, _d in self.filas), default=0)
        columna_antes = max((cell_len(pr(a)) for _e, a, _d in self.filas), default=0)
        ancho_fila = 3 + columna + 2 + columna_antes + cell_len(pr(self.SEPARADOR)) + max(
            (cell_len(pr(d)) for _e, _a, d in self.filas), default=0
        )
        una_linea = ancho_fila <= ancho
        for etiqueta, antes, despues in self.filas:
            if una_linea:
                lineas.append(t(
                    ("   " + pr(etiqueta).ljust(columna) + "  ", "texto"), (pr(antes).ljust(columna_antes), "tenue"),
                    (self.SEPARADOR, "tenue"), (despues, "acento"),
                ))
            else:
                lineas.append(t(("   " + etiqueta, "texto")))
                lineas.append(t(("     " + antes, "tenue"), (" → ", "tenue"), (despues, "acento")))
        return lineas, 0

    def tecla(self, k):
        if k == ENTER:
            self.app.volver()
            self.al_confirmar()
            return True
        return False


# ------------------------------------------------------------------ vista previa
class VistaPrevia:
    """Texto que se desplaza por páginas (RePág, AvPág) con «1-19 de 24»."""

    def __init__(self, lineas: Sequence[Text] = ()):
        self.lineas = list(lineas)
        self.arriba = 0

    def poner(self, lineas: Sequence[Text]) -> None:
        """Cambia el texto (se recalculó); se queda donde estaba mientras quepa."""
        self.lineas = list(lineas)

    def tecla(self, k: str, alto: int) -> bool:
        pagina = max(PASO_PAGINA_MIN, alto - 1)
        if k == REPAG:
            self.arriba -= pagina
        elif k == AVPAG:
            self.arriba += pagina
        elif k == INICIO:
            self.arriba = 0
        elif k == FIN:
            self.arriba = len(self.lineas)
        else:
            return False
        self.arriba = min(max(0, self.arriba), max(0, len(self.lineas) - alto))
        return True

    def ventana(self, alto: int) -> Tuple[List[Text], str]:
        """(las líneas a la vista, «1-19 de 24»)."""
        self.arriba = min(max(0, self.arriba), max(0, len(self.lineas) - alto))
        visibles = self.lineas[self.arriba:self.arriba + max(0, alto)]
        return visibles, f"{self.arriba + 1}-{self.arriba + len(visibles)} de {len(self.lineas)}" if visibles else ""


# ------------------------------------------------------------------ estados
def estado_vacio(app, clave: str) -> List[Text]:
    """Una línea en `tenue` que dice qué hacer (el texto, de recorder/ayuda.py)."""
    return [app.t((ayuda.linea(clave), "tenue"))]


def estado_error(app, texto: str) -> List[Text]:
    """Una línea en `error` con su símbolo, para lo que no se pudo hacer."""
    return [app.t((f"⚠ {texto}", "error"))]
