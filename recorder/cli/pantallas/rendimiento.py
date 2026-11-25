"""Rendimiento: si el equipo da para grabar (desde el menú) y cómo va una grabación (la vista en vivo).

Dos vistas con las mismas piezas (docs/terminal-especificacion.md, sección 7.6):

- `vista_reposo`: sin grabación. Veredicto de margen (media del procesador del equipo en los últimos
  `VENTANA_MARGEN_S` s), con qué se transcribiría, y procesador, tarjeta gráfica y memoria del equipo con
  su tendencia de ~2 min. La pinta la pantalla `Rendimiento` del menú.
- `vista_en_vivo`: durante la grabación. Veredicto de velocidad frente al tiempo real, cola y atraso, lo que
  gasta Recorder frente al equipo, memoria, último fragmento y motor efectivo con su caída a CPU.

Las dos son funciones puras: reciben `Metricas` y sus historias (`nuevas_historias` y `anotar` las llevan) y
devuelven líneas de trozos (texto, estilo) ya con los símbolos del juego activo, para un ancho y un alto. No
dependen de la pantalla del menú: la grabación usa `vista_en_vivo` tal cual, dentro de su propio marco.
"""
import collections
import re
from typing import Deque, Dict, List, Mapping, Optional, Sequence, Tuple

from rich.cells import cell_len

from ... import ayuda
from ...config.hardware import HardwareProfile, describe_hardware, peek_hardware
from ...config.schema import describe_quality
from ...metricas import INTERVALO as INTERVALO_METRICAS
from ...metricas import MotorEfectivo, Metricas, factor
from ..consola import JUEGO_ASCII, JUEGO_COMPLETO, JUEGO_CONSOLA, asciify, consolificar, emoji_seguro, fotograma
from ..teclas import ENTER
from .base import CHISPAS, HISTORIA, Pantalla, Partes, barra, motor_previsto, pie, tendencia

# Umbrales (docs/terminal-especificacion.md, 7.6)
MARGEN_HOLGADO = 50.0  # % medio de procesador por debajo del cual hay margen
MARGEN_JUSTO = 75.0  # hasta aquí va justo; por encima, cargado
VENTANA_MARGEN_S = 30.0  # los segundos que promedia el veredicto de margen
VELOCIDAD_AL_DIA = 1.5  # veces el tiempo real desde las que va al día
VELOCIDAD_AL_RITMO = 1.0  # por debajo se atrasa
TOPE_VELOCIDAD = 4.0  # veces el tiempo real que llenan la barra de velocidad
MUESTRAS_INICIALES = 3  # intervalos de muestreo que se espera la primera cifra antes de decir «n/d»

# Medidas
SANGRIA = 2  # columnas antes de cada línea del cuerpo
ETIQUETA = 17  # ancho de la columna de nombres («Tarjeta gráfica» y «1× = al ritmo del habla» caben)
VALOR = 7  # ancho de la columna de cifras
SEPARACION = 2  # entre cifra, barra y tendencia
CELDAS_MINIMAS, CELDAS_MAXIMAS = 6, 20  # ancho de la barra
FIJO = SANGRIA + ETIQUETA + VALOR + 2 * SEPARACION  # lo que ocupa una fila sin la barra ni la tendencia
GIRO = "•"  # el fotograma que se pone donde aún no hay cifra, si quien llama no gira un spinner

HISTORIAS = ("velocidad", "cpu_proceso", "cpu_sistema", "gpu_proceso", "gpu_sistema", "ram_proceso", "ram_sistema")
# El veredicto de margen: (símbolo, estilo) de cada uno. Siempre lleva palabras: no depende solo del color.
VEREDICTOS = {
    "ok": ("✔", "ok"), "justo": ("⚠", "aviso"), "no": ("⚠", "error"),
    "al_dia": ("✔", "ok"), "va_justo": ("⚠", "aviso"), "se_atrasa": ("⚠", "error"),
}
PRESENTADORES = {JUEGO_ASCII: asciify, JUEGO_CONSOLA: consolificar, JUEGO_COMPLETO: emoji_seguro}


