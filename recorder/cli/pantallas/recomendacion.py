"""Recomendación del equipo: la configuración que conviene a este equipo frente a la que tienes, el porqué en
frases llanas y «Aplicar lo recomendado» con su confirmación «antes → después». Hace lo mismo que
`daily recomendar --aplicar` (`apply_recommendation` y guardar), pero sin salir de la pantalla.

Con la entrada redirigida `daily recomendar` sigue imprimiendo texto plano (recorder/cli/recomendar.py)."""
import copy
import re
import threading
from typing import List, Optional, Tuple

from rich.cells import cell_len
from rich.text import Text

from ... import ayuda
from ...config.hardware import cached_hardware, describe_hardware, peek_hardware
from ...config.schema import (
    QUALITY_PRESETS, AppConfig, Recommendation, apply_recommendation, preset_key_for_config,
)
from ...medicion import TIER_MEDIDO, recomendar
from ...metricas import hilos_efectivos
from .. import configurar
from ..teclas import ABAJO, ARRIBA, ENTER
from .base import Pantalla, pie
from .componentes import Confirmacion, estado_error

ANCHO_CON_FICHA = 70  # de ancho útil; por debajo, «Tu equipo» se quita (el equipo ya se ve en Rendimiento)
SANGRIA = 3  # margen izquierdo de la tabla y de los apartados
SANGRIA_VINETA = 4
MAX_VINETAS = 3  # «Por qué» en dos o tres viñetas
HUECO = 2  # entre las columnas de la tabla
PREFIJO = "recomendacion_"
# Las recomendaciones que no tienen ninguna medida detrás (solo cifras de terceros): se dicen «aproximadas».
NIVELES_SIN_MEDIDA = ("gpu-nvidia",)
FIN_DE_FRASE = re.compile(r"(?<=[.!?])\s+")


# ------------------------------------------------------------------ lógica pura
def vinetas(motivo: str, maximo: int = MAX_VINETAS) -> List[str]:
    """El motivo de la recomendación como frases sueltas, una por viñeta; las que pasan de `maximo` se
    juntan en la última."""
    frases = [f for f in FIN_DE_FRASE.split(motivo.strip()) if f]
    return frases[:maximo - 1] + [" ".join(frases[maximo - 1:])] if len(frases) > maximo else frases


def clave_fiabilidad(rec: Recommendation) -> str:
    """La clave de ayuda que dice la confianza de `rec` en palabras. Por el código de recommend_config:
    «medida» (hay una medición en ese modelo de procesador o tarjeta) es «medido»; «estimada» con una
    tarjeta NVIDIA, que solo tiene cifras de terceros, es «aproximado»; el resto de «estimada» (la gama
    del procesador o Vulkan, deducidas de equipos medidos) es «estimado»; la que sale de «Medir mi equipo» es
    la «medida en este equipo»."""
    if rec.tier == TIER_MEDIDO:
        return PREFIJO + "fiable_tuyo"
    if rec.confidence == "medida":
        return PREFIJO + "fiable_medido"
    if rec.tier in NIVELES_SIN_MEDIDA:
        return PREFIJO + "fiable_aprox"
    return PREFIJO + "fiable_estimado"


def _donde(device: str) -> str:
    return ayuda.entrada(PREFIJO + ("procesador" if device == "cpu" else "grafica"))[0]


def _hilos(n: int) -> str:
    return str(n) if n > 0 else ayuda.entrada("opciones_hilos_auto")[0].format(n=hilos_efectivos(0))


def _calidad(config: AppConfig) -> str:
    clave = preset_key_for_config(config)
    return QUALITY_PRESETS[clave].label if clave else "Personalizado"


def filas_comparacion(config: AppConfig, rec: Recommendation) -> List[Tuple[str, str, str, bool]]:
    """[(rótulo, ahora, recomendado, cambia)] de calidad, dónde se transcribe e hilos."""
    return [
        (
            ayuda.entrada(PREFIJO + "calidad")[0], _calidad(config), rec.label,
            (config.model, config.beam_size, config.compute_type) != (rec.model, rec.beam_size, rec.compute_type)
            or _calidad(config) != rec.label,
        ),
        (
            ayuda.entrada(PREFIJO + "donde")[0], _donde(config.device), _donde(rec.device),
            _donde(config.device) != _donde(rec.device),
        ),
        (
            ayuda.entrada(PREFIJO + "hilos")[0], _hilos(config.cpu_threads), _hilos(rec.cpu_threads),
            _hilos(config.cpu_threads) != _hilos(rec.cpu_threads),
        ),
    ]


