"""Buffer circular de capturas: una imagen cada pocos segundos mientras hay reunión.

La transcripción va por detrás del audio (minutos, en una reunión larga), así que capturar al
terminar de transcribir retrata lo que hay en pantalla entonces, no cuando se dijo la palabra.
El buffer guarda imágenes con su propia hora y el worker se queda con la más cercana a la de la
palabra (docs/captura-diferida.md). Nada de la pantalla queda en disco más tiempo del necesario:
el worker purga conforme avanza la transcripción, el propio hilo borra en cada vuelta (también
sin reunión) lo más viejo que RETENTION_SEC, y el buffer se vacía al arrancar y al parar.
"""
import pathlib
import threading
import time
from typing import Callable, Dict, List, NamedTuple, Optional

from .power import AWAKE_GRACE_SEC

INTERVAL_SEC = 5.0
# Más viejo que esto no lo pide ya ningún fragmento razonable: con la transcripción más atrasada
# que esto, la captura cae al plan B (inmediata, anotada como tardía). Acota el disco y el tiempo
# que la pantalla queda guardada aunque el worker no procese nada (silencio, pausa).
RETENTION_SEC = AWAKE_GRACE_SEC
BUFFER_DIR = ".buffer"  # con punto: Obsidian no lo indexa


class Quality(NamedTuple):
    ext: str
    scale: float  # 1.0 = tamaño real; 0.5 = media resolución (reducida con LANCZOS)
    jpeg_quality: Optional[int]  # None = PNG sin pérdida
    subsampling: Optional[int]  # 0 = 4:4:4 (el texto pequeño no se emborrona); None = el de Pillow (4:2:0)


# Medido a 2560×1440 con un escritorio cargado, 12 fotogramas/min, sin Whisper
# (docs/captura-diferida.md): light 125 KB/img, ~88 MB/h, ~2,3 % de un núcleo (el LANCZOS cuesta);
# normal (JPEG 85, 4:4:4) 673 KB/img, ~470 MB/h, ~1,7 %; high (PNG) 625 KB/img, ~440 MB/h, ~3,1 %.
# "off" no está aquí: sin buffer no hay capturas automáticas.
QUALITIES: Dict[str, Quality] = {
    "light": Quality("jpg", 0.5, 70, None),
    "normal": Quality("jpg", 1.0, 85, 0),
    "high": Quality("png", 1.0, None, None),
}


def should_buffer(now: float, last_audio_at: float, paused: bool, grace: float = AWAKE_GRACE_SEC) -> bool:
    """Política pura: capturar solo en reunión (sin pausa y con un fragmento de audio hace menos de
    `grace`). Antes del primer fragmento (`last_audio_at` = 0) no hay reunión que retratar.

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
        on_error: Optional[Callable[[Exception], None]] = None,
        retention: float = RETENTION_SEC,
    ):
        self.dir = pathlib.Path(caps_dir) / BUFFER_DIR
        self.quality = QUALITIES[quality]
        self.ext = self.quality.ext
        self.grab = grab  # devuelve una imagen PIL del objetivo configurado
        self.active = active
        self.interval = interval
        self.retention = retention
        self.on_error = on_error  # se llama una sola vez, con el primer fallo (la unidad de caps_dir no está…)
        self.lock = threading.Lock()  # take() y purge_before() llegan desde el hilo de transcripción
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.errors = 0

    def start(self):
        self.clear()  # restos de una sesión que no cerró bien
        self.thread = threading.Thread(target=self._loop, name="capture-buffer", daemon=True)
        self.thread.start()

    def stop(self, timeout: float = 2.0):
        """Para el hilo, espera a que termine el fotograma en curso y vacía el buffer: al parar no
        queda nada de la pantalla en disco."""
        self.stop_event.set()
        if self.thread is not None and self.thread is not threading.current_thread():
            self.thread.join(timeout)
        self.clear()

    def _loop(self):
        while not self.stop_event.wait(self.interval):
            if self.active():
                try:
                    self.snap()
                except Exception as e:  # ponytail: un fotograma perdido no para el buffer; take() cae al plan B
                    self.errors += 1
                    if self.errors == 1 and self.on_error is not None:
                        self.on_error(e)
            try:
                self.purge_before(time.time() - self.retention)  # también sin reunión: nada se queda más de lo debido
            except OSError:
                pass

    def snap(self, now: Optional[float] = None) -> pathlib.Path:
        """Toma y guarda un fotograma con su hora."""
        from PIL import Image

        now = time.time() if now is None else now
        img = self.grab()
        q = self.quality
        if q.scale != 1.0:
            size = (max(1, int(img.width * q.scale)), max(1, int(img.height * q.scale)))
            img = img.resize(size, Image.LANCZOS)  # sin resample explícito Pillow usa NEAREST y el texto pequeño se rompe
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{now:.3f}.{self.ext}"
        tmp = path.with_suffix(".tmp")
        if q.jpeg_quality:
            opts = {"quality": q.jpeg_quality}
            if q.subsampling is not None:
                opts["subsampling"] = q.subsampling
            img.convert("RGB").save(tmp, "JPEG", **opts)
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
            if not self.dir.is_dir():
                return
            for ts, p in self._frames().items():
                if ts < t:
                    p.unlink(missing_ok=True)

    def clear(self):
        """Borra todo el buffer (al arrancar y al parar)."""
        with self.lock:
            if self.dir.is_dir():
                for p in self.dir.iterdir():
                    if p.is_file():
                        p.unlink(missing_ok=True)
