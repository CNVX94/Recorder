import datetime as dt
import queue
import threading
import time
from typing import Callable, Optional

from ..actions.notes import NotesSession, md_ref
from ..actions.screenshot import take_screenshot
from ..config.schema import AppConfig
from ..filters.pipeline import TextPipeline

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
        self.errors = 0  # fragmentos perdidos y capturas fallidas de esta sesion
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
            self.ui_queue.put(("status", f"Cargando modelo {self.config.model}…"))
            from faster_whisper import WhisperModel

            model = WhisperModel(self.config.model, device="cpu", compute_type="int8")
        except Exception as e:
            self.ui_queue.put(("status", f"⛔ No se pudo cargar el modelo: {e!r}"))
            return

        self.ui_queue.put(("status", "● Escuchando"))
        while not self.stop_event.is_set():
            try:
                t0, kind, audio = self.chunk_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self.busy = True
            try:
                self._process(model, t0, kind, audio)
            except Exception as e:
                self._report_lost(t0, e)
            finally:
                self.busy = False

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
            beam_size=self.config.beam_size,
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
