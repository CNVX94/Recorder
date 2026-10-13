import pathlib
import threading
import tkinter as tk
from tkinter import filedialog
from typing import Callable, Dict, List, Optional, Tuple
import pyaudiowpatch as pa

from ...actions.screenshot import screen_labels, window_titles
from ...audio.devices import wasapi_devices
from ...config.hardware import HardwareProfile, cached_hardware, describe_gpu, peek_hardware
from ...config.schema import (
    AppConfig,
    CUSTOM_PRESET,
    PRESET_ORDER,
    QUALITY_PRESETS,
    Recommendation,
    apply_preset,
    describe_recommendation,
    describe_runtime,
    detect_cuda_device_count,
    preset_availability,
    preset_key_for_config,
    recommend_config,
    recommended_cpu_threads,
)
from ...engine.whispercpp import installed_models, server_exe_path, vulkan_readiness, whispercpp_ready
from ..theme import ACC, BG, BTN_STYLE, DIM, ENTRY_STYLE, ERR, FG, LABEL_STYLE, PANEL, SUCCESS, fit_window
from .tuning_dialog import TuningDialog

DEFAULT_DEV = "(predeterminado de Windows)"
WINDOW_PREFIX = "Ventana: "  # distingue en el selector una ventana de aplicación de una pantalla
AUTO_GPU = "Automática (dedicada)"
MAX_THREADS = 256


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
        # El perfil lo detecta MainWindow al arrancar en otro hilo (~1 s); si aún no está, el
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
        self.v_threads = tk.StringVar(value=str(self.config.cpu_threads))
        self.v_wcpp_dir = tk.StringVar(value=self.config.whispercpp_dir)
        self.v_flash = tk.BooleanVar(value=self.config.whispercpp_flash_attn)
        self.v_gpu = tk.StringVar()

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
        self._quality_label_by_key = {k: self._quality_display(k) for k in keys}
        self._quality_key_by_label = {v: k for k, v in self._quality_label_by_key.items()}
        menu = self.om_quality["menu"]
        menu.delete(0, "end")
        for k in keys:
            label = self._quality_label_by_key[k]
            menu.add_command(label=label, command=lambda v=label: self.v_quality.set(v))
        self.v_quality.set(self._quality_label_by_key[current_key])

    def _quality_display(self, key: str) -> str:
        """Texto del desplegable para un preset: el nombre, o por qué no está disponible aquí."""
        if key == CUSTOM_PRESET:
            return "Personalizado"
        preset = QUALITY_PRESETS[key]
        if preset_availability(key, self.cuda_devices, self.vulkan_ready).available:
            return preset.label
        return f"{preset.label} (no disponible en este equipo)"

    def _custom_runtime(self) -> Tuple[str, int, str, str]:
        """Lo que se guarda con «Personalizado»: lo de «Usar recomendado» o lo que ya había."""
        c = self.config
        return self._custom_values or (c.model, c.beam_size, c.device, c.compute_type)

    def _quality_description(self, key: str) -> str:
        if key == CUSTOM_PRESET:
            valores = self._custom_runtime()
            es_rec = self.rec is not None and valores == (
                self.rec.model, self.rec.beam_size, self.rec.device, self.rec.compute_type
            )
            return (
                f"Personalizado: {describe_runtime(*valores)}"
                f"{' (la recomendada para este equipo)' if es_rec else ''}. "
                "No coincide con ningún preset; se guarda tal cual si no eliges otro."
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
        if not hasattr(self, "lbl_quality_desc"):
            return  # el desplegable se rellena antes de existir la descripción
        key = self._current_quality_key()
        unavailable = key != CUSTOM_PRESET and not preset_availability(key, self.cuda_devices, self.vulkan_ready).available
        self.lbl_quality_desc.config(fg=ERR if unavailable else DIM)
        self.v_quality_desc.set(self._quality_description(key))

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
            self.v_rec.set("Recomendado para este equipo: detectando el equipo…")
            self.btn_rec.config(state="disabled")
            return
        self.rec = recommend_config(self.hardware, *vulkan_readiness(self.v_wcpp_dir.get().strip()))
        self.v_rec.set(
            f"Recomendado para este equipo: {describe_recommendation(self.rec)} — {self.rec.reason} "
            f"[{self.rec.confidence}]"
        )
        self.btn_rec.config(state="normal")

    def _use_recommended(self):
        rec = self.rec
        if rec is None:
            return
        if rec.preset:
            self._custom_values = None
            self.v_quality.set(self._quality_label_by_key[rec.preset])
        else:
            self._custom_values = (rec.model, rec.beam_size, rec.device, rec.compute_type)
            self.v_quality.set(self._quality_label_by_key[CUSTOM_PRESET])
        self.v_threads.set(str(rec.cpu_threads))
        if rec.engine == "whisper.cpp":
            self.v_flash.set(rec.flash_attn)

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

    def _gpu_choices(self) -> Dict[str, int]:
        """Etiqueta del desplegable -> whispercpp_device."""
        opciones = {AUTO_GPU: -1}
        for g in (self.hardware.vulkan_devices if self.hardware else []):
            opciones[f"{g.vulkan_index}: {describe_gpu(g)}"] = g.vulkan_index
        actual = self.config.whispercpp_device
        if actual >= 0 and actual not in opciones.values():
            opciones[f"{actual}: (no detectada ahora)"] = actual
        return opciones

    def _rebuild_gpu_menu(self):
        previo = self._gpu_choices_map.get(self.v_gpu.get()) if hasattr(self, "_gpu_choices_map") else None
        elegido = self.config.whispercpp_device if previo is None else previo
        self._gpu_choices_map = self._gpu_choices()
        menu = self.om_gpu["menu"]
        menu.delete(0, "end")
        for label in self._gpu_choices_map:
            menu.add_command(label=label, command=lambda v=label: self.v_gpu.set(v))
        self.v_gpu.set(next((k for k, v in self._gpu_choices_map.items() if v == elegido), AUTO_GPU))

    def _wcpp_status(self) -> Tuple[str, str]:
        """(texto, color) del estado de la carpeta de whisper.cpp."""
        carpeta = self.v_wcpp_dir.get().strip()
        dgpu = None
        if self.hardware is not None and self.cuda_devices <= 0:
            dgpu = self.hardware.best_vulkan_discrete
        if not carpeta:
            if dgpu is not None:
                return (
                    f"⚠ Vacía: la GPU {describe_gpu(dgpu)} no se usa. Ejecuta tools\\instalar_whispercpp.ps1 "
                    f"(docs/gpu-amd-vulkan.md) o indica aquí su carpeta.", ERR,
                )
            return "Vacía: sin motor Vulkan. Solo hace falta para una GPU AMD o Intel (docs/gpu-amd-vulkan.md).", DIM
        if not server_exe_path(pathlib.Path(carpeta)).is_file():
            return f"⚠ No hay bin\\whisper-server.exe en «{carpeta}».", ERR
        modelos = installed_models(carpeta)
        if not modelos:
            return "⚠ whisper-server encontrado, pero no hay modelos ggml en models\\.", ERR
        return f"✔ whisper-server y modelos: {', '.join(modelos)}.", SUCCESS

    def _refresh_engine(self):
        """Lo que depende de la carpeta de whisper.cpp o del perfil: estado, Extra y recomendación."""
        texto, color = self._wcpp_status()
        self.v_wcpp_status.set(texto)
        self.lbl_wcpp_status.config(fg=color)
        ready = self._extra_vulkan_ready()
        if ready != self.vulkan_ready:
            self.vulkan_ready = ready
            self._rebuild_quality_menu(self._current_quality_key())
        self._refresh_recommendation()
        self._on_quality_change()
        if self.hardware is not None:
            p = self.hardware
            nucleos = f"{p.physical_cores} núcleos" if p.physical_cores else f"{p.logical_cores} hilos"
            self.v_threads_hint.set(f"0 = 4 de la biblioteca · recomendado: {recommended_cpu_threads(p)} ({nucleos})")
        else:
            self.v_threads_hint.set("0 = 4 de la biblioteca")
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
        elif self._custom_values:
            c = self.config
            c.model, c.beam_size, c.device, c.compute_type = self._custom_values
        # Personalizado sin «Usar recomendado»: no se toca ningun campo de modelo/haz/dispositivo/precision.

        try:
            self.config.cpu_threads = min(max(int(self.v_threads.get().strip()), 0), MAX_THREADS)
        except ValueError:
            pass  # texto no numerico: se conserva el valor anterior
        self.config.whispercpp_dir = self.v_wcpp_dir.get().strip()
        self.config.whispercpp_flash_attn = self.v_flash.get()
        self.config.whispercpp_device = self._gpu_choices_map.get(self.v_gpu.get(), -1)

        self.on_save(self.config, notes_changed, devices_changed)
        self.destroy()