# ------------------------------------------------------------------ historias
def nuevas_historias() -> Dict[str, Deque[Optional[float]]]:
    """Las series de ~2 min (una muestra cada INTERVALO s) que `anotar` va llenando, todas de 0 a 100."""
    return {nombre: collections.deque(maxlen=HISTORIA) for nombre in HISTORIAS}


def _porcentaje(parte: Optional[float], total: Optional[float]) -> Optional[float]:
    return None if parte is None or not total else min(100.0, max(0.0, 100.0 * parte / total))


def valores(m: Metricas) -> Dict[str, Optional[float]]:
    """Lo que `anotar` guarda de una foto, de 0 a 100 (la velocidad, como parte de `TOPE_VELOCIDAD`)."""
    velocidad = None if m.velocidad is None else min(100.0, 100.0 * m.velocidad / TOPE_VELOCIDAD)
    return {
        "velocidad": velocidad, "cpu_proceso": m.cpu_proceso, "cpu_sistema": m.cpu_sistema,
        "gpu_proceso": m.gpu_proceso, "gpu_sistema": m.gpu_sistema,
        "ram_proceso": _porcentaje(m.ram_mb, m.ram_total_mb), "ram_sistema": _porcentaje(m.ram_sistema_mb, m.ram_total_mb),
    }


def anotar(historias: Mapping[str, Deque[Optional[float]]], m: Metricas) -> None:
    """Añade una muestra a cada serie. Llámala una vez por INTERVALO s, no en cada repintado."""
    for nombre, valor in valores(m).items():
        historias[nombre].append(valor)


# ------------------------------------------------------------------ veredictos
def margen(historia: Sequence[Optional[float]], intervalo: float = INTERVALO_METRICAS) -> Optional[str]:
    """«ok», «justo» o «no» según la media del procesador del equipo en los últimos VENTANA_MARGEN_S s;
    None mientras no hay ninguna muestra."""
    n = max(1, round(VENTANA_MARGEN_S / intervalo))
    datos = [v for v in list(historia)[-n:] if v is not None]
    if not datos:
        return None
    media = sum(datos) / len(datos)
    return "ok" if media < MARGEN_HOLGADO else "justo" if media <= MARGEN_JUSTO else "no"


def veredicto_velocidad(velocidad: Optional[float]) -> Optional[str]:
    """«al_dia», «va_justo» o «se_atrasa»; None hasta el primer fragmento."""
    if velocidad is None:
        return None
    return "al_dia" if velocidad >= VELOCIDAD_AL_DIA else "va_justo" if velocidad >= VELOCIDAD_AL_RITMO else "se_atrasa"


# ------------------------------------------------------------------ piezas de texto
def numero(x: float, decimales: int = 1) -> str:
    """11.25 → «11,2»; los ceros que sobran se quitan («32,0» → «32»)."""
    texto = f"{x:.{decimales}f}".replace(".", ",")
    return texto.removesuffix("," + "0" * decimales) if decimales else texto


def gigas(mb: float) -> str:
    return numero(mb / 1024)


def pct(valor: Optional[float]) -> str:
    return ayuda.entrada("rendimiento_nd")[0] if valor is None else f"{valor:.0f} %"


def tendencia_doble(valores_: Sequence[Optional[float]], ancho: int, juego: str) -> Tuple[str, str]:
    """(fila de arriba, fila de abajo) de una tendencia de dos filas: el doble de resolución que `tendencia`.
    Sin dato queda un hueco; las filas se alinean a la derecha, con lo último en el borde."""
    if ancho <= 0:
        return "", ""
    chispas = CHISPAS[juego]
    n = len(chispas)
    arriba, abajo = [], []
    for v in list(valores_)[-ancho:]:
        if v is None:
            arriba.append(" ")
            abajo.append(" ")
            continue
        nivel = min(2 * n - 1, int(max(0.0, v) / 100 * 2 * n))
        abajo.append(chispas[min(nivel, n - 1)])
        arriba.append(" " if nivel < n else chispas[nivel - n])
    return "".join(arriba).rjust(ancho), "".join(abajo).rjust(ancho)


