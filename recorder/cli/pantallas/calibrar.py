"""Calibrar: los ajustes de los filtros y, fija abajo, una frase de prueba cuyo veredicto se recalcula al
escribir y al cambiar cualquier ajuste (docs/terminal-especificacion.md, sección 7.3).

Sobre la misma lógica que `daily calibrar` y la ventana (filters/tuning.py): el mismo `TuningForm`, el mismo
guardado (`apply_tuning` y `ConfigManager.save`) y la misma tabla «antes → después». Las filas son texto
(Enter lo edita, con cursor), números (←→ mueven de paso en paso dentro de su rango; Enter permite teclearlo),
un interruptor y una acción («Añadir las comunes»). La frase de prueba es la última fila y queda siempre a la
vista: si la lista no cabe, es la lista la que se desplaza.
"""
import copy
import dataclasses
from typing import Dict, List, Optional, Sequence, Tuple

from rich.cells import cell_len
from rich.text import Text

from ... import ayuda
from ...filters.blacklist import contains_blacklisted_phrase
from ...filters.echo import strip_prompt_echo
from ...filters.lexicon import fix
from ...filters.samples import random_sample
from ...filters.tuning import (
    COMMON_IGNORE, THRESHOLD_RANGES, TuningForm, apply_tuning, format_ignore, test_phrase, tuning_form,
    with_common_ignore,
)
from .. import configurar
from ..teclas import AVPAG, DERECHA, ENTER, ESC, ESPACIO, FIN, INICIO, IZQUIERDA, REPAG
from .base import Pantalla, mover
from .componentes import CampoTexto, Confirmacion, Fila, Interruptor, ListaAjustes, Numerico, coma
from .marco import ventana

TEXTO, NUMERO, INTERRUPTOR, ACCION = "texto", "numero", "interruptor", "accion"  # lo que hace Enter en cada fila
COMUNES = "comunes"  # el campo de la fila que no edita nada: añade las frases comunes
SIMBOLO_SE_QUEDA, SIMBOLO_SE_DESCARTA = "✅", "⛔"
SANGRIA_PROBAR = 5  # columnas hasta la frase de prueba y su veredicto
SANGRIA_CONTINUACION = 2  # lo que se mete más el veredicto cuando pasa a otra línea
MAX_LINEAS_VEREDICTO = 3
MIN_LINEAS_LISTA = 5  # lo mínimo de lista que se deja a la vista aunque haya que acortar la prueba
HUECOS_PISTA = (3, 2)  # espacios entre el número y la pista de hacia dónde descarta más
# Hacia qué lado descarta más cada filtro (filters/quality.py): el de silencio y el de repeticiones descartan
# lo que pasa de su valor, así que bajarlos descarta más; el de confianza descarta lo que queda por debajo.
DESCARTA_MAS_A_LA_IZQUIERDA = {
    "no_speech_threshold": True, "logprob_threshold": False, "compression_ratio_threshold": True,
}


@dataclasses.dataclass
class Ajuste(Fila):
    """Una fila de Calibrar: su campo de `TuningForm`, qué tipo de fila es y la clave de ayuda de su explicación."""

    campo: str = ""
    tipo: str = TEXTO


# ------------------------------------------------------------------ lógica pura
def _pie(*pares: Tuple[str, str]) -> List[Tuple[str, str]]:
    """((tecla, clave), …) → ((tecla, palabra), …): la palabra de «calibrar_…» o, si no, de «pie_» + clave."""
    return [(t, ayuda.entrada(c if c.startswith("calibrar_") else "pie_" + c)[0]) for t, c in pares]


@dataclasses.dataclass(frozen=True)
class Veredicto:
    """Lo que pasa con una frase de prueba: si se queda y la línea que lo cuenta (trozos de texto y estilo)."""

    se_queda: bool
    partes: Tuple[Tuple[str, str], ...]


def decimales_de(paso: float) -> int:
    """Los decimales que enseña un número que se mueve de `paso` en `paso` (0.05 → 2, 0.1 → 1)."""
    texto = f"{paso:g}"
    return len(texto.split(".")[1]) if "." in texto else 0


