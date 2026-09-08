import queue
import threading
import time
from typing import Callable, Dict, Optional, Tuple
import numpy as np
import pyaudiowpatch as pa

from .devices import resolve_wasapi_device
from .processing import rms, to_16k

FRAMES_PER_BUFFER = 1024
DEFAULT_MIN_SEC = 8.0
DEFAULT_MAX_SEC = 20.0
DEFAULT_PAUSE_SEC = 0.6
DEFAULT_SILENCE_RMS = 150.0


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


def capture_thread(
    kind: str,
    stream: pa.Stream,
    rate: int,
    channels: int,
    chunk_queue: queue.Queue,
    status_callback: Callable[[str], None],
    level_callback: Callable[[str, float], None],
    is_paused: Callable[[], bool],
    is_mic_enabled: Callable[[], bool],
    stop_event: threading.Event,
    min_sec: float = DEFAULT_MIN_SEC,
    max_sec: float = DEFAULT_MAX_SEC,
    pause_sec: float = DEFAULT_PAUSE_SEC,
    silence_threshold: float = DEFAULT_SILENCE_RMS,
):
    try:
        tail = max(1, int(pause_sec * rate / FRAMES_PER_BUFFER))
        buf = []
        t0 = None
        while not stop_event.is_set():
            raw = np.frombuffer(
                stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False),
                dtype=np.int16,
            )
            current_rms = rms(raw)
            level_callback(kind, current_rms)

            if is_paused() or (kind == "mic" and not is_mic_enabled()):
                buf = []
                t0 = None
                continue

            if not buf:
                t0 = None
            if t0 is None and current_rms > silence_threshold:
                t0 = time.time()

            buf.append(raw)
            secs = len(buf) * FRAMES_PER_BUFFER / rate

            if (secs >= min_sec and rms(np.concatenate(buf[-tail:])) < silence_threshold) or secs >= max_sec:
                pcm = np.concatenate(buf)
                buf = []
                if t0 is not None and rms(pcm) > silence_threshold:
                    audio_16k = to_16k(pcm, rate, channels)
                    chunk_queue.put((t0, kind, audio_16k))
                t0 = None
    except Exception as e:
        status_callback(f"Error audio ({kind}): {e!r}")
    finally:
        level_callback(kind, 0.0)
        try:
            stream.close()
        except Exception:
            pass


class AudioCaptureManager:
    """Gestiona la captura concurrente de audio (salida loopback y micrófono)."""

    def __init__(
        self,
        pa_instance: pa.PyAudio,
        chunk_queue: queue.Queue,
        status_callback: Callable[[str], None],
        out_dev: str = "",
        mic_dev: str = "",
        mic_enabled: bool = True,
    ):
        self.pa = pa_instance
        self.chunk_queue = chunk_queue
        self.status_callback = status_callback
        self.out_dev = out_dev
        self.mic_dev = mic_dev
        self.mic_enabled = mic_enabled
        self.paused = False
        self.levels: Dict[str, float] = {"out": 0.0, "mic": 0.0}
        self.stop_event = threading.Event()
        self._threads = []

    def _update_level(self, kind: str, level: float):
        self.levels[kind] = level

    def start(self):
        """Abre los flujos de audio y arranca los hilos de captura."""
        self.stop_event.clear()
        self._threads = []
        for kind in ("out", "mic"):
            preferred = self.out_dev if kind == "out" else self.mic_dev
            try:
                session = AudioStreamSession(self.pa, kind, preferred)
                t = threading.Thread(
                    target=capture_thread,
                    args=(
                        kind,
                        session.stream,
                        session.rate,
                        session.channels,
                        self.chunk_queue,
                        self.status_callback,
                        self._update_level,
                        lambda: self.paused,
                        lambda: self.mic_enabled,
                        self.stop_event,
                    ),
                    daemon=True,
                )
                t.start()
                self._threads.append(t)
            except Exception as e:
                self.status_callback(f"Sin audio ({kind}): {e!r}")

    def stop(self):
        """Detiene la captura de audio y cierra los flujos."""
        self.stop_event.set()
        self.levels["out"] = 0.0
        self.levels["mic"] = 0.0

    def restart(self, out_dev: str, mic_dev: str, mic_enabled: bool):
        """Reinicia la captura con nuevos dispositivos sin reiniciar la aplicación."""
        self.stop()
        self.out_dev = out_dev
        self.mic_dev = mic_dev
        self.mic_enabled = mic_enabled
        self.start()