def _partir(partes: Partes, ancho: int, sangria: int = SANGRIA, continuacion: Optional[int] = None) -> List[Partes]:
    """Trozos → líneas de hasta `ancho` celdas partidas por palabras; las de continuación van sangradas."""
    continuacion = sangria + 2 if continuacion is None else continuacion
    lineas: List[List[Tuple[str, str]]] = [[(" " * sangria, "texto")]]
    usado = sangria
    for texto, estilo in partes:
        for palabra in re.findall(r"\S+\s*", texto):
            largo = cell_len(palabra.rstrip())
            if usado + largo > ancho and usado > (continuacion if len(lineas) > 1 else sangria):
                lineas[-1][-1] = (lineas[-1][-1][0].rstrip(), lineas[-1][-1][1])
                lineas.append([(" " * continuacion, "texto")])
                usado = continuacion
            lineas[-1].append((palabra, estilo))
            usado += cell_len(palabra)
    return lineas


def _veredicto(clave: str, marca: Tuple[str, str], detalle: str = "") -> Partes:
    """El veredicto de una línea («✔ Hay margen para grabar. El equipo va…»): símbolo, título y su explicación.
    `marca` es (símbolo, estilo); `detalle` sustituye a la explicación de `clave` si trae algo."""
    simbolo, estilo = marca
    titulo, explicacion = ayuda.entrada(clave)
    return [(f"{simbolo} ", estilo), (titulo + ". ", f"{estilo} bold"), (detalle or explicacion, "texto")]


def _elidir(texto: str, ancho: int, juego: str) -> str:
    """`texto` cortado a `ancho` celdas con «…» («...» en ASCII); entero si cabe."""
    if cell_len(texto) <= ancho:
        return texto
    return texto[: ancho - 3] + "..." if juego == JUEGO_ASCII else texto[: ancho - 1] + "…"


