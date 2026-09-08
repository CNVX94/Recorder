import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from ...config.schema import AppConfig
from ...filters.lexicon import format_fixes, parse_fixes
from ...filters.pipeline import TextPipeline
from ..theme import ACC, BG, BTN_STYLE, DIM, ENTRY_STYLE, ERR, FG, LABEL_STYLE, PANEL, SUCCESS


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
        self.geometry("720x680")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._init_variables()
        self._build_ui()

    def _init_variables(self):
        self.var_vocab = tk.StringVar(value=self.config.vocab)
        self.var_ignore = tk.StringVar(value=", ".join(self.config.ignore))
        self.var_fixes = tk.StringVar(value=format_fixes(self.config.fixes))
        self.var_no_speech = tk.DoubleVar(value=self.config.no_speech_threshold)
        self.var_logprob = tk.DoubleVar(value=self.config.logprob_threshold)
        self.var_compression = tk.DoubleVar(value=self.config.compression_ratio_threshold)

        # Sandbox
        self.var_test_input = tk.StringVar(value="Desplegamos en cuba y en el ayayas. ¡Suscríbete!")
        self.var_test_result = tk.StringVar(value="")

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
        sc_no_speech = tk.Scale(
            sliders_frame,
            variable=self.var_no_speech,
            from_=0.1,
            to=0.95,
            resolution=0.05,
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
        sc_logprob = tk.Scale(
            sliders_frame,
            variable=self.var_logprob,
            from_=-2.5,
            to=-0.2,
            resolution=0.1,
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
        sc_comp = tk.Scale(
            sliders_frame,
            variable=self.var_compression,
            from_=1.5,
            to=3.5,
            resolution=0.1,
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
        tk.Entry(test_row, textvariable=self.var_test_input, **ENTRY_STYLE).pack(
            side="left", fill="x", expand=True, ipady=4
        )
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
        common = [
            "suscríbete",
            "gracias por ver",
            "amara.org",
            "hasta el próximo vídeo",
            "subtítulos por",
            "dale a la campanita",
        ]
        current = [x.strip() for x in self.var_ignore.get().split(",") if x.strip()]
        for c in common:
            if c not in current:
                current.append(c)
        self.var_ignore.set(", ".join(current))
        self._run_test()

    def _run_test(self):
        ignore_list = [x.strip() for x in self.var_ignore.get().split(",") if x.strip()]
        fixes_dict = parse_fixes(self.var_fixes.get())
        pipeline = TextPipeline(
            keywords=self.config.keywords,
            ignore=ignore_list,
            fixes=fixes_dict,
            no_speech_thresh=self.var_no_speech.get(),
            logprob_thresh=self.var_logprob.get(),
            compression_ratio_thresh=self.var_compression.get(),
        )

        sample = self.var_test_input.get()
        res = pipeline.test_sample(sample)

        if res["is_ignored"]:
            self.lbl_test_status.config(fg=ERR)
            self.var_test_result.set("⛔ DESCARTADA: Contiene una frase de la lista negra de alucinaciones.")
        else:
            self.lbl_test_status.config(fg=SUCCESS)
            out = f"✅ ACEPTADA: \"{res['processed']}\""
            if res["hits"]:
                out += f"  (📸 Palabras clave detectadas: {', '.join(res['hits'])})"
            self.var_test_result.set(out)

    def _save_changes(self):
        ignore_list = [x.strip() for x in self.var_ignore.get().split(",") if x.strip()]
        fixes_dict = parse_fixes(self.var_fixes.get())

        self.config.vocab = self.var_vocab.get().strip()
        self.config.ignore = ignore_list
        self.config.fixes = fixes_dict
        self.config.no_speech_threshold = float(self.var_no_speech.get())
        self.config.logprob_threshold = float(self.var_logprob.get())
        self.config.compression_ratio_threshold = float(self.var_compression.get())

        self.on_save(self.config)
        self.destroy()
