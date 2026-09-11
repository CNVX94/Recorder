import datetime as dt
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext
from typing import Optional
import pyaudiowpatch as pa

from ..actions.notes import NotesSession, md_ref
from ..actions.power import keep_awake, should_stay_awake
from ..actions.screenshot import take_screenshot
from ..audio.capture import AudioCaptureManager, meter_label, pending_audio_sec, pending_summary
from ..config.manager import ConfigManager
from ..config.schema import AppConfig
from ..engine.whisper_worker import TranscriberWorker
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.digest_dialog import DigestDialog
from .dialogs.tuning_dialog import TuningDialog
from .theme import ACC, BG, BTN_STYLE, DIM, ERR, FG, HEADER_STYLE, MIC, PANEL


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
            source_callback=lambda kind, up, detail: self.ui_queue.put(("source", kind, up, detail)),
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

        self.awake = False     # True mientras se le pide a Windows que no suspenda por inactividad
        self.draining = False  # True cuando se cerró la ventana pero se espera a vaciar la cola

        self._build_gui()
        self._avisar_config_ilegible()

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
        self.root.geometry("1040x560")  # la cabecera con "⛔ reintento N" y "☕" no cabe en 860

        # Cabecera
        top = tk.Frame(self.root, bg=BG)
        top.pack(fill="x", padx=14, pady=(12, 0))

        self.lbl_status = tk.Label(
            top, text="Iniciando…", bg=BG, fg=DIM, anchor="w", font=("Segoe UI Semibold", 11)
        )
        self.lbl_meter = tk.Label(top, text="", bg=BG, fg=DIM, font=("Consolas", 10), cursor="hand2")
        self.lbl_meter.bind("<Button-1>", lambda _e: self.reconnect_audio())

        # Botones cabecera. Se empacan ANTES que el estado y los medidores: con pack, lo primero
        # reserva su sitio, así que un estado largo (por ejemplo "transcribiendo 200 fragmentos")
        # se recorta en vez de empujar los botones fuera de la ventana.
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

        self.lbl_meter.pack(side="right", padx=16)
        self.lbl_status.pack(side="left", fill="x", expand=True)

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
        self.txt.tag_config("err", foreground=ERR)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _avisar_config_ilegible(self):
        """Si la configuración no se pudo leer, decirlo en vez de arrancar como si nada.

        Va al visor y a la nota, no a la cabecera: la cabecera la reescribe el hilo de
        transcripción en cuanto carga el modelo y el aviso se perdería de vista.
        """
        motivo = getattr(self.config_manager, "last_error", "")
        if not motivo:
            return
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        self.txt.insert("end", f"{stamp}  ", "t")
        self.txt.insert("end", f"⚠ {motivo}\n", "err")
        self.txt.see("end")
        try:
            self.notes_session.write_line(f"> ⚠ {stamp} {motivo}")
        except Exception:  # ponytail: si ni la nota se puede escribir, el visor ya avisó
            pass

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

    def _mensaje_pausa(self) -> str:
        """Texto de la pausa, explicando que lo pendiente se sigue transcribiendo."""
        pendiente = self._pending_summary() if self.chunk_queue.qsize() else ""
        cola = f"; siguen {pendiente} por transcribir" if pendiente else ""
        return f"⏸ pausa: no se captura audio nuevo{cola}"

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
            self._mensaje_pausa() if is_paused else "▶ continúa, se vuelve a capturar audio",
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

    def note_source(self, kind: str, up: bool, detail: str):
        """Deja constancia en pantalla y en la nota de que una fuente cayó o volvió, como con la pausa."""
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        name = "salida" if kind == "out" else "micrófono"
        msg = f"✔ audio de {name} recuperado" if up else f"⚠ audio de {name} caído, reintentando: {detail}"
        self.notes_session.write_line(f"\n> {msg} {stamp}\n")
        self.add_line(stamp, "out", msg, [])

    def reconnect_audio(self):
        """Clic en los medidores: reabre las dos fuentes con los dispositivos configurados.

        Es el plan B para un flujo que tras despertar se queda mudo sin dar error (ahí el
        reintento automático no salta porque no hay excepción que lo dispare).
        """
        if self.draining:
            return
        self.audio_manager.restart(self.config.out_dev, self.config.mic_dev, self.config.mic)

    def _pending_summary(self) -> str:
        with self.chunk_queue.mutex:  # queue.Queue documenta mutex y queue para esto
            chunks = list(self.chunk_queue.queue)
        return pending_summary(len(chunks), pending_audio_sec(chunks))

    def poll(self):
        while not self.ui_queue.empty():
            m = self.ui_queue.get()
            if m[0] == "status":
                self.lbl_status.config(text=m[1], fg=FG if m[1].startswith("●") else DIM)
            elif m[0] == "line":
                self.add_line(*m[1:])
            elif m[0] == "source":
                self.note_source(*m[1:])

        pending = self.chunk_queue.qsize()
        busy = self.transcriber.busy
        cur_text = self.lbl_status.cget("text")
        if cur_text and cur_text[0] in "●⏸⏳":
            if self.draining:
                self.lbl_status.config(text=f"⏳ Terminando {self._pending_summary()}…", fg=FG)
            elif self.audio_manager.paused:
                # La pausa solo deja de capturar audio nuevo; la cola pendiente se sigue
                # transcribiendo. Se muestra el avance para que eso se vea y no parezca parado.
                fallos = getattr(self.transcriber, "errors", 0)
                aviso = f" · ⚠ {fallos} con fallo" if fallos else ""
                awake = " · ☕" if self.awake else ""
                resto = (
                    f" · transcribiendo {self._pending_summary()}"
                    if (pending or busy)
                    else " · sin pendientes"
                )
                self.lbl_status.config(text=f"⏸ En pausa{resto}{aviso}{awake}")
            else:
                mic_tag = " + 🎤" if self.config.mic else ""
                fallos = getattr(self.transcriber, "errors", 0)
                aviso = f" · ⚠ {fallos} con fallo" if fallos else ""
                awake = " · ☕" if self.awake else ""
                self.lbl_status.config(
                    text=f"● Escuchando{mic_tag} · pendientes: {pending}{aviso}{awake}"
                )

        self.lbl_meter.config(text=meter_label(self.audio_manager.levels, self.audio_manager.attempts))

        awake = should_stay_awake(
            time.time(), self.audio_manager.last_audio_at, pending, busy, self.audio_manager.paused
        )
        if awake != self.awake:
            keep_awake(awake)
            self.awake = awake

        if self.draining and pending == 0 and not busy:
            self._shutdown()
            return
        self.root.after(200, self.poll)

    def on_close(self):
        """Cerrar con fragmentos pendientes pregunta: esperar a que se transcriban o perderlos."""
        if self.chunk_queue.qsize():
            resumen = self._pending_summary()
            esperar = messagebox.askyesno(
                "Recorder",
                f"Quedan {resumen} sin transcribir.\n\n"
                "Sí: seguir transcribiendo; la ventana se cierra sola al terminar.\n"
                "No: salir ahora y perder esos fragmentos.",
                parent=self.root,
            )
            if esperar:
                self.draining = True
                self.audio_manager.stop()  # no entran fragmentos nuevos; la cola solo baja
                self.btn_pause.config(state="disabled")
                self.lbl_status.config(text=f"⏳ Terminando {resumen}…", fg=FG)
                return
        self._shutdown()

    def _shutdown(self):
        self.audio_manager.stop()
        self.stop_event.set()
        keep_awake(False)
        # ponytail: a propósito no se llama a pa.terminate(). Cierra cada stream desde este hilo
        # mientras el del loopback sigue bloqueado en read() (bloquea hasta que suena algo) y eso
        # revienta el proceso con 0xC0000005 (pasaba en cada cierre, invisible porque la ventana
        # desaparece igual). El proceso termina justo después y Windows recoge los recursos.
        self.root.destroy()

    def run(self):
        self.root.mainloop()