def _fila(
    etiqueta: str, valor: str, porcentaje: Optional[float], sub: str, historia: Sequence[Optional[float]],
    ancho: int, juego: str, doble: bool,
) -> List[Partes]:
    """Una cifra con su barra y su tendencia; con `doble`, una segunda línea con `sub` bajo la cifra y la
    mitad de abajo de la tendencia."""
    celdas = max(CELDAS_MINIMAS, min(CELDAS_MAXIMAS, (ancho - FIJO) // 3))
    largo = max(0, ancho - FIJO - celdas)
    lleno, vacio = barra(porcentaje or 0.0, celdas)
    separacion = " " * SEPARACION
    campo = ETIQUETA + VALOR
    if doble:
        arriba, abajo = tendencia_doble(historia, largo, juego)
    else:
        arriba, abajo = tendencia(historia, largo, juego).rjust(largo), ""
    primera = [
        (" " * SANGRIA + etiqueta.ljust(ETIQUETA), "texto"), (valor.rjust(VALOR), "texto"), (separacion, "texto"),
        (lleno, "acento"), (vacio, "borde"), (separacion, "texto"), (arriba, "mic"),
    ]
    if not doble:
        return [primera]
    segunda = [
        (" " * SANGRIA + _elidir(sub, campo, juego).rjust(campo), "tenue"), (" " * (celdas + 2 * SEPARACION), "texto"),
        (abajo, "mic"),
    ]
    return [primera, segunda]


def _presentar(lineas: Sequence[Partes], juego: str, alto: int) -> List[Partes]:
    pres = PRESENTADORES[juego]
    return [[(pres(texto), estilo) for texto, estilo in linea] for linea in lineas[:alto]]


def _elegir(niveles, alto: int) -> List[Partes]:
    """El primer nivel de detalle que cabe en `alto` líneas (del más completo al más apretado); si ninguno,
    el último, cortado."""
    for nivel in niveles:
        lineas = nivel()
        if len(lineas) <= alto:
            return lineas
    return lineas


def _con_respiros(bloques: Sequence[Sequence[Partes]], respiro: bool) -> List[Partes]:
    lineas: List[Partes] = []
    for bloque in bloques:
        if not bloque:
            continue
        if lineas and respiro:
            lineas.append([])
        lineas += list(bloque)
    return lineas


# ------------------------------------------------------------------ vista sin grabación
def lineas_equipo(hw: HardwareProfile, ancho: int) -> List[Partes]:
    """«Equipo» y debajo lo detectado: procesador, núcleos y memoria, y la tarjeta gráfica."""
    partes = describe_hardware(hw).split(" · ")
    sangria = SANGRIA + 2
    lineas = [[(" " * SANGRIA + ayuda.entrada("rendimiento_equipo")[0], "tenue")]]
    for texto in (" · ".join(partes[:-1]), partes[-1]):
        lineas += _partir([(texto, "tenue")], ancho, sangria, sangria + 2)
    return lineas


def vista_reposo(
    m: Metricas, historias: Mapping[str, Sequence[Optional[float]]], hw: Optional[HardwareProfile],
    motor: Optional[MotorEfectivo], calidad: str, ancho: int, alto: int, juego: str = JUEGO_COMPLETO,
    *, giro: str = GIRO, midiendo: bool = False,
) -> List[Partes]:
    """Las líneas de Rendimiento sin grabación para `ancho` × `alto`: veredicto de margen, con qué se
    transcribiría y procesador, tarjeta gráfica y memoria del equipo. `giro` es el fotograma del spinner mientras
    llega la primera cifra (`midiendo`); `calidad` es «Calidad Media». Si no cabe, quita primero los respiros,
    luego la segunda línea de cada cifra y por último el equipo."""
    veredicto = margen(historias["cpu_sistema"])
    if veredicto:
        cabeza = _veredicto("rendimiento_margen_" + veredicto, VEREDICTOS[veredicto])
    elif midiendo:
        cabeza = _veredicto("rendimiento_midiendo", (giro, "acento"))
    else:
        cabeza = [("⚠ ", "aviso"), (ayuda.entrada("rendimiento_nd")[1], "texto")]
    if hw is None:
        previsto = [[(" " * SANGRIA + giro + " ", "acento"), (ayuda.linea("terminal_detectando_equipo").rstrip(".") + "…", "tenue")]]
    else:
        donde = f"{motor.donde} · {calidad.split(' · ')[0]}" if motor else calidad
        previsto = [[(" " * SANGRIA + ayuda.entrada("rendimiento_motor")[0] + ": ", "tenue"), (donde, "texto")]]
        if motor and motor.caida:
            previsto += _partir([("⚠ " + ayuda.entrada("rendimiento_caida")[1].format(motivo=motor.caida), "error")], ancho)
    ram = _porcentaje(m.ram_sistema_mb, m.ram_total_mb)
    ram_de = (
        ayuda.entrada("rendimiento_ram_de")[0].format(usada=gigas(m.ram_sistema_mb), total=gigas(m.ram_total_mb))
        if ram is not None else ""
    )
    series = (
        ("rendimiento_cpu", "cpu_sistema", m.cpu_sistema, ""),
        ("rendimiento_gpu", "gpu_sistema", m.gpu_sistema, ""),
        ("rendimiento_ram", "ram_sistema", ram, ram_de),
    )

    def cifras(doble: bool) -> List[Partes]:
        izquierda = ayuda.entrada("rendimiento_ahora")[0]
        derecha = ayuda.entrada("rendimiento_tendencia")[0]
        hueco = max(1, ancho - SANGRIA - cell_len(izquierda) - cell_len(derecha))
        filas: List[Partes] = [[
            (" " * SANGRIA + izquierda, "bold"), (" " * hueco + derecha, "tenue"),
        ]]
        for clave, serie, valor, sub in series:
            historia = historias[serie]
            picos = [v for v in historia if v is not None]
            if sub == "" and picos:
                sub = ayuda.entrada("rendimiento_pico")[0].format(n=f"{max(picos):.0f}")
            texto = giro if midiendo and valor is None else pct(valor)
            filas += _fila(ayuda.entrada(clave)[0], texto, valor, sub, historia, ancho, juego, doble)
        return filas

    equipo = lineas_equipo(hw, ancho) if hw else []

    def nivel(respiro: bool, doble: bool, con_equipo: bool):
        return lambda: _con_respiros([_partir(cabeza, ancho, SANGRIA, SANGRIA + 2), previsto, cifras(doble), equipo if con_equipo else []], respiro)

    lineas = _elegir(
        [nivel(True, True, True), nivel(False, True, True), nivel(False, False, True), nivel(False, False, False)], alto
    )
    return _presentar(lineas, juego, alto)


# ------------------------------------------------------------------ vista en vivo
def vista_en_vivo(
    m: Metricas, historias: Mapping[str, Sequence[Optional[float]]], ancho: int, alto: int,
    juego: str = JUEGO_COMPLETO, *, giro: str = GIRO,
) -> List[Partes]:
    """Las líneas de Rendimiento durante la grabación para `ancho` × `alto`, con los símbolos de `juego`.

    Veredicto de velocidad («Va al día» desde VELOCIDAD_AL_DIA veces el tiempo real, «Va justo» hasta
    VELOCIDAD_AL_RITMO, «Se atrasa» por debajo; «Cargando el modelo» hasta el primer fragmento), velocidad,
    cola con su atraso y el último trozo, procesador y tarjeta gráfica de Recorder frente a los del equipo
    (n/d si Windows no da el dato), memoria y el motor efectivo, con la caída a CPU si la hubo. Si no cabe, quita
    primero los respiros, luego la segunda línea de cada cifra y por último el motor y la cola.
    `historias` es lo que lleva `anotar`; `giro` es el fotograma del spinner. Sin dependencias de la pantalla
    del menú: la pinta igual el menú que la grabación."""
    veredicto = veredicto_velocidad(m.velocidad)
    if veredicto:
        detalle = ayuda.entrada("rendimiento_" + veredicto)[1].format(factor=factor(m.velocidad).removesuffix("×"))
        cabeza = _veredicto("rendimiento_" + veredicto, VEREDICTOS[veredicto], detalle)
    else:
        cabeza = _veredicto("rendimiento_cargando", (giro, "acento"))

    total = m.ram_total_mb
    ultimo = "" if m.ultimo_fragmento_s is None else " · " + ayuda.entrada("rendimiento_ultimo")[0].format(s=numero(m.ultimo_fragmento_s))
    if m.cola:
        clave = "rendimiento_cola_uno" if m.cola == 1 else "rendimiento_cola_valor"
        cola = ayuda.entrada(clave)[0].format(n=m.cola, s=f"{m.atraso_s:.0f}")
    else:
        cola = ayuda.entrada("rendimiento_cola_vacia")[0]
    todo = ayuda.entrada("rendimiento_todo")[0]

    def cifras(doble: bool) -> List[Partes]:
        filas: List[Partes] = []
        filas += _fila(
            ayuda.entrada("rendimiento_velocidad")[0], giro if m.velocidad is None else factor(m.velocidad),
            valores(m)["velocidad"], ayuda.entrada("rendimiento_tiempo_real")[0], historias["velocidad"], ancho, juego, doble,
        )
        filas += _partir([(ayuda.entrada("rendimiento_cola")[0].ljust(ETIQUETA), "tenue"), (cola + ultimo, "texto")], ancho, SANGRIA, SANGRIA + ETIQUETA)
        return filas

    def recursos(doble: bool) -> List[Partes]:
        ram = m.ram_mb
        gb = "n/d" if ram is None else f"{numero(ram / 1024)} GB"
        filas: List[Partes] = []
        filas += _fila(
            ayuda.entrada("rendimiento_cpu")[0], pct(m.cpu_proceso), m.cpu_proceso, f"{todo} {pct(m.cpu_sistema)}",
            historias["cpu_proceso"], ancho, juego, doble,
        )
        filas += _fila(
            ayuda.entrada("rendimiento_gpu")[0], pct(m.gpu_proceso), m.gpu_proceso, f"{todo} {pct(m.gpu_sistema)}",
            historias["gpu_proceso"], ancho, juego, doble,
        )
        filas += _fila(
            ayuda.entrada("rendimiento_ram")[0], gb, _porcentaje(ram, total),
            ayuda.entrada("rendimiento_de_total")[0].format(total=gigas(total)) if total else "",
            historias["ram_proceso"], ancho, juego, doble,
        )
        return filas

    motor_lineas: List[Partes] = []
    if m.motor:
        e = m.motor
        texto = f"{e.motor} · {e.donde} · {e.modelo} · haz {e.haz}"
        motor_lineas = _partir(
            [(ayuda.entrada("rendimiento_motor_efectivo")[0].ljust(ETIQUETA), "tenue"), (texto, "texto")],
            ancho, SANGRIA, SANGRIA + ETIQUETA,
        )
        if e.caida:
            motor_lineas += _partir([("⚠ " + ayuda.entrada("rendimiento_caida")[1].format(motivo=e.caida), "error")], ancho)

    def nivel(respiro: bool, doble: bool, con_cifras: bool = True):
        return lambda: _con_respiros(
            [_partir(cabeza, ancho, SANGRIA, SANGRIA + 2), cifras(doble) if con_cifras else [], recursos(doble), motor_lineas], respiro
        )

    lineas = _elegir([nivel(True, True), nivel(False, True), nivel(False, False)], alto)
    return _presentar(lineas, juego, alto)


# ------------------------------------------------------------------ la pantalla del menú
class Rendimiento(Pantalla):
    """Rendimiento desde el menú: no hay grabación, así que las cifras son las del equipo entero (`Muestreador`
    sin transcriptor), que es lo que dice si hay margen antes de grabar. Con «Medir mi equipo» construido
    (acción «medir» del registro), Enter lo abre desde aquí; si no, la fila no existe."""

    titulo = "Rendimiento"
    ACCION_MEDIR = "medir"

    def __init__(self, terminal):
        super().__init__(terminal)
        self.muestreo = terminal.nuevo_muestreador()
        self.muestreo.iniciar()
        self.desde = terminal.reloj()
        self.ultima: Optional[float] = None
        self.historias = nuevas_historias()

    @property
    def clase_medir(self):
        from .registro import clase_de

        return clase_de(self.ACCION_MEDIR)

    def al_salir(self):
        self.muestreo.parar()

    def ayuda(self):
        if self.clase_medir:
            return ayuda.linea("rendimiento_medir"), "tenue"
        return ayuda.linea("menu_rendimiento"), "tenue"

    def teclas(self):
        base = pie(("Esc", "volver"), ("?", "ayuda"), ("t", "tema"))
        if not self.clase_medir:
            return base
        return [("Enter", ayuda.entrada("rendimiento_medir")[0])] + base

    def tecla(self, k):
        if k == ENTER and self.clase_medir:
            self.app.abrir(self.clase_medir(self.app))
            return True
        return False

    def _anotar(self, m: Metricas) -> None:
        ahora = self.app.reloj()
        if self.ultima is None or ahora - self.ultima >= INTERVALO_METRICAS:
            self.ultima = ahora
            anotar(self.historias, m)

    def cuerpo(self, ancho, sitio):
        app, m = self.app, self.muestreo.foto()
        if any(v is not None for v in (m.cpu_sistema, m.gpu_sistema, m.ram_sistema_mb)):
            self._anotar(m)
        midiendo = app.reloj() - self.desde < MUESTRAS_INICIALES * INTERVALO_METRICAS
        hw = peek_hardware()
        girando = midiendo or hw is None
        if girando:
            app.spinner("")  # pide repintar: cada fotograma cambia el giro
        medir = self.clase_medir
        reservado = 2 if medir else 0
        lineas = vista_reposo(
            m, self.historias, hw, motor_previsto(app.config, hw) if hw else None, describe_quality(app.config),
            ancho, max(1, sitio - reservado), app.juego, giro=fotograma(app.juego, app.reloj()) if girando else GIRO,
            midiendo=midiendo,
        )
        texto = [app.t(*linea) if linea else app.t() for linea in lineas]
        if medir:
            texto += [
                app.t(),
                app.t_fila(("▶ ", "acento"), (ayuda.entrada("rendimiento_medir")[0], "elegido")),
            ]
        return texto, len(texto) - 1 if medir else 0
