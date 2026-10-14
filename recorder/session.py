"""La sesión de grabación sin interfaz: lo que hace Recorder, lo pinte quien lo pinte.

Aquí vive todo lo que estaba en la ventana principal y no es Tkinter: construir el núcleo
(notas, PyAudio, colas, captura, transcriptor, buffer de capturas), la detección del equipo y la
recomendación del primer arranque, la pausa, la captura manual, lo que guardan Opciones y
Calibrar, el texto de la cabecera, la política de mantener el equipo despierto, el aviso de una
fuente muda y el cierre esperando (o no) a la cola. No importa tkinter ni abre diálogos: lo que
haya que preguntarle al usuario (cerrar con cola pendiente) lo decide la interfaz con los datos
que la sesión le da.

El modelo es de tirón (pull), igual para la ventana y para un frontal de terminal:

    session = RecorderSession(); session.start()
    cada ~200 ms, desde el hilo de la interfaz:
        for ev in session.poll(): pintar(ev)   # líneas, avisos, fuentes que caen, vuelven o enmudecen
        st = session.status                    # cabecera y medidores ya compuestos, y si toca cerrar
    al cerrar: session.request_close() dice si hay cola; la interfaz pregunta y llama a
        begin_drain() (esperar; `status.finished` avisa cuando se vació) o a shutdown().

`poll()` y las acciones se llaman siempre desde el mismo hilo: `keep_awake` es por hilo.
"""
import dataclasses
import datetime as dt
import pathlib
import queue
import threading
import time
from typing import Callable, Dict, List, Optional, Union
import pyaudiowpatch as pa

from .actions.capture_buffer import QUALITIES, CaptureBuffer, should_buffer
from .actions.notes import NotesSession, md_ref
from .actions.power import keep_awake, should_stay_awake
from .actions.screenshot import grab_image, take_screenshot
from .audio.capture import (
    MUTE_WARN_SEC, AudioCaptureManager, meter_label, mute_source, pending_audio_sec, pending_summary,
)
from .audio.devices import resolve_wasapi_device
from .config.hardware import HardwareProfile, cached_hardware, describe_hardware
from .config.manager import ConfigManager
from .config.schema import (
    ACTION_DEVICES,
    ACTION_RECOMMEND,
    ACTION_SETTINGS,
    DEFAULT_CAPTURES,
    AppConfig,
    Recommendation,
    apply_recommendation,
    describe_recommendation,
    recommend_config,
    startup_notices,
)
from .engine.whisper_worker import TranscriberWorker
from .engine.whispercpp import vulkan_readiness


# ---------------------------------------------------------------------------
# Eventos: lo que la interfaz pinta como líneas. Todos llevan su hora ya formateada.
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Status:
    """Texto crudo de cabecera que mandó el transcriptor ("Cargando modelo…", "● Escuchando", "⚠ …").

    Informativo: la cabecera se pinta desde `RecorderSession.status`, que ya lo tiene en cuenta.
    """

    text: str


@dataclasses.dataclass(frozen=True)
class Line:
    """Una línea del visor: una frase transcrita ("out" o "mic") o un hecho de la sesión ("info":
    pausa, captura manual, marcadores del transcriptor como el atraso), que el frontal pinta sin
    icono de fuente."""

    stamp: str
    kind: str  # "out", "mic" o "info"
    text: str
    hits: List[str]  # palabras clave que dispararon captura; vacío si no hubo


@dataclasses.dataclass(frozen=True)
class Notice:
    """Una línea con hora en el visor, informativa (config ilegible, primer arranque, las fuentes
    de audio resueltas, una captura manual fallida); lo que de ella merece quedar en la nota ya
    está escrito cuando llega. `action` (ACTION_*) dice qué puede hacer el usuario, y cada frontal
    lo añade con sus palabras; vacío si nada."""

    stamp: str
    text: str
    level: str  # "info" o "err"
    action: str = ""


