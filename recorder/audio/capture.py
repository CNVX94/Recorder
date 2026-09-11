import queue
import threading
import time
from typing import Callable, Dict, Iterable, Tuple
import numpy as np
import pyaudiowpatch as pa

from .devices import resolve_wasapi_device
from .processing import bars, rms, to_16k

FRAMES_PER_BUFFER = 1024
DEFAULT_MIN_SEC = 8.0
DEFAULT_MAX_SEC = 20.0
DEFAULT_PAUSE_SEC = 0.6
DEFAULT_SILENCE_RMS = 150.0
RETRY_MAX_SEC = 30.0
FLUSH_MIN_SEC = 1.0  # al morir un flujo, lo que hubiera a medias se salva si dura al menos esto
WHISPER_RATE = 16000  # los fragmentos de la cola ya están a 16 kHz (ver to_16k)


# ---------------------------------------------------------------------------
# Políticas puras (sin audio ni interfaz), probadas en tests/test_audio_recovery.py
# ---------------------------------------------------------------------------

def retry_delay(attempt: int) -> float:
    """Espera antes del reintento n: 1, 2, 4, 8, 16, 30, 30… segundos.

    Crece para no girar en vacío mientras los auriculares siguen desconectados o el equipo
    acaba de despertar, y se acota para que reconectar no tarde más de medio minuto en notarse.
    """
    return min(RETRY_MAX_SEC, 2.0 ** (attempt - 1))


def meter_label(levels: Dict[str, float], attempts: Dict[str, int]) -> str:
    """Texto de los medidores de la cabecera: barras si la fuente está viva, aviso si está caída."""
    parts = []
    for icon, kind in (("🔊", "out"), ("🎤", "mic")):
        n = attempts.get(kind, 0)
        parts.append(f"{icon} {bars(levels.get(kind, 0.0))}" if n == 0 else f"{icon} ⛔ reintento {n}")
    return "   ".join(parts)


def pending_audio_sec(chunks: Iterable[Tuple[float, str, np.ndarray]]) -> float:
    """Segundos de audio que suman los fragmentos aún sin transcribir."""
    return sum(len(audio) / WHISPER_RATE for _, _, audio in chunks)


def pending_summary(pending: int, secs: float) -> str:
    """'212 fragmentos (~48 min de audio)', para la cabecera y el aviso al cerrar."""
    dur = f"{secs / 60:.0f} min" if secs >= 60 else f"{secs:.0f} s"
    return f"{pending} fragmento{'' if pending == 1 else 's'} (~{dur} de audio)"


# ---------------------------------------------------------------------------
# Captura
# ---------------------------------------------------------------------------

class AudioStreamSession:
    def __init__(
        self,
        pa_instance: pa.PyAudio,
        kind: str,
        preferred_device: str,
        frames: int = FRAMES_PER_BUFFER,
    ):
        self.dev = resolve_wasapi_device(pa_instance, kind, preferred_device)
        self.rate = int(self.dev["defaultSampleRate"])
        self.channels = int(self.dev["maxInputChannels"])
        self.stream = pa_instance.open(
            format=pa.paInt16,
            channels=self.channels,
            rate=self.rate,
            input=True,
            input_device_index=self.dev["index"],
            frames_per_buffer=frames,
        )


def _read_loop(
    kind: str,
    stream,
    rate: int,
    channels: int,
    chunk_queue: queue.Queue,
    level_callback: Callable[[str, float], None],
    alive_callback: Callable[[], None],
    is_paused: Callable[[], bool],
    is_mic_enabled: Callable[[], bool],
    stop_event: threading.Event,
    min_sec: float = DEFAULT_MIN_SEC,
    max_sec: float = DEFAULT_MAX_SEC,
    pause_sec: float = DEFAULT_PAUSE_SEC,
    silence_threshold: float = DEFAULT_SILENCE_RMS,
):
    """Lee y segmenta hasta que stop_event se active. Si el flujo muere, la excepción sube.

    alive_callback() se llama tras la primera lectura que funciona: es la prueba de que la
    fuente está viva de verdad (abrir puede ir bien y leer fallar igualmente).
    """
    tail = max(1, int(pause_sec * rate / FRAMES_PER_BUFFER))
    buf = []
    t0 = None
    alive = False

    def flush(min_len_sec: float = 0.0):
        nonlocal buf, t0
        if buf and t0 is not None and len(buf) * FRAMES_PER_BUFFER / rate >= min_len_sec:
            pcm = np.concatenate(buf)
            if rms(pcm) > silence_threshold:
                chunk_queue.put((t0, kind, to_16k(pcm, rate, channels)))
        buf = []
        t0 = None

    try:
        while not stop_event.is_set():
            raw = np.frombuffer(
                stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False),
                dtype=np.int16,
            )
            if not alive:
                alive = True
                alive_callback()
            current_rms = rms(raw)
            level_callback(kind, current_rms)

            if is_paused() or (kind == "mic" and not is_mic_enabled()):
                buf = []
                t0 = None
                continue

            if t0 is None and current_rms > silence_threshold:
                t0 = time.time()

            buf.append(raw)
            secs = len(buf) * FRAMES_PER_BUFFER / rate

            if (secs >= min_sec and rms(np.concatenate(buf[-tail:])) < silence_threshold) or secs >= max_sec:
                flush()
    finally:
        # Lo que hubiera a medias cuando el flujo muere (o se para) no se tira: se encola y se
        # transcribe como un fragmento más. Así desconectar los auriculares a mitad de frase
        # cuesta como mucho la frase siguiente, no la que ya estaba grabada.
        flush(FLUSH_MIN_SEC)


