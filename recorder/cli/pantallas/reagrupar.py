"""Reagrupar nota: la ventana «Reagrupar nota» como pantalla del menú, viendo el resultado mientras se eligen
las opciones. Dos pantallas: `ReagruparNota` (elegir la nota) y `ReagruparOpciones` (ajustar con la vista previa
viva y crear la copia). Usa la misma lógica que `daily sintesis` (digest/): `preview_digest` solo lee el
original y `write_digest` escribe una copia nueva, nunca encima.

Con 80 columnas o más la vista previa va a la derecha de las opciones; con menos, debajo. RePág y AvPág la
desplazan. «Crear la copia» ([g] o Enter en su fila) dice cómo se llamará y pide confirmar antes de escribir.
"""
import contextlib
import dataclasses
import datetime as dt
import pathlib
from typing import List, Optional, Tuple

from rich.cells import cell_len
from rich.text import Text

from ... import ayuda
from ...digest import (
    DEFAULT_INTERVAL,
    INTERVAL_LABELS,
    INTERVALS,
    DerivedSourceError,
    DigestOptions,
    DigestPreview,
    digest_options,
    list_originals,
    preview_digest,
    unique_digest_path,
    write_digest,
)
from ...digest.writer import WouldOverwriteSourceError
from ..sintesis import cuerpo as cuerpo_de_la_copia, en_curso
from ..teclas import ABAJO, ARRIBA, AVPAG, DERECHA, ENTER, ESC, ESPACIO, IZQUIERDA, REPAG
from .base import Pantalla, pie
from .componentes import (
    Fila, Interruptor, ListaAjustes, ListaSeleccion, VistaPrevia, estado_error, estado_vacio, recortar_por_el_medio,
)
from .marco import MARGEN

ANCHO_DOS_COLUMNAS = 80  # columnas de la terminal desde las que la vista previa va a la derecha
ANCHO_PREVIA_MIN = 20  # lo mínimo que tiene sentido enseñar de la vista previa en dos columnas
SEPARADOR = " │ "  # entre las opciones y la vista previa
FORMATO_FECHA, FORMATO_HORA = "%d/%m/%Y", "%H:%M"
HUECO_COLUMNAS = 2  # entre las columnas del listado de notas
SANGRIA_NOTA = 5  # la marca de fila, el número y su hueco
SANGRIA_PREVIA = 2  # las líneas partidas de la vista previa
SANGRIA_CONFIRMAR = 2
ANCHO_AVISO_EN_CURSO = 17  # lo que ocupa « ● escribiéndose» a la derecha del nombre
LINEAS_FIJAS_PREVIA = 2  # título y cifras sobre la vista previa
NUMEROS = "123456789"

# Las filas de las opciones (el `dato` de cada `Fila`) y la clave de su texto de ayuda.
AGRUPAR, UNIR, HORA, IMAGENES, CORTAS, ECO, CREAR = "agrupar", "unir", "hora", "imagenes", "cortas", "eco", "crear"
CLAVES = {
    AGRUPAR: "reagrupar_agrupar", UNIR: "reagrupar_unir", HORA: "reagrupar_hora_corta",
    IMAGENES: "reagrupar_sin_imagenes", CORTAS: "reagrupar_cortas", ECO: "reagrupar_eco", CREAR: "reagrupar_crear",
}
INTERRUPTORES = (UNIR, HORA, IMAGENES, CORTAS, ECO)
# Lo que digest_options propone por defecto (las casillas de la ventana): imágenes fuera, eco fuera, cortas dentro.
POR_DEFECTO = {UNIR: True, HORA: True, IMAGENES: True, CORTAS: False, ECO: True}


def titulo(clave: str) -> str:
    return ayuda.entrada(clave)[0]


def estilo_de(linea: str) -> str:
    """El color de una línea de la copia: títulos en acento, avisos y marcas en tenue, capturas en mic."""
    if linea.startswith("#"):
        return "acento"
    if linea.startswith(">"):
        return "tenue"
    if "![](" in linea:
        return "mic"
    return "texto"


