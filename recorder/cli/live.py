"""La grabación desde la terminal: `daily` sin más.

Dos pantallas sobre la misma `RecorderSession`:

- `PantallaCompleta` (`daily` en una terminal): pantalla alternativa con regiones fijas (cabecera de
  estado, transcripción, avisos y pie de teclas), panel de opciones con ↑↓, vistas de rendimiento ([m])
  y de teclas ([?]), pregunta de salida y vaciado de la cola dentro de la pantalla. Al salir deja en el
  historial solo el resumen. Está al final de este módulo.
- `PantallaEnVivo` (`daily --historial` y la salida redirigida): lo de antes, descrito aquí debajo.

`PantallaEnVivo`: lo mismo que la ventana, pero en la propia consola y barato.
Una cabecera de dos líneas (la nota de hoy y la calidad, sin jerga) y, debajo, las frases, los
avisos (las fuentes resueltas al arrancar, el atraso de la transcripción) y las fuentes que
caen, vuelven o enmudecen como líneas normales, que se quedan en el historial de la terminal (se
pueden copiar y desplazar): la hora en tenue, una columna de icono (🔊 la salida, 🎤 el
micrófono, nada en los hechos de la sesión y los avisos, que llevan su propio símbolo) y el
texto. Al pie, líneas que se redibujan solo cuando cambian: la cabecera (`status_text`) con
los medidores (`meter_text`, con 🔇 en la fuente muda), el motor efectivo con su velocidad en
cuanto carga el modelo (`metricas.linea`, cambia al acabar cada fragmento) y las teclas. En silencio no se escribe
nada y el proceso no gasta CPU. Las líneas se imprimen sin partir (`soft_wrap`): las parte la
terminal a su ancho real, así que cambiar el tamaño de la ventana no deja frases rotas.

Teclas: [p] pausar/continuar · [c] captura · [r] reconectar audio · [a] abrir la nota ·
[o] opciones · [q] salir (Ctrl+C también sale). Al salir con cola pendiente se pregunta en el
pie, como en la ventana: [e] esperar a que se transcriba y salir · [s] salir sin esperar, perdiéndola ·
[Esc] seguir grabando (la c de captura no hace nada mientras pregunta).

[o] abre en el pie un panel de opciones sin parar la grabación (el bucle sigue sondeando la
sesión e imprimiendo frases mientras tanto): salida de audio, micrófono (apagado o cuál), qué
capturar (pantallas o una ventana abierta, [r] las relee) y calidad de las capturas. Se elige
con el número ([1]-[9] directo; con más opciones se teclea el número y Enter, Retroceso borra),
Esc vuelve sin cambiar nada y Ctrl+C sigue siendo salir. Lo elegido se aplica con
`RecorderSession.apply_settings` como lo haría ⚙ Opciones en la ventana: se guarda en
config.json y solo se reabre el audio; el transcriptor y la cola no se tocan. Los dispositivos
que se conectan después de arrancar no aparecen: PortAudio enumera al inicializar y no se puede
reinicializar con el loopback abierto (ver `RecorderSession.shutdown`); el panel lo avisa.

Los avisos que piden algo al usuario (`action` del evento) se completan aquí con la acción de
esta interfaz («pulsa [o]», «daily config»), no con la de la ventana.

Con la salida redirigida (`daily > log.txt`) no hay pie: las teclas se imprimen una vez en la
cabecera, las líneas van tal cual, los cambios de cabecera también, [o] solo avisa y Ctrl+C
cierra igual de limpio.

Se prueba con la sesión de mentira de tests/test_session.py: la sesión, el lector de teclas, la
espera, la consola, el entorno (dispositivos, pantallas, ventanas) y cómo se abre la nota se
inyectan (tests/test_cli_live.py).
"""
import collections
import contextlib
import copy
import dataclasses
import itertools
import os
import re
import signal
import time
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

from rich.cells import cell_len
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.style import Style
from rich.text import Text

from .. import ayuda
from ..actions.screenshot import screen_labels, window_titles
from ..audio.capture import MUTE_WARN_SEC
from ..audio.devices import wasapi_devices
from ..audio.processing import bars
from ..config.options import (
    apply_settings,
    capture_choice,
    capture_choices,
    device_choice,
    device_choices,
    settings_form,
    target_choice,
    target_choices,
)
from ..config.schema import describe_quality
from ..session import (
    ACTION_DEVICES, ACTION_RECOMMEND, ACTION_SETTINGS, AVISO_CAIDA, AVISO_MUDA, LIVE_STATUS,
    Event, Line, Notice, RecorderSession, Resumen, SourceChanged, SourceMuted, Status, StatusSnapshot, with_action,
)
from . import teclas
from .consola import (
    ELIDIDO, ELIDIDO_ASCII, JUEGO_COMPLETO, fotograma, juego_de, make_console, partes_teclas, presentar,
)
from .pantallas.base import barra
from .pantallas.marco import ANCHO_MINIMO, ALTO_MINIMO, MARGEN, SANGRIA_LISTA, alto_ayuda, demasiado_pequena, ventana
from .pantallas.rendimiento import INTERVALO_METRICAS, anotar, nuevas_historias, vista_en_vivo
from .pantallas.terminal import COLORES_PROPIOS
from .teclas import ABAJO, ARRIBA, AVPAG, CTRL_C, ENTER, ESC, FIN, INICIO, REPAG, RETROCESO  # las teclas, con su nombre

INTERVALO = 0.2  # segundos entre sondeos, como la ventana (POLL_MS)

# La barra de teclas cabe en 80 columnas (79 con «seguir» en pausa): un pie de dos líneas.
TECLAS = (("p", "pausar"), ("c", "captura"), ("r", "reconectar"), ("a", "nota"), ("o", "opciones"), ("q", "salir"))
TECLAS_PAUSA = (("p", "seguir"),) + TECLAS[1:]
TECLAS_CIERRE = (("e", "esperar y salir"), ("s", "salir sin esperar"), ("Esc", "seguir grabando"))
TECLAS_TERMINANDO = (("s", "salir sin esperar, perdiendo lo pendiente"),)

ICONOS = {"out": "🔊", "mic": "🎤"}  # la columna de icono de cada frase; los hechos de la sesión van sin él

# Lo que esta interfaz añade a un aviso según su `action`: con pie, el panel [o]; sin él, `daily config`.
ACCIONES = {
    ACTION_DEVICES: "Si hablaste, pulsa [o] y elige el dispositivo que usa Teams.",
    ACTION_SETTINGS: "Se cambia con `daily config` (vale desde la próxima grabación).",
    ACTION_RECOMMEND: "`daily config` → Calidad → usar la recomendada (vale desde la próxima grabación).",
}
ACCIONES_SIN_PIE = {**ACCIONES, ACTION_DEVICES: "Si hablaste, elige el dispositivo que usa Teams con `daily config`."}

# El panel de opciones: (tecla, sección, título). Lo que se puede cambiar sin parar la grabación.
SECCIONES = (
    ("1", "out", "salida de audio 🔊"),
    ("2", "mic", "micrófono 🎤"),
    ("3", "target", "qué capturar 📸"),
    ("4", "captures", "calidad de capturas"),
)
MIC_APAGADO = ayuda.entrada("grabacion_mic_apagado")[1].rstrip(".")  # la primera opción de la sección del micrófono
AVISO_DISPOSITIVOS = "¿no aparece? si se conectó después de arrancar, sal con q y vuelve a entrar"
AVISO_SIN_PIE = "opciones: hacen falta una terminal y su pie; con la salida redirigida usa `daily config` al terminar"

Partes = List[Tuple[str, str]]  # trozos (texto, estilo) de una línea


def _ahora() -> str:
    return time.strftime("%H:%M:%S")


class Entorno:
    """Lo que el panel de opciones consulta al abrir una sección: los dispositivos WASAPI (de la
    PyAudio de la sesión: la misma tabla con la que se abren los flujos), las pantallas y las
    ventanas abiertas. Las pruebas lo sustituyen por listas fijas."""

    def __init__(self, pa):
        self.pa = pa

    def dispositivos(self, kind: str) -> List[str]:
        return wasapi_devices(self.pa, kind)

    def pantallas(self) -> List[str]:
        return screen_labels()

    def ventanas(self) -> List[str]:
        return window_titles()


@dataclasses.dataclass
class Panel:
    """El panel de opciones abierto en el pie: qué sección se ve, su lista y lo tecleado."""

    seccion: Optional[str] = None  # None = el índice de secciones
    opciones: List[str] = dataclasses.field(default_factory=list)
    actual: int = -1  # índice en `opciones` de lo configurado ahora
    tecleado: str = ""  # dígitos a la espera de Enter (listas de más de 9)
    pantallas: List[str] = dataclasses.field(default_factory=list)  # las etiquetas con que se compuso la lista de captura
    fila: int = 0  # la fila elegida con ↑↓ (la pantalla completa; el pie del historial se maneja solo con números)

    def clave(self) -> tuple:
        return (self.seccion, tuple(self.opciones), self.actual, self.tecleado, self.fila)