def capture_thread(
    kind: str,
    open_stream: Callable[[], Tuple[object, int, int]],
    chunk_queue: queue.Queue,
    level_callback: Callable[[str, float], None],
    state_callback: Callable[[str, int, str], None],
    is_paused: Callable[[], bool],
    is_mic_enabled: Callable[[], bool],
    stop_event: threading.Event,
    retry_delay: Callable[[int], float] = retry_delay,
    **segment_kwargs,
):
    """Mantiene viva una fuente: abre el flujo, lee hasta que muere y lo reabre con espera creciente.

    open_stream() devuelve (stream, rate, channels) y se llama de nuevo en cada reintento, de modo
    que el dispositivo se vuelve a resolver por si cambió (auriculares desconectados, suspensión).
    state_callback(kind, intento, detalle): intento 0 = la fuente lee bien; n > 0 = caída, en el
    reintento n. Solo se sale de aquí cuando stop_event se activa; una fuente nunca muere sola.
    """
    attempt = 0

    def alive():
        nonlocal attempt
        attempt = 0
        state_callback(kind, 0, "")

    while not stop_event.is_set():
        if attempt:
            stop_event.wait(retry_delay(attempt))
            if stop_event.is_set():
                break
        try:
            stream, rate, channels = open_stream()
        except Exception as e:
            attempt += 1
            state_callback(kind, attempt, repr(e))
            continue
        try:
            _read_loop(
                kind, stream, rate, channels, chunk_queue, level_callback, alive,
                is_paused, is_mic_enabled, stop_event, **segment_kwargs,
            )
        except Exception as e:
            attempt += 1
            state_callback(kind, attempt, repr(e))
        finally:
            level_callback(kind, 0.0)
            try:
                stream.close()
            except Exception:
                pass


class AudioCaptureManager:
    """Gestiona la captura concurrente de audio (salida loopback y micrófono).

    Cada fuente vive en su propio hilo y se recupera sola si su dispositivo falla; la otra sigue
    funcionando mientras tanto. `attempts` dice si una fuente está caída (0 = viva, n = reintento n)
    y `source_callback(kind, up, detalle)` avisa cuando cae o vuelve.
    """

    def __init__(
        self,
        pa_instance: pa.PyAudio,
        chunk_queue: queue.Queue,
        source_callback: Callable[[str, bool, str], None],
        out_dev: str = "",
        mic_dev: str = "",
        mic_enabled: bool = True,
    ):
        self.pa = pa_instance
        self.chunk_queue = chunk_queue
        self.source_callback = source_callback
        self.out_dev = out_dev
        self.mic_dev = mic_dev
        self.mic_enabled = mic_enabled
        self.paused = False
        self.levels: Dict[str, float] = {"out": 0.0, "mic": 0.0}
        self.attempts: Dict[str, int] = {"out": 0, "mic": 0}
        self.last_audio_at = time.time()  # última vez que alguna fuente oyó algo por encima del umbral
        self.retry_delay = retry_delay  # las pruebas lo sustituyen para no esperar de verdad
        self.open_lock = threading.Lock()  # PortAudio no soporta abrir flujos desde dos hilos a la vez
        self.stop_event = threading.Event()
        self._threads = []

    def _update_level(self, kind: str, level: float):
        self.levels[kind] = level
        if level > DEFAULT_SILENCE_RMS:
            self.last_audio_at = time.time()

    def _on_state(self, kind: str, attempt: int, detail: str):
        before = self.attempts.get(kind, 0)
        self.attempts[kind] = attempt
        if attempt and not before:
            self.source_callback(kind, False, detail)
        elif before and not attempt:
            self.source_callback(kind, True, "")

    def _open(self, kind: str):
        """Resuelve el dispositivo (de nuevo en cada llamada) y abre el flujo, en serie."""
        with self.open_lock:
            preferred = self.out_dev if kind == "out" else self.mic_dev
            s = AudioStreamSession(self.pa, kind, preferred)
            return s.stream, s.rate, s.channels

    def start(self):
        """Arranca un hilo de captura por fuente; cada hilo abre (y reabre) su propio flujo."""
        # Evento nuevo por arranque: antes se reutilizaba y clear() resucitaba a los hilos del
        # arranque anterior, que seguían leyendo el dispositivo viejo tras cambiarlo en Opciones.
        self.stop_event = threading.Event()
        self._threads = []
        for kind in ("out", "mic"):
            t = threading.Thread(
                target=capture_thread,
                name=f"capture-{kind}",
                args=(
                    kind,
                    lambda k=kind: self._open(k),
                    self.chunk_queue,
                    self._update_level,
                    self._on_state,
                    lambda: self.paused,
                    lambda: self.mic_enabled,
                    self.stop_event,
                    self.retry_delay,
                ),
                daemon=True,
            )
            t.start()
            self._threads.append(t)

    def stop(self):
        """Detiene la captura de audio; los hilos cierran sus flujos al salir."""
        self.stop_event.set()
        self.levels["out"] = 0.0
        self.levels["mic"] = 0.0
        self.attempts["out"] = 0
        self.attempts["mic"] = 0

    def restart(self, out_dev: str, mic_dev: str, mic_enabled: bool):
        """Reinicia la captura con nuevos dispositivos sin reiniciar la aplicación."""
        self.stop()
        self.out_dev = out_dev
        self.mic_dev = mic_dev
        self.mic_enabled = mic_enabled
        self.start()
