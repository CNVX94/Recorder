import threading
import tkinter as tk
from tkinter import filedialog
from typing import Callable, List, Optional, Tuple
import pyaudiowpatch as pa

from ...actions.screenshot import screen_labels, window_titles
from ...audio.devices import wasapi_devices
from ...config.hardware import HardwareProfile, cached_hardware, peek_hardware
from ...config.options import (
    AUTO_GPU,
    DEFAULT_DEV,
    MAX_THREADS,
    WINDOW_PREFIX,
    SettingsForm,
    apply_settings,
    custom_runtime,
    device_choices,
    gpu_choice,
    gpu_choices,
    quality_description,
    quality_display,
    recommendation_text,
    settings_form,
    target_choices,
    threads_hint,
    use_recommendation,
)
from ...config.schema import (
    AppConfig,
    CUSTOM_PRESET,
    PRESET_ORDER,
    QUALITY_PRESETS,
    Recommendation,
    detect_cuda_device_count,
    preset_availability,
    preset_key_for_config,
    recommend_config,
)
from ...engine.whispercpp import vulkan_readiness, whispercpp_ready, whispercpp_status
from ..theme import ACC, BG, BTN_STYLE, DIM, ENTRY_STYLE, ERR, FG, LABEL_STYLE, PANEL, SUCCESS, fit_window
from .tuning_dialog import TuningDialog