def sin_aviso(lineas: List[str]) -> List[str]:
    """Las líneas de la copia sin el aviso («No es un resumen…») que va tras el título: la pantalla ya lo dice al
    confirmar y repetirlo en cada vista previa lo gastaría. Es el primer bloque con «>» antes del contenido."""
    for i, linea in enumerate(lineas):
        if linea.startswith(">"):
            fin = i
            while fin < len(lineas) and lineas[fin].startswith(">"):
                fin += 1
            fin += 1 if fin < len(lineas) and not lineas[fin].strip() else 0
            return lineas[:i] + lineas[fin:]
        if linea.startswith(("##", "- ")):
            break
    return lineas


def frases_de(vista: DigestPreview) -> int:
    """Las frases de la copia: sus viñetas de primer nivel."""
    return sum(1 for linea in cuerpo_de_la_copia(vista.markdown) if linea.startswith("- "))


def cifras(vista: DigestPreview) -> str:
    """«10 frases en 2 tramos · 67 palabras, 0 quitadas» (sin tramos si no se agrupa)."""
    clave = "reagrupar_previa" if vista.blocks else "reagrupar_previa_sin_tramos"
    return ayuda.linea(clave).rstrip(".").format(
        frases=frases_de(vista), tramos=vista.blocks, palabras=vista.words, quitadas=max(0, vista.source_words - vista.words),
    )


@dataclasses.dataclass
class Nota:
    ruta: pathlib.Path
    fecha: str
    hora: str
    tamano: str
    en_curso: bool = False


# ------------------------------------------------------------------ elegir la nota
class ReagruparNota(Pantalla):
    titulo = ayuda.entrada("menu_sintesis")[0]

    def __init__(self, terminal):
        super().__init__(terminal)
        rutas = list_originals(terminal.config.notes_dir)
        activa = en_curso(rutas)
        self.notas: List[Nota] = []
        for ruta in rutas:
            try:
                st = ruta.stat()
            except OSError:  # desapareció entre listarla y verla
                continue
            m = dt.datetime.fromtimestamp(st.st_mtime)
            self.notas.append(Nota(ruta, f"{m:{FORMATO_FECHA}}", f"{m:{FORMATO_HORA}}", f"{st.st_size / 1024:.0f} KB", ruta.name == activa))
        self.lista = ListaAjustes([Fila(n.ruta.name) for n in self.notas])

    def ayuda(self):
        if not self.notas:
            return "", "tenue"
        return ayuda.linea("reagrupar_en_curso" if self.notas[self.lista.sel].en_curso else "reagrupar_elegir"), "tenue"

    def teclas(self):
        if not self.notas:
            return pie(("Esc", "volver"))
        n = min(len(self.notas), len(NUMEROS))
        directo = [(f"1-{n}", "directo")] if n > 1 else []
        return pie(("Enter", "elegir"), ("Esc", "volver"), ("↑↓", "mover"), *directo, ("?", "ayuda"))

    def cuerpo(self, ancho, sitio):
        if not self.notas:
            return estado_vacio(self.app, "reagrupar_vacio"), 0
        t = self.app.t
        self.lista.sitio = sitio
        nombre = max(cell_len(n.ruta.name) for n in self.notas)
        tamano = max(len(n.tamano) for n in self.notas)
        fecha, hora = len(self.notas[0].fecha), len(self.notas[0].hora)
        # fecha y hora se quitan cuando no caben, dejando sitio al aviso de la nota que se está escribiendo
        con_fecha = SANGRIA_NOTA + nombre + 2 * HUECO_COLUMNAS + fecha + hora + HUECO_COLUMNAS + tamano + ANCHO_AVISO_EN_CURSO <= ancho
        nombre = min(nombre, max(8, ancho - SANGRIA_NOTA - HUECO_COLUMNAS - tamano - ANCHO_AVISO_EN_CURSO - (
            2 * HUECO_COLUMNAS + fecha + hora if con_fecha else 0
        )))
        hueco = " " * HUECO_COLUMNAS
        cabecera = [(" " * SANGRIA_NOTA + titulo("reagrupar_col_nota").ljust(nombre), "tenue")]
        if con_fecha:
            cabecera.append((hueco + titulo("reagrupar_col_fecha").ljust(fecha) + hueco + titulo("reagrupar_col_hora").ljust(hora), "tenue"))
        cabecera.append((hueco + titulo("reagrupar_col_tamano").rjust(tamano), "tenue"))
        lineas = [t(*cabecera)]
        for i, nota in enumerate(self.notas):
            elegida = i == self.lista.sel
            numero = f"{i + 1}" if i < len(NUMEROS) else " "
            partes = [
                ("▶" if elegida else " ", "acento"), (f" {numero}  ", "acento"),
                (recortar_por_el_medio(nota.ruta.name, nombre, self.app.elidido).ljust(nombre), "elegido" if elegida else "texto"),
            ]
            if con_fecha:
                partes.append((f"{hueco}{nota.fecha}{hueco}{nota.hora}", "tenue"))
            partes.append((hueco + nota.tamano.rjust(tamano), "tenue"))
            if nota.en_curso:
                partes.append((f"{hueco}● {titulo('reagrupar_en_curso')}", "acento"))
            lineas.append(self.app.t_fila(*partes) if elegida else t(*partes))
        return lineas, self.lista.sel + 1

    def tecla(self, k):
        if not self.notas:
            return False
        if self.lista.tecla(k):
            return True
        if k == ENTER:
            self._elegir(self.lista.sel)
        elif k in NUMEROS and int(k) <= len(self.notas):
            self._elegir(int(k) - 1)
        else:
            return False
        return True

    def _elegir(self, i: int) -> None:
        self.lista.sel = i
        self.app.abrir(ReagruparOpciones(self.app, self.notas[i].ruta, self.notas[i].en_curso))