class PantallaEnVivo:
    """El bucle de `daily`: sondea la sesión en este hilo, pinta y atiende las teclas."""

    def __init__(
        self,
        session: Optional[RecorderSession] = None,
        *,
        consola: Optional[Console] = None,
        leer_tecla: Optional[Callable[[], Optional[str]]] = None,  # None: el teclado de la terminal (teclas.py)
        dormir: Callable[[float], None] = time.sleep,
        abrir: Callable[[str], object] = os.startfile,
        entorno: Optional[Entorno] = None,
    ):
        self.session = session or RecorderSession()
        self.consola = consola or make_console()
        self._leer_tecla = leer_tecla
        self._dormir = dormir
        self._abrir = abrir
        self._entorno = entorno or Entorno(self.session.pa)
        self.ascii = juego_de(self.consola) != JUEGO_COMPLETO  # sin emoji: la columna de icono va en texto
        self.plano = not self.consola.is_interactive  # salida redirigida: sin pie
        self._teclas: Deque[str] = collections.deque()  # lo que mete el manejador de Ctrl+C; va antes que el teclado
        self._live: Optional[Live] = None  # el pie; None en modo plano
        self._preguntando = False  # el pie muestra la pregunta de cerrar con cola pendiente
        self._resumen = ""  # lo que queda sin transcribir, para esa pregunta
        self._panel: Optional[Panel] = None  # el panel de opciones, mientras está abierto
        self._pie_pintado: Optional[tuple] = None  # lo último pintado en el pie, para no redibujar lo mismo

    # ------------------------------------------------------------------ pintar
    def _texto(self, *partes: Tuple[str, str]) -> Text:
        """Trozos (texto, estilo) → Text, sin marcado de rich y con los símbolos de esta consola."""
        return Text.assemble(*[(presentar(t, self.consola), e) for t, e in partes])

    def _imprimir(self, *partes: Tuple[str, str]) -> None:
        """Una línea por encima del pie (o tal cual sin pie). Sin marcado de rich: una frase con
        corchetes, «[música]», se tomaría por una etiqueta de estilo y desaparecería. Sin partir
        (`soft_wrap`): la parte la terminal a su ancho real, no al que rich creyó al arrancar, y
        hacia un archivo cada frase es una línea del registro."""
        self.consola.print(self._texto(*partes), soft_wrap=True)

    def _icono(self, kind: str) -> str:
        """La columna de icono, del mismo ancho para todas las líneas: 🔊 o 🎤 (OUT, MIC sin emoji)
        y un espacio; en blanco para los hechos de la sesión y los avisos."""
        icono = ICONOS.get(kind, "")
        if self.ascii:
            return (presentar(icono, self.consola) or "   ") + " "
        return (icono or "  ") + " "

    def _linea(self, stamp: str, kind: str, text: str, hits: List[str]) -> None:
        """Como `MainWindow.add_line`: hora, icono de la fuente, la frase y las palabras clave."""
        icono = self._icono(kind)
        partes: Partes = [(f"{stamp}  ", "tenue"), (icono, "mic" if kind == "mic" else "tenue"), (text, "acento" if hits else "texto")]
        self._imprimir(*partes)
        if hits:
            sangria = " " * (len(stamp) + 2 + cell_len(icono))  # bajo el texto, no bajo la hora
            self._imprimir((f"{sangria}📸 captura: {', '.join(hits)}", "tenue"))

    def _hecho(self, stamp: str, texto: str, estilo: str = "tenue") -> None:
        """Una línea sin icono de fuente: un aviso o un hecho de la sesión, con su propio símbolo."""
        self._imprimir((f"{stamp}  ", "tenue"), (self._icono("info"), "tenue"), (texto, estilo))

    def _aviso(self, texto: str, estilo: str = "tenue") -> None:
        """Un hecho con la hora de ahora, de la propia pantalla (no de la sesión)."""
        self._hecho(_ahora(), texto, estilo)

    def _con_accion(self, texto: str, action: str) -> str:
        """El texto de un aviso con lo que puede hacer el usuario, dicho como lo ofrece esta pantalla."""
        acciones = ACCIONES_SIN_PIE if self.plano else ACCIONES
        return with_action(texto, acciones.get(action, ""))

    def _pintar(self, ev: Event) -> None:
        if isinstance(ev, Line):
            self._linea(ev.stamp, ev.kind, ev.text, ev.hits)
        elif isinstance(ev, Notice):
            self._hecho(ev.stamp, self._con_accion(ev.text, ev.action), "error" if ev.level == "err" else "tenue")
        elif isinstance(ev, SourceMuted):
            self._linea(ev.stamp, "info", self._con_accion(ev.text, ev.action), [])
        elif isinstance(ev, SourceChanged):
            self._linea(ev.stamp, "info", ev.text, [])
        elif isinstance(ev, Status) and self.plano:
            # Sin pie, los cambios de cabecera quedan como líneas: así el registro dice cuándo
            # se cargó el modelo o se quedó escuchando. Con pie ya se ven ahí.
            self._hecho(_ahora(), ev.text)

    def _cabecera(self) -> None:
        """Dos líneas: la nota de hoy (la ruta entera sale al terminar y la abre [a]) y la calidad
        sin jerga. Las teclas viven en el pie; sin pie se imprimen aquí una vez."""
        self._imprimir(("Recorder", "bold"), (" · ", "tenue"), (self.session.file_path.name, "texto"))
        self._imprimir((describe_quality(self.session.config), "tenue"))
        if self.plano:
            self._imprimir(*partes_teclas(TECLAS), ("   (Ctrl+C también sale)", "tenue"))

    def _despedida(self) -> None:
        self._imprimir(("Grabación terminada", "bold"), (" · nota: ", "tenue"), (str(self.session.file_path), "texto"))
        perdido = self.session.request_close()
        if perdido:
            self._imprimir((f"⚠ se perdieron {perdido} sin transcribir", "error"))

    def _teclas_del_pie(self, st: StatusSnapshot) -> Sequence[Tuple[str, str]]:
        if self._preguntando:
            return TECLAS_CIERRE
        if st.draining:
            return TECLAS_TERMINANDO
        return TECLAS_PAUSA if st.paused else TECLAS

    def _pregunta(self) -> Partes:
        return [(f"Quedan {self._resumen} sin transcribir. ", "acento")] + partes_teclas(TECLAS_CIERRE)

    def _actualizar_pie(self, st: StatusSnapshot) -> None:
        """Redibuja el pie solo si algo cambió: en silencio no se escribe nada."""
        if self._live is None:
            return  # modo plano, o aún no arrancó el pie
        teclas = self._teclas_del_pie(st)
        # El motor y la velocidad solo cambian al cargar el modelo o al acabar un fragmento.
        motor = st.metricas.linea if st.metricas else ""
        clave = (st.status_text, st.status_highlight, st.meter_text, motor, teclas, self._panel and self._panel.clave())
        if clave == self._pie_pintado:
            return
        self._pie_pintado = clave
        self._live.update(self._pie(st, teclas), refresh=True)

    def _pie(self, st: StatusSnapshot, teclas: Sequence[Tuple[str, str]]) -> RenderableType:
        """El pie: cabecera y medidores en una línea; debajo el motor efectivo y su velocidad (en
        cuanto carga el modelo) y las teclas, la pregunta de cierre o el panel de opciones."""
        lineas = [self._texto((st.status_text, "bold" if st.status_highlight else "tenue"), ("   ", ""), (st.meter_text, "tenue"))]
        if st.metricas and st.metricas.linea:
            lineas.append(self._texto((st.metricas.linea, "tenue")))
        if self._panel is not None:
            lineas += self._lineas_panel()
        elif self._preguntando:
            lineas.append(self._texto(*self._pregunta()))
        else:
            lineas.append(self._texto(*partes_teclas(teclas)))
        return Group(*lineas)

    # ------------------------------------------------------------------ panel de opciones
    def _valores_actuales(self) -> Dict[str, str]:
        """Lo configurado ahora en cada sección del panel: salida, micrófono, qué capturar y calidad."""
        cfg = self.session.config
        titulo = lambda clave, **datos: ayuda.entrada(clave)[0].format(**datos)  # noqa: E731
        if cfg.window:
            captura = titulo("grabacion_cap_ventana", titulo=cfg.window)
        else:
            captura = titulo("grabacion_cap_pantalla", n=cfg.screen) if cfg.screen else titulo("grabacion_cap_todas")
        return {
            "out": device_choice(cfg.out_dev),
            "mic": device_choice(cfg.mic_dev) if cfg.mic else titulo("grabacion_mic_apagado"),
            "target": captura,
            "captures": capture_choice(cfg.captures).split(":")[0].split(" (")[0],
        }

    def _ahora_configurado(self) -> str:
        """Lo configurado ahora, en una línea: para el índice del panel."""
        v = self._valores_actuales()
        return f"🔊 {v['out']} · 🎤 {v['mic']} · 📸 {v['target']} · capturas {v['captures'].lower()}"

    def _lineas_panel(self) -> List[Text]:
        p = self._panel
        if p.seccion is None:
            indice = [(f"[{tecla}]", "acento") for tecla, _s, _t in SECCIONES]
            partes: Partes = [("⚙ Opciones", "bold"), ("   ahora: ", "tenue"), (self._ahora_configurado(), "tenue")]
            lineas = [self._texto(*partes)]
            partes = []
            for (tecla, _s, titulo), marca in zip(SECCIONES, indice):
                partes += [marca, (f" {titulo}", "tenue"), (" · ", "tenue")]
            lineas.append(self._texto(*partes, *partes_teclas((("Esc/o", "volver"),))))
            return lineas
        titulo = next(t for _k, s, t in SECCIONES if s == p.seccion)
        lineas = [self._texto((f"⚙ {titulo[0].upper()}{titulo[1:]}", "bold"), ("  elige con el número", "tenue"))]
        for i, opcion in enumerate(p.opciones):
            actual = i == p.actual
            linea = self._texto((f"  [{i + 1}] ", "acento"), (opcion, "texto" if actual else "tenue"), ("  (actual)" if actual else "", "acento"))
            linea.no_wrap = True  # un título de ventana larguísimo se recorta con «…», no parte la lista
            linea.overflow = "ellipsis"
            lineas.append(linea)
        if p.seccion in ("out", "mic"):
            lineas.append(self._texto((AVISO_DISPOSITIVOS, "tenue")))
        n = len(p.opciones)
        teclas = [(f"1-{n}", "elegir")] if n <= 9 else [(f"1-{n}", "y Enter, elegir")]
        if p.seccion == "target":
            teclas.append(("r", "releer ventanas"))
        teclas += [("Esc", "volver"), ("o", "cerrar")]
        partes = [(f"› {p.tecleado}_  ", "acento")] if p.tecleado else []
        lineas.append(self._texto(*partes, *partes_teclas(teclas)))
        return lineas

    def _abrir_panel(self) -> None:
        if self.plano:
            self._aviso(f"⚙ {AVISO_SIN_PIE}")
            return
        self._panel = Panel()

    def _cerrar_panel(self) -> None:
        self._panel = None

    def _abrir_seccion(self, seccion: str) -> None:
        """Compone la lista de la sección con lo que hay ahora (dispositivos, pantallas, ventanas)
        y marca lo configurado. Lo guardado que ya no se detecta sigue en la lista, como en `daily config`."""
        cfg = self.session.config
        p = Panel(seccion=seccion)
        if seccion == "out":
            p.opciones, p.actual = self._con_el_actual(device_choices(self._entorno.dispositivos("out")), device_choice(cfg.out_dev))
        elif seccion == "mic":
            opciones, actual = self._con_el_actual(device_choices(self._entorno.dispositivos("mic")), device_choice(cfg.mic_dev))
            p.opciones = [MIC_APAGADO] + opciones
            p.actual = actual + 1 if cfg.mic else 0
        elif seccion == "target":
            p.pantallas = self._entorno.pantallas()
            p.opciones = target_choices(p.pantallas, self._entorno.ventanas(), cfg.window)
            p.actual = p.opciones.index(target_choice(cfg.window, cfg.screen, p.pantallas))
        else:
            p.opciones = capture_choices()
            p.actual = p.opciones.index(capture_choice(cfg.captures))
        self._panel = p

    @staticmethod
    def _con_el_actual(opciones: List[str], actual: str) -> Tuple[List[str], int]:
        if actual not in opciones:
            opciones = opciones[:1] + [actual] + opciones[1:]  # el guardado que ya no se detecta sigue elegible
        return opciones, opciones.index(actual)

    def _tecla_panel(self, k: str) -> bool:
        """Las teclas con el panel abierto. Ctrl+C lo cierra y sigue siendo salir."""
        p = self._panel
        if k == CTRL_C:
            self._cerrar_panel()
            return self._pedir_cierre()
        if p.seccion is None:
            if k in ("o", "q", ESC):
                self._cerrar_panel()
            else:
                seccion = next((s for tecla, s, _t in SECCIONES if tecla == k), None)
                if seccion:
                    self._abrir_seccion(seccion)
            return True
        if k == ESC:
            self._panel = Panel()  # vuelve al índice sin cambiar nada
        elif k in ("o", "q"):
            self._cerrar_panel()
        elif k == "r" and p.seccion == "target":
            self._abrir_seccion("target")  # relee las ventanas abiertas
        elif k in "0123456789" and len(k) == 1:
            self._digito(k)
        elif k == ENTER and p.tecleado:
            self._elegir(int(p.tecleado) - 1)
        elif k == RETROCESO:
            p.tecleado = p.tecleado[:-1]
        return True

    def _digito(self, d: str) -> None:
        """Un dígito más del número: se elige en cuanto ningún otro dígito podría formar un número
        válido (con 9 opciones o menos, al primero); si no, se espera a Enter."""
        p = self._panel
        n = int(p.tecleado + d)
        if not 1 <= n <= len(p.opciones):
            return
        p.tecleado += d
        if n * 10 > len(p.opciones):
            self._elegir(n - 1)

    def _elegir(self, indice: int) -> None:
        hecho = self._aplicar(indice)
        if hecho:
            seccion, etiqueta = hecho
            titulo = next(t for _k, s, t in SECCIONES if s == seccion)
            self._aviso(f"⚙ {titulo}: {etiqueta}", "ok")

    def _aplicar(self, indice: int) -> Optional[Tuple[str, str]]:
        """Aplica la opción elegida como ⚙ Opciones: el formulario de la configuración actual con
        ese campo cambiado, volcado sobre una copia, y la sesión guarda y reabre lo que toque.
        Devuelve (sección, etiqueta) de lo que cambió, o None si ya era esa."""
        p = self._panel
        etiqueta = p.opciones[indice]
        self._cerrar_panel()
        if indice == p.actual:
            return None  # ya era esa
        cfg = self.session.config
        pantallas = p.pantallas or self._entorno.pantallas()
        form = settings_form(cfg, pantallas)
        if p.seccion == "out":
            form.out_dev = etiqueta
        elif p.seccion == "mic":
            form.mic = indice > 0
            if form.mic:
                form.mic_dev = etiqueta
        elif p.seccion == "target":
            form.target = etiqueta
        else:
            form.captures = etiqueta
        nuevo = copy.deepcopy(cfg)
        cambios = apply_settings(nuevo, form, pantallas)
        self.session.apply_settings(nuevo, cambios.notes_changed, cambios.devices_changed)
        return p.seccion, etiqueta

    # ------------------------------------------------------------------ teclas
    def _siguiente_tecla(self) -> Optional[str]:
        return self._teclas.popleft() if self._teclas else self._leer_tecla()

    def _tecla(self, tecla: str) -> bool:
        """Atiende una tecla. False cuando hay que salir del bucle (ya se decidió cerrar)."""
        k = tecla.lower()
        if self._preguntando:
            if k == "e":
                self._preguntando = False
                self._esperar()
            elif k in ("s", CTRL_C):
                return False
            elif k == ESC:  # como en todas las pantallas: un paso atrás, aquí seguir grabando
                self._preguntando = False
            return True  # el resto (también la c de captura) no hace nada mientras pregunta
        if self.session.draining:
            if k in ("s", CTRL_C):
                return False
            if k == "a":
                self._abrir_nota()
            return True
        if self._panel is not None:
            return self._tecla_panel(k)
        if k in ("q", CTRL_C):
            return self._pedir_cierre()
        if k == "p":
            self._pintar(self.session.toggle_pause())
        elif k == "c":
            self.session.manual_screenshot()  # la línea llega después por poll(); otra en curso se ignora
        elif k == "r":
            self.session.reconnect_audio()
        elif k == "a":
            self._abrir_nota()
        elif k == "o":
            self._abrir_panel()
        return True

    def _pedir_cierre(self) -> bool:
        """Como `MainWindow.on_close`: sin cola se cierra; con cola se pregunta (en el pie)."""
        resumen = self.session.request_close()
        if resumen is None:
            return False
        self._resumen = resumen
        self._preguntando = True
        if self.plano:
            self._imprimir(*self._pregunta())
        return True

    def _esperar(self) -> None:
        """Se eligió esperar: la cola solo baja y el bucle acaba cuando `status.finished`."""
        self.session.begin_drain()
        if self.plano:
            self._hecho(_ahora(), self.session.status.status_text)

    def _abrir_nota(self) -> None:
        try:
            self._abrir(str(self.session.file_path))
        except OSError as e:
            self._aviso(f"⚠ no se pudo abrir la nota: {e}", "error")

    def _on_sigint(self, _signum, _frame) -> None:
        """Ctrl+C se encola como una tecla y lo atiende el bucle: la primera vez pregunta como
        [q]; preguntando o terminando, sale perdiendo lo pendiente. Así KeyboardInterrupt no
        corta el bucle a medias ni deja el pie a medio pintar."""
        self._teclas.append(CTRL_C)

    # ------------------------------------------------------------------ bucle
    def _bucle(self) -> None:
        """Cada 200 ms, en este hilo: eventos → líneas; una tecla; el pie si cambió."""
        while True:
            for ev in self.session.poll():
                self._pintar(ev)
            if self.session.status.finished:
                return
            tecla = self._siguiente_tecla()
            if tecla is not None and not self._tecla(tecla):
                return
            self._actualizar_pie(self.session.status)
            self._dormir(INTERVALO)

    def run(self) -> int:
        self._cabecera()
        self.session.start()
        try:
            anterior = signal.signal(signal.SIGINT, self._on_sigint)
        except ValueError:  # fuera del hilo principal no se puede; se queda el de siempre
            anterior = None
        lector = contextlib.nullcontext(self._leer_tecla) if self._leer_tecla else teclas.teclado()
        try:
            with lector as self._leer_tecla:  # la terminal se restaura al salir, pase lo que pase
                if self.plano:
                    self._bucle()
                else:
                    # transient: al salir el pie se borra y queda solo la transcripción y la despedida
                    with Live(console=self.consola, auto_refresh=False, transient=True) as live:
                        self._live = live
                        self._bucle()
        finally:
            self._live = None
            if anterior is not None:
                signal.signal(signal.SIGINT, anterior)
            self.session.shutdown()  # sin pa.terminate(): ver RecorderSession.shutdown
        self._despedida()
        return 0


