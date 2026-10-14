"""Buffer circular de capturas: una imagen cada pocos segundos mientras hay reunión.

La transcripción va por detrás del audio (minutos, en una reunión larga), así que capturar al
terminar de transcribir retrata lo que hay en pantalla entonces, no cuando se dijo la palabra.
El buffer guarda imágenes con su propia hora y el worker se queda con la más cercana a la de la
palabra (docs/captura-diferida.md). Se purga conforme avanza la transcripción y se vacía al
arrancar y al cerrar: nada de la pantalla queda en disco más tiempo del necesario.
"""
import pathlib
import threading
import time
from typing import Callable, Dict, List, Optional

from .power import AWAKE_GRACE_SEC

INTERVAL_SEC = 5.0
# calidad -> (extensión, escala, calidad JPEG). Disco por hora medido: 54, 180 y 316 MB
# (docs/captura-diferida.md). "off" no está aquí: sin buffer no hay capturas automáticas.
QUALITIES = {"light": ("jpg", 0.5, 70), "normal": ("jpg", 1.0, 70), "high": ("png", 1.0, None)}
BUFFER_DIR = ".buffer"  # con punto: Obsidian no lo indexa


def should_buffer(now: float, last_audio_at: float, paused: bool, grace: float = AWAKE_GRACE_SEC) -> bool:
    """Política pura: capturar solo en reunión (sin pausa y con audio oído hace menos de `grace`).

    Es la misma ventana que retiene el equipo despierto (power.should_stay_awake), sin la cola:
    lo que haya en pantalla mientras se drena la cola tras la reunión no le importa a nadie.
    """
    return not paused and (now - last_audio_at) < grace


def nearest_frame(times: List[float], t: float, max_gap: float) -> Optional[float]:
    """Política pura: la hora de fotograma más cercana a `t`, o None si ninguna dista menos de `max_gap`."""
    best = min(times, key=lambda x: abs(x - t), default=None)
    return best if best is not None and abs(best - t) <= max_gap else None


class CaptureBuffer:
    """Fotogramas en `caps_dir/.buffer/<hora>.<ext>`; `take()` mueve uno a su nombre definitivo."""

    def __init__(
        self,
        caps_dir,
        quality: str,
        grab: Callable[[], object],
        active: Callable[[], bool],
        interval: float = INTERVAL_SEC,
    ):
        self.dir = pathlib.Path(caps_dir) / BUFFER_DIR
        self.ext, self.scale, self.jpeg_quality = QUALITIES[quality]
        self.grab = grab  # devuelve una imagen PIL del objetivo configurado
        self.active = active
        self.interval = interval
        self.lock = threading.Lock()  # take() y purge_before() llegan desde el hilo de transcripción
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.errors = 0

    def start(self):
        self.clear()  # restos de una sesión que no cerró bien
        self.thread = threading.Thread(target=self._loop, name="capture-buffer", daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 2.0):
        """Para el hilo y espera a que termine el fotograma en curso: un clear() justo después
        no debe dejar en disco uno escrito a destiempo."""
        self.stop_event.set()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout)

    def _loop(self):
        while not self.stop_event.wait(self.interval):
            if self.active():
                try:
                    self.snap()
                except Exception:  # ponytail: un fotograma perdido no para el buffer; take() cae al plan B
                    self.errors += 1

    def snap(self, now: Optional[float] = None) -> pathlib.Path:
        """Toma y guarda un fotograma con su hora."""
        now = time.time() if now is None else now
        img = self.grab()
        if self.scale != 1.0:
            img = img.resize((max(1, int(img.width * self.scale)), max(1, int(img.height * self.scale))))
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{now:.3f}.{self.ext}"
        tmp = path.with_suffix(".tmp")
        if self.jpeg_quality:
            img.convert("RGB").save(tmp, "JPEG", quality=self.jpeg_quality)
        else:
            img.save(tmp, "PNG")
        tmp.replace(path)  # take() nunca ve un archivo a medio escribir
        return path

    def _frames(self) -> Dict[float, pathlib.Path]:
        frames = {}
        for p in self.dir.glob(f"*.{self.ext}"):
            try:
                frames[float(p.stem)] = p
            except ValueError:
                pass
        return frames

    def take(self, t: float, dest: pathlib.Path, max_gap: Optional[float] = None) -> Optional[pathlib.Path]:
        """Mueve a `dest` (con la extensión del buffer) el fotograma más cercano a `t`, sin recomprimir.

        None si no hay ninguno a menos de `max_gap` (por defecto dos intervalos): buffer recién
        arrancado, apagado o ya purgado. El llamador decide el plan B.
        """
        gap = 2 * self.interval if max_gap is None else max_gap
        with self.lock:
            frames = self._frames()
            best = nearest_frame(list(frames), t, gap)
            if best is None:
                return None
            dest = pathlib.Path(dest).with_suffix("." + self.ext)
            dest.parent.mkdir(parents=True, exist_ok=True)
            frames[best].replace(dest)
            return dest

    def purge_before(self, t: float):
        """Borra los fotogramas anteriores a `t`: ya no puede pedirlos ningún fragmento pendiente."""
        with self.lock:
            for ts, p in self._frames().items():
                if ts < t:
                    p.unlink(missing_ok=True)

    def clear(self):
        """Borra todo el buffer (al arrancar y al cerrar)."""
        with self.lock:
            if self.dir.is_dir():
                for p in self.dir.iterdir():
                    if p.is_file():
                        p.unlink(missing_ok=True)
