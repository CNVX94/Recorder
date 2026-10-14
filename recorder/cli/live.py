"""La grabación desde la terminal: `daily` sin más.

Lo mismo que la ventana, sobre la misma `RecorderSession`, pero en la propia consola y barato.
Una cabecera de dos líneas (la nota de hoy y la calidad, sin jerga) y, debajo, las frases, los
avisos (las fuentes resueltas al arrancar, el atraso de la transcripción) y las fuentes que
caen, vuelven o enmudecen como líneas normales, que se quedan en el historial de la terminal (se
pueden copiar y desplazar): la hora en tenue, una columna de icono (🔊 la salida, 🎤 el
micrófono, nada en los hechos de la sesión y los avisos, que llevan su propio símbolo) y el
texto. Al pie, dos líneas que se redibujan solo cuando cambian: la cabecera (`status_text`) con
los medidores (`meter_text`, con 🔇 en la fuente muda) y las teclas. En silencio no se escribe
nada y el proceso no gasta CPU. Las líneas se imprimen sin partir (`soft_wrap`): las parte la
terminal a su ancho real, así que cambiar el tamaño de la ventana no deja frases rotas.

Teclas: [p] pausar/continuar · [c] captura · [r] reconectar audio · [a] abrir la nota ·
[o] opciones · [q] salir (Ctrl+C también sale). Al salir con cola pendiente se pregunta en el
pie, como en la ventana: [e] esperar a que se transcriba · [s] salir perdiéndola · [c] cancelar.

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
import copy
import dataclasses
import msvcrt
import os
import signal
import time
from typing import Callable, Deque, List, Optional, Sequence, Tuple

from rich.cells import cell_len
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.text import Text

from ..actions.screenshot import screen_labels, window_titles
from ..audio.devices import wasapi_devices
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
    ACTION_DEVICES, ACTION_RECOMMEND, ACTION_SETTINGS,
    Event, Line, Notice, RecorderSession, SourceChanged, SourceMuted, Status, StatusSnapshot, with_action,
)
from .consola import make_console, presentar

INTERVALO = 0.2  # segundos entre sondeos, como la ventana (POLL_MS)
CTRL_C = "\x03"  # lo que el manejador de SIGINT mete en la cola de teclas
ESC, ENTER, RETROCESO = "\x1b", "\r", "\x08"  # como los devuelve msvcrt.getwch

# La barra de teclas cabe en 80 columnas (79 con «seguir» en pausa): un pie de dos líneas.
TECLAS = (("p", "pausar"), ("c", "captura"), ("r", "reconectar"), ("a", "nota"), ("o", "opciones"), ("q", "salir"))
TECLAS_PAUSA = (("p", "seguir"),) + TECLAS[1:]
TECLAS_CIERRE = (("e", "esperar"), ("s", "salir perdiéndolos"), ("c", "cancelar"))
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
MIC_APAGADO = "apagado: no se transcribe el micrófono"  # la primera opción de la sección del micrófono
AVISO_DISPOSITIVOS = "¿no aparece? si se conectó después de arrancar, sal con q y vuelve a entrar"
AVISO_SIN_PIE = "opciones: hacen falta una terminal y su pie; con la salida redirigida usa `daily config` al terminar"

Partes = List[Tuple[str, str]]  # trozos (texto, estilo) de una línea


def leer_tecla() -> Optional[str]:
    """La tecla pulsada si hay alguna esperando; None si no. No bloquea.

    Las teclas especiales (flechas, F1…) llegan como un prefijo \\x00 o \\xe0 y un segundo
    carácter: se consume y se ignoran.
    """
    if not msvcrt.kbhit():
        return None
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        msvcrt.getwch()
        return None
    return ch


def partes_teclas(ayudas: Sequence[Tuple[str, str]]) -> Partes:
    """(("p", "pausar"), …) → «[p] pausar · [c] captura…», con la tecla en acento."""
    partes: Partes = []
    for tecla, ayuda in ayudas:
        if partes:
            partes.append((" · ", "tenue"))
        partes += [(f"[{tecla}]", "acento"), (f" {ayuda}", "tenue")]
    return partes


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

    def clave(self) -> tuple:
        return (self.seccion, tuple(self.opciones), self.actual, self.tecleado)


class PantallaEnVivo:
    """El bucle de `daily`: sondea la sesión en este hilo, pinta y atiende las teclas."""

    def __init__(
        self,
        session: Optional[RecorderSession] = None,
        *,
        consola: Optional[Console] = None,
        leer_tecla: Callable[[], Optional[str]] = leer_tecla,
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
        self.ascii = getattr(self.consola, "ascii_mode", False)
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
        """La columna de icono, del mismo ancho para todas las líneas: 🔊 o 🎤 (OUT, MIC en ASCII)
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
        clave = (st.status_text, st.status_highlight, st.meter_text, teclas, self._panel and self._panel.clave())
        if clave == self._pie_pintado:
            return
        self._pie_pintado = clave
        self._live.update(self._pie(st, teclas), refresh=True)

    def _pie(self, st: StatusSnapshot, teclas: Sequence[Tuple[str, str]]) -> RenderableType:
        """El pie: cabecera y medidores en una línea; debajo las teclas, la pregunta de cierre o
        el panel de opciones."""
        lineas = [self._texto((st.status_text, "bold" if st.status_highlight else "tenue"), ("   ", ""), (st.meter_text, "tenue"))]
        if self._panel is not None:
            lineas += self._lineas_panel()
        elif self._preguntando:
            lineas.append(self._texto(*self._pregunta()))
        else:
            lineas.append(self._texto(*partes_teclas(teclas)))
        return Group(*lineas)

    # ------------------------------------------------------------------ panel de opciones
    def _ahora_configurado(self) -> str:
        """Lo configurado ahora, en una línea: para el índice del panel."""
        cfg = self.session.config
        mic = device_choice(cfg.mic_dev) if cfg.mic else "apagado"
        captura = f"ventana «{cfg.window}»" if cfg.window else (f"pantalla {cfg.screen}" if cfg.screen else "todas las pantallas")
        calidad = capture_choice(cfg.captures).split(":")[0].split(" (")[0].lower()
        return f"🔊 {device_choice(cfg.out_dev)} · 🎤 {mic} · 📸 {captura} · capturas {calidad}"

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
        """Aplica la opción elegida como ⚙ Opciones: el formulario de la configuración actual con
        ese campo cambiado, volcado sobre una copia, y la sesión guarda y reabre lo que toque."""
        p = self._panel
        etiqueta = p.opciones[indice]
        self._cerrar_panel()
        if indice == p.actual:
            return  # ya era esa
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
        titulo = next(t for _k, s, t in SECCIONES if s == p.seccion)
        self._aviso(f"⚙ {titulo}: {etiqueta}", "ok")

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
            elif k == "c":
                self._preguntando = False
            return True
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
        try:
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


def grabar(consola: Optional[Console] = None, **kwargs) -> int:
    """`daily`: la pantalla en vivo con la sesión real. Devuelve el código de salida."""
    return PantallaEnVivo(consola=consola, **kwargs).run()