def correcciones_aplicadas(texto: str, correcciones: Dict[str, str]) -> List[Tuple[str, str]]:
    """Las correcciones (mal, bien) que de verdad cambian algo de `texto`, en el orden en que se aplican."""
    aplicadas = []
    for mal, bien in correcciones.items():
        nuevo = fix(texto, {mal: bien})
        if nuevo != texto:
            aplicadas.append((mal, bien))
            texto = nuevo
    return aplicadas


def veredicto(form: TuningForm, frase: str, keywords: Sequence[str]) -> Optional[Veredicto]:
    """Qué harían los filtros tal como están escritos con `frase` (sin guardar); None si no hay frase."""
    if not frase.strip():
        return None
    resultado = test_phrase(form, frase, keywords)
    texto = lambda clave: ayuda.entrada(clave)[1].rstrip(".")  # noqa: E731 - la frase sin su punto final, con sus huecos
    if not resultado.accepted:
        if resultado.echo:
            mensaje = texto("calibrar_descarta_eco")
        else:
            coincide = next((p for p in form.ignore_list if contains_blacklisted_phrase(frase, [p])), "")
            mensaje = texto("calibrar_descarta_ignorar").format(frase=coincide)
        return Veredicto(False, ((f"{SIMBOLO_SE_DESCARTA} {mensaje}", "error"),))
    partes = [(f"{SIMBOLO_SE_QUEDA} " + texto("calibrar_se_queda").format(frase=resultado.processed), "ok")]
    base = strip_prompt_echo(frase, form.vocab) if form.echo_filter else frase.strip()
    cambios = correcciones_aplicadas(base, form.fixes_dict)
    if cambios:
        partes.append((" " + texto("calibrar_corregido").format(
            de=", ".join(m for m, _b in cambios), a=", ".join(b for _m, b in cambios)), "tenue"))
    if resultado.hits:
        partes.append((" " + texto("calibrar_con_captura").format(palabras=", ".join(resultado.hits)), "tenue"))
    return Veredicto(True, tuple(partes))


def pistas(campo: str) -> Tuple[str, str]:
    """(la que va a la izquierda, la que va a la derecha) de «← descarta más · descarta menos →» de un filtro."""
    mas, menos = ayuda.entrada("calibrar_descarta_mas")[0], ayuda.entrada("calibrar_descarta_menos")[0]
    return (mas, menos) if DESCARTA_MAS_A_LA_IZQUIERDA[campo] else (menos, mas)


