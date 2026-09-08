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
        try:
            self.ui_queue.put(("status", f"Cargando modelo {self.config.model}…"))
            from faster_whisper import WhisperModel

            model = WhisperModel(self.config.model, device="cpu", compute_type="int8")
            self.ui_queue.put(("status", "● Escuchando"))

            while not self.stop_event.is_set():
                try:
                    t0, kind, audio = self.chunk_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

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
                    continue

                stamp = dt.datetime.fromtimestamp(t0).strftime("%H:%M:%S")
                line = f"- **{stamp}** {'🎤 ' if kind == 'mic' else ''}{text}"

                now = time.time()
                if hits and (now - self.last_cap_time > CAP_COOLDOWN_SEC):
                    self.last_cap_time = now
                    cap_file = take_screenshot(
                        hits[0],
                        self.config.caps_dir,
                        screen_idx=self.config.screen,
                    )
                    rel_ref = md_ref(cap_file, self.notes_session.file_path.parent)
                    line += f"\n  - 📸 `{', '.join(hits)}` → ![]({rel_ref})"
                else:
                    hits = []

                self.notes_session.write_line(line)
                self.ui_queue.put(("line", stamp, kind, text, hits))
        except Exception as e:
            self.ui_queue.put(("status", f"Error transcripción: {e!r}"))
