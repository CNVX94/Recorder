import tkinter as tk
from tkinter import filedialog
from typing import Callable, List
import pyaudiowpatch as pa

from ...actions.screenshot import screen_labels, window_titles
from ...audio.devices import wasapi_devices
from ...config.schema import AppConfig
from ..theme import ACC, BG, BTN_STYLE, DIM, ENTRY_STYLE, FG, LABEL_STYLE, PANEL
from .tuning_dialog import TuningDialog

DEFAULT_DEV = "(predeterminado de Windows)"
AVAILABLE_MODELS = ["small", "medium", "base", "tiny", "large-v3-turbo"]
WINDOW_PREFIX = "Ventana: "  # distingue en el selector una ventana de aplicación de una pantalla


class SettingsDialog(tk.Toplevel):
    """Diálogo general de opciones de la aplicación."""

    def __init__(
        self,
        parent: tk.Widget,
        config: AppConfig,
        pa_instance: pa.PyAudio,
        on_save: Callable[[AppConfig, bool, bool], None],
    ):
        super().__init__(parent)
        self.config = config
        self.pa = pa_instance
        self.on_save = on_save

        self.title("Opciones del Sistema")
        self.configure(bg=BG)
        self.geometry("640x530")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.screens = screen_labels()
        self._init_variables()
        self._build_ui()

    def _init_variables(self):
        screen_idx = self.config.screen if self.config.screen < len(self.screens) else 0
        self.v_notes = tk.StringVar(value=self.config.notes_dir)
        self.v_caps = tk.StringVar(value=self.config.caps_dir)
        self.v_keywords = tk.StringVar(value=", ".join(self.config.keywords))
        self.v_mic = tk.BooleanVar(value=self.config.mic)
        self.v_out_dev = tk.StringVar(value=self.config.out_dev or DEFAULT_DEV)
        self.v_mic_dev = tk.StringVar(value=self.config.mic_dev or DEFAULT_DEV)
        self.v_screen = tk.StringVar(
            value=WINDOW_PREFIX + self.config.window if self.config.window else self.screens[screen_idx]
        )
        self.v_model = tk.StringVar(value=self.config.model)

    def _build_ui(self):
        # Filas de configuración
        self._row_entry(0, "Carpeta de notas (.md):", self.v_notes, browse=True)
        self._row_entry(1, "Carpeta de capturas:", self.v_caps, browse=True)
        self._row_entry(2, "Palabras clave (coma):", self.v_keywords)

        out_devs = wasapi_devices(self.pa, "out")
        mic_devs = wasapi_devices(self.pa, "mic")
        self._row_choice(3, "Salida a capturar 🔊:", self.v_out_dev, out_devs)
        self._row_choice(4, "Micrófono 🎤:", self.v_mic_dev, mic_devs)
        targets = self._targets()
        self.om_target = self._row_choice(5, "Qué capturar 📸:", self.v_screen, targets[1:], first=targets[0])
        tk.Button(self, text="🔄", command=self._refresh_targets, **BTN_STYLE).grid(row=5, column=2, padx=(6, 16))
        self._row_choice(6, "Modelo Whisper (al reiniciar):", self.v_model, AVAILABLE_MODELS[1:], first=AVAILABLE_MODELS[0])

        tk.Checkbutton(
            self,
            text="Transcribir también mi micrófono 🎤",
            variable=self.v_mic,
            bg=BG,
            fg=FG,
            selectcolor=PANEL,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 10),
        ).grid(row=7, column=0, columnspan=2, sticky="w", padx=16, pady=10)

        # Botón destacado para calibrar alucinaciones
        btn_tuning = tk.Button(
            self,
            text="🎯 Calibrar Alucinaciones & Vocabulario...",
            command=self._open_tuning,
            bg=PANEL,
            fg=ACC,
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=4,
        )
        btn_tuning.grid(row=8, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 16))

        # Botonera inferior
        btn_box = tk.Frame(self, bg=BG)
        btn_box.grid(row=9, column=1, sticky="e", padx=16, pady=10)

        tk.Button(
            btn_box,
            text="Cancelar",
            command=self.destroy,
            bg=PANEL,
            fg=DIM,
            relief="flat",
            padx=10,
            font=("Segoe UI", 10),
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            btn_box,
            text="Guardar",
            command=self._save,
            **BTN_STYLE,
        ).pack(side="right")

    def _row_entry(self, r: int, text: str, var: tk.StringVar, browse: bool = False):
        tk.Label(self, text=text, **LABEL_STYLE).grid(row=r, column=0, sticky="w", padx=16, pady=6)
        tk.Entry(self, textvariable=var, width=46, **ENTRY_STYLE).grid(
            row=r, column=1, ipady=4, sticky="ew", padx=(0, 16 if not browse else 0)
        )
        if browse:
            tk.Button(
                self,
                text="📁",
                command=lambda: var.set(filedialog.askdirectory(initialdir=var.get()) or var.get()),
                **BTN_STYLE,
            ).grid(row=r, column=2, padx=(6, 16))

    def _row_choice(self, r: int, text: str, var: tk.StringVar, names: List[str], first: str = DEFAULT_DEV):
        tk.Label(self, text=text, **LABEL_STYLE).grid(row=r, column=0, sticky="w", padx=16, pady=6)
        om = tk.OptionMenu(self, var, first, *names)
        om.config(
            bg=PANEL,
            fg=FG,
            activebackground=ACC,
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 10),
            anchor="w",
            width=40,  # los títulos de ventana pueden ser larguísimos; que no ensanchen el diálogo
        )
        om["menu"].config(bg=PANEL, fg=FG, activebackground=ACC)
        om.grid(row=r, column=1, sticky="ew", padx=(0, 16))
        return om

    def _targets(self) -> List[str]:
        """Opciones de captura: las pantallas y las ventanas abiertas ahora (más la guardada, aunque esté cerrada)."""
        titles = window_titles()
        if self.config.window and self.config.window not in titles:
            titles.insert(0, self.config.window)
        return self.screens + [WINDOW_PREFIX + t for t in titles]

    def _refresh_targets(self):
        """Las ventanas abiertas cambian: vuelve a leerlas y reconstruye el desplegable."""
        menu = self.om_target["menu"]
        menu.delete(0, "end")
        for label in self._targets():
            menu.add_command(label=label, command=lambda v=label: self.v_screen.set(v))

    def _open_tuning(self):
        TuningDialog(self, self.config, on_save=lambda cfg: None)

    def _save(self):
        new_notes = self.v_notes.get().strip()
        notes_changed = new_notes != self.config.notes_dir

        new_out = "" if self.v_out_dev.get() == DEFAULT_DEV else self.v_out_dev.get()
        new_mic = "" if self.v_mic_dev.get() == DEFAULT_DEV else self.v_mic_dev.get()
        devices_changed = (
            new_out != self.config.out_dev
            or new_mic != self.config.mic_dev
            or self.v_mic.get() != self.config.mic
        )

        self.config.notes_dir = new_notes
        self.config.caps_dir = self.v_caps.get().strip()
        self.config.keywords = [k.strip() for k in self.v_keywords.get().split(",") if k.strip()]
        self.config.out_dev = new_out
        self.config.mic_dev = new_mic
        self.config.mic = self.v_mic.get()
        choice = self.v_screen.get()
        if choice.startswith(WINDOW_PREFIX):
            self.config.window = choice[len(WINDOW_PREFIX):]  # `screen` se conserva como plan B
        else:
            self.config.window = ""
            self.config.screen = self.screens.index(choice) if choice in self.screens else 0
        self.config.model = self.v_model.get()

        self.on_save(self.config, notes_changed, devices_changed)
        self.destroy()