@dataclasses.dataclass(frozen=True)
class SourceChanged:
    """Una fuente de audio cayó o volvió; `text` es la frase ya compuesta (también va a la nota)."""

    stamp: str
    kind: str  # "out" o "mic"
    up: bool
    detail: str
    text: str


@dataclasses.dataclass(frozen=True)
class SourceMuted:
    """Una fuente lleva MUTE_WARN_SEC sin audio mientras la otra sí (`muted`: silenciada, o es otro
    el dispositivo), o vuelve a tenerlo; `text` es la frase ya compuesta (también va a la nota) y
    `action` es ACTION_DEVICES mientras está muda (el frontal dice cómo elegir otro dispositivo).
    Una vez por episodio. Ver `audio.capture.mute_source` y `mute_text`."""

    stamp: str
    kind: str  # "out" o "mic"
    muted: bool
    text: str
    action: str = ""


@dataclasses.dataclass(frozen=True)
class HardwareReady:
    """El equipo ya está detectado; `applied` si era el primer arranque y se aplicó la recomendación."""

    profile: HardwareProfile
    recommendation: Recommendation
    applied: bool


Event = Union[Status, Line, Notice, SourceChanged, SourceMuted, HardwareReady]


# ---------------------------------------------------------------------------
# Cabecera: política pura, probada en tests/test_session.py
# ---------------------------------------------------------------------------

LIVE_STATUS = "●⏸⏳"  # cabeceras que se recomponen en cada sondeo; el resto se deja tal cual
SOURCE_NAMES = {"out": "salida 🔊", "mic": "micrófono 🎤"}
SOURCE_ARTICLES = {"out": "la", "mic": "el"}


def compose_status(
    base: str,
    *,
    draining: bool,
    paused: bool,
    pending: int,
    busy: bool,
    errors: int,
    awake: bool,
    mic: bool,
    pending_summary: str,
) -> str:
    """Texto de la cabecera a partir del estado.

    Un texto del transcriptor que no empieza por ●/⏸/⏳ ("Cargando modelo…", "⚠ …", "⛔ …") se
    muestra tal cual hasta que llegue otro: es un aviso y no hay que taparlo con el estado.
    """
    if not base or base[0] not in LIVE_STATUS:
        return base
    if draining:
        return f"⏳ Terminando {pending_summary}…"
    aviso = f" · ⚠ {errors} con fallo" if errors else ""
    cafe = " · ☕" if awake else ""
    if paused:
        # La pausa solo deja de capturar audio nuevo; la cola pendiente se sigue
        # transcribiendo. Se muestra el avance para que eso se vea y no parezca parado.
        resto = f" · transcribiendo {pending_summary}" if (pending or busy) else " · sin pendientes"
        return f"⏸ En pausa{resto}{aviso}{cafe}"
    mic_tag = " + 🎤" if mic else ""
    return f"● Escuchando{mic_tag} · pendientes: {pending}{aviso}{cafe}"


def with_action(text: str, action_text: str) -> str:
    """El aviso seguido de la frase de acción del frontal («Se cambia en ⚙ Opciones.», «pulsa
    [o]…»), como una oración más: con punto entre medias si el aviso no cierra con uno."""
    if not action_text:
        return text
    separador = " " if text.rstrip().endswith((".", "!", "?", "…")) else ". "
    return f"{text}{separador}{action_text}"


def mute_text(kind: str, muted: bool) -> str:
    """La frase del aviso de fuente sin audio: política pura, la misma para la nota, la ventana y
    la terminal, y completa por sí sola (en el visor la hora va delante; en la nota, detrás con
    su conector, ver `_check_mute`). Neutra: estar callado o silenciado es normal; lo que se
    señala es que, si se habló, puede ser otro el dispositivo, y eso lo dice el frontal con
    `SourceMuted.action`."""
    if muted:
        other = "mic" if kind == "out" else "out"
        return (
            f"⚠ sin audio de {SOURCE_NAMES[kind]} desde hace {MUTE_WARN_SEC // 60} min (¿silenciado?; "
            f"{SOURCE_ARTICLES[other]} {SOURCE_NAMES[other]} sí suena)"
        )
    return f"✔ vuelve a haber audio de {SOURCE_NAMES[kind]}"