# Color del estado de la carpeta de whisper.cpp según su nivel (ver `whispercpp_status`).
STATUS_COLOR = {"ok": SUCCESS, "warning": ERR, "info": DIM}


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
        # El perfil lo detecta la sesión al arrancar en otro hilo (~1 s); si aún no está, el
        # diálogo se abre igual y la recomendación aparece cuando llegue.
        self.hardware: Optional[HardwareProfile] = peek_hardware()
        # 0 si no hay GPU CUDA o falla la consulta
        self.cuda_devices = self.hardware.cuda_devices if self.hardware else detect_cuda_device_count()
        self.rec: Optional[Recommendation] = None
        # (modelo, haz, dispositivo, precisión) puestos por «Usar recomendado» cuando no es un preset
        self._custom_values: Optional[Tuple[str, int, str, str]] = None
        self._init_variables()
        self.vulkan_ready = self._extra_vulkan_ready()
        self._build_ui()
        self._refresh_engine()
        fit_window(self, 680, 600)
        if self.hardware is None:
            self._hw_result: List[HardwareProfile] = []
            threading.Thread(target=lambda: self._hw_result.append(cached_hardware()), daemon=True).start()
            self.after(200, self._poll_hardware)

    def _init_variables(self):
        f = settings_form(self.config, self.screens)
        self.v_notes = tk.StringVar(value=f.notes_dir)
        self.v_caps = tk.StringVar(value=f.caps_dir)
        self.v_keywords = tk.StringVar(value=f.keywords)
        self.v_mic = tk.BooleanVar(value=f.mic)
        self.v_out_dev = tk.StringVar(value=f.out_dev)
        self.v_mic_dev = tk.StringVar(value=f.mic_dev)
        self.v_screen = tk.StringVar(value=f.target)
        self.v_threads = tk.StringVar(value=f.cpu_threads)
        self.v_wcpp_dir = tk.StringVar(value=f.whispercpp_dir)
        self.v_flash = tk.BooleanVar(value=f.whispercpp_flash_attn)
        self.v_gpu = tk.StringVar()

    def _form(self) -> SettingsForm:
        """Lo que hay escrito y elegido ahora en la ventana, como valores planos."""
        return SettingsForm(
            notes_dir=self.v_notes.get(),
            caps_dir=self.v_caps.get(),
            keywords=self.v_keywords.get(),
            out_dev=self.v_out_dev.get(),
            mic_dev=self.v_mic_dev.get(),
            mic=self.v_mic.get(),
            target=self.v_screen.get(),
            quality=self._current_quality_key(),
            custom_values=self._custom_values,
            cpu_threads=self.v_threads.get(),
            whispercpp_dir=self.v_wcpp_dir.get(),
            whispercpp_flash_attn=self.v_flash.get(),
            whispercpp_device=self._gpu_choices_map.get(self.v_gpu.get(), -1),
        )

    def _build_ui(self):
        # Filas de configuración
        self._row_entry(0, "Carpeta de notas (.md):", self.v_notes, browse=True)
        self._row_entry(1, "Carpeta de capturas:", self.v_caps, browse=True)
        self._row_entry(2, "Palabras clave (coma):", self.v_keywords)

        out_devs = device_choices(wasapi_devices(self.pa, "out"))
        mic_devs = device_choices(wasapi_devices(self.pa, "mic"))
        self._row_choice(3, "Salida a capturar 🔊:", self.v_out_dev, out_devs)
        self._row_choice(4, "Micrófono 🎤:", self.v_mic_dev, mic_devs)
        self.om_target = self._row_choice(5, "Qué capturar 📸:", self.v_screen, self._targets())
        tk.Button(self, text="🔄", command=self._refresh_targets, **BTN_STYLE).grid(row=5, column=2, padx=(6, 16))
        self._build_quality_row(6)  # fila 6 = selector, fila 7 = descripción (se aplica al reiniciar)
        self._build_recommendation_row(8)
        self._build_engine_rows(9)  # filas 9 a 12: hilos, whisper.cpp, su estado y la GPU de Vulkan

        bottom = tk.Frame(self, bg=BG)
        bottom.grid(row=13, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 4))
        tk.Checkbutton(
            bottom,
            text="Transcribir también mi micrófono 🎤",
            variable=self.v_mic,
            bg=BG,
            fg=FG,
            selectcolor=PANEL,
            activebackground=BG,
            activeforeground=FG,
            font=("Segoe UI", 10),
        ).pack(side="left")

        # Botón destacado para calibrar alucinaciones
        tk.Button(
            bottom,
            text="🎯 Calibrar Alucinaciones & Vocabulario...",
            command=self._open_tuning,
            bg=PANEL,
            fg=ACC,
            relief="flat",
            font=("Segoe UI Semibold", 10),
            padx=12,
            pady=4,
        ).pack(side="right")

        # Botonera inferior
        btn_box = tk.Frame(self, bg=BG)
        btn_box.grid(row=14, column=1, columnspan=2, sticky="e", padx=16, pady=10)

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

    def _row_choice(self, r: int, text: str, var: tk.StringVar, choices: List[str]):
        tk.Label(self, text=text, **LABEL_STYLE).grid(row=r, column=0, sticky="w", padx=16, pady=6)
        om = tk.OptionMenu(self, var, *choices)
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

    # ------------------------------------------------------------------ calidad
    def _build_quality_row(self, r: int):
        """Selector de calidad: la decisión principal, con una línea que explica cada preset."""
        tk.Label(
            self,
            text="Calidad de transcripción (se aplica al reiniciar):",
            bg=BG,
            fg=FG,
            font=("Segoe UI Semibold", 10),
        ).grid(row=r, column=0, sticky="w", padx=16, pady=(10, 2))

        self.v_quality = tk.StringVar()
        self.om_quality = tk.OptionMenu(self, self.v_quality, "")
        self.om_quality.config(
            bg=PANEL,
            fg=ACC,
            activebackground=ACC,
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI Semibold", 10),
            anchor="w",
            width=40,
        )
        self.om_quality["menu"].config(bg=PANEL, fg=FG, activebackground=ACC)
        self.om_quality.grid(row=r, column=1, sticky="ew", padx=(0, 16), pady=(10, 2))
        self._rebuild_quality_menu(preset_key_for_config(self.config) or CUSTOM_PRESET)

        self.v_quality_desc = tk.StringVar()
        self.lbl_quality_desc = tk.Label(
            self,
            textvariable=self.v_quality_desc,
            bg=BG,
            fg=DIM,
            font=("Segoe UI", 9),
            wraplength=620,
            justify="left",
            anchor="w",
        )
        self.lbl_quality_desc.grid(row=r + 1, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 6))

        self.v_quality.trace_add("write", self._on_quality_change)
        self._on_quality_change()

    def _rebuild_quality_menu(self, current_key: str):
        """Rehace las etiquetas del desplegable: la disponibilidad de Extra cambia con la carpeta de whisper.cpp."""
        keys = PRESET_ORDER + [CUSTOM_PRESET]
        self._quality_label_by_key = {k: quality_display(k, self.cuda_devices, self.vulkan_ready) for k in keys}
        self._quality_key_by_label = {v: k for k, v in self._quality_label_by_key.items()}
        menu = self.om_quality["menu"]
        menu.delete(0, "end")
        for k in keys:
            label = self._quality_label_by_key[k]
            menu.add_command(label=label, command=lambda v=label: self.v_quality.set(v))
        self.v_quality.set(self._quality_label_by_key[current_key])

    def _current_quality_key(self) -> str:
        return self._quality_key_by_label.get(self.v_quality.get(), CUSTOM_PRESET)

    def _on_quality_change(self, *_args):
        if not hasattr(self, "lbl_quality_desc"):
            return  # el desplegable se rellena antes de existir la descripción
        key = self._current_quality_key()
        unavailable = key != CUSTOM_PRESET and not preset_availability(key, self.cuda_devices, self.vulkan_ready).available
        self.lbl_quality_desc.config(fg=ERR if unavailable else DIM)
        self.v_quality_desc.set(
            quality_description(
                key, custom_runtime(self.config, self._custom_values), self.rec, self.cuda_devices, self.vulkan_ready
            )
        )

    # ------------------------------------------------------------------ recomendación
    def _build_recommendation_row(self, r: int):
        box = tk.Frame(self, bg=BG)
        box.grid(row=r, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 6))
        box.columnconfigure(0, weight=1)
        self.v_rec = tk.StringVar()
        tk.Label(
            box, textvariable=self.v_rec, bg=BG, fg=SUCCESS, font=("Segoe UI", 9),
            wraplength=480, justify="left", anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.btn_rec = tk.Button(box, text="Usar recomendado", command=self._use_recommended, **BTN_STYLE)
        self.btn_rec.grid(row=0, column=1, sticky="ne", padx=(8, 0))

    def _refresh_recommendation(self):
        if self.hardware is None:
            self.rec = None
        else:
            self.rec = recommend_config(self.hardware, *vulkan_readiness(self.v_wcpp_dir.get().strip()))
        self.v_rec.set(recommendation_text(self.rec))
        self.btn_rec.config(state="disabled" if self.rec is None else "normal")

    def _use_recommended(self):
        rec = self.rec
        if rec is None:
            return
        form = self._form()
        use_recommendation(form, rec)
        self._custom_values = form.custom_values
        self.v_quality.set(self._quality_label_by_key[form.quality])
        self.v_threads.set(form.cpu_threads)
        self.v_flash.set(form.whispercpp_flash_attn)

    # ------------------------------------------------------------------ motor
    def _build_engine_rows(self, r: int):
        tk.Label(self, text="Hilos de CPU:", **LABEL_STYLE).grid(row=r, column=0, sticky="w", padx=16, pady=4)
        fila = tk.Frame(self, bg=BG)
        fila.grid(row=r, column=1, columnspan=2, sticky="ew", padx=(0, 16))
        tk.Spinbox(
            fila, from_=0, to=MAX_THREADS, width=5, textvariable=self.v_threads,
            buttonbackground=PANEL, **ENTRY_STYLE,
        ).pack(side="left", ipady=2)
        self.v_threads_hint = tk.StringVar()
        tk.Label(fila, textvariable=self.v_threads_hint, **LABEL_STYLE).pack(side="left", padx=(8, 0))

        tk.Label(self, text="whisper.cpp (GPU AMD/Intel):", **LABEL_STYLE).grid(
            row=r + 1, column=0, sticky="w", padx=16, pady=4
        )
        tk.Entry(self, textvariable=self.v_wcpp_dir, width=46, **ENTRY_STYLE).grid(
            row=r + 1, column=1, ipady=4, sticky="ew"
        )
        tk.Button(
            self,
            text="📁",
            command=lambda: self.v_wcpp_dir.set(
                filedialog.askdirectory(initialdir=self.v_wcpp_dir.get() or None) or self.v_wcpp_dir.get()
            ),
            **BTN_STYLE,
        ).grid(row=r + 1, column=2, padx=(6, 16))
        self.v_wcpp_status = tk.StringVar()
        self.lbl_wcpp_status = tk.Label(
            self, textvariable=self.v_wcpp_status, bg=BG, fg=DIM, font=("Segoe UI", 9),
            wraplength=620, justify="left", anchor="w",
        )
        self.lbl_wcpp_status.grid(row=r + 2, column=0, columnspan=3, sticky="ew", padx=16)

        tk.Label(self, text="GPU de whisper.cpp:", **LABEL_STYLE).grid(row=r + 3, column=0, sticky="w", padx=16, pady=4)
        fila = tk.Frame(self, bg=BG)
        fila.grid(row=r + 3, column=1, columnspan=2, sticky="ew", padx=(0, 16))
        self.om_gpu = tk.OptionMenu(fila, self.v_gpu, AUTO_GPU)
        self.om_gpu.config(
            bg=PANEL, fg=FG, activebackground=ACC, relief="flat", highlightthickness=0,
            font=("Segoe UI", 10), anchor="w", width=30,
        )
        self.om_gpu["menu"].config(bg=PANEL, fg=FG, activebackground=ACC)
        self.om_gpu.pack(side="left")
        tk.Checkbutton(
            fila, text="Flash attention", variable=self.v_flash, bg=BG, fg=FG, selectcolor=PANEL,
            activebackground=BG, activeforeground=FG, font=("Segoe UI", 10),
        ).pack(side="left", padx=(10, 0))
        self._rebuild_gpu_menu()
        self.v_wcpp_dir.trace_add("write", lambda *_: self._refresh_engine())

    def _rebuild_gpu_menu(self):
        previo = self._gpu_choices_map.get(self.v_gpu.get()) if hasattr(self, "_gpu_choices_map") else None
        elegido = self.config.whispercpp_device if previo is None else previo
        vulkan = self.hardware.vulkan_devices if self.hardware else []
        self._gpu_choices_map = gpu_choices(vulkan, self.config.whispercpp_device)
        menu = self.om_gpu["menu"]
        menu.delete(0, "end")
        for label in self._gpu_choices_map:
            menu.add_command(label=label, command=lambda v=label: self.v_gpu.set(v))
        self.v_gpu.set(gpu_choice(self._gpu_choices_map, elegido))

    def _refresh_engine(self):
        """Lo que depende de la carpeta de whisper.cpp o del perfil: estado, Extra y recomendación."""
        estado = whispercpp_status(self.v_wcpp_dir.get(), self.hardware)
        self.v_wcpp_status.set(estado.text)
        self.lbl_wcpp_status.config(fg=STATUS_COLOR[estado.level])
        ready = self._extra_vulkan_ready()
        if ready != self.vulkan_ready:
            self.vulkan_ready = ready
            self._rebuild_quality_menu(self._current_quality_key())
        self._refresh_recommendation()
        self._on_quality_change()
        self.v_threads_hint.set(threads_hint(self.hardware))
        self._grow_to_fit()

    def _grow_to_fit(self):
        """Si un texto creció después de dimensionar (perfil que llega tarde, otra carpeta), agranda sin mover."""
        if not self.winfo_ismapped():
            return  # aún sin mostrar: fit_window ya mide el contenido
        self.update_idletasks()
        w = min(max(self.winfo_width(), self.winfo_reqwidth()), self.winfo_screenwidth() - 16)
        h = min(max(self.winfo_height(), self.winfo_reqheight()), self.winfo_screenheight() - 80)
        if (w, h) != (self.winfo_width(), self.winfo_height()):
            self.geometry(f"{w}x{h}")

    def _extra_vulkan_ready(self) -> bool:
        extra = QUALITY_PRESETS["extra"]
        return whispercpp_ready(self.v_wcpp_dir.get().strip(), extra.model, extra.compute_type)

    def _poll_hardware(self):
        if not self.winfo_exists():
            return
        if not self._hw_result:
            self.after(200, self._poll_hardware)
            return
        self.hardware = self._hw_result[0]
        self.cuda_devices = self.hardware.cuda_devices
        self._rebuild_quality_menu(self._current_quality_key())
        self._rebuild_gpu_menu()
        self._refresh_engine()

    # ------------------------------------------------------------------ captura
    def _targets(self) -> List[str]:
        """Opciones de captura: las pantallas y las ventanas abiertas ahora (más la guardada, aunque esté cerrada)."""
        return target_choices(self.screens, window_titles(), self.config.window)

    def _refresh_targets(self):
        """Las ventanas abiertas cambian: vuelve a leerlas y reconstruye el desplegable."""
        menu = self.om_target["menu"]
        menu.delete(0, "end")
        for label in self._targets():
            menu.add_command(label=label, command=lambda v=label: self.v_screen.set(v))

    def _open_tuning(self):
        TuningDialog(self, self.config, on_save=lambda cfg: None)

    def _save(self):
        cambios = apply_settings(self.config, self._form(), self.screens)
        self.on_save(self.config, cambios.notes_changed, cambios.devices_changed)
        self.destroy()