def con_lo_recomendado(config: AppConfig, rec: Recommendation) -> AppConfig:
    """Una copia de `config` con `rec` aplicada: lo mismo que guarda `daily recomendar --aplicar`."""
    nuevo = copy.deepcopy(config)
    apply_recommendation(nuevo, rec)
    return nuevo


# ------------------------------------------------------------------ la pantalla
class Recomendacion(Pantalla):
    titulo = ayuda.entrada("menu_recomendar")[0]

    def __init__(self, terminal):
        super().__init__(terminal)
        self.rec: Optional[Recommendation] = None
        self.perfil = None
        self.foco = 0  # la línea que se mantiene a la vista cuando el cuerpo no cabe
        if peek_hardware() is None:  # el cerrojo de cached_hardware evita detectar dos veces
            threading.Thread(target=cached_hardware, daemon=True, name="equipo").start()

    # ------------------------------------------------------------ estado
    def _preparar(self) -> bool:
        """True cuando el equipo ya está detectado y la recomendación calculada (una sola vez)."""
        if self.rec is None:
            perfil = peek_hardware()
            if perfil is None:
                return False
            self.perfil = perfil
            self.rec = recomendar(perfil, self.app.config, self.app.mgr.path)  # con la última medición, si la hay
        return True

    def _no_aplica(self) -> str:
        """Por qué no se puede aplicar: lo que dice el gestor de la configuración, en una frase."""
        return ayuda.linea(PREFIJO + "no_aplica").format(motivo=self.app.mgr.last_error.rstrip("."))

    def _cambios(self) -> List[Tuple[str, str, str]]:
        if self.rec is None:
            return []
        return configurar.diferencias(self.app.config, con_lo_recomendado(self.app.config, self.rec))

    def _ya_coincide(self) -> bool:
        return self.rec is not None and not self._cambios()

    # ------------------------------------------------------------ pintar
    def ayuda(self):
        if not self._preparar():
            return "", "tenue"
        return ayuda.linea(PREFIJO + ("ya" if self._ya_coincide() else "aplicar")), "tenue"

    def teclas(self):
        resto = pie(("Esc", "volver"), ("?", "ayuda"), ("t", "tema"))
        if not self._preparar() or self._ya_coincide():
            return resto
        return [("Enter", ayuda.entrada(PREFIJO + "aplicar")[0])] + resto

    def _tabla(self, ancho: int) -> List[Text]:
        t = self.app.t
        filas = filas_comparacion(self.app.config, self.rec)
        estados = {
            True: ("● " + ayuda.entrada(PREFIJO + "cambia")[0], "acento"),
            False: ("○ " + ayuda.entrada(PREFIJO + "igual")[0], "tenue"),
        }
        pr = self.app.presentar
        cab_ahora, cab_rec = (ayuda.entrada(PREFIJO + c)[0] for c in ("ahora", "recomendado"))
        rotulo = max(cell_len(r) for r, *_ in filas)
        ahora = max([cell_len(cab_ahora)] + [cell_len(a) for _r, a, _x, _c in filas])
        rec = max([cell_len(cab_rec)] + [cell_len(x) for _r, _a, x, _c in filas])
        estado = max(cell_len(pr(e)) for e, _s in estados.values())
        aparte = SANGRIA + rotulo + HUECO + ahora + HUECO + rec + HUECO + estado <= ancho  # si no, el estado va pegado
        if not aparte:
            rec = max(cell_len(x) + 1 + cell_len(pr(estados[c][0])) for _r, _a, x, c in filas)
        lineas = [t(
            (" " * SANGRIA + " " * rotulo + " " * HUECO, "texto"), (cab_ahora.ljust(ahora) + " " * HUECO, "tenue"),
            (cab_rec, "tenue"),
        )]
        for etiqueta, actual, recomendado, cambia in filas:
            texto, estilo = estados[cambia]
            if aparte:
                partes = [(recomendado.ljust(rec) + " " * HUECO, "acento" if cambia else "texto"), (texto, estilo)]
            else:
                partes = [(recomendado + " ", "acento" if cambia else "texto"), (texto, estilo)]
            lineas.append(t(
                (" " * SANGRIA + etiqueta.ljust(rotulo) + " " * HUECO, "texto"),
                (actual.ljust(ahora) + " " * HUECO, "tenue"), *partes,
            ))
        return lineas

    def _porque(self, ancho: int) -> List[Text]:
        t = self.app.t
        lineas = [t((" " * SANGRIA + ayuda.entrada(PREFIJO + "porque")[0], "bold"))]
        for frase in vinetas(self.rec.reason):
            lineas += self.app.parrafo([(" " * SANGRIA_VINETA + "· " + frase, "texto")], ancho, sangria=SANGRIA_VINETA + 2)
        titulo, texto = ayuda.entrada(clave_fiabilidad(self.rec))
        lineas += self.app.parrafo([(" " * SANGRIA_VINETA + f"{titulo}: {texto[:1].lower()}{texto[1:]}", "tenue")], ancho, sangria=SANGRIA_VINETA)
        return lineas

    def _equipo(self, ancho: int) -> List[Text]:
        t = self.app.t
        lineas = [t((" " * SANGRIA + ayuda.entrada(PREFIJO + "equipo")[0], "bold"))]
        lineas += self.app.parrafo([(" " * SANGRIA_VINETA + describe_hardware(self.perfil), "texto")], ancho, sangria=SANGRIA_VINETA)
        for error in self.perfil.detection_errors:
            texto = ayuda.entrada(PREFIJO + "sin_detectar")[1].format(que=error)
            lineas += self.app.parrafo([(" " * SANGRIA_VINETA + texto, "tenue")], ancho, sangria=SANGRIA_VINETA)
        return lineas

    def cuerpo(self, ancho, sitio):
        if not self._preparar():
            return [self.app.spinner(ayuda.linea("terminal_detectando_equipo").rstrip(".") + "…")], 0
        t = self.app.t
        lineas: List[Text] = []
        if self.app.mgr.last_error:
            lineas += estado_error(self.app, self._no_aplica())
            lineas.append(Text())
        tabla, porque, hueco = self._tabla(ancho), self._porque(ancho), [Text()]
        if self._ya_coincide():
            accion = t(("✔ " + ayuda.entrada(PREFIJO + "ya")[0], "ok"))
        else:
            accion = self.app.t_fila(("▶", "acento"), (" " + ayuda.entrada(PREFIJO + "aplicar")[0], "elegido"))
        resto = tabla + hueco + porque + hueco + [accion]
        if len(lineas) + len(resto) > sitio:  # no cabe: la acción sube bajo la tabla y el porqué se lee bajando
            resto = tabla + hueco + [accion] + hueco + porque
        elif ancho >= ANCHO_CON_FICHA and len(lineas) + len(resto) + len(ficha := self._equipo(ancho)) + 1 <= sitio:
            resto = ficha + hueco + resto  # «Tu equipo» solo si cabe todo lo demás a la vez
        lineas += resto
        self.foco = min(self.foco, len(lineas) - 1)
        return lineas, self.foco

    # ------------------------------------------------------------ teclas
    def tecla(self, k):
        if self.rec is None:
            return False  # mientras detecta, solo se puede volver
        if k in (ARRIBA, "k"):
            self.foco = max(0, self.foco - 1)
        elif k in (ABAJO, "j"):
            self.foco += 1
        elif k == ENTER:
            if not self._ya_coincide():
                self._pedir_aplicar()
        else:
            return False
        return True

    def _pedir_aplicar(self) -> None:
        config = self.app.mgr.load()
        if self.app.mgr.last_error:  # guardar pisaría lo que el usuario tiene escrito en un archivo que no se lee
            self.app.avisar("⚠ " + self._no_aplica(), "error")
            return
        cambios = configurar.diferencias(config, con_lo_recomendado(config, self.rec))
        if not cambios:
            self.app.avisar("✔ " + ayuda.entrada(PREFIJO + "ya")[0], "ok")
            return
        self.app.abrir(Confirmacion(
            self.app, cambios, self._aplicar,
            encabezado=ayuda.linea("terminal_se_guardara").format(archivo=self.app.mgr.path.name).rstrip(".") + ":",
        ))

    def _aplicar(self) -> None:
        config = self.app.mgr.load()
        if self.app.mgr.last_error:
            self.app.avisar("⚠ " + self._no_aplica(), "error")
            return
        apply_recommendation(config, self.rec)
        self.app.mgr.save(config)
        self.app.config = config
        self.app.avisar("✔ " + ayuda.linea(PREFIJO + "aplicada"), "ok")