@dataclasses.dataclass(frozen=True)
class StatusSnapshot:
    """Lo que la interfaz pinta en cada sondeo; `status_text` y `meter_text` ya vienen compuestos
    para que la ventana y la terminal muestren exactamente lo mismo."""

    base_status: str  # último texto crudo de la cabecera (del transcriptor o de la sesión)
    status_highlight: bool  # cabecera destacada (escuchando, terminando) o apagada (cargando, avisos)
    pending: int
    pending_summary: str  # "3 fragmentos (~45 s de audio)"
    busy: bool  # el transcriptor está con un fragmento ya sacado de la cola
    paused: bool
    draining: bool  # se pidió cerrar y se espera a vaciar la cola
    finished: bool  # se esperó y la cola ya está vacía: la interfaz debe cerrarse
    awake: bool  # se le está pidiendo a Windows que no suspenda
    errors: int  # fragmentos perdidos y capturas fallidas
    mic: bool
    levels: Dict[str, float]
    attempts: Dict[str, int]
    muted: Optional[str]  # "out" o "mic" si esa fuente lleva MUTE_WARN_SEC sin fragmentos (🔇); None si no
    file_path: pathlib.Path  # la nota de hoy

    @property
    def status_text(self) -> str:
        return compose_status(
            self.base_status,
            draining=self.draining,
            paused=self.paused,
            pending=self.pending,
            busy=self.busy,
            errors=self.errors,
            awake=self.awake,
            mic=self.mic,
            pending_summary=self.pending_summary,
        )

    @property
    def meter_text(self) -> str:
        return meter_label(self.levels, self.attempts, self.muted)


def _now() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Sesión
# ---------------------------------------------------------------------------

