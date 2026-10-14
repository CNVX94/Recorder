import tkinter as tk
from tkinter import messagebox, scrolledtext
from typing import Optional

from ..config.manager import ConfigManager
from ..config.schema import AppConfig
from ..session import Event, Line, Notice, RecorderSession, SourceChanged, StatusSnapshot
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.digest_dialog import DigestDialog
from .dialogs.tuning_dialog import TuningDialog
from .theme import ACC, BG, BTN_STYLE, DIM, ERR, FG, HEADER_STYLE, MIC, PANEL, fit_window

POLL_MS = 200  # sondeo con la ventana a la vista
POLL_HIDDEN_MS = 1000  # minimizada: no hay nada que pintar; basta vaciar la cola y decidir el ☕
MAX_LINES = 5000  # líneas que conserva el visor; la nota en disco guarda la reunión entera
TRIM_LINES = 500  # cuántas se borran de golpe al pasarse, para no recortar en cada inserción


class MainWindow:
    """Ventana principal de la aplicación Recorder: pinta la sesión y le pasa lo que pide el usuario.

    Toda la lógica (núcleo, pausa, cierre, cabecera, equipo despierto) vive en `RecorderSession`;
    aquí solo hay widgets, diálogos y el sondeo cada 200 ms.
    """

    def __init__(
        self,
        config_manager: Optional[ConfigManager] = None,
        session: Optional[RecorderSession] = None,
    ):
        # `session` se inyecta en las pruebas (núcleo de mentira, config temporal); si no, se construye.
        self.session = session or RecorderSession(config_manager)

        self._poll_id = None  # el `after` del próximo sondeo, para adelantarlo al volver a la vista
        self._painted: dict = {}  # lo último escrito en cada etiqueta, para no reescribir lo mismo

        self._build_gui()

        # Iniciar hilos en segundo plano (captura, detección del equipo, transcriptor)
        self.session.start()

        # Iniciar sondeo de eventos de interfaz
        self.poll()

    def _render(self, ev: Event):
        """Pinta un evento de la sesión. Status y HardwareReady no se pintan: la cabecera sale de `status`."""
        if isinstance(ev, Line):
            self.add_line(ev.stamp, ev.kind, ev.text, ev.hits)
        elif isinstance(ev, Notice):
            self._visor(ev.stamp, ev.text, ev.level)
        elif isinstance(ev, SourceChanged):
            self.add_line(ev.stamp, "out", ev.text, [])

    def _visor(self, stamp: str, texto: str, tag: str):
        """Una línea con hora en la ventana, sin tocar la nota (no es parte de la reunión)."""
        self.txt.insert("end", f"{stamp}  ", "t")
        self.txt.insert("end", texto + "\n", tag)
        self._show_end()

    def _show_end(self):
        """Desplaza el visor al final y lo recorta por arriba si pasó de MAX_LINES.

        Se borra de TRIM_LINES en TRIM_LINES para no hacerlo en cada inserción. Solo afecta a lo
        que se ve: la nota en disco es la que guarda la reunión entera.
        """
        lines = int(self.txt.index("end-1c").split(".")[0])
        if lines > MAX_LINES:
            self.txt.delete("1.0", f"{lines - MAX_LINES + TRIM_LINES}.0")
        self.txt.see("end")

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("Recorder · Daily")
        self.root.configure(bg=BG)
        fit_window(self.root, 1040, 560)  # la cabecera con "⛔ reintento N" y "☕" no cabe en 860

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
            text=str(self.session.file_path),
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
        self.txt.tag_config("info", foreground=DIM)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # Al volver de la barra de tareas se repinta ya, sin esperar al sondeo lento (ver _tick)
        self.root.bind("<Map>", self._on_map)

    def add_line(self, stamp: str, kind: str, text: str, hits: list):
        self.txt.insert("end", f"{stamp}  ", "t")
        if kind == "mic":
            self.txt.insert("end", "🎤 ", "mic")
        self.txt.insert("end", text + "\n", "kw" if hits else "")
        if hits:
            self.txt.insert("end", f"          📸 captura: {', '.join(hits)}\n", "t")
        self._show_end()

    def manual_screenshot(self):
        """La sesión captura en un hilo y la línea llega por el sondeo; un clic con otra en curso se ignora."""
        self.session.manual_screenshot()

    def toggle_pause(self):
        line = self.session.toggle_pause()
        self.btn_pause.config(text="▶ Continuar" if self.session.paused else "⏸ Pausar")
        self._render(line)

    def open_digest(self):
        """Abre el generador de sintesis. Solo lee notas; nunca modifica el original."""
        DigestDialog(self.root, self.session.config, active_note=self.session.file_path)

    def open_options(self):
        def handle_save(new_config: AppConfig, notes_changed: bool, devices_changed: bool):
            self.session.apply_settings(new_config, notes_changed, devices_changed)
            if notes_changed:
                self.lbl_path.config(text=str(self.session.file_path))

        SettingsDialog(self.root, self.session.config, self.session.pa, on_save=handle_save)

    def open_tuning(self):
        TuningDialog(self.root, self.session.config, on_save=self.session.apply_tuning)

    def reconnect_audio(self):
        """Clic en los medidores: reabre las dos fuentes con los dispositivos configurados."""
        self.session.reconnect_audio()

    def _set_label(self, lbl: tk.Label, **opts):
        """Escribe en la etiqueta solo si algo cambió: cada config() cuesta aunque el texto sea el
        mismo (dos por tic suman ~1 % de CPU) y en silencio los medidores no cambian."""
        if self._painted.get(lbl) != opts:
            lbl.config(**opts)
            self._painted[lbl] = opts

    def _paint_header(self, st: StatusSnapshot):
        self._set_label(self.lbl_status, text=st.status_text, fg=FG if st.status_highlight else DIM)
        self._set_label(self.lbl_meter, text=st.meter_text)

    def _visible(self) -> bool:
        """False con la ventana minimizada o retirada: pintar ahí es trabajo que nadie ve."""
        return self.root.state() not in ("iconic", "withdrawn")

    def _tick(self) -> Optional[int]:
        """Un sondeo. Devuelve en cuántos ms toca el siguiente, o None si hay que cerrar.

        La sesión se sondea siempre (vacía la cola de los hilos, decide el ☕ y detecta el final
        del vaciado) y las líneas se insertan siempre, para que no se pierda nada; minimizada,
        solo se deja de pintar la cabecera y se sondea más despacio.
        """
        for ev in self.session.poll():
            self._render(ev)

        st = self.session.status
        visible = self._visible()
        if visible:
            self._paint_header(st)

        if st.finished:
            return None
        return POLL_MS if visible else POLL_HIDDEN_MS

    def poll(self):
        siguiente = self._tick()
        if siguiente is None:
            self._shutdown()
            return
        self._poll_id = self.root.after(siguiente, self.poll)

    def _on_map(self, event):
        """La ventana vuelve a la vista: se sondea y repinta ya en vez de esperar al tic lento.

        Los hijos también mandan su <Map> a la ventana (está en sus bindtags); solo cuenta el suyo.
        """
        if event.widget is self.root and self._poll_id is not None:
            self.root.after_cancel(self._poll_id)
            self.poll()

    def on_close(self):
        """Cerrar con fragmentos pendientes pregunta: esperar a que se transcriban o perderlos."""
        resumen = self.session.request_close()
        if resumen is not None:
            esperar = messagebox.askyesno(
                "Recorder",
                f"Quedan {resumen} sin transcribir.\n\n"
                "Sí: seguir transcribiendo; la ventana se cierra sola al terminar.\n"
                "No: salir ahora y perder esos fragmentos.",
                parent=self.root,
            )
            if esperar:
                self.session.begin_drain()  # no entran fragmentos nuevos; la cola solo baja
                self.btn_pause.config(state="disabled")
                self._paint_header(self.session.status)
                return
        self._shutdown()

    def _shutdown(self):
        # La sesión para los hilos sin tocar PortAudio (ver RecorderSession.shutdown); la ventana se va después.
        self.session.shutdown()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
