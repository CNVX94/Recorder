import tkinter as tk
from tkinter import filedialog
from typing import Callable, List
import pyaudiowpatch as pa

from ...actions.screenshot import screen_labels, window_titles
from ...audio.devices import wasapi_devices
from ...config.schema import (
    AppConfig,
    CUSTOM_PRESET,
    PRESET_ORDER,
    QUALITY_PRESETS,
    apply_preset,
    detect_cuda_device_count,
    preset_availability,
    preset_key_for_config,
)
from ...engine.whispercpp import whispercpp_ready
from ..theme import ACC, BG, BTN_STYLE, DIM, ENTRY_STYLE, ERR, FG, LABEL_STYLE, PANEL, fit_window
from .tuning_dialog import TuningDialog

DEFAULT_DEV = "(predeterminado de Windows)"
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
        self.transient(parent)
        self.grab_set()

        self.screens = screen_labels()
        self.cuda_devices = detect_cuda_device_count()  # 0 si no hay GPU CUDA o falla la consulta
        extra = QUALITY_PRESETS["extra"]
        self.vulkan_ready = whispercpp_ready(config.whispercpp_dir, extra.model, extra.compute_type)
        self._init_variables()
        self._build_ui()
        fit_window(self, 640, 600)

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
        self._build_quality_row(6)  # fila 6 = selector, fila 7 = descripción (se aplica al reiniciar)

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
        ).grid(row=8, column=0, columnspan=2, sticky="w", padx=16, pady=10)

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
        btn_tuning.grid(row=9, column=0, columnspan=2, sticky="w", padx=16, pady=(4, 16))

        # Botonera inferior
        btn_box = tk.Frame(self, bg=BG)
        btn_box.grid(row=10, column=1, sticky="e", padx=16, pady=10)

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

    def _build_quality_row(self, r: int):
        """Selector de calidad: la decisión principal, con una línea que explica cada preset."""
        tk.Label(
            self,
            text="Calidad de transcripción (se aplica al reiniciar):",
            bg=BG,
            fg=FG,
            font=("Segoe UI Semibold", 10),
        ).grid(row=r, column=0, sticky="w", padx=16, pady=(10, 2))

        keys = PRESET_ORDER + [CUSTOM_PRESET]
        current_key = preset_key_for_config(self.config) or CUSTOM_PRESET
        self._quality_label_by_key = {k: self._quality_display(k) for k in keys}
        self._quality_key_by_label = {v: k for k, v in self._quality_label_by_key.items()}
        self.v_quality = tk.StringVar(value=self._quality_label_by_key[current_key])

        other_labels = [self._quality_label_by_key[k] for k in keys if k != current_key]
        om = tk.OptionMenu(self, self.v_quality, self._quality_label_by_key[current_key], *other_labels)
        om.config(
            bg=PANEL,
            fg=ACC,
            activebackground=ACC,
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI Semibold", 10),
            anchor="w",
            width=40,
        )
        om["menu"].config(bg=PANEL, fg=FG, activebackground=ACC)
        om.grid(row=r, column=1, sticky="ew", padx=(0, 16), pady=(10, 2))

        self.v_quality_desc = tk.StringVar()
        self.lbl_quality_desc = tk.Label(
            self,
            textvariable=self.v_quality_desc,
            bg=BG,
            fg=DIM,
            font=("Segoe UI", 9),
            wraplength=600,
            justify="left",
            anchor="w",
        )
        self.lbl_quality_desc.grid(row=r + 1, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 10))

        self.v_quality.trace_add("write", self._on_quality_change)
        self._on_quality_change()

    def _quality_display(self, key: str) -> str:
        """Texto del desplegable para un preset: el nombre, o por qué no está disponible aquí."""
        if key == CUSTOM_PRESET:
            return "Personalizado"
        preset = QUALITY_PRESETS[key]
        if preset_availability(key, self.cuda_devices, self.vulkan_ready).available:
            return preset.label
        return f"{preset.label} (no disponible en este equipo)"

    def _quality_description(self, key: str) -> str:
        if key == CUSTOM_PRESET:
            return (
                "Personalizado: el modelo, el haz, el dispositivo y la precisión guardados "
                "no coinciden con ningún preset. Se guardan tal cual si no eliges otro."
            )
        preset = QUALITY_PRESETS[key]
        avail = preset_availability(key, self.cuda_devices, self.vulkan_ready)
        text = preset.summary
        if not avail.available:
            text += f" ⚠ {avail.reason} Si se guarda igual, Recorder cae a CPU solo, sin romperse."
        return text

    def _current_quality_key(self) -> str:
        return self._quality_key_by_label.get(self.v_quality.get(), CUSTOM_PRESET)

    def _on_quality_change(self, *_args):
        key = self._current_quality_key()
        unavailable = key != CUSTOM_PRESET and not preset_availability(key, self.cuda_devices, self.vulkan_ready).available
        self.lbl_quality_desc.config(fg=ERR if unavailable else DIM)
        self.v_quality_desc.set(self._quality_description(key))

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

        quality_key = self._current_quality_key()
        if quality_key != CUSTOM_PRESET:
            apply_preset(self.config, quality_key)
        # Personalizado: no se toca ningun campo de modelo/haz/dispositivo/precision.

        self.on_save(self.config, notes_changed, devices_changed)
        self.destroy()