class RecorderSession:
    """Núcleo, estado y acciones de una sesión de Recorder, sin interfaz.

    Las fábricas existen para las pruebas: una sesión completa con audio, transcriptor y buffer
    de capturas de mentira, sin PortAudio, Whisper ni pantalla. En la aplicación se usan las reales.
    """

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        *,
        pa_factory: Callable[[], object] = pa.PyAudio,
        audio_manager_factory: Callable[..., AudioCaptureManager] = AudioCaptureManager,
        transcriber_factory: Callable[..., TranscriberWorker] = TranscriberWorker,
        hardware_detector: Callable[[], HardwareProfile] = cached_hardware,
        buffer_factory: Callable[..., CaptureBuffer] = CaptureBuffer,
    ):
        self.config_manager = config_manager or ConfigManager()
        self.config: AppConfig = self.config_manager.load()

        self.notes_session = NotesSession(self.config.notes_dir)
        self.pa = pa_factory()

        self.chunk_queue: queue.Queue = queue.Queue()
        self.ui_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()

        # Componentes del núcleo
        self.audio_manager = audio_manager_factory(
            pa_instance=self.pa,
            chunk_queue=self.chunk_queue,
            source_callback=lambda kind, up, detail: self.ui_queue.put(("source", kind, up, detail)),
            out_dev=self.config.out_dev,
            mic_dev=self.config.mic_dev,
            mic_enabled=self.config.mic,
        )

        self.transcriber = transcriber_factory(
            config=self.config,
            chunk_queue=self.chunk_queue,
            ui_queue=self.ui_queue,
            notes_session=self.notes_session,
            stop_event=self.stop_event,
        )
        self._detect = hardware_detector
        self._buffer_factory = buffer_factory

        self.awake = False     # True mientras se le pide a Windows que no suspenda por inactividad
        self.draining = False  # True cuando se pidió cerrar pero se espera a vaciar la cola
        self.finished = False  # True cuando, esperando, la cola ya se vació: toca cerrar
        self.muted: Optional[str] = None  # fuente que lleva MUTE_WARN_SEC sin fragmentos (ya avisada)
        self._resumed_at = 0.0  # última vuelta de una pausa: lo callado durante la pausa no cuenta como mudo
        # Buffer circular de capturas (actions/capture_buffer.py): un hilo propio que guarda un
        # fotograma cada 5 s mientras hay reunión (desde el primer fragmento de audio); el
        # transcriptor toma de él la imagen de la hora en que se dijo la palabra clave. None con
        # `captures: off`.
        self.buffer: Optional[CaptureBuffer] = None
        self._buffer_key = None  # (caps_dir, captures) con que se arrancó: si Opciones lo cambia, se rearranca
        # El hardware se detecta en otro hilo (~1 s) para no congelar la interfaz; el resultado
        # llega por ui_queue ("hardware") y queda en caché para Opciones y el transcriptor.
        self.hardware: Optional[HardwareProfile] = None
        self.transcribe_thread: Optional[threading.Thread] = None
        # Primer arranque: falta aplicar la recomendación (salvo que antes se guarde Opciones).
        self.recommend_pending = getattr(self.config_manager, "first_run", False)

        self._base_status = "Iniciando…"  # último texto crudo de la cabecera
        self._status_highlight = False
        self._events: List[Event] = []  # lo que devolverá el próximo poll(); solo lo toca el hilo de la interfaz
        self._capturing = False  # True mientras un hilo captura la pantalla; otro clic mientras tanto se ignora
        self.capture_errors = 0  # capturas manuales fallidas; suman en la cabecera con las del transcriptor

    # ------------------------------------------------------------------ arranque
    def start(self) -> None:
        """Arranca el buffer de capturas, la captura de audio y la detección del equipo; el
        transcriptor, ya o tras detectar."""
        self._avisar_config_ilegible()
        self._anotar_fuentes()  # antes de abrir los flujos: solo enumera dispositivos
        self._start_buffer()
        self.audio_manager.start()
        threading.Thread(target=self._detect_hardware, daemon=True).start()
        if self.recommend_pending:
            # Sin config.json, los valores de fábrica (Media, 4 hilos) no dependen del equipo:
            # se espera a la detección para cargar ya el modelo recomendado (ver _on_hardware).
            self._base_status = "Detectando el equipo…"
        else:
            self._start_transcriber()

    def _start_transcriber(self):
        self.transcribe_thread = threading.Thread(target=self.transcriber.run, daemon=True)
        self.transcribe_thread.start()

    def _detect_hardware(self):
        try:
            profile = self._detect()
        except Exception as e:  # detect_hardware no lanza; esto evita un primer arranque colgado si algo cambia
            profile = HardwareProfile(detection_errors=[repr(e)])
        self.ui_queue.put(("hardware", profile))

    def _on_hardware(self, profile: HardwareProfile):
        """Primer arranque: aplica la recomendación y arranca el transcriptor. Si no, avisos."""
        self.hardware = profile
        rec = recommend_config(profile, *vulkan_readiness(self.config.whispercpp_dir))
        aplicar = self.transcribe_thread is None and self.recommend_pending
        self._events.append(HardwareReady(profile, rec, aplicar))
        if self.transcribe_thread is None:
            if aplicar:
                self.recommend_pending = False
                apply_recommendation(self.config, rec)  # el mismo objeto que usa el transcriptor
                guardado = ""
                try:
                    self.config_manager.save(self.config)
                except OSError as e:
                    guardado = f" (no se pudo guardar {self.config_manager.path.name}: {e})"
                self._events.append(Notice(
                    _now(),
                    f"🖥 Primer arranque en este equipo: {describe_hardware(profile)}. Se aplicó la "
                    f"configuración recomendada, {describe_recommendation(rec)}: {rec.reason}{guardado}",
                    "info",
                    ACTION_SETTINGS,
                ))
            self._start_transcriber()  # también si se está cerrando: es quien vacía la cola
            return
        for aviso, accion in startup_notices(self.config, profile, rec):
            self._events.append(Notice(_now(), aviso, "err" if aviso.startswith("⚠") else "info", accion))

    def _avisar_config_ilegible(self):
        """Si la configuración no se pudo leer, decirlo en vez de arrancar como si nada.

        Va al visor y a la nota, no a la cabecera: la cabecera la reescribe el hilo de
        transcripción en cuanto carga el modelo y el aviso se perdería de vista.
        """
        motivo = getattr(self.config_manager, "last_error", "")
        if not motivo:
            return
        stamp = _now()
        self._events.append(Notice(stamp, f"⚠ {motivo}", "err"))
        try:
            self.notes_session.write_line(f"> ⚠ {stamp} {motivo}")
        except Exception:  # ponytail: si ni la nota se puede escribir, el visor ya avisó
            pass

    def _anotar_fuentes(self, cambio: bool = False):
        """Deja en la nota y en el visor qué dispositivo resolvió cada fuente: sin esto, un
        micrófono equivocado no se ve en la nota (una daily entera sin 🎤 y nada que dijera por qué).

        Con `cambio` (Opciones reabrió el audio con otros dispositivos) la línea de la nota lleva la
        hora, como la pausa: la nota dice desde cuándo se oye por el otro dispositivo.
        """
        partes = []
        for icon, kind, pref in (("🔊", "out", self.config.out_dev), ("🎤", "mic", self.config.mic_dev)):
            if kind == "mic" and not self.config.mic:
                partes.append(f"{icon} desactivado")
                continue
            try:
                partes.append(f"{icon} {resolve_wasapi_device(self.pa, kind, pref)['name']}")
            except Exception:
                partes.append(f"{icon} no encontrado: {pref or 'predeterminado'}")
        texto = f"{'⚙ ' if cambio else ''}Fuentes: {' · '.join(partes)}"
        stamp = _now()
        self._events.append(Notice(stamp, texto, "info"))
        try:
            self.notes_session.write_line(f"\n> {texto} {stamp}\n" if cambio else f"> {texto}\n")
        except Exception:  # ponytail: es informativo; si la nota no se puede escribir ya se verá luego
            pass

    # ------------------------------------------------------------------ buffer de capturas
    def _last_audio_chunk(self) -> float:
        """El último fragmento encolado por cualquier fuente (0 si aún ninguno).

        Fragmentos y no nivel: el ruido de un jack sin micrófono pasa el umbral en frames sueltos
        y, con el nivel, el equipo nunca se soltaba ni el buffer dejaba de capturar. Continuar
        tras una pausa tampoco cuenta: la ventana de 15 min se mide desde audio real.
        """
        return max(self.audio_manager.last_chunk_at.values(), default=0.0)

    def _last_meeting_audio(self) -> float:
        """Para retener el equipo despierto: el arranque o el último fragmento, lo más reciente.
        Recién abierto, Recorder se queda despierto 15 min aunque la reunión aún no empiece."""
        return max(self.audio_manager.started_at, self._last_audio_chunk())

    def _buffer_active(self) -> bool:
        """Lo que el hilo del buffer pregunta antes de cada fotograma: si hay reunión. Hasta el
        primer fragmento de audio no la hay, y la pantalla no se guarda."""
        return should_buffer(time.time(), self._last_audio_chunk(), self.audio_manager.paused)

    def _buffer_failed(self, e: Exception) -> None:
        """El primer fallo del buffer (la unidad de la carpeta de capturas no está, la pantalla no se
        deja leer…), desde su hilo: a la nota y, por `ui_queue`, al visor. Los siguientes solo cuentan."""
        stamp = _now()
        texto = (
            f"⚠ el buffer de capturas falló ({e!r}): las capturas por palabra clave se tomarán al "
            f"transcribir, tardías si hay cola"
        )
        try:
            self.notes_session.write_line(f"\n> {texto} {stamp}\n")
        except Exception:  # ponytail: si la nota tampoco se puede escribir, el visor avisa igual
            pass
        self.ui_queue.put(("notice", stamp, texto, "err"))

    def _start_buffer(self):
        """(Re)arranca el buffer de capturas con la calidad y carpeta de la configuración actual.
        Una calidad desconocida vale como la de fábrica, no como apagado."""
        if self.buffer is not None:
            self.buffer.stop()  # para y vacía
        self.buffer = None
        quality = self.config.captures
        if quality != "off" and quality not in QUALITIES:
            quality = DEFAULT_CAPTURES
        if quality != "off":
            self.buffer = self._buffer_factory(
                self.config.caps_dir,
                quality,
                grab=lambda: grab_image(self.config.screen, self.config.window),
                active=self._buffer_active,
                on_error=self._buffer_failed,
            )
            self.buffer.start()
        self._buffer_key = (self.config.caps_dir, self.config.captures)
        self.transcriber.buffer = self.buffer

    # ------------------------------------------------------------------ estado
    @property
    def paused(self) -> bool:
        return self.audio_manager.paused

    @property
    def file_path(self) -> pathlib.Path:
        return self.notes_session.file_path

    def _pending_summary(self) -> str:
        with self.chunk_queue.mutex:  # queue.Queue documenta mutex y queue para esto
            chunks = list(self.chunk_queue.queue)
        return pending_summary(len(chunks), pending_audio_sec(chunks))

    @property
    def status(self) -> StatusSnapshot:
        """Foto del estado para pintar la cabecera y los medidores."""
        return StatusSnapshot(
            base_status=self._base_status,
            status_highlight=self._status_highlight,
            pending=self.chunk_queue.qsize(),
            pending_summary=self._pending_summary(),
            busy=self.transcriber.busy,
            paused=self.paused,
            draining=self.draining,
            finished=self.finished,
            awake=self.awake,
            errors=getattr(self.transcriber, "errors", 0) + self.capture_errors,
            mic=self.config.mic,
            levels=dict(self.audio_manager.levels),
            attempts=dict(self.audio_manager.attempts),
            muted=self.muted,
            file_path=self.file_path,
        )

    def poll(self) -> List[Event]:
        """Un sondeo: traduce lo que llegó de los hilos, mira si una fuente enmudeció, decide si
        retener el equipo despierto y si ya se puede cerrar. Devuelve los eventos para pintar; la
        cabecera se lee de `status`."""
        while not self.ui_queue.empty():
            m = self.ui_queue.get()
            if m[0] == "status":
                self._base_status = m[1]
                self._status_highlight = m[1].startswith("●")
                self._events.append(Status(m[1]))
            elif m[0] == "line":
                self._events.append(Line(*m[1:]))
            elif m[0] == "notice":
                self._events.append(Notice(*m[1:]))
            elif m[0] == "source":
                self._events.append(self._note_source(*m[1:]))
            elif m[0] == "hardware":
                self._on_hardware(m[1])

        self._check_mute()

        pending = self.chunk_queue.qsize()
        busy = self.transcriber.busy

        awake = should_stay_awake(time.time(), self._last_meeting_audio(), pending, busy, self.paused)
        if awake != self.awake:
            keep_awake(awake)
            self.awake = awake

        if self.draining and pending == 0 and not busy:
            self.finished = True

        events, self._events = self._events, []
        return events

    def _check_mute(self):
        """Una fuente que lleva MUTE_WARN_SEC sin audio mientras la otra sí (un micrófono que no es
        el que usa Teams, un jack sin micrófono, o simplemente silenciado) no da error: se detecta
        aquí y se avisa una vez por episodio, en la nota y en el visor; al volver a haber audio,
        otra vez. En pausa, terminando o con la fuente caída (eso ya lo avisa
        `_note_source`) no cuenta, y el plazo se mide desde el arranque de la captura o desde la
        última vuelta de una pausa. Si el micrófono se desactiva en Opciones con el aviso puesto,
        el aviso se retira sin anunciar una vuelta que no hubo."""
        am = self.audio_manager
        if self.muted == "mic" and not am.mic_enabled:
            self.muted = None
        since = max(am.started_at, self._resumed_at)
        muted = None if (am.paused or self.draining) else mute_source(time.time(), am.last_chunk_at, since, am.mic_enabled)
        if muted and am.attempts.get(muted):
            muted = None  # caída, no muda
        if muted == self.muted:
            return
        kind = muted or self.muted
        texto = mute_text(kind, bool(muted))
        stamp = _now()
        # En la nota la hora va detrás con su conector («… sí suena). Detectado a las 09:58:27», «… desde 10:00:41»)
        self.notes_session.write_line(f"\n> {texto}{'. Detectado a las' if muted else ' desde'} {stamp}\n")
        self._events.append(SourceMuted(stamp, kind, bool(muted), texto, ACTION_DEVICES if muted else ""))
        self.muted = muted

    # ------------------------------------------------------------------ acciones
    def manual_screenshot(self) -> bool:
        """Captura la pantalla en un hilo; la línea del visor llega después por `poll()`.

        Capturar y guardar el PNG tarda (cientos de ms con varios monitores) y hacerlo aquí
        congelaría la ventana. Es una captura instantánea, al margen del buffer: la manual retrata
        lo que hay ahora y a tamaño completo. Devuelve False si ya hay una captura en curso: ese
        clic se ignora.
        """
        if self._capturing:
            return False
        self._capturing = True
        cfg = self.config  # se lee en este hilo: Opciones puede cambiarlo mientras el otro captura
        threading.Thread(
            target=self._capture, args=(_now(), cfg.caps_dir, cfg.screen, cfg.window), daemon=True
        ).start()
        return True

    def _capture(self, stamp: str, caps_dir: str, screen: int, window: str) -> None:
        """En su hilo: captura, deja constancia en la nota y avisa por ui_queue. Un fallo se ve en
        el visor como las capturas automáticas fallidas y no revienta nada."""
        try:
            f = take_screenshot("manual", caps_dir, screen, window)
            ref = md_ref(f, self.notes_session.file_path.parent)
            self.notes_session.write_line(f"- **{stamp}** 📸 captura manual → ![]({ref})")
            msg = ("line", stamp, "info", "(captura manual)", ["manual"])
        except Exception as e:
            self.capture_errors += 1
            msg = ("notice", stamp, f"⚠ captura manual fallida: {e!r}", "err")
            try:  # ponytail: si lo que falla es escribir la nota, el aviso tampoco cabe; el visor ya avisa
                self.notes_session.write_line(f"- **{stamp}** ⚠ captura manual fallida: {e!r}")
            except Exception:
                pass
        self._capturing = False  # antes de avisar: cuando la línea llega ya se puede volver a capturar
        self.ui_queue.put(msg)

    def _mensaje_pausa(self) -> str:
        """Texto de la pausa, explicando que lo pendiente se sigue transcribiendo."""
        pendiente = self._pending_summary() if self.chunk_queue.qsize() else ""
        cola = f"; siguen {pendiente} por transcribir" if pendiente else ""
        return f"⏸ pausa: no se captura audio nuevo{cola}"

    def toggle_pause(self) -> Line:
        """Pausa o continúa; deja constancia en la nota y devuelve la línea para el visor."""
        self.audio_manager.paused = not self.audio_manager.paused
        is_paused = self.audio_manager.paused
        if not is_paused:
            # Lo callado durante la pausa no cuenta como mudo; el reloj de la reunión (buffer, ☕) no
            # se toca: ese cuenta desde el último audio real.
            self._resumed_at = time.time()
        stamp = _now()
        state_msg = "⏸ Pausa" if is_paused else "▶ Continúa"
        self.notes_session.write_line(f"\n> {state_msg} {stamp}\n")
        return Line(
            stamp,
            "info",
            self._mensaje_pausa() if is_paused else "▶ continúa, se vuelve a capturar audio",
            [],
        )

    def _note_source(self, kind: str, up: bool, detail: str) -> SourceChanged:
        """Deja constancia en la nota de que una fuente cayó o volvió, como con la pausa."""
        stamp = _now()
        name = "salida" if kind == "out" else "micrófono"
        msg = f"✔ audio de {name} recuperado" if up else f"⚠ audio de {name} caído, reintentando: {detail}"
        self.notes_session.write_line(f"\n> {msg} {stamp}\n")
        return SourceChanged(stamp, kind, up, detail, msg)

    def reconnect_audio(self) -> None:
        """Reabre las dos fuentes con los dispositivos configurados (clic en los medidores).

        Es el plan B para un flujo que tras despertar se queda mudo sin dar error (ahí el
        reintento automático no salta porque no hay excepción que lo dispare).
        """
        if self.draining:
            return
        self.audio_manager.restart(self.config.out_dev, self.config.mic_dev, self.config.mic)

    def apply_settings(self, new_config: AppConfig, notes_changed: bool, devices_changed: bool) -> None:
        """Lo que guarda ⚙ Opciones (o el panel [o] de la terminal, en plena grabación): mueve la
        nota (sus enlaces a capturas se reescriben), guarda, recarga filtros, rearranca el buffer
        si cambió su carpeta o calidad y reabre el audio si cambiaron los dispositivos, dejando en
        la nota y el visor qué dispositivo resolvió cada fuente. Si config.json no se deja escribir,
        lo cambiado vale igual para esta sesión y se avisa: la grabación no se para por eso."""
        if notes_changed:
            self.notes_session.move_notes(new_config.notes_dir)

        self.config = new_config
        try:
            self.config_manager.save(self.config)
        except OSError as e:
            self._events.append(Notice(
                _now(), f"⚠ no se pudo guardar {self.config_manager.path.name}: {e}; lo cambiado vale solo para esta sesión", "err",
            ))
        self.transcriber.update_pipeline(self.config)
        self.recommend_pending = False  # lo elegido en Opciones manda sobre la recomendación
        if (self.config.caps_dir, self.config.captures) != self._buffer_key:
            self._start_buffer()

        if devices_changed:
            self._base_status = "● Escuchando"
            self._anotar_fuentes(cambio=True)  # antes de reabrir: solo enumera dispositivos
            self.audio_manager.restart(
                out_dev=self.config.out_dev,
                mic_dev=self.config.mic_dev,
                mic_enabled=self.config.mic,
            )

    def apply_tuning(self, new_config: AppConfig) -> None:
        """Lo que guarda 🎯 Calibrar: filtros y umbrales en caliente, sin recargar el modelo."""
        self.config = new_config
        self.config_manager.save(self.config)
        self.transcriber.update_pipeline(self.config)

    # ------------------------------------------------------------------ cierre
    def request_close(self) -> Optional[str]:
        """Al cerrar: el resumen de lo que queda sin transcribir, para preguntar si esperar; None si nada."""
        if self.chunk_queue.qsize():
            return self._pending_summary()
        return None

    def begin_drain(self) -> None:
        """Se eligió esperar: no entran fragmentos nuevos y la cola solo baja; `status.finished` avisa."""
        self.draining = True
        self.audio_manager.stop()
        self._base_status = f"⏳ Terminando {self._pending_summary()}…"
        self._status_highlight = True

    def shutdown(self) -> None:
        """Para la captura, el transcriptor y el buffer, y suelta el equipo. La interfaz se cierra después."""
        self.audio_manager.stop()
        self.stop_event.set()
        keep_awake(False)
        if self.buffer is not None:  # la cola ya se vació o se abandonó: nada de la pantalla queda en disco
            self.buffer.stop()  # para y vacía
            self.buffer = None
        # ponytail: a propósito no se llama a pa.terminate(). Cierra cada stream desde este hilo
        # mientras el del loopback sigue bloqueado en read() (bloquea hasta que suena algo) y eso
        # revienta el proceso con 0xC0000005 (pasaba en cada cierre, invisible porque la ventana
        # desaparece igual). El proceso termina justo después y Windows recoge los recursos.