# ====================================================================== la pantalla completa
# Tiempos, tamaños y umbrales de `PantallaCompleta` (docs/terminal-especificacion.md, secciones 6 y 7.8).
LINEAS_MEMORIA = 2000  # frases y avisos que se guardan en memoria; la nota en disco las tiene todas
DURACION_FRASE_NUEVA = 1.5  # s que la última frase queda resaltada
DURACION_AVISO = 6.0  # s que se ve un aviso pasajero
INTERVALO_TECLA = 0.05  # s entre lecturas del teclado; el sondeo y el repintado van cada INTERVALO
TIC_LENTO = 1.0  # s del pulso del indicador y del giro con animaciones reducidas
ANIMACIONES_COMPLETAS, ANIMACIONES_NINGUNA = "completas", "ninguna"  # valores de «animations» que cambian algo
MEDIDOR_ANCHO, MEDIDOR_ESTRECHO, ANCHO_MEDIDOR_COMPLETO = 8, 4, 80  # bloques del medidor y desde qué ancho
ANCHO_HORA = len("HH:MM:SS")
COLUMNA_FUENTE = 4  # «PC  », «Mic »: la columna entre la hora y el texto
SEPARACION_HORA = 2
ANCHO_MINIMO_TEXTO = 20  # las frases no se parten en menos columnas que estas
MINIMO_TRANSCRIPCION = 4  # líneas que quedan a la transcripción aunque haya un panel abierto
ANCHO_PROGRESO = 40  # lo más ancha que se pinta la barra del vaciado
FILAS_AVISO = 2  # lo más que ocupa la región de aviso cuando su texto no cabe en una línea
SANGRIA_ITEM = 4  # las líneas de continuación del arranque van bajo el texto, no bajo el símbolo
COLUMNA_TECLAS = 13  # la columna de teclas de la leyenda [?]
SANGRIA_LEYENDA = 2
VELOCIDAD_MINIMA = 0.5  # veces el tiempo real que se supone, como mínimo, al estimar lo que falta
FUENTES_PREFIJO = "Fuentes: "  # como anota las fuentes `RecorderSession._anotar_fuentes`
FUENTES = re.compile(r"🔊 (?P<out>.+?) · 🎤 (?P<mic>.+)$")
FUENTE_NO_ENCONTRADA = "no encontrado"  # lo que antecede al nombre en esa misma línea
MIC_DESACTIVADO = "desactivado"

