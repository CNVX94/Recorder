import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from ...config.schema import AppConfig
from ...filters.samples import random_sample
from ...filters.tuning import (
    ECHO_FILTER_LABEL,
    THRESHOLD_RANGES,
    VOCAB_HINT,
    TuningForm,
    apply_tuning,
    format_ignore,
    parse_ignore,
    test_phrase,
    tuning_form,
    with_common_ignore,
)
from ..theme import ACC, BG, BTN_STYLE, DIM, ENTRY_STYLE, ERR, FG, LABEL_STYLE, PANEL, SUCCESS, fit_window


class TuningDialog(tk.Toplevel):
    """Ventana de calibración fina (fine-tuning) para filtros anti-alucinaciones y léxico personal."""

    def __init__(
        self,
        parent: tk.Widget,
        config: AppConfig,
        on_save: Callable[[AppConfig], None],
    ):
        super().__init__(parent)
        self.config = config
        self.on_save = on_save

        self.title("Calibración Anti-Alucinaciones & Léxico Personal")
        self.configure(bg=BG)
        self.transient(parent)
        self.grab_set()

        self._init_variables()
        self._build_ui()
        fit_window(self, 720, 730)

    def _init_variables(self):
        f = tuning_form(self.config)
        self.var_vocab = tk.StringVar(value=f.vocab)
        self.var_ignore = tk.StringVar(value=f.ignore)
        self.var_fixes = tk.StringVar(value=f.fixes)
        self.var_no_speech = tk.DoubleVar(value=f.no_speech_threshold)
        self.var_logprob = tk.DoubleVar(value=f.logprob_threshold)
        self.var_compression = tk.DoubleVar(value=f.compression_ratio_threshold)
        self.var_echo_filter = tk.BooleanVar(value=f.echo_filter)

        # Sandbox
        self.var_test_input = tk.StringVar(value="Desplegamos en cuba y en el ayayas. ¡Suscríbete!")
        self.var_test_result = tk.StringVar(value="")

    def _form(self) -> TuningForm:
        """Lo que hay escrito ahora en la ventana, como valores planos."""
        return TuningForm(
            vocab=self.var_vocab.get(),
            ignore=self.var_ignore.get(),
            fixes=self.var_fixes.get(),
            no_speech_threshold=self.var_no_speech.get(),
            logprob_threshold=self.var_logprob.get(),
            compression_ratio_threshold=self.var_compression.get(),
            echo_filter=self.var_echo_filter.get(),
        )

    def _build_ui(self):
        pad = {"padx": 16, "pady": 6}

        # Título
        header = tk.Label(
            self,
            text="🎯 Calibración Anti-Alucinaciones y Léxico Personal",
            bg=BG,
            fg=ACC,
            font=("Segoe UI Semibold", 13),
        )
        header.pack(fill="x", padx=16, pady=(14, 8))

        desc = tk.Label(
            self,
            text=(
                "Ajusta cómo Whisper interpreta tu vocabulario técnico y filtra frases fantasma en silencios."
            ),
            bg=BG,
            fg=DIM,
            font=("Segoe UI", 9),
            wraplength=680,
            justify="left",
        )
        desc.pack(fill="x", padx=16, pady=(0, 10))

        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=16)

        # 1. Vocabulario de contexto (Initial prompt)
        lbl_vocab = tk.Label(
            container,
            text="1. Vocabulario de contexto / Initial Prompt (guía a Whisper antes de oír):",
            **{**LABEL_STYLE, "font": ("Segoe UI Semibold", 9)},
        )
        lbl_vocab.pack(anchor="w", pady=(4, 2))
        ent_vocab = tk.Entry(container, textvariable=self.var_vocab, **ENTRY_STYLE)
        ent_vocab.pack(fill="x", ipady=4)
        tk.Label(
            container, text=VOCAB_HINT, bg=BG, fg=DIM, font=("Segoe UI", 8), wraplength=680, justify="left",
        ).pack(anchor="w", pady=(2, 0))
        tk.Checkbutton(
            container, text=ECHO_FILTER_LABEL, variable=self.var_echo_filter, command=self._run_test,
            bg=BG, fg=FG, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
            font=("Segoe UI", 9), anchor="w",
        ).pack(anchor="w", pady=(2, 0))

        # 2. Frases prohibidas / Lista negra (Blacklist)
        f_ignore = tk.Frame(container, bg=BG)
        f_ignore.pack(fill="x", pady=(10, 2))
        lbl_ignore = tk.Label(
            f_ignore,
            text="2. Frases prohibidas / Alucinaciones a descartar (separadas por coma):",
            **{**LABEL_STYLE, "font": ("Segoe UI Semibold", 9)},
        )
        lbl_ignore.pack(side="left")

        btn_preset = tk.Button(
            f_ignore,
            text="+ Añadir comunes",
            command=self._append_common_ignore,
            bg=PANEL,
            fg=ACC,
            relief="flat",
            font=("Segoe UI", 8),
            padx=6,
            pady=1,
        )
        btn_preset.pack(side="right")

        ent_ignore = tk.Entry(container, textvariable=self.var_ignore, **ENTRY_STYLE)
        ent_ignore.pack(fill="x", ipady=4)

        # 3. Diccionario fonético / Reemplazos (Fixes)
        lbl_fixes = tk.Label(
            container,
            text="3. Correcciones de léxico personal ('oído_mal=escrito_bien; ...'):",
            **{**LABEL_STYLE, "font": ("Segoe UI Semibold", 9)},
        )
        lbl_fixes.pack(anchor="w", pady=(10, 2))
        ent_fixes = tk.Entry(container, textvariable=self.var_fixes, **ENTRY_STYLE)
        ent_fixes.pack(fill="x", ipady=4)

        # 4. Umbrales heurísticos (Sliders de calidad)
        sliders_frame = tk.Frame(container, bg=PANEL, padx=12, pady=8)
        sliders_frame.pack(fill="x", pady=12)

        lbl_sliders_title = tk.Label(
            sliders_frame,
            text="4. Umbrales Heurísticos del Decodificador:",
            bg=PANEL,
            fg=FG,
            font=("Segoe UI Semibold", 9),
        )
        lbl_sliders_title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))

        # Slider no_speech
        tk.Label(
            sliders_frame,
            text="Filtro silencio (no_speech_prob > X descarta):",
            bg=PANEL,
            fg=DIM,
            font=("Segoe UI", 9),
        ).grid(row=1, column=0, sticky="w")
        lo, hi, paso = THRESHOLD_RANGES["no_speech_threshold"]
        sc_no_speech = tk.Scale(
            sliders_frame,
            variable=self.var_no_speech,
            from_=lo,
            to=hi,
            resolution=paso,
            orient="horizontal",
            bg=PANEL,
            fg=FG,
            highlightthickness=0,
            troughcolor=BG,
            length=180,
        )
        sc_no_speech.grid(row=1, column=1, sticky="w", padx=10)

        # Slider logprob
        tk.Label(
            sliders_frame,
            text="Confianza mínima (avg_logprob < X descarta):",
            bg=PANEL,
            fg=DIM,
            font=("Segoe UI", 9),
        ).grid(row=2, column=0, sticky="w")
        lo, hi, paso = THRESHOLD_RANGES["logprob_threshold"]
        sc_logprob = tk.Scale(
            sliders_frame,
            variable=self.var_logprob,
            from_=lo,
            to=hi,
            resolution=paso,
            orient="horizontal",
            bg=PANEL,
            fg=FG,
            highlightthickness=0,
            troughcolor=BG,
            length=180,
        )
        sc_logprob.grid(row=2, column=1, sticky="w", padx=10)

        # Slider compression
        tk.Label(
            sliders_frame,
            text="Anti-bucles repetición (ratio compresión > X descarta):",
            bg=PANEL,
            fg=DIM,
            font=("Segoe UI", 9),
        ).grid(row=3, column=0, sticky="w")
        lo, hi, paso = THRESHOLD_RANGES["compression_ratio_threshold"]
        sc_comp = tk.Scale(
            sliders_frame,
            variable=self.var_compression,
            from_=lo,
            to=hi,
            resolution=paso,
            orient="horizontal",
            bg=PANEL,
            fg=FG,
            highlightthickness=0,
            troughcolor=BG,
            length=180,
        )
        sc_comp.grid(row=3, column=1, sticky="w", padx=10)

        # 5. Sandbox de prueba interactivo
        sandbox = tk.LabelFrame(
            container,
            text="🧪 Sandbox de Prueba en Vivo",
            bg=BG,
            fg=ACC,
            font=("Segoe UI Semibold", 9),
            padx=10,
            pady=8,
        )
        sandbox.pack(fill="x", pady=(4, 10))

        test_row = tk.Frame(sandbox, bg=BG)
        test_row.pack(fill="x")
        btn_test = tk.Button(
            test_row,
            text="⚡ Probar Reglas",
            command=self._run_test,
            bg=PANEL,
            fg=ACC,
            relief="flat",
            font=("Segoe UI", 9),
            padx=8,
        )
        btn_test.pack(side="right", padx=(8, 0))
        btn_random = tk.Button(
            test_row,
            text="🎲 Frase de ejemplo",
            command=self._random_sample,
            bg=PANEL,
            fg=FG,
            relief="flat",
            font=("Segoe UI", 9),
            padx=8,
        )
        btn_random.pack(side="right", padx=(8, 0))
        tk.Entry(test_row, textvariable=self.var_test_input, **ENTRY_STYLE).pack(
            side="left", fill="x", expand=True, ipady=4
        )

        self.lbl_test_status = tk.Label(
            sandbox,
            textvariable=self.var_test_result,
            bg=BG,
            fg=DIM,
            font=("Segoe UI", 9),
            anchor="w",
            justify="left",
            wraplength=640,
        )
        self.lbl_test_status.pack(fill="x", pady=(6, 2))

        # Botonera inferior
        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", padx=16, pady=(8, 16))

        tk.Button(
            actions,
            text="Cancelar",
            command=self.destroy,
            bg=PANEL,
            fg=DIM,
            relief="flat",
            padx=12,
            font=("Segoe UI", 9),
        ).pack(side="right", padx=(8, 0))

        tk.Button(
            actions,
            text="💾 Guardar Calibración",
            command=self._save_changes,
            **BTN_STYLE,
        ).pack(side="right")

        self._run_test()

    def _append_common_ignore(self):
        self.var_ignore.set(format_ignore(with_common_ignore(parse_ignore(self.var_ignore.get()))))
        self._run_test()

    def _random_sample(self):
        """Genera una frase de ejemplo con el glosario escrito ahora mismo en el dialogo."""
        f = self._form()
        self.var_test_input.set(random_sample(f.vocab, f.fixes_dict, f.ignore_list, self.config.keywords))
        self._run_test()

    def _run_test(self):
        veredicto = test_phrase(self._form(), self.var_test_input.get(), self.config.keywords)
        self.lbl_test_status.config(fg=SUCCESS if veredicto.accepted else ERR)
        self.var_test_result.set(veredicto.message)

    def _save_changes(self):
        apply_tuning(self.config, self._form())
        self.on_save(self.config)
        self.destroy()
