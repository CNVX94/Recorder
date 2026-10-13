import datetime as dt
import queue
import threading
import time
from typing import Callable, Optional

from ..actions.notes import NotesSession, md_ref
from ..actions.screenshot import take_screenshot
from ..config.hardware import cached_vulkan_devices
from ..config.schema import (
    CPU_FALLBACK_PRESET,
    QUALITY_PRESETS,
    AppConfig,
    choose_vulkan_device,
    detect_cuda_device_count,
    resolve_runtime,
    vulkan_model_for,
)
from ..filters.pipeline import TextPipeline
from .whispercpp import EngineUnavailable, load_whispercpp_model, whispercpp_ready

CAP_COOLDOWN_SEC = 15.0
kind_lost = "out"  # los avisos se pintan como una linea normal en la ventana
DEFAULT_LANGUAGE = "es"


class TranscriberWorker:
    """Hilo trabajador que consume fragmentos de audio y ejecuta la inferencia con Whisper."""

    def __init__(
        self,
        config: AppConfig,
        chunk_queue: queue.Queue,
        ui_queue: queue.Queue,
        notes_session: NotesSession,
        stop_event: threading.Event,
    ):
        self.config = config
        self.chunk_queue = chunk_queue
        self.ui_queue = ui_queue
        self.notes_session = notes_session
        self.stop_event = stop_event
        self.last_cap_time = 0.0
        self.errors = 0
        self.beam_size = config.beam_size  # run() lo reajusta si cae a CPU  # fragmentos perdidos y capturas fallidas de esta sesion
        self.busy = False  # True mientras transcribe un fragmento ya sacado de la cola

        self.pipeline = TextPipeline(
            keywords=self.config.keywords,
            ignore=self.config.ignore,
            fixes=self.config.fixes,
            no_speech_thresh=self.config.no_speech_threshold,
            logprob_thresh=self.config.logprob_threshold,
            compression_ratio_thresh=self.config.compression_ratio_threshold,
        )

    def update_pipeline(self, config: AppConfig):
        """Actualiza las reglas de filtrado y diccionario sin necesidad de recargar el modelo de IA."""
        self.config = config
        self.pipeline = TextPipeline(
            keywords=self.config.keywords,
            ignore=self.config.ignore,
            fixes=self.config.fixes,
            no_speech_thresh=self.config.no_speech_threshold,
            logprob_thresh=self.config.logprob_threshold,
            compression_ratio_thresh=self.config.compression_ratio_threshold,
        )

    def run(self):
        """Bucle de transcripcion.

        Solo cargar el modelo es fatal: sin modelo no hay nada que hacer. Cualquier otro
        fallo afecta a un unico fragmento y no debe costar el resto de la reunion.
        """
        try:
            model = self._load_model()
        except Exception as e:
            self.ui_queue.put(("status", f"⛔ No se pudo cargar el modelo: {e!r}"))
            return

        self.ui_queue.put(("status", "● Escuchando"))
        try:
            while not self.stop_event.is_set():
                try:
                    t0, kind, audio = self.chunk_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
                self.busy = True
                try:
                    self._process(model, t0, kind, audio)
                except EngineUnavailable as e:
                    # El servidor de GPU murio y no volvio: el resto de la reunion sigue en CPU,
                    # empezando por este mismo fragmento.
                    self.ui_queue.put(("status", f"⚠ {e}; se sigue en CPU."))
                    try:
                        getattr(model, "close", lambda: None)()
                        model = self._load_cpu_fallback()
                        self._process(model, t0, kind, audio)
                    except Exception as e2:
                        self._report_lost(t0, e2)
                except Exception as e:
                    self._report_lost(t0, e)
                finally:
                    self.busy = False
        finally:
            close = getattr(model, "close", None)  # whisper.cpp: parar el servidor y liberar la VRAM
            if close:
                close()

    def _load_model(self):
        # Resolver el hardware ANTES de construir el modelo: WhisperModel descarga los
        # pesos antes de validar el dispositivo, así que detectar el fallo después ya
        # habría bajado varios GB de un modelo que en CPU no sirve.
        cfg = self.config
        cuda = detect_cuda_device_count()
        vulkan = None  # qué GPU de Vulkan tocaría; solo se pregunta si whisper.cpp puede entrar en juego
        if cfg.whispercpp_dir.strip() and (cfg.device == "vulkan" or (cfg.device == "gpu" and cuda <= 0)):
            vulkan = choose_vulkan_device(cfg.whispercpp_device, cached_vulkan_devices())
        model_name, device, compute_type, beam, aviso = resolve_runtime(
            cfg,
            cuda,
            whispercpp_ready(cfg.whispercpp_dir, vulkan_model_for(cfg.model, vulkan), cfg.compute_type),
            vulkan,
        )
        self.beam_size = beam
        if aviso:
            self.ui_queue.put(("status", aviso))
        donde = f" en {vulkan.name}" if device == "vulkan" and vulkan is not None and vulkan.name else ""
        self.ui_queue.put(("status", f"Cargando modelo {model_name}{donde}…"))

        if device == "vulkan":
            dev = {"device": vulkan.index} if vulkan is not None and vulkan.index >= 0 else {}
            try:
                model = load_whispercpp_model(
                    cfg.whispercpp_dir, model_name, compute_type, DEFAULT_LANGUAGE,
                    cfg.cpu_threads, cfg.whispercpp_flash_attn, **dev,
                )
            except Exception as e:
                # Vulkan no arranca (driver, VRAM): preset de CPU entero, no el mismo modelo,
                # porque en faster-whisper serian otros GB de descarga para ir lento.
                self.ui_queue.put(("status", f"⚠ La GPU (Vulkan) no pudo cargar {model_name} ({e!r}); usando CPU en su lugar."))
                return self._load_cpu_fallback()
            usada = getattr(model, "vulkan_device", None)
            if usada is not None and usada.uma and cfg.whispercpp_device < 0:
                # Sin enumeracion previa (o si no coincidio), whisper.cpp toma su dispositivo 0,
                # que puede ser la integrada. Su registro lo dice: en automatico no se acepta.
                model.close()
                self.ui_queue.put((
                    "status",
                    f"⚠ whisper.cpp tomó la GPU integrada ({usada.name}), que Recorder no usa sin "
                    f"pedírsela (whispercpp_device); usando CPU en su lugar.",
                ))
                return self._load_cpu_fallback()
            return model

        from faster_whisper import WhisperModel

        try:
            return WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                cpu_threads=cfg.cpu_threads,  # 0 = por defecto de la biblioteca
            )
        except Exception as e:
            if device == "cpu":
                raise
            # Hay GPU pero no arranca (driver, VRAM): mismo modelo en CPU, avisando.
            self.ui_queue.put((
                "status",
                f"⚠ La GPU no pudo cargar {model_name} ({e!r}); usando CPU en su lugar.",
            ))
            return WhisperModel(
                model_name, device="cpu", compute_type="int8",
                cpu_threads=cfg.cpu_threads,
            )

    def _load_cpu_fallback(self):
        """El preset de CPU entero (modelo y haz), para cuando la GPU de whisper.cpp falla."""
        from faster_whisper import WhisperModel

        cpu = QUALITY_PRESETS[CPU_FALLBACK_PRESET]
        self.beam_size = cpu.beam_size
        return WhisperModel(
            cpu.model, device=cpu.device, compute_type=cpu.compute_type,
            cpu_threads=self.config.cpu_threads,
        )

    def _report_lost(self, t0: float, err: Exception):
        """Deja constancia del fragmento perdido en la nota y en el contador de la cabecera."""
        self.errors += 1
        stamp = dt.datetime.fromtimestamp(t0).strftime("%H:%M:%S")
        try:  # ponytail: si lo que falla es escribir la nota, el aviso tampoco cabe; se calla
            self.notes_session.write_line(f"- **{stamp}** ⚠ fragmento perdido: {err!r}")
        except Exception:
            pass
        self.ui_queue.put(("line", stamp, kind_lost, f"⚠ fragmento perdido: {err!r}", []))

    def _process(self, model, t0: float, kind: str, audio):
        """Transcribe un fragmento y lo anota. Cualquier excepcion la gestiona run()."""
        vocab_prompt = self.config.vocab.strip() or None
        segs, _ = model.transcribe(
            audio,
            language=DEFAULT_LANGUAGE,
            beam_size=self.beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
            initial_prompt=vocab_prompt,
            repetition_penalty=self.config.repetition_penalty,
        )

        text, hits = self.pipeline.process_segments(segs)
        if not text:
            return

        stamp = dt.datetime.fromtimestamp(t0).strftime("%H:%M:%S")
        line = f"- **{stamp}** {'🎤 ' if kind == 'mic' else ''}{text}"

        now = time.time()
        if hits and (now - self.last_cap_time > CAP_COOLDOWN_SEC):
            self.last_cap_time = now
            try:
                cap_file = take_screenshot(
                    hits[0],
                    self.config.caps_dir,
                    screen_idx=self.config.screen,
                    window=self.config.window,
                )
                rel_ref = md_ref(cap_file, self.notes_session.file_path.parent)
                line += f"\n  - 📸 `{', '.join(hits)}` → ![]({rel_ref})"
            except Exception as e:
                # Perder la imagen no justifica perder la frase: se anota el fallo y se sigue.
                self.errors += 1
                line += f"\n  - ⚠ captura fallida: {e!r}"
                hits = []
        else:
            hits = []

        self.notes_session.write_line(line)
        self.ui_queue.put(("line", stamp, kind, text, hits))