VISTA_TRANSCRIPCION, VISTA_RENDIMIENTO, VISTA_TECLAS = "transcripcion", "rendimiento", "teclas"
NOMBRES = {"out": "grabacion_nombre_pc", "mic": "grabacion_nombre_mic"}
# El panel [o]: la clave de su título y la de la línea de ayuda de cada sección.
TITULOS_SECCION = {"out": "grabacion_op_salida", "mic": "grabacion_op_micro", "target": "grabacion_op_captura", "captures": "grabacion_op_calidad"}
AYUDA_SECCION = {"out": "salida_audio", "mic": "microfono", "target": "que_capturar", "captures": "capturas_clave"}
FILAS_SALIDA = ("cierre_e", "cierre_s", "cierre_esc")  # las filas de la pregunta de salida: esperar, salir, seguir
LEYENDA = (  # (tecla, clave del texto) de la leyenda [?], en el orden en que se enseña
    ("p", "tecla_p"), ("c", "tecla_c"), ("a", "tecla_a"), ("r", "tecla_r"), ("o", "tecla_o"), ("m", "tecla_m"),
    ("RePág AvPág", "tecla_revisar"), ("?", "tecla_ayuda"), ("q", "tecla_q"),
)
SALTOS = {ARRIBA: -1, ABAJO: 1}  # lo que mueven las flechas, en filas o frases
TECLAS_REVISAR = (ARRIBA, ABAJO, REPAG, AVPAG, INICIO, FIN)


def titulo_de(clave: str, **datos) -> str:
    """El título de una entrada de recorder/ayuda.py, con sus huecos rellenos."""
    return ayuda.entrada(clave)[0].format(**datos)


def frase_de(clave: str, **datos) -> str:
    """La explicación de una entrada de recorder/ayuda.py como frase de la pantalla, con su punto."""
    return ayuda.entrada(clave)[1].format(**datos)


def texto_de(clave: str, **datos) -> str:
    """La explicación de una entrada de recorder/ayuda.py hecha frase de la pantalla: con sus huecos rellenos y
    sin el punto final (las entradas acaban en punto; las líneas de la transcripción y del resumen no)."""
    return ayuda.entrada(clave)[1].format(**datos).removesuffix(".")


