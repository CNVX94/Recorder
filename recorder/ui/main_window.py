import datetime as dt
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext
from typing import Optional
import pyaudiowpatch as pa

from ..actions.notes import NotesSession, md_ref
from ..actions.screenshot import take_screenshot
from ..audio.capture import AudioCaptureManager
from ..audio.processing import bars
from ..config.manager import ConfigManager
from ..config.schema import AppConfig
from ..engine.whisper_worker import TranscriberWorker
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.digest_dialog import DigestDialog
from .dialogs.tuning_dialog import TuningDialog
from .theme import ACC, BG, BTN_STYLE, DIM, FG, HEADER_STYLE, MIC, PANEL


class MainWindow:
    """Ventana principal de la aplicación Recorder."""

    def __init__(self, config_manager: Optional[ConfigManager] = None):
        self.config_manager = config_manager or ConfigManager()
        self.config: AppConfig = self.config_manager.load()

        self.notes_session = NotesSession(self.config.notes_dir)
        self.pa = pa.PyAudio()

        self.chunk_queue: queue.Queue = queue.Queue()
        self.ui_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()

        # Componentes del núcleo
        self.audio_manager = AudioCaptureManager(
            pa_instance=self.pa,
            chunk_queue=self.chunk_queue,
            status_callback=lambda msg: self.ui_queue.put(("status", msg)),
            out_dev=self.config.out_dev,
            mic_dev=self.config.mic_dev,
            mic_enabled=self.config.mic,
        )

        self.transcriber = TranscriberWorker(
            config=self.config,
            chunk_queue=self.chunk_queue,
            ui_queue=self.ui_queue,
            notes_session=self.notes_session,
            stop_event=self.stop_event,
        )

        self._build_gui()

        # Iniciar hilos en segundo plano
        self.audio_manager.start()
        self.transcribe_thread = threading.Thread(
            target=self.transcriber.run, daemon=True
        )
        self.transcribe_thread.start()

        # Iniciar sondeo de eventos de interfaz
        self.poll()

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("Recorder · Daily")
        self.root.configure(bg=BG)
        self.root.geometry("860x560")

        # Cabecera
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 0))

        self.lbl_status = tk.Label(
            top, text="Iniciando…", bg=BG, fg=DIM, anchor="w", font=("Segoe UI Semibold", 11)
        )
        self.lbl_status.pack(side="left")

        self.lbl_meter = tk.Label(top, text="", bg=BG, fg=DIM, font=("Consolas", 10))
        self.lbl_meter.pack(side="left", padx=16)

        # Botones cabecera
        self.btn_pause = tk.Button(top, text="⏸ Pausar", command=self.toggle_pause, **BTN_STYLE)
        self.btn_pause.pack(side="right")

        self.btn_tuning = tk.Button(
            top, text="🎯 Calibrar", command=self.open_tuning, **BTN_STYLE
        )
        self.btn_tuning.pack(side="right", padx=(0, 6))

        self.btn_options = tk.Button(
            top, text="⚙ Opciones", command=self.open_options, **BTN_STYLE
        )
        self.btn_options.pack(side="right", padx=(0, 6))

        self.btn_digest = tk.Button(
            top,
            text="📑 Sintesis",
            command=self.open_digest,
            **BTN_STYLE,
        )
        self.btn_digest.pack(side="right", padx=(0, 6))

        self.btn_shot = tk.Button(
            top, text="📸 Captura", command=self.manual_screenshot, **BTN_STYLE
        )
        self.btn_shot.pack(side="right", padx=(0, 6))

        # Etiqueta de ruta de archivo
        self.lbl_path = tk.Label(
            self.root,
            text=str(self.notes_session.file_path),
            bg=BG,
            fg=DIM,
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.lbl_path.pack(fill="x", padx=14, pady=(2, 0))

        # Área de texto desplazable
        self.txt = scrolledtext.ScrolledText(
            self.root,
            bg=BG,
            fg=FG,
            insertbackground=FG,
            wrap="word",
            relief="flat",
            font=("Segoe UI", 11),
            padx=10,
            pady=8,
            spacing3=6,
            height=10,
        )
        self.txt.pack(fill="both", expand=True, padx=14, pady=(10, 14))
        self.txt.tag_config("t", foreground=DIM, font=("Consolas", 10))
        self.txt.tag_config("kw", foreground=ACC)
        self.txt.tag_config("mic", foreground=MIC)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def add_line(self, stamp: str, kind: str, text: str, hits: list):
        self.txt.insert("end", f"{stamp}  ", "t")
        if kind == "mic":
            self.txt.insert("end", "🎤 ", "mic")
        self.txt.insert("end", text + "\n", "kw" if hits else "")
        if hits:
            self.txt.insert("end", f"          📸 captura: {', '.join(hits)}\n", "t")
        self.txt.see("end")

    def manual_screenshot(self):
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        f = take_screenshot("manual", self.config.caps_dir, self.config.screen, self.config.window)
        ref = md_ref(f, self.notes_session.file_path.parent)
        self.notes_session.write_line(f"- **{stamp}** 📸 captura manual → ![]({ref})")
        self.add_line(stamp, "out", "(captura manual)", ["manual"])

    def toggle_pause(self):
        self.audio_manager.paused = not self.audio_manager.paused
        is_paused = self.audio_manager.paused
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        state_msg = "⏸ Pausa" if is_paused else "▶ Continúa"
        self.notes_session.write_line(f"\n> {state_msg} {stamp}\n")
        self.btn_pause.config(text="▶ Continuar" if is_paused else "⏸ Pausar")
        self.add_line(
            stamp,
            "out",
            "⏸ pausa, no se toma nota" if is_paused else "▶ continúa",
            [],
        )

    def open_digest(self):
        """Abre el generador de sintesis. Solo lee notas; nunca modifica el original."""
        DigestDialog(self.root, self.config, active_note=self.notes_session.file_path)

    def open_options(self):
        def handle_save(new_config: AppConfig, notes_changed: bool, devices_changed: bool):
            if notes_changed:
                self.notes_session.move_notes(new_config.notes_dir)
                self.lbl_path.config(text=str(self.notes_session.file_path))

            self.config = new_config
            self.config_manager.save(self.config)
            self.transcriber.update_pipeline(self.config)

            if devices_changed:
                self.lbl_status.config(text="● Escuchando")
                self.audio_manager.restart(
                    out_dev=self.config.out_dev,
                    mic_dev=self.config.mic_dev,
                    mic_enabled=self.config.mic,
                )

        SettingsDialog(self.root, self.config, self.pa, on_save=handle_save)

    def open_tuning(self):
        def handle_save(new_config: AppConfig):
            self.config = new_config
            self.config_manager.save(self.config)
            self.transcriber.update_pipeline(self.config)

        TuningDialog(self.root, self.config, on_save=handle_save)

    def poll(self):
        while not self.ui_queue.empty():
            m = self.ui_queue.get()
            if m[0] == "status":
                self.lbl_status.config(text=m[1], fg=FG if m[1].startswith("●") else DIM)
            elif m[0] == "line":
                self.add_line(*m[1:])

        cur_text = self.lbl_status.cget("text")
        if cur_text and cur_text[0] in "●⏸":
            if self.audio_manager.paused:
                self.lbl_status.config(text="⏸ En pausa")
            else:
                mic_tag = " + 🎤" if self.config.mic else ""
                pending = self.chunk_queue.qsize()
                fallos = getattr(self.transcriber, "errors", 0)
                aviso = f" · ⚠ {fallos} con fallo" if fallos else ""
                self.lbl_status.config(
                    text=f"● Escuchando{mic_tag} · pendientes: {pending}{aviso}"
                )

        out_lvl = self.audio_manager.levels.get("out", 0.0)
        mic_lvl = self.audio_manager.levels.get("mic", 0.0)
        self.lbl_meter.config(text=f"🔊 {bars(out_lvl)}   🎤 {bars(mic_lvl)}")

        self.root.after(200, self.poll)

    def on_close(self):
        self.audio_manager.stop()
        self.stop_event.set()
        try:
            self.pa.terminate()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()