# ------------------------------------------------------------------ ajustar y crear
class ReagruparOpciones(Pantalla):
    """Las opciones y, junto a ellas, la copia tal como quedaría. Con `confirmando` el cuerpo pasa a «Se creará…»."""

    def __init__(self, terminal, origen: pathlib.Path, en_curso: bool = False):
        super().__init__(terminal)
        self.origen, self.en_curso = pathlib.Path(origen), en_curso
        self.cada = INTERVALS.index(DEFAULT_INTERVAL)
        self.interruptores = {c: Interruptor(v) for c, v in POR_DEFECTO.items()}
        etiquetas = {c: titulo(CLAVES[c]) for c in CLAVES}
        self.lista = ListaAjustes([Fila(etiquetas[c], CLAVES[c], dato=c) for c in (AGRUPAR, *INTERRUPTORES, CREAR)])
        self.previa = VistaPrevia()
        self.confirmando = False
        self._alto_previa = 1  # líneas de la vista previa que se vieron la última vez: lo que mide una página
        self._clave: Optional[Tuple] = None  # lo que se calculó: opciones, estado del original y ancho
        self._vista: Optional[DigestPreview] = None
        self._error = ""

    # ------------------------------------------------------------ estado
    @property
    def titulo(self) -> str:  # la ruta dice la nota y, al confirmar, «Crear la copia»
        return titulo("reagrupar_crear") if self.confirmando else self.origen.name

    @property
    def minutos(self) -> int:
        return INTERVALS[self.cada]

    def opciones(self) -> DigestOptions:
        i = self.interruptores
        return digest_options(
            self.minutos, merge=i[UNIR].valor, strip_stamps=i[HORA].valor, keep_captures=not i[IMAGENES].valor,
            drop_short=i[CORTAS].valor, drop_echo=i[ECO].valor, vocab=self.app.config.vocab,
        )

    def deshabilitada(self, dato: str) -> bool:
        """«Hora corta» no se puede sin agrupar: ahí la hora exacta es lo único que ordena las frases."""
        return dato == HORA and not self.minutos

    def _calcular(self, ancho: int) -> None:
        """La copia en memoria con las opciones de ahora, y sus líneas partidas a `ancho`. Se recalcula solo
        si cambió algo: una opción, el original (si se está escribiendo) o el ancho."""
        opts = self.opciones()
        try:
            st = self.origen.stat()
            clave = (dataclasses.astuple(opts), st.st_mtime_ns, st.st_size, ancho)
        except OSError as e:
            self._vista, self._error, self._clave = None, ayuda.linea("reagrupar_error").format(motivo=e), None
            self.previa.poner([])
            return
        if clave == self._clave:
            return
        self._clave = clave
        try:
            self._vista, self._error = preview_digest(self.origen, opts), ""
        except DerivedSourceError:
            self._vista, self._error = None, ayuda.linea("reagrupar_derivada")
        except OSError as e:
            self._vista, self._error = None, ayuda.linea("reagrupar_error").format(motivo=e)
        lineas: List[Text] = []
        if self._vista is not None:
            for linea in sin_aviso(cuerpo_de_la_copia(self._vista.markdown)):
                partidas = self.app.parrafo([(linea, estilo_de(linea))], ancho, SANGRIA_PREVIA) if linea.strip() else []
                lineas += partidas or [Text()]
        self.previa.poner(lineas)

    # ------------------------------------------------------------ pintar
    def ayuda(self):
        if self.confirmando:
            return ayuda.linea("reagrupar_confirmar"), "tenue"
        dato = self.lista.actual.dato
        if dato == AGRUPAR and not self.minutos:  # «Hora corta» no se puede elegir: se explica aquí
            return ayuda.linea("reagrupar_hora_corta_no"), "tenue"
        return ayuda.linea(CLAVES[dato]), "tenue"

    def teclas(self):
        crear = (("Enter" if self.lista.actual.dato == CREAR else "g", titulo("reagrupar_crear")),)
        if self.confirmando:
            return [("Enter", titulo("reagrupar_crear")), ("Esc", titulo("reagrupar_seguir"))]
        return [
            *pie(("←→", "cambiar")), *crear, *pie(("Esc", "volver"), ("RePág/AvPág", "vista_previa"), ("↑↓", "mover"), ("?", "ayuda"), ("t", "tema")),
        ]

    def _valor(self, fila: Fila, elegida: bool, ancho: int):
        if fila.dato == CREAR:
            return []
        if fila.dato == AGRUPAR:
            etiqueta = INTERVAL_LABELS[self.minutos]
            return [("‹ ", "acento"), (etiqueta, "texto"), (" ›", "acento")] if elegida else [(etiqueta, "tenue")]
        partes = self.interruptores[fila.dato].partes(self.app.juego)
        if self.deshabilitada(fila.dato):  # no cuenta sin agrupar: se ve apagada
            return [(s, "tenue") for s, _e in Interruptor(False).partes(self.app.juego)]
        return partes

    @contextlib.contextmanager
    def _ancho(self, ancho: int):
        """Las líneas de `app.t` y `app.t_fila` miden `ancho` mientras se componen las opciones."""
        anterior, self.app._ancho = self.app._ancho, ancho
        try:
            yield
        finally:
            self.app._ancho = anterior

    def _opciones(self, ancho: int, sitio: int, con_regla: bool) -> Tuple[List[Text], int]:
        """La lista de opciones, con una regla antes de «Crear la copia» si `con_regla`."""
        with self._ancho(ancho):
            lineas, foco = self.lista.lineas(self.app, self._valor, ancho, sitio)
            regla = self.app.t(("─" * ancho, "borde"))
        if con_regla:
            lineas.insert(len(lineas) - 1, regla)
        return lineas, foco + (1 if con_regla and self.lista.sel == len(self.lista.filas) - 1 else 0)

    def _lineas_previa(self, ancho: int, alto: int) -> List[Text]:
        """Título con la posición, las cifras y `alto` líneas de la copia."""
        if self._vista is None:
            return estado_error(self.app, self._error)
        self._alto_previa = max(1, alto)
        visibles, posicion = self.previa.ventana(self._alto_previa)
        with self._ancho(ancho):
            cabecera = self.app.t((titulo("reagrupar_previa"), "bold"))
            hueco = max(1, ancho - cell_len(cabecera.plain) - len(posicion))
            cabecera = self.app.t((titulo("reagrupar_previa"), "bold"), (" " * hueco + posicion, "tenue"))
            cifra = self.app.t((cifras(self._vista), "tenue"))
        return [cabecera, cifra, *visibles]

    def _confirmacion(self, ancho: int) -> List[Text]:
        destino = unique_digest_path(self.origen, self.opciones())
        etiquetas = (titulo("reagrupar_se_creara"), titulo("reagrupar_en"))
        columna = max(len(e) for e in etiquetas)
        sangria = " " * SANGRIA_CONFIRMAR
        valor = max(1, ancho - SANGRIA_CONFIRMAR - columna - HUECO_COLUMNAS)
        t = self.app.t
        lineas = [
            t((sangria + etiquetas[0].ljust(columna) + " " * HUECO_COLUMNAS, "tenue"), (destino.name, "acento")),
            t((sangria + etiquetas[1].ljust(columna) + " " * HUECO_COLUMNAS, "tenue"),
              (recortar_por_el_medio(str(destino.parent), valor, self.app.elidido), "texto")),
            Text(),
        ]
        if self._vista is not None:
            lineas.append(t((sangria + cifras(self._vista), "tenue")))
        return lineas

    def cuerpo(self, ancho, sitio):
        dos = ancho + 2 * MARGEN >= ANCHO_DOS_COLUMNAS and ancho - len(SEPARADOR) >= ANCHO_PREVIA_MIN
        if self.confirmando:
            self._calcular(ancho)
            return self._confirmacion(ancho), 0
        if not dos:
            self._calcular(ancho)
            lista, foco = self._opciones(ancho, sitio, False)
            with self._ancho(ancho):
                regla = self.app.t(("─" * ancho, "borde"))
            restante = sitio - len(lista) - 1 - LINEAS_FIJAS_PREVIA
            return lista + [regla] + self._lineas_previa(ancho, max(1, restante)), foco
        izquierda = self._ancho_opciones()
        derecha = ancho - izquierda - len(SEPARADOR)
        self._calcular(derecha)
        lista, foco = self._opciones(izquierda, sitio, True)
        previa = self._lineas_previa(derecha, sitio - LINEAS_FIJAS_PREVIA)
        separador = self.app.t((SEPARADOR, "borde"))
        lineas = []
        for i in range(max(len(lista), len(previa))):
            uno = lista[i] if i < len(lista) else Text()
            uno = uno.copy()
            uno.pad_right(max(0, izquierda - cell_len(uno.plain)))
            lineas.append(uno + separador + (previa[i] if i < len(previa) else Text()))
        return lineas, foco

    def _ancho_opciones(self) -> int:
        """Lo que miden las opciones en dos columnas: la etiqueta más larga y el valor más ancho de «Agrupar»."""
        etiquetas = max(cell_len(self.app.presentar(f.etiqueta)) for f in self.lista.filas)
        valor = max(cell_len(e) for e in INTERVAL_LABELS.values()) + 4  # «‹ » y « ›»
        return 2 + etiquetas + 2 + valor

    # ------------------------------------------------------------ teclas
    def tecla(self, k):
        if self.confirmando:
            if k == ENTER:
                self._crear()
            elif k in (ESC, "q"):
                self.confirmando = False
            return True
        if k in (REPAG, AVPAG):
            return self.previa.tecla(k, self._alto_previa)
        fila = self.lista.actual
        if self.lista.tecla(k):
            self._saltar_apagada(k)
        elif k in (IZQUIERDA, DERECHA) and fila.dato == AGRUPAR:
            self.cada = min(len(INTERVALS) - 1, max(0, self.cada + (1 if k == DERECHA else -1)))
        elif fila.dato in INTERRUPTORES and k in (IZQUIERDA, DERECHA, ESPACIO, ENTER):
            self.interruptores[fila.dato].alternar()
        elif k == ENTER and fila.dato == AGRUPAR:
            self._abrir_lista()
        elif k == "g" or (k == ENTER and fila.dato == CREAR):
            self._pedir_crear()
        else:
            return False
        return True

    def _saltar_apagada(self, k: str) -> None:
        """↑↓ no se paran en una fila apagada: pasan a la siguiente en esa dirección."""
        if self.deshabilitada(self.lista.actual.dato):
            self.lista.tecla(ARRIBA if k in (ARRIBA, "k") else ABAJO)

    def _abrir_lista(self) -> None:
        self.app.abrir(ListaSeleccion(
            self.app, self.lista.actual.etiqueta, [(INTERVAL_LABELS[m], m) for m in INTERVALS], self.minutos,
            lambda minutos: setattr(self, "cada", INTERVALS.index(minutos)), clave_ayuda=CLAVES[AGRUPAR],
        ))

    def _pedir_crear(self) -> None:
        if self._vista is None:
            self.app.avisar(f"⚠ {self._error}", "error")
        else:
            self.confirmando = True

    def _crear(self) -> None:
        """Escribe la copia y vuelve a las opciones con el aviso; nunca sobrescribe (write_digest numera)."""
        try:
            destino = write_digest(self.origen, self.opciones())
        except (DerivedSourceError, WouldOverwriteSourceError, OSError) as e:
            self.confirmando = False
            self.app.avisar(f"⚠ {ayuda.linea('reagrupar_error').format(motivo=e)}", "error")
            return
        self.confirmando = False
        self.app.avisar(f"✔ {ayuda.linea('reagrupar_creada').format(nombre=destino.name)}", "ok")