def duracion_texto(segundos: float) -> str:
    """«45 s», «28 min» o «1 h 05 min»."""
    s = int(segundos)
    if s < 60:
        return titulo_de("grabacion_dur_s", n=s)
    minutos = s // 60
    if minutos < 60:
        return titulo_de("grabacion_dur_min", n=minutos)
    return titulo_de("grabacion_dur_h", h=minutos // 60, m=minutos % 60)


def reloj_texto(segundos: float) -> str:
    """«00:04:02»."""
    s = int(max(0, segundos))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def cantidad_texto(n: int, una: str, varias: str) -> str:
    """«1 frase» o «142 frases», con los textos de recorder/ayuda.py."""
    return titulo_de(una) if n == 1 else titulo_de(varias, n=n)


def pie_con_prioridad(botones: Sequence[Tuple[str, str]], prioridad: Sequence[str], cabe, mas: Tuple[str, str],
                      con_mas: bool = True) -> List[Tuple[str, str]]:
    """Los botones del pie que caben en una línea, en el orden en que se pintan. Si no caben todos, se quedan los
    de más prioridad (`prioridad`: sus teclas, de más a menos importante, hasta el primero que ya no cabe) y, con
    `con_mas`, «[?] Más» en lugar de «[?] Teclas». `cabe(botones)` dice si una lista cabe en la línea."""
    botones = list(botones)
    if cabe(botones):
        return botones
    resto = [b for b in botones if b[0] != "?"]
    elegidos: List[Tuple[str, str]] = []
    for tecla in prioridad:
        boton = next((b for b in resto if b[0] == tecla), None)
        if boton is None:
            continue
        if not cabe([b for b in resto if b in elegidos or b is boton] + ([mas] if con_mas else [])):
            break
        elegidos.append(boton)
    return [b for b in resto if b in elegidos] + ([mas] if con_mas else [])


@dataclasses.dataclass
class Frase:
    """Una línea de la transcripción: una frase de una fuente («out», «mic») o un hecho de la sesión («info»).
    `captura` son las palabras de la captura que dejó, para su segunda línea."""

    n: int  # su número de orden: no se reutiliza aunque salga de la memoria
    stamp: str
    fuente: str
    texto: str
    estilo: str  # el estilo del texto
    captura: str = ""
    nueva_hasta: float = 0.0  # hasta cuándo va resaltada (reloj de la pantalla)
    ancho: int = 0  # el ancho con que se partió `lineas`
    lineas: List[List[Tuple[str, str]]] = dataclasses.field(default_factory=list)


class PantallaCompleta(PantallaEnVivo):
    """`daily` en una terminal: la grabación a pantalla completa.

    Regiones fijas, de arriba abajo: cabecera de dos líneas (nota, calidad y motor; estado, tiempo, cola y
    medidores), regla, cuerpo, aviso, y pie de teclas. El cuerpo es la transcripción (se desplaza sola con lo
    último a la vista; RePág, AvPág, ↑↓ e Inicio la recorren y Fin vuelve a seguirla), con un panel debajo
    cuando se abre [o], la pregunta de salida o el vaciado de la cola; o la vista de rendimiento ([m]) o la de
    teclas ([?]). Hereda de `PantallaEnVivo` lo que no cambia: el lector de teclas, Ctrl+C, las secciones del
    panel de opciones y cómo se aplican. Esc nunca termina la grabación.

    Se repinta como mucho `1 / INTERVALO` veces por segundo, solo si el cuadro cambió, y solo se componen las
    líneas que se ven. Al salir de la pantalla alternativa se imprime el resumen (`imprimir_resumen`); si la abre
    el menú, el resumen vuelve como aviso para Inicio (`aviso_fin`).
    """

    def __init__(self, session: Optional[RecorderSession] = None, *, reloj: Callable[[], float] = time.monotonic,
                 imprimir_resumen: bool = True, **kwargs):
        super().__init__(session, **kwargs)
        self.plano = False  # esta pantalla solo existe con terminal
        self._reloj = reloj
        self._imprimir_resumen_al_salir = imprimir_resumen
        self.juego = juego_de(self.consola)
        self.fondo = not self.ascii and self.consola.color_system in COLORES_PROPIOS
        self.resumen: Optional[Resumen] = None  # lo que dejó la sesión; al salir
        self.perdido = ""  # lo que quedó sin transcribir, si se salió sin esperar
        self._animaciones = self.session.config.animations
        self._frases: Deque[Frase] = collections.deque(maxlen=LINEAS_MEMORIA)
        self._siguiente = 0
        self._arriba: Optional[int] = None  # número de la primera frase a la vista al revisar; None = siguiendo
        self._nuevas = 0  # frases llegadas mientras se revisa
        self._vista = VISTA_TRANSCRIPCION
        self._desplazamiento = 0  # la primera línea a la vista de la leyenda
        self._pasajero: Optional[Tuple[str, str, float]] = None  # (texto, estilo, hasta cuándo) del aviso pasajero
        self._cargado = False  # el modelo ya cargó: se pasa del arranque a la transcripción
        self._fuentes: Dict[str, Tuple[bool, str]] = {}  # lo que resolvió la sesión: (¿bien?, nombre o motivo)
        self._historias = nuevas_historias()
        self._ultima_muestra: Optional[float] = None
        self._t0 = 0.0
        self._fila_salida = 0
        self._cola_inicial = 0  # lo pendiente al empezar a esperar: la base de la barra del vaciado
        self._ancho = 0  # el ancho útil del cuadro que se está componiendo
        ancho, alto = self.consola.size
        # lo último pintado: lo que miden las páginas (hasta el primer cuadro, lo que se espera del tamaño)
        self._util, self._sitio, self._sitio_vista = max(1, ancho - 2 * MARGEN), max(1, alto - 7), 1
        self._firma: Optional[tuple] = None
        self._visual: tuple = ()  # lo que cambia el aspecto sin cambiar el texto: pulso y frases resaltadas

    # ------------------------------------------------------------------ texto con estilo
    def _estilo(self, estilo: str):
        """Un estilo de rich o varios nombres juntos («elegido fila»): se combinan."""
        estilo = estilo or "texto"
        if " " not in estilo.strip():
            return estilo
        return Style.combine([self.consola.get_style(e) for e in estilo.split()])

    def _armar(self, partes: Sequence[Tuple[str, str]], partir: bool = False) -> Text:
        """Trozos (texto, estilo) → Text sin marcado de rich y con los símbolos de esta consola."""
        return Text.assemble(*[(presentar(s, self.consola), self._estilo(e)) for s, e in partes], no_wrap=not partir)

    def _recortar(self, texto: Text, ancho: int) -> Text:
        """Corta a `ancho` celdas con «…» al final («...» en ASCII)."""
        if cell_len(texto.plain) <= ancho:
            return texto
        if self.ascii:
            texto.truncate(max(0, ancho - len(ELIDIDO_ASCII)), overflow="crop")
            texto.append(ELIDIDO_ASCII)
        else:
            texto.truncate(ancho, overflow="ellipsis")
        return texto

    def _t(self, *partes: Tuple[str, str]) -> Text:
        """Una línea que no se parte: lo que sobra se corta con «…»."""
        return self._recortar(self._armar(partes), self._ancho)

    def _t_fila(self, *partes: Tuple[str, str]) -> Text:
        """Como `_t`, para la fila elegida: con el fondo de superficie hasta el borde si hay color real."""
        if not self.fondo:
            return self._t(*partes)
        texto = self._recortar(self._armar([(s, f"{e or 'texto'} fila") for s, e in partes]), self._ancho)
        texto.append(" " * max(0, self._ancho - cell_len(texto.plain)), self._estilo("fila"))
        return texto

    def _envolver(self, partes: Sequence[Tuple[str, str]], ancho: int) -> List[Text]:
        """Trozos → líneas partidas por palabras a `ancho`."""
        lineas = list(self._armar(partes, partir=True).wrap(self.consola, max(1, ancho)))
        for linea in lineas:
            linea.rstrip()
        return lineas

    def _enmarcar(self, linea: Text, ancho: int) -> Text:
        """La línea con su margen, rellena hasta el ancho y, con color real, sobre el fondo de la paleta."""
        marco = Text.assemble(" " * MARGEN, linea)
        marco.pad_right(max(0, ancho - cell_len(marco.plain)))
        if self.fondo:
            marco.style = "fondo"
        return marco

    def _giro(self, ahora: float) -> str:
        """El fotograma del giro: cada TIC_ANIMACION s; con animaciones reducidas, cada TIC_LENTO; sin ellas, «…»."""
        if self._animaciones == ANIMACIONES_NINGUNA:
            return ELIDIDO
        if self._animaciones == ANIMACIONES_COMPLETAS:
            return fotograma(self.juego, ahora)
        return fotograma(self.juego, ahora // TIC_LENTO * TIC_LENTO)

    def _item(self, simbolo: str, estilo: str, texto: str, estilo_texto: str = "texto") -> List[Text]:
        """Una línea del arranque, «  √ texto»; si no cabe se parte con sangría bajo el texto."""
        lineas = self._envolver([(texto, estilo_texto)], self._ancho - SANGRIA_ITEM)
        salida = [self._armar([("  ", ""), (simbolo, estilo), (" ", "")]) + lineas[0]]
        return salida + [self._armar([(" " * SANGRIA_ITEM, "")]) + linea for linea in lineas[1:]]

    # ------------------------------------------------------------------ lo que llega de la sesión
    def _anadir(self, stamp: str, fuente: str, texto: str, estilo: str, captura: str = "") -> None:
        frase = Frase(self._siguiente, stamp, fuente, texto, estilo, captura)
        self._siguiente += 1
        habla = fuente in NOMBRES
        if habla and self._animaciones != ANIMACIONES_NINGUNA:
            frase.nueva_hasta = self._reloj() + DURACION_FRASE_NUEVA
        self._frases.append(frase)
        if self._arriba is not None:
            self._nuevas += habla
            self._arriba = max(self._arriba, self._frases[0].n)  # la frase que se miraba salió de la memoria

    def _evento(self, ev: Event) -> None:
        """Una línea de la transcripción (o la cabecera) por cada cosa que cuenta la sesión."""
        if isinstance(ev, Line):
            self._linea_de_sesion(ev)
        elif isinstance(ev, Notice):
            self._noticia(ev)
        elif isinstance(ev, SourceMuted):
            nombre = titulo_de(NOMBRES[ev.kind])
            if ev.muted:
                self._anadir(ev.stamp, "info", "⚠ " + frase_de("grabacion_muda", fuente=nombre, min=MUTE_WARN_SEC // 60), "aviso")
            else:
                self._anadir(ev.stamp, "info", "✔ " + frase_de("grabacion_vuelve", fuente=nombre), "ok")
        elif isinstance(ev, SourceChanged):
            nombre = titulo_de(NOMBRES[ev.kind])
            if ev.up:
                self._anadir(ev.stamp, "info", "✔ " + frase_de("grabacion_vuelve", fuente=nombre), "ok")
            else:
                intento = max(1, self.session.status.attempts.get(ev.kind, 0))
                self._anadir(ev.stamp, "info", "⚠ " + frase_de("grabacion_caida", fuente=nombre, n=intento), "error")

    def _linea_de_sesion(self, ev: Line) -> None:
        if ev.kind in NOMBRES:
            self._anadir(ev.stamp, ev.kind, ev.text, "acento" if ev.hits else "texto", ", ".join(ev.hits))
        elif ev.hits == ["manual"]:
            self._anadir(ev.stamp, "info", "📸 " + titulo_de("grabacion_captura_manual"), "tenue")
        else:
            self._anadir(ev.stamp, "info", ev.text, "tenue", ", ".join(ev.hits))

    def _noticia(self, ev: Notice) -> None:
        if ev.text.startswith(FUENTES_PREFIJO):
            self._anotar_fuentes(ev.text.removeprefix(FUENTES_PREFIJO), ev.stamp)
            return
        self._anadir(ev.stamp, "info", self._con_accion(ev.text, ev.action), "error" if ev.level == "err" else "tenue")

    def _anotar_fuentes(self, texto: str, stamp: str) -> None:
        """«🔊 Altavoces · 🎤 Micro»: lo que se ve en el arranque y la primera línea de la transcripción."""
        m = FUENTES.match(texto)
        if not m:
            self._anadir(stamp, "info", titulo_de("grabacion_empieza"), "tenue")
            return
        salida, micro = m["out"], m["mic"]
        apagado = micro == MIC_DESACTIVADO
        self._fuentes = {
            "out": (not salida.startswith(FUENTE_NO_ENCONTRADA), salida),
            "mic": (not micro.startswith(FUENTE_NO_ENCONTRADA), titulo_de("grabacion_mic_apagado") if apagado else micro),
        }
        nombres = [salida] + ([] if apagado else [micro])
        self._anadir(stamp, "info", texto_de("grabacion_empieza", fuentes=" · ".join(nombres)), "tenue")

    def _avisar(self, texto: str, estilo: str = "tenue") -> None:
        """Un aviso que se va solo, tras DURACION_AVISO s."""
        self._pasajero = (texto, estilo, self._reloj() + DURACION_AVISO)

    def _aviso(self, texto: str, estilo: str = "tenue") -> None:
        self._avisar(texto, estilo)

    def _abrir_nota(self) -> None:
        try:
            self._abrir(str(self.session.file_path))
        except OSError as e:
            self._avisar("⚠ " + frase_de("grabacion_nota_no_abre", motivo=e), "error")

    def _muestrear(self, st: StatusSnapshot, ahora: float) -> None:
        """Con el modelo cargado, pasa del arranque a la transcripción; cada INTERVALO_METRICAS s anota las
        cifras de la vista de rendimiento (para que su tendencia ya esté al abrirla)."""
        if not self._cargado and ((st.base_status and st.base_status[0] in LIVE_STATUS) or (st.metricas and st.metricas.motor)):
            self._cargado = True
        if st.metricas and (self._ultima_muestra is None or ahora - self._ultima_muestra >= INTERVALO_METRICAS):
            self._ultima_muestra = ahora
            anotar(self._historias, st.metricas)

    # ------------------------------------------------------------------ teclas
    def _tecla(self, tecla: str) -> bool:
        """Atiende una tecla. False cuando hay que salir del bucle (ya se decidió cerrar)."""
        k = tecla.lower()
        if self._preguntando:
            return self._tecla_salida(k)
        if self.session.draining:
            if k in ("s", CTRL_C):
                return False
            if k == "a":
                self._abrir_nota()
            return True
        if self._panel is not None:
            return self._tecla_opciones(k)
        return self._tecla_principal(k)

    def _tecla_principal(self, k: str) -> bool:
        if k in ("q", CTRL_C):
            return self._pedir_cierre()
        if k == "?":
            self._vista, self._desplazamiento = VISTA_TECLAS, 0
        elif k == ESC:
            if self._vista == VISTA_TRANSCRIPCION:
                self._avisar(ayuda.linea("grabacion_esc"))  # Esc nunca termina una grabación
            self._vista = VISTA_TRANSCRIPCION
        elif not self._cargado:
            pass  # hasta que cargue el modelo solo valen salir, ? y Esc
        elif k == "p":
            self._pausar()
        elif k == "c":
            self.session.manual_screenshot()  # la línea llega después por poll(); otra en curso se ignora
        elif k == "a":
            self._abrir_nota()
        elif self._vista == VISTA_TRANSCRIPCION and k == "r":
            self.session.reconnect_audio()
        elif self._vista == VISTA_TRANSCRIPCION and k == "o":
            self._abrir_panel()
        elif self._vista == VISTA_TRANSCRIPCION and k == "m":
            self._vista = VISTA_RENDIMIENTO
        elif k in TECLAS_REVISAR:
            self._desplazar(k)
        return True

    def _pausar(self) -> None:
        pausada = self.session.toggle_pause()
        if self.session.paused:
            self._anadir(pausada.stamp, "info", "⏸ " + texto_de("grabacion_linea_pausa"), "tenue")
        else:
            self._anadir(pausada.stamp, "info", "▶ " + texto_de("grabacion_linea_sigue"), "tenue")

    def _tecla_salida(self, k: str) -> bool:
        """La pregunta de salida con audio pendiente: e, s y Esc, o ↑↓ y Enter sobre sus filas."""
        if k in ("s", CTRL_C):
            return False
        if k in (ARRIBA, ABAJO):
            self._fila_salida = (self._fila_salida + SALTOS[k]) % len(FILAS_SALIDA)
            return True
        eleccion = {"e": 0, ENTER: self._fila_salida, ESC: 2}.get(k)
        if eleccion is None:
            return True  # el resto, también la c de captura, no hace nada mientras pregunta
        self._preguntando, self._fila_salida = False, 0
        if eleccion == 1:
            return False
        if eleccion == 0:
            self._cola_inicial = self.session.chunk_queue.qsize() + bool(self.session.transcriber.busy)
            self._esperar()
        return True

    def _tecla_opciones(self, k: str) -> bool:
        """Las teclas con el panel [o] abierto: ↑↓ mueven la fila, Enter abre o elige, los números son atajos,
        Esc vuelve (sección → índice → cierra) y q cierra el panel y sale. ←/→ no hacen nada."""
        p = self._panel
        if k in ("q", CTRL_C):
            self._cerrar_panel()
            return self._pedir_cierre()
        if k == "?":
            self._cerrar_panel()
            self._vista, self._desplazamiento = VISTA_TECLAS, 0
        elif k == "o":
            self._cerrar_panel()
        elif k == ESC:
            if p.seccion is None:
                self._cerrar_panel()
            else:
                self._panel = Panel(fila=next(i for i, (_t, s, _n) in enumerate(SECCIONES) if s == p.seccion))
        elif k in (ARRIBA, ABAJO):
            p.fila = (p.fila + SALTOS[k]) % (len(SECCIONES) if p.seccion is None else len(p.opciones))
            p.tecleado = ""
        elif p.seccion is None:
            self._tecla_indice(k)
        elif k == "r" and p.seccion == "target":
            self._abrir_seccion("target")  # relee las ventanas abiertas
        elif k in "0123456789" and len(k) == 1:
            self._digito(k)
        elif k == ENTER:
            self._elegir(int(p.tecleado) - 1 if p.tecleado else p.fila)
        elif k == RETROCESO:
            p.tecleado = p.tecleado[:-1]
        return True

    def _tecla_indice(self, k: str) -> None:
        p = self._panel
        if k == ENTER:
            self._abrir_seccion(SECCIONES[p.fila][1])
        else:
            seccion = next((s for tecla, s, _t in SECCIONES if tecla == k), None)
            if seccion:
                self._abrir_seccion(seccion)

    def _abrir_seccion(self, seccion: str) -> None:
        super()._abrir_seccion(seccion)
        self._panel.fila = max(0, self._panel.actual)

    def _elegir(self, indice: int) -> None:
        hecho = self._aplicar(indice)
        if hecho:
            seccion, etiqueta = hecho
            self._avisar("✔ " + texto_de("grabacion_aplicado", ajuste=titulo_de(TITULOS_SECCION[seccion]), valor=etiqueta), "ok")

    # ------------------------------------------------------------------ revisar la transcripción
    def _lineas_de(self, frase: Frase, ancho: int) -> List[List[Tuple[str, str]]]:
        """Las líneas de la frase partidas a `ancho` (se guardan: solo se vuelven a partir si cambia el ancho)."""
        if frase.ancho == ancho and frase.lineas:
            return frase.lineas
        hueco = ANCHO_HORA + SEPARACION_HORA + COLUMNA_FUENTE
        etiqueta = titulo_de(NOMBRES[frase.fuente]) if frase.fuente in NOMBRES else ""
        sangria = " " * hueco
        trozos = self._envolver([(frase.texto, frase.estilo)], max(ANCHO_MINIMO_TEXTO, ancho - hueco))
        lineas = []
        for i, trozo in enumerate(trozos):
            if i == 0:
                cabeza = [(frase.stamp, "tenue"), (" " * SEPARACION_HORA, ""), (etiqueta.ljust(COLUMNA_FUENTE), "mic" if frase.fuente == "mic" else "tenue")]
            else:
                cabeza = [(sangria, "")]
            lineas.append(cabeza + [(trozo.plain, frase.estilo)])
        if frase.captura:
            lineas.append([(sangria, ""), ("📸 " + titulo_de("grabacion_captura", palabras=frase.captura), "tenue")])
        frase.ancho, frase.lineas = ancho, lineas
        return lineas

    def _inicio_siguiendo(self) -> int:
        """El número de la primera frase que se ve cuando se sigue lo último."""
        usadas, primera = 0, self._siguiente
        for frase in reversed(self._frases):
            usadas += len(self._lineas_de(frase, self._util))
            if usadas > self._sitio:
                break
            primera = frase.n
        return primera

    def _cabe_hasta_el_final(self, desde: int) -> bool:
        """Si desde esa frase hasta la última caben a la vista: ahí ya se sigue lo último."""
        resto = itertools.islice(self._frases, desde - self._frases[0].n, None)
        return sum(len(self._lineas_de(frase, self._util)) for frase in resto) <= self._sitio

    def _seguir(self) -> None:
        self._arriba, self._nuevas = None, 0

    def _desplazar(self, k: str) -> None:
        """↑↓ mueven una frase, RePág y AvPág una página, Inicio va al principio y Fin vuelve a seguir lo último."""
        if self._vista == VISTA_TECLAS:
            pagina = max(1, self._sitio_vista - 1)
            cambio = {ARRIBA: -1, ABAJO: 1, REPAG: -pagina, AVPAG: pagina}.get(k)
            self._desplazamiento = 0 if k == INICIO else 10 ** 6 if k == FIN else max(0, self._desplazamiento + (cambio or 0))
            return
        if self._vista != VISTA_TRANSCRIPCION or not self._frases:
            return
        if k == FIN:
            self._seguir()
            return
        base, ultima = self._frases[0].n, self._frases[-1].n
        actual = self._arriba if self._arriba is not None else self._inicio_siguiendo()
        if k == INICIO:
            destino = base
        elif k in SALTOS:
            destino = min(ultima, max(base, actual + SALTOS[k]))
        else:
            faltan, i = max(1, self._sitio - 1), actual - base
            if k == REPAG:
                while i > 0 and faltan > 0:
                    i -= 1
                    faltan -= len(self._lineas_de(self._frases[i], self._util))
            else:
                while i < len(self._frases) - 1 and faltan > 0:
                    faltan -= len(self._lineas_de(self._frases[i], self._util))
                    i += 1
            destino = self._frases[i].n
        if self._cabe_hasta_el_final(destino):
            self._seguir()
            return
        if self._arriba is None:
            self._nuevas = 0
        self._arriba = destino

    def _transcripcion(self, sitio: int, ahora: float) -> List[Text]:
        """Las líneas de la transcripción que caben en `sitio`, siempre de frases enteras por arriba."""
        if sitio <= 0 or not self._frases:
            return []
        util, elegidas, usadas = self._util, [], 0
        if self._arriba is None:  # siguiendo: de lo último hacia atrás
            for frase in reversed(self._frases):
                n = len(self._lineas_de(frase, util))
                if usadas + n > sitio:
                    break
                elegidas.append(frase)
                usadas += n
            elegidas.reverse()
            if not elegidas:  # una frase más alta que el sitio: se ven sus últimas líneas
                elegidas = [self._frases[-1]]
        else:  # revisando: desde la frase elegida hacia delante
            i = max(0, self._arriba - self._frases[0].n)
            for frase in itertools.islice(self._frases, i, None):
                if usadas >= sitio:
                    break
                elegidas.append(frase)
                usadas += len(self._lineas_de(frase, util))
        lineas: List[Text] = []
        resaltadas = []
        for frase in elegidas:
            resaltada = frase.nueva_hasta > ahora
            if resaltada:
                resaltadas.append(frase.n)
            for partes in self._lineas_de(frase, util):
                lineas.append(self._t_fila(*partes) if resaltada else self._t(*partes))
        self._visual = self._visual + (tuple(resaltadas),)
        return lineas[-sitio:] if self._arriba is None else lineas[:sitio]

    # ------------------------------------------------------------------ las regiones
    def _regla(self, titulo: str) -> Text:
        """«── Título ─────────»: abre un panel bajo la transcripción."""
        relleno = max(0, self._ancho - cell_len(presentar(titulo, self.consola)) - 4)
        return self._t(("── ", "borde"), (titulo, "bold"), (" ", ""), ("─" * relleno, "borde"))

    def _medidores(self, st: StatusSnapshot) -> List[Tuple[str, str]]:
        """«PC █████░░░  Mic █░░░░░░░»: el micrófono apagado no se pinta; una fuente caída dice su reintento y la
        que lleva rato sin voz, «sin audio»."""
        n = MEDIDOR_ANCHO if self.consola.size[0] >= ANCHO_MEDIDOR_COMPLETO else MEDIDOR_ESTRECHO
        partes: List[Tuple[str, str]] = []
        for kind, estilo in (("out", "tenue"), ("mic", "mic")):
            if kind == "mic" and not st.mic:
                continue
            if partes:
                partes.append(("  ", ""))
            partes.append((titulo_de(NOMBRES[kind]) + " ", estilo))
            if st.attempts.get(kind):
                partes.append(("× " + titulo_de("grabacion_reintento", n=st.attempts[kind]), "error"))
            elif st.muted == kind:
                partes.append((titulo_de("grabacion_sin_audio"), "aviso"))
            else:
                partes.append((bars(st.levels.get(kind, 0.0), n), "texto"))
        return partes

    def _estado(self, st: StatusSnapshot, ahora: float) -> List[Tuple[str, str]]:
        """«● Escuchando  00:04:02 · en cola 1»: el estado en palabras y con su símbolo; el pulso del ● es un refuerzo."""
        if not self._cargado:
            return [(self._giro(ahora) + " ", "acento"), (titulo_de("grabacion_preparando"), "acento")]
        if st.draining:
            partes = [("… " + titulo_de("grabacion_terminando"), "acento")]
        elif st.paused:
            partes = [("⏸ " + titulo_de("grabacion_pausa"), "aviso")]
        else:
            late = self._animaciones == ANIMACIONES_COMPLETAS and int(ahora / TIC_LENTO) % 2
            partes = [("● " + titulo_de("grabacion_escuchando"), "tenue" if late else "ok")]
            self._visual += (bool(late),)
        partes += [("  " + reloj_texto(ahora - self._t0), "tenue")]
        if st.pending:
            partes.append((" · " + titulo_de("grabacion_en_cola", n=st.pending), "tenue"))
        if st.errors:
            partes.append((" · " + titulo_de("grabacion_con_fallo", n=st.errors), "error"))
        return partes

    def _cabecera_pantalla(self, st: StatusSnapshot, ahora: float) -> List[Text]:
        """Las dos líneas de la cabecera y la regla."""
        calidad = describe_quality(self.session.config)
        if st.metricas and st.metricas.motor:
            calidad = f"{calidad.split(' · ')[0]} · {st.metricas.motor.donde}"
        uno = self._t(("Recorder", "bold"), (" · ", "tenue"), (st.file_path.name, "texto"), (" · ", "tenue"), (calidad, "tenue"))
        izquierda = self._armar(self._estado(st, ahora))
        derecha = self._armar(self._medidores(st)) if self._cargado else Text()
        hueco = self._ancho - cell_len(izquierda.plain) - cell_len(derecha.plain)
        if hueco < 1:
            izquierda = self._recortar(izquierda, max(1, self._ancho - cell_len(derecha.plain) - 1))
            hueco = max(1, self._ancho - cell_len(izquierda.plain) - cell_len(derecha.plain))
        return [uno, izquierda + Text(" " * hueco) + derecha, self._t(("─" * self._ancho, "borde"))]

    def _lineas_aviso(self, st: StatusSnapshot, ahora: float) -> List[Text]:
        """La región de aviso: el pasajero si lo hay; si no, las frases nuevas mientras se revisa; si no, el de una
        fuente caída o sin audio, que dura mientras dure. Una línea reservada y hasta dos si el texto no cabe."""
        if self._pasajero and self._pasajero[2] <= ahora:
            self._pasajero = None
        if self._pasajero:
            texto, estilo = self._pasajero[:2]
        elif self._arriba is not None and self._nuevas:
            una = self._nuevas == 1
            texto = f"↓ {titulo_de('grabacion_nueva_una' if una else 'grabacion_nuevas', n=self._nuevas)} · {texto_de('grabacion_nuevas', n=self._nuevas)}"
            estilo = "acento"
        else:
            texto, estilo = self._aviso_persistente(st)
        lineas = self._envolver([(texto, estilo)], self._ancho)[:FILAS_AVISO] if texto else []
        return [self._t(*[(linea.plain, estilo)]) for linea in lineas] or [Text()]

    def _aviso_persistente(self, st: StatusSnapshot) -> Tuple[str, str]:
        for kind in NOMBRES:
            if st.attempts.get(kind):
                return "× " + frase_de("grabacion_caida", fuente=titulo_de(NOMBRES[kind]), n=st.attempts[kind]), "error"
        if st.muted:
            return "⚠ " + frase_de("grabacion_muda", fuente=titulo_de(NOMBRES[st.muted]), min=MUTE_WARN_SEC // 60), "aviso"
        return "", "tenue"

    # ------------------------------------------------------------------ el pie
    def _botones(self, st: StatusSnapshot) -> Tuple[List[Tuple[str, str]], Sequence[str], Optional[List[Tuple[str, str]]], bool]:
        """(botones, prioridad, botones más cortos, con «Más») del pie de lo que se ve ahora."""
        P = lambda clave: ayuda.entrada(clave)[0]  # noqa: E731
        salir, teclas = ("q", P("pie_salir")), ("?", P("grabacion_pie_teclas"))
        if self._preguntando:
            largos = [("e", P("cierre_e")), ("s", P("cierre_s")), ("Esc", P("cierre_esc"))]
            cortos = largos[:2] + [("Esc", P("grabacion_pie_seguir"))]
            return largos, ("e", "s", "Esc"), cortos, False
        if st.draining:
            return [("s", P("cierre_s")), ("a", P("grabacion_pie_nota"))], ("s", "a"), None, False
        if self._panel is not None:
            filas = [("↑↓", P("pie_mover")), ("Enter", P("pie_abrir" if self._panel.seccion is None else "pie_elegir"))]
            n = len(SECCIONES) if self._panel.seccion is None else min(9, len(self._panel.opciones))
            if n > 1:
                filas.append((f"1-{n}", P("pie_directo")))
            if self._panel.seccion == "target":
                filas.append(("r", P("grabacion_pie_releer")))
            volver = P("grabacion_pie_cerrar" if self._panel.seccion is None else "pie_volver")
            return filas + [("Esc", volver), salir], ("↑↓", "Enter", "Esc", "q"), None, True
        if not self._cargado:
            return [("q", P("pie_cancelar")), teclas], ("q",), None, False
        if self._vista == VISTA_TECLAS:
            return [("Esc", P("grabacion_pie_a_la_transcripcion")), salir], ("Esc", "q"), None, False
        pausa = ("p", P("grabacion_pie_seguir" if st.paused else "grabacion_pie_pausar"))
        captura = ("c", P("grabacion_pie_captura"))
        if self._vista == VISTA_RENDIMIENTO:
            return [("Esc", P("grabacion_pie_a_la_transcripcion")), pausa, captura, salir, teclas], ("Esc", "q", "p", "c"), None, True
        if self._arriba is not None:
            botones = [("RePág/AvPág", P("grabacion_pie_revisar")), ("Fin", P("grabacion_pie_ultimo")), pausa, captura, salir, teclas]
            return botones, ("RePág/AvPág", "Fin", "p", "q", "c"), None, True
        botones = [pausa, captura, ("a", P("grabacion_pie_nota")), ("o", P("grabacion_pie_opciones")),
                   ("m", P("grabacion_pie_rendimiento")), salir, teclas]
        return botones, ("p", "q", "c", "o", "m", "a"), None, True

    def _pie_pantalla(self, st: StatusSnapshot) -> Text:
        botones, prioridad, cortos, con_mas = self._botones(st)

        def cabe(lista) -> bool:
            return cell_len(presentar("".join(s for s, _e in partes_teclas(lista)), self.consola)) <= self._ancho

        mas = ("?", ayuda.entrada("pie_mas")[0])
        if cortos and not cabe(botones):
            botones = cortos
        return self._t(*partes_teclas(pie_con_prioridad(botones, prioridad, cabe, mas, con_mas)))

    # ------------------------------------------------------------------ los paneles bajo la transcripción
    def _filas_indice(self) -> List[Tuple[str, str, str]]:
        """(número, título, lo configurado ahora) de cada sección del panel [o]."""
        valores = self._valores_actuales()
        return [(tecla, titulo_de(TITULOS_SECCION[s]), valores[s]) for tecla, s, _t in SECCIONES]

    def _ayuda_de(self, clave: str) -> List[Text]:
        """La línea de ayuda de la fila elegida, en las líneas que se le reservan (fijas para cada ancho)."""
        reservadas = alto_ayuda(self.consola.size[0])
        lineas = [self._t((linea.plain, "tenue")) for linea in self._envolver([(ayuda.linea(clave), "tenue")], self._ancho)[:reservadas]]
        return lineas + [Text()] * (reservadas - len(lineas))

    def _fila(self, elegida: bool, numero: str, partes: Sequence[Tuple[str, str]]) -> Text:
        todo = [("▶" if elegida else " ", "acento"), (f" {numero:<3}" if numero else " ", "acento"), *partes]
        return self._t_fila(*todo) if elegida else self._t(*todo)

    def _panel_opciones(self, tope: int) -> List[Text]:
        p = self._panel
        if p.seccion is None:
            filas = self._filas_indice()
            columna = max(cell_len(t) for _n, t, _v in filas)
            lineas = [self._regla(titulo_de("grabacion_opciones"))]
            for i, (numero, titulo, valor) in enumerate(filas):
                elegida = i == p.fila
                lineas.append(self._fila(elegida, numero, [(titulo + " " * (columna - cell_len(titulo) + 2), "elegido" if elegida else "texto"), (valor, "tenue")]))
            return lineas + self._ayuda_de(AYUDA_SECCION[SECCIONES[p.fila][1]])
        titulo = f"{titulo_de('grabacion_opciones')} › {titulo_de(TITULOS_SECCION[p.seccion])}"
        extra = (
            [self._t((linea.plain, "tenue")) for linea in self._envolver([(ayuda.linea("grabacion_dispositivo_nuevo"), "tenue")], self._ancho)]
            if p.seccion in ("out", "mic") else []
        )
        sitio = max(1, tope - 1 - len(extra) - 1)
        visibles, arriba, abajo = ventana(len(p.opciones), p.fila, sitio)
        lineas = [self._regla(titulo)]
        if arriba:
            lineas.append(self._marca_lista("terminal_mas_arriba", arriba))
        for i in visibles:
            elegida = i == p.fila
            actual = "  " + titulo_de("terminal_actual") if i == p.actual else ""
            lineas.append(self._fila(elegida, str(i + 1), [(p.opciones[i], "elegido" if elegida else "texto"), (actual, "tenue")]))
        if abajo:
            lineas.append(self._marca_lista("terminal_mas_abajo", abajo))
        lineas += extra
        if p.tecleado:
            lineas.append(self._t(("› " + p.tecleado + "_", "acento")))
        return lineas

    def _marca_lista(self, clave: str, n: int) -> Text:
        flecha = "↑" if clave.endswith("arriba") else "↓"
        return self._t((" " * SANGRIA_LISTA + f"{flecha} {titulo_de(clave, n=n)}", "tenue"))

    def _panel_salida(self) -> List[Text]:
        lineas = [self._regla(titulo_de("grabacion_salir")), self._t(("  " + ayuda.linea("grabacion_salir").format(resumen=self._resumen), "acento"))]
        for i, clave in enumerate(FILAS_SALIDA):
            elegida = i == self._fila_salida
            lineas.append(self._fila(elegida, "", [(titulo_de(clave), "elegido" if elegida else "texto")]))
        return lineas + self._ayuda_de(FILAS_SALIDA[self._fila_salida])

    def _panel_vaciado(self, st: StatusSnapshot) -> List[Text]:
        total = max(self._cola_inicial, 1)
        pendientes = st.pending + bool(st.busy)
        hechos = min(total, max(0, total - pendientes))
        m = st.metricas
        restante = (m.atraso_s / max(VELOCIDAD_MINIMA, m.velocidad or 1.0)) if m else 0.0
        detalle = f"  {texto_de('grabacion_vaciando', hechos=hechos, total=total, tiempo=duracion_texto(restante))}"
        ancho = max(1, min(ANCHO_PROGRESO, self._ancho - cell_len(detalle) - 2))
        lleno, vacio = barra(hechos / total * 100, ancho)
        return [self._regla(titulo_de("grabacion_vaciando")), self._t(("  " + lleno, "ok"), (vacio, "tenue"), (detalle, "tenue"))]

    def _paneles(self, st: StatusSnapshot, libre: int) -> List[Text]:
        """Lo que va bajo la transcripción: el panel de opciones, la pregunta de salida o el vaciado."""
        if self._preguntando:
            return self._panel_salida()
        if st.draining:
            return self._panel_vaciado(st)
        if self._panel is not None:
            return self._panel_opciones(libre - MINIMO_TRANSCRIPCION)
        return []

    # ------------------------------------------------------------------ las vistas de pantalla entera
    def _vista_rendimiento(self, st: StatusSnapshot, sitio: int, ahora: float) -> List[Text]:
        cabeza = [self._t((titulo_de("grabacion_nombre") + " › " + titulo_de("grabacion_rendimiento"), "bold")), Text()]
        if st.metricas is None:
            return cabeza
        lineas = vista_en_vivo(st.metricas, self._historias, self._ancho, max(1, sitio - len(cabeza)), self.juego, giro=self._giro(ahora))
        return cabeza + [self._t(*linea) if linea else Text() for linea in lineas]

    def _vista_teclas(self, sitio: int) -> List[Text]:
        cabeza = [self._t((titulo_de("grabacion_nombre") + " › " + titulo_de("tecla_ayuda"), "bold")), Text()]
        lineas: List[Text] = []
        for tecla, clave in LEYENDA:
            titulo, texto = ayuda.entrada(clave)
            ancho = SANGRIA_LEYENDA + COLUMNA_TECLAS + 1
            trozos = self._envolver([(f"{titulo}: ", "texto"), (texto, "tenue")], self._ancho - ancho)
            for i, trozo in enumerate(trozos):
                izquierda = f"{' ' * SANGRIA_LEYENDA}{tecla:<{COLUMNA_TECLAS}} " if i == 0 else " " * ancho
                lineas.append(self._armar([(izquierda, "acento")]) + trozo)
        alto = max(1, sitio - len(cabeza))
        self._sitio_vista = alto
        if len(lineas) > alto:
            self._desplazamiento = min(self._desplazamiento, len(lineas) - alto)
            visibles = lineas[self._desplazamiento:self._desplazamiento + alto]
            if self._desplazamiento:
                visibles[0] = self._marca_lista("terminal_mas_arriba", self._desplazamiento + 1)
            abajo = len(lineas) - self._desplazamiento - alto
            if abajo:
                visibles[-1] = self._marca_lista("terminal_mas_abajo", abajo + 1)
            lineas = visibles
        else:
            self._desplazamiento = 0
        return cabeza + lineas

    def _arranque(self, st: StatusSnapshot, ahora: float) -> List[Text]:
        """El arranque en la propia pantalla: el modelo y cada fuente, con su giro hasta que se abren."""
        cfg = self.session.config
        giro = self._giro(ahora)
        lineas = [Text()]
        calidad = describe_quality(cfg).split(" · ")[0]
        if st.base_status[:1] in "⚠⛔" and st.base_status:
            lineas += self._item("×", "error", st.base_status, "error")
        else:
            lineas += self._item(giro, "acento", f"{titulo_de('grabacion_cargando_modelo')} ({calidad})…", "tenue")
        for kind, clave in (("out", "grabacion_fuente_salida"), ("mic", "grabacion_fuente_micro")):
            if kind not in self._fuentes:
                if kind == "out":
                    lineas += self._item(giro, "acento", titulo_de("grabacion_abriendo_audio") + "…", "tenue")
                continue
            bien, nombre = self._fuentes[kind]
            lineas += self._item("√" if bien else "×", "ok" if bien else "error", f"{titulo_de(clave)}: {nombre}", "texto" if bien else "error")
        v = self._valores_actuales()
        que = titulo_de("grabacion_cap_apagadas") if cfg.captures == "off" else texto_de("grabacion_fuente_capturas", que=v["target"], palabras=", ".join(cfg.keywords))
        lineas += self._item("·", "tenue", f"{titulo_de('grabacion_fuente_capturas')}: {que}", "tenue")
        return lineas

    # ------------------------------------------------------------------ el cuadro
    def _pequena(self, ancho: int) -> List[Text]:
        """Lo único que se pinta por debajo del tamaño mínimo: el aviso, que se va solo al agrandar."""
        titulo, texto = ayuda.entrada("terminal_pequena")
        self._ancho = max(1, ancho)
        partes = [(texto.format(columnas=ANCHO_MINIMO, lineas=ALTO_MINIMO), "tenue")]
        return [self._t((titulo, "bold"))] + self._envolver(partes, self._ancho)

    def _marco(self, st: StatusSnapshot, ahora: float) -> List[Text]:
        """El cuadro entero, de la altura de la terminal."""
        ancho, alto = self.consola.size
        self._visual = ()
        if demasiado_pequena(ancho, alto):
            return self._pequena(ancho)
        self._ancho = self._util = ancho - 2 * MARGEN
        arriba = self._cabecera_pantalla(st, ahora)
        aviso = self._lineas_aviso(st, ahora)
        pie = self._pie_pantalla(st)
        libre = alto - len(arriba) - len(aviso) - 1
        if self._vista == VISTA_TECLAS:
            cuerpo = self._vista_teclas(libre)
        elif not self._cargado:
            cuerpo = self._arranque(st, ahora)
        elif self._vista == VISTA_RENDIMIENTO:
            cuerpo = self._vista_rendimiento(st, libre, ahora)
        else:
            paneles = self._paneles(st, libre)
            self._sitio = max(1, libre - len(paneles))
            cuerpo = self._transcripcion(self._sitio, ahora)
            cuerpo += [Text()] * (self._sitio - len(cuerpo)) + paneles
        cuerpo = cuerpo[:libre] + [Text()] * (libre - len(cuerpo))
        return [self._enmarcar(linea, ancho) for linea in arriba + cuerpo + aviso + [pie]]

    def _repintar(self, st: StatusSnapshot, ahora: float) -> None:
        """Pinta el cuadro solo si cambió: quieto no se escribe nada."""
        lineas = self._marco(st, ahora)
        firma = (tuple(linea.plain for linea in lineas), self.consola.size, self._visual)
        if firma != self._firma:
            self._firma = firma
            self._live.update(Group(*lineas), refresh=True)

    # ------------------------------------------------------------------ bucle
    def _bucle(self) -> None:
        """Cada INTERVALO_TECLA s se lee una tecla; cada INTERVALO s se sondea la sesión. Se repinta tras una
        tecla, en cada sondeo o al cambiar el tamaño, y solo se escribe si el cuadro cambió."""
        ultimo, tam, st = None, None, self.session.status
        while True:
            ahora = self._reloj()
            sondeo = ultimo is None or ahora - ultimo >= INTERVALO
            if sondeo:
                ultimo = ahora
                for ev in self.session.poll():
                    self._evento(ev)
                st = self.session.status
                if st.finished:
                    return
                self._muestrear(st, ahora)
            tecla = self._siguiente_tecla()
            if tecla is not None:
                if not self._tecla(tecla):
                    return
                st = self.session.status
            if sondeo or tecla is not None or self.consola.size != tam:
                tam = self.consola.size
                self._repintar(st, ahora)
            self._dormir(INTERVALO_TECLA)

    def run(self) -> int:
        self.session.start()
        self._t0 = self._reloj()
        try:
            anterior = signal.signal(signal.SIGINT, self._on_sigint)
        except ValueError:  # fuera del hilo principal no se puede; se queda el de siempre
            anterior = None
        lector = contextlib.nullcontext(self._leer_tecla) if self._leer_tecla else teclas.teclado()
        try:
            with lector as self._leer_tecla:  # la terminal se restaura al salir, pase lo que pase
                with Live(console=self.consola, screen=True, auto_refresh=False) as live:
                    self._live = live
                    self._bucle()
        finally:
            self._live = None
            if anterior is not None:
                signal.signal(signal.SIGINT, anterior)
            self.session.shutdown()  # sin pa.terminate(): ver RecorderSession.shutdown
        self.perdido = self.session.request_close() or ""
        self.resumen = self.session.resumen
        if self._imprimir_resumen_al_salir:
            self._escribir_resumen()
        return 0

    # ------------------------------------------------------------------ al salir
    def _nombre_aviso(self, clase: str, dato: str) -> str:
        if clase == AVISO_MUDA:
            return titulo_de("grabacion_muda", fuente=titulo_de(NOMBRES[dato]))
        if clase == AVISO_CAIDA:
            return titulo_de("grabacion_caida", fuente=titulo_de(NOMBRES[dato]))
        return dato.removeprefix("⚠ ")

    def _escribir_resumen(self) -> None:
        """Lo único que la grabación deja en el historial: título en negrita y lo demás en el color de la consola."""
        r = self.resumen
        filas = [
            (titulo_de("grabacion_resumen_nota"), str(self.session.file_path)),
            (titulo_de("grabacion_resumen_duracion"), self._duracion_y_cuentas()),
        ]
        if r.avisos:
            lista = "; ".join(self._nombre_aviso(c, d) for c, d in r.avisos)
            filas.append((titulo_de("grabacion_resumen_avisos"), texto_de("grabacion_resumen_avisos", n=len(r.avisos), lista=lista)))
        columna = max(len(e) for e, _v in filas)
        titulo = f"Recorder · {titulo_de('grabacion_resumen').lower()}"
        self.consola.print(Text(presentar(titulo, self.consola), style="bold"), soft_wrap=True)
        for etiqueta, valor in filas:
            self.consola.print(Text(presentar(f"  {etiqueta.ljust(columna)}  {valor}", self.consola)), soft_wrap=True)
        if self.perdido:
            self.consola.print(Text(presentar("⚠ " + ayuda.linea("grabacion_perdido").format(resumen=self.perdido), self.consola)), soft_wrap=True)

    def _duracion_y_cuentas(self) -> str:
        r = self.resumen
        return texto_de(
            "grabacion_resumen_duracion", duracion=duracion_texto(r.duracion_s),
            frases=cantidad_texto(r.frases, "grabacion_una_frase", "grabacion_n_frases"),
            capturas=cantidad_texto(r.capturas, "grabacion_una_captura", "grabacion_n_capturas"),
        )

    def aviso_fin(self) -> str:
        """El resumen en una línea, para el aviso con que Inicio recibe de vuelta la grabación que abrió el menú."""
        r = self.resumen
        return texto_de(
            "grabacion_fin_aviso", duracion=duracion_texto(r.duracion_s),
            frases=cantidad_texto(r.frases, "grabacion_una_frase", "grabacion_n_frases"),
            capturas=cantidad_texto(r.capturas, "grabacion_una_captura", "grabacion_n_capturas"), nota=self.session.file_path,
        )


def grabar(consola: Optional[Console] = None, *, historial: bool = False, **kwargs) -> int:
    """`daily`: la grabación con la sesión real. En una terminal, a pantalla completa y con el resumen al salir;
    con `historial` (`daily --historial`) o con la salida redirigida, las frases en el historial con el pie vivo.
    Devuelve el código de salida."""
    consola = consola or make_console()
    if historial or not consola.is_interactive:
        return PantallaEnVivo(consola=consola, **kwargs).run()
    return PantallaCompleta(consola=consola, **kwargs).run()


def grabar_en_menu(consola: Optional[Console] = None, **kwargs) -> Tuple[int, str]:
    """La grabación a pantalla completa abierta desde el menú: no imprime el resumen, lo devuelve como el aviso con
    que Inicio recibe de vuelta la terminal. Devuelve (código de salida, aviso)."""
    pantalla = PantallaCompleta(consola=consola or make_console(), imprimir_resumen=False, **kwargs)
    codigo = pantalla.run()
    return codigo, pantalla.aviso_fin()