# ------------------------------------------------------------------ la pantalla
class Calibrar(Pantalla):
    titulo = ayuda.entrada("menu_calibrar")[0]

    def __init__(self, terminal):
        super().__init__(terminal)
        self.config = terminal.mgr.load()
        self.error = terminal.mgr.last_error  # ilegible: se ve y se prueba, pero no se guarda
        self.form = tuning_form(self.config)
        self.numericos: Dict[str, Numerico] = {}
        for campo, (minimo, maximo, paso) in THRESHOLD_RANGES.items():
            self.numericos[campo] = Numerico(getattr(self.form, campo), minimo, maximo, paso, decimales_de(paso))
        e = lambda clave: ayuda.entrada(clave)[0]  # noqa: E731
        a = lambda campo, clave, tipo, ayuda_clave, seccion="": Ajuste(  # noqa: E731
            etiqueta=e(clave), clave=ayuda_clave, seccion=e(seccion) if seccion else "", campo=campo, tipo=tipo)
        self.lista = ListaAjustes([
            a("vocab", "calibrar_vocabulario", TEXTO, "vocabulario", "calibrar_terminos"),
            a("fixes", "calibrar_correcciones", TEXTO, "correcciones"),
            a("ignore", "calibrar_ignorar", TEXTO, "ignorar", "calibrar_inventadas"),
            a(COMUNES, "calibrar_comunes", ACCION, "comunes"),
            a("echo_filter", "calibrar_eco", INTERRUPTOR, "eco_vocab"),
            a("no_speech_threshold", "calibrar_silencio", NUMERO, "umbral_silencio", "calibrar_filtros"),
            a("logprob_threshold", "calibrar_confianza", NUMERO, "umbral_confianza"),
            a("compression_ratio_threshold", "calibrar_repeticiones", NUMERO, "umbral_bucles"),
        ])
        self.sel = 0  # 0..len(lista.filas)-1 son filas de la lista; la última posición es la frase de prueba
        self.frase = ""
        self.editando: Optional[CampoTexto] = None  # el campo abierto: el de una fila o el de la frase de prueba
        self.avisado = False  # ya se dijo que hay cambios sin guardar: el siguiente Esc sale

    # ------------------------------------------------------------ estado
    @property
    def escribiendo(self) -> bool:
        return self.editando is not None

    @property
    def n(self) -> int:
        return len(self.lista.filas) + 1

    @property
    def en_probar(self) -> bool:
        return self.sel == len(self.lista.filas)

    @property
    def ajuste(self) -> Ajuste:
        return self.lista.filas[self.sel]

    def cambios(self) -> List[Tuple[str, str, str]]:
        nuevo = copy.deepcopy(self.config)
        apply_tuning(nuevo, self.form)
        return configurar.diferencias(self.config, nuevo)

    def _frase_viva(self) -> str:
        """La frase que se está probando: la que se teclea ahora o la última aceptada."""
        return self.editando.texto if self.editando is not None and self.en_probar else self.frase

    def _form_vivo(self) -> TuningForm:
        """El formulario con lo que se está tecleando en una fila de texto, para que el veredicto cambie al escribir."""
        if self.editando is None or self.en_probar or self.ajuste.tipo != TEXTO:
            return self.form
        return dataclasses.replace(self.form, **{self.ajuste.campo: self.editando.texto})

    # ------------------------------------------------------------ pintar
    def marca(self):
        if self.cambios():
            return f"● {ayuda.entrada('terminal_marca_cambios')[0]}", "acento"
        return "", "tenue"

    def ayuda(self):
        if self.editando is not None:
            return ayuda.linea("opciones_editar"), "tenue"
        return ayuda.linea("calibrar_probar" if self.en_probar else self.ajuste.clave), "tenue"

    def _pista(self, campo: str, libre: int, ancho_numero: int) -> List[Tuple[str, str]]:
        """«← descarta más · descarta menos →» si cabe; si no, solo el lado de la izquierda, y si no, nada."""
        izquierda, derecha = pistas(campo)
        pr = self.app.presentar
        for hueco, texto in ((HUECOS_PISTA[0], f"← {izquierda} · {derecha} →"), (HUECOS_PISTA[0], f"← {izquierda}"),
                             (HUECOS_PISTA[1], f"← {izquierda}")):
            if ancho_numero + hueco + cell_len(pr(texto)) <= libre:
                return [(" " * hueco + texto, "tenue")]
        return []

    def partes_valor(self, a: Ajuste, elegida: bool, ancho: int):
        if a.tipo == ACCION:
            return []
        if elegida and self.editando is not None:
            return self.editando.partes(ancho, self.app.elidido)
        if a.tipo == INTERRUPTOR:
            return Interruptor(getattr(self.form, a.campo)).partes(self.app.juego)
        if a.tipo == NUMERO:
            partes = self.numericos[a.campo].partes(elegida)
            if elegida:
                partes += self._pista(a.campo, ancho, sum(cell_len(s) for s, _e in partes))
            return partes
        valor = getattr(self.form, a.campo)
        return [(valor or ayuda.entrada("terminal_vacio")[0], "texto" if elegida else "tenue")]

    def _bloque_probar(self, ancho: int) -> List[Text]:
        """El rótulo, la frase (o su campo abierto) y el veredicto, partido a `ancho`."""
        t = self.app.t
        elegida = self.en_probar
        marca = ("▶" if elegida else " ", "acento")
        hueco = (" " * (SANGRIA_PROBAR - 1), "texto")
        if self.editando is not None and elegida:
            fila = [marca, hueco, *self.editando.partes(ancho - SANGRIA_PROBAR, self.app.elidido)]
        elif self.frase:
            fila = [marca, hueco, ("› ", "acento"), (self.frase, "elegido" if elegida else "texto")]
        else:
            fila = [marca, hueco, (ayuda.entrada("calibrar_probar_vacio")[1].rstrip("."), "tenue")]
        lineas = [t((" " * 2 + ayuda.entrada("calibrar_probar")[0], "bold")), self.app.t_fila(*fila) if elegida else t(*fila)]
        v = veredicto(self._form_vivo(), self._frase_viva(), self.config.keywords)
        if v:
            partes = self.app.parrafo(list(v.partes), ancho - SANGRIA_PROBAR, SANGRIA_CONTINUACION)
            lineas += [Text(" " * SANGRIA_PROBAR) + linea for linea in partes]
        return lineas

    def cuerpo(self, ancho, sitio):
        self.lista.sel = self.sel if self.sel < len(self.lista.filas) else -1  # la frase de prueba no es de la lista
        lista, foco = self.lista.lineas(self.app, self.partes_valor, ancho, sitio)
        probar = self._bloque_probar(ancho)
        fijo = probar[:2]
        veredicto_lineas = probar[2:][:MAX_LINEAS_VEREDICTO]
        reservado = len(fijo) + len(veredicto_lineas) + 1  # +1: la línea en blanco sobre «Probar una frase»
        sobra = sitio - MIN_LINEAS_LISTA
        if reservado > sobra:  # no cabe: se quita el respiro y se acorta el veredicto
            veredicto_lineas = veredicto_lineas[:max(0, sobra - len(fijo))]
            reservado = len(fijo) + len(veredicto_lineas)
            blanco: List[Text] = []
        else:
            blanco = [Text()]
        sitio_lista = max(1, sitio - reservado)
        self.lista.sitio = sitio_lista
        filas, arriba, abajo = ventana(len(lista), foco, sitio_lista)
        visibles = [lista[i] for i in filas]
        if arriba:
            visibles.insert(0, self.app._con_marcador("terminal_mas_arriba", arriba))
        if abajo:
            visibles.append(self.app._con_marcador("terminal_mas_abajo", abajo))
        return visibles + blanco + fijo + veredicto_lineas, 0  # el resto lo rellena el marco: la prueba va pegada a la lista y, si esta no cabe, fija abajo

    def teclas(self):
        if self.editando is not None:
            return _pie(("←→", "cursor"), ("Enter", "aceptar"), ("Esc", "cancelar"))
        if self.en_probar:
            principal, cambiar = ("Enter", "calibrar_pie_teclear"), []
        else:
            tipo = self.ajuste.tipo
            principal = {
                TEXTO: ("Enter", "calibrar_pie_teclear"), NUMERO: ("Enter", "calibrar_pie_teclear"),
                INTERRUPTOR: ("Espacio", "cambiar"), ACCION: ("Enter", "usar"),
            }[tipo]
            cambiar = [("←→", "calibrar_pie_ajustar" if tipo == NUMERO else "cambiar")] if tipo in (NUMERO, INTERRUPTOR) else []
        return _pie(
            *cambiar, ("g", "guardar"), ("Esc", "volver"), ("↑↓", "mover"), ("e", "calibrar_pie_ejemplo"), principal,
            ("?", "ayuda"), ("t", "tema"),
        )

    # ------------------------------------------------------------ teclas
    def _mover(self, k: str) -> bool:
        movida = mover(self.sel, self.n, k)
        if movida is not None:
            self.sel = movida
        elif k == INICIO:
            self.sel = 0
        elif k == FIN:
            self.sel = self.n - 1
        elif k in (REPAG, AVPAG):
            pagina = max(1, self.lista.sitio - 1)
            self.sel = min(self.n - 1, max(0, self.sel + (pagina if k == AVPAG else -pagina)))
        else:
            return False
        return True

    def tecla(self, k):
        if self.editando is not None:
            if k == ENTER:
                self._aceptar()
            elif k == ESC:
                self.editando = None
            else:
                self.editando.tecla(k)
            return True
        if k not in (ESC, "q"):
            self.avisado = False  # tras el aviso se siguió trabajando: el próximo Esc vuelve a avisar
        if self._mover(k):
            return True
        if k == "e":
            self.frase = random_sample(self.form.vocab, self.form.fixes_dict, self.form.ignore_list, self.config.keywords)
        elif k == "g":
            self._pedir_guardar()
        elif k in (ESC, "q"):
            if not self.cambios() or self.avisado:
                return False  # sale la terminal
            self.avisado = True
            self.app.avisar(f"⚠ {ayuda.linea('terminal_sin_guardar')}", "error")
        elif self.en_probar:
            if k != ENTER:
                return False
            self.editando = CampoTexto(self.frase)
        else:
            return self._tecla_de_fila(k)
        return True

    def _tecla_de_fila(self, k: str) -> bool:
        a = self.ajuste
        if a.tipo == INTERRUPTOR and k in (IZQUIERDA, DERECHA, ESPACIO, ENTER):
            setattr(self.form, a.campo, not getattr(self.form, a.campo))
        elif a.tipo == NUMERO and k in (IZQUIERDA, DERECHA):
            numerico = self.numericos[a.campo]
            numerico.tecla(k)
            setattr(self.form, a.campo, numerico.valor)
        elif a.tipo == NUMERO and k == ENTER:
            self.editando = CampoTexto(self.numericos[a.campo].texto())
        elif a.tipo == TEXTO and k == ENTER:
            self.editando = CampoTexto(getattr(self.form, a.campo))
        elif a.tipo == ACCION and k == ENTER:
            self._anadir_comunes()
        else:
            return False
        return True

    def _aceptar(self) -> None:
        if self.en_probar:
            self.frase, self.editando = self.editando.texto, None
            return
        a = self.ajuste
        if a.tipo == NUMERO:
            numerico = self.numericos[a.campo]
            if not numerico.aceptar(self.editando.texto):
                titulo, explicacion = ayuda.entrada("calibrar_fuera_de_rango")
                self.app.avisar(f"⚠ {titulo}: " + explicacion.format(
                    min=coma(numerico.minimo, numerico.decimales), max=coma(numerico.maximo, numerico.decimales)), "error")
                return
            setattr(self.form, a.campo, numerico.valor)
        else:
            setattr(self.form, a.campo, self.editando.texto.strip() if a.campo == "vocab" else self.editando.texto)
        self.editando = None

    def _anadir_comunes(self) -> None:
        antes = self.form.ignore_list
        nuevas = [c for c in COMMON_IGNORE if c not in antes]
        if not nuevas:
            self.app.avisar(ayuda.linea("calibrar_comunes_ya"), "tenue")
            return
        self.form.ignore = format_ignore(with_common_ignore(antes))
        self.app.avisar(
            ayuda.linea("calibrar_comunes_hecho").format(n=len(nuevas), total=len(self.form.ignore_list)), "ok")

    # ------------------------------------------------------------ guardar
    def _pedir_guardar(self) -> None:
        if self.error:
            self.app.avisar(f"⚠ {ayuda.linea('terminal_no_se_guarda')}", "error")
        elif not self.cambios():
            self.app.avisar(ayuda.linea("terminal_sin_cambios"), "tenue")
        else:
            self.app.abrir(Confirmacion(
                self.app, self.cambios(), self._guardar, marca=self.marca(),
                encabezado=ayuda.linea("terminal_se_guardara").format(archivo=self.app.mgr.path.name).rstrip(".") + ":",
            ))

    def _guardar(self) -> None:
        nuevo = self.app.mgr.load()  # lo guardado ahora (el tema, por ejemplo, pudo cambiar): solo se tocan los filtros
        if self.app.mgr.last_error:
            self.app.avisar(f"⚠ {ayuda.linea('terminal_no_se_guarda')}", "error")
            return
        apply_tuning(nuevo, self.form)
        self.app.mgr.save(nuevo)
        self.config = nuevo
        self.avisado = False
        self.app.avisar(f"✔ {ayuda.linea('calibrar_guardado')}", "ok")
