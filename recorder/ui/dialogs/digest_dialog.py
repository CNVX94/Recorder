"""Dialogo de sintesis de notas.

Implementa el diseno acordado: seleccion de nota origen marcada como solo lectura,
agrupamiento temporal como decision principal, limpieza en rejilla, vista previa en
vivo ampliable, aviso de perdida justo antes del nombre de salida, y botonera.
"""

import datetime as dt
import pathlib
import tkinter as tk
from tkinter import ttk
from typing import List, Optional

from ...config.schema import AppConfig
from ...digest import (
    INTERVALS,
    DerivedSourceError,
    DigestOptions,
    build_digest,
    list_originals,
    unique_digest_path,
    write_digest,
)
from ..theme import ACC, BG, BORDER, BTN_STYLE, DIM, ERR, FG, LABEL_STYLE, MIC, PANEL, SUCCESS

SEMIBOLD = {**LABEL_STYLE, "font": ("Segoe UI Semibold", 9)}
ETIQUETAS = {0: "Sin agrupar", 5: "Cada 5 min", 15: "Cada 15 min", 30: "Cada 30 min", 60: "Cada hora"}
ALTO_NORMAL, ALTO_AMPLIADO = 780, 940
LINEAS_NORMAL, LINEAS_AMPLIADO = 6, 16
PALABRAS_MINIMAS = 4


class DigestDialog(tk.Toplevel):
    """Genera copias resumidas de una nota. El original nunca se modifica."""

    def __init__(self, parent: tk.Widget, config: AppConfig, active_note: Optional[pathlib.Path] = None):
        super().__init__(parent)
        self.config = config
        self.active_note = pathlib.Path(active_note).name if active_note else None
        self.notas: List[pathlib.Path] = list_originals(config.notes_dir)

        self.title("Síntesis de notas")
        self.configure(bg=BG)
        self.geometry(f"760x{ALTO_NORMAL}")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._init_vars()
        self._build_ui()
        if self.notas:
            self.lista.selection_set(0)
            self._refresh()

    # --------------------------------------------------------------- estado
    def _init_vars(self):
        self.ampliado = False
        self.var_interval = tk.IntVar(value=15)
        self.var_merge = tk.BooleanVar(value=True)
        self.var_strip_stamps = tk.BooleanVar(value=True)
        self.var_captures = tk.BooleanVar(value=True)
        self.var_drop = tk.BooleanVar(value=False)
        self.var_stats = tk.StringVar(value="")
        self.var_estado = tk.StringVar(value="")

    def _opciones(self) -> DigestOptions:
        agrupa = self.var_interval.get()
        return DigestOptions(
            interval_min=agrupa,
            merge=self.var_merge.get(),
            drop_short_words=PALABRAS_MINIMAS if self.var_drop.get() else 0,
            keep_captures=self.var_captures.get(),
            # sin agrupar, la marca de tiempo es lo unico que ordena: se conserva siempre
            inline_stamps=not self.var_strip_stamps.get() or not agrupa,
        )

    def _origen(self) -> Optional[pathlib.Path]:
        sel = self.lista.curselection()
        return self.notas[sel[0]] if sel else None

    # ------------------------------------------------------------------- ui
    def _build_ui(self):
        tk.Label(self, text="📑 Síntesis de notas", bg=BG, fg=ACC,
                 font=("Segoe UI Semibold", 13)).pack(fill="x", padx=16, pady=(14, 8))
        tk.Label(
            self,
            text="Crea una copia resumida y agrupada de una nota diaria. El archivo original nunca se "
            "modifica: siempre se genera un clon con otro nombre.",
            bg=BG, fg=DIM, font=("Segoe UI", 9), wraplength=728, justify="left",
        ).pack(fill="x", padx=16, pady=(0, 10))

        cont = tk.Frame(self, bg=BG)
        if self.notas:
            # La botonera se ancla abajo ANTES de empacar el contenido: con pack, lo que se
            # empaca primero reserva su sitio, asi que al ampliar la vista previa los botones
            # nunca quedan fuera de la ventana.
            self._botonera()
        cont.pack(fill="both", expand=True, padx=16)

        if not self.notas:
            tk.Label(cont, text=f"No hay notas originales en {self.config.notes_dir}",
                     bg=BG, fg=ERR, font=("Segoe UI", 10), wraplength=720,
                     justify="left").pack(anchor="w", pady=20)
            tk.Button(self, text="Cerrar", command=self.destroy, **BTN_STYLE).pack(pady=16)
            return

        self._seccion_origen(cont)
        self._seccion_agrupamiento(cont)
        self._seccion_limpieza(cont)
        # El aviso y el nombre de salida se anclan al fondo, en ese orden inverso, para que
        # ampliar la vista previa nunca los empuje fuera. La previa se queda con lo que sobre.
        self._salida(cont)
        self._aviso(cont)
        self._seccion_preview(cont)

    def _seccion_origen(self, cont):
        fila = tk.Frame(cont, bg=BG)
        fila.pack(fill="x", pady=(0, 2))
        tk.Label(fila, text="1. Nota origen (se abre solo para leer):", **SEMIBOLD).pack(side="left")
        tk.Label(fila, text="🔒 SOLO LECTURA", bg=PANEL, fg=SUCCESS,
                 font=("Segoe UI Semibold", 8), padx=6, pady=1).pack(side="right")

        tk.Label(cont, text=f"{'archivo':<32}{'fecha':<12}{'hora':<8}{'tamaño':>9}",
                 bg=BG, fg=DIM, font=("Consolas", 9), anchor="w").pack(fill="x")

        caja = tk.Frame(cont, bg=BG)
        caja.pack(fill="x")
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure("Digest.Vertical.TScrollbar", troughcolor=BG, background=BORDER,
                         bordercolor=BG, arrowcolor=FG)
        scroll = ttk.Scrollbar(caja, orient="vertical", style="Digest.Vertical.TScrollbar")
        scroll.pack(side="right", fill="y")
        self.lista = tk.Listbox(
            caja, height=5, bg=PANEL, fg=FG, font=("Consolas", 9), relief="flat",
            selectbackground=ACC, selectforeground=BG, activestyle="none", exportselection=0,
            highlightthickness=0, yscrollcommand=scroll.set,
        )
        self.lista.pack(side="left", fill="both", expand=True)
        scroll.config(command=self.lista.yview)
        self.lista.bind("<<ListboxSelect>>", lambda _e: self._refresh())

        for p in self.notas:
            m = dt.datetime.fromtimestamp(p.stat().st_mtime)
            marca = " ● en curso" if p.name == self.active_note else ""
            kb = f"{p.stat().st_size / 1024:.0f} KB"
            self.lista.insert("end", f"{p.name:<32}{m:%d/%m/%Y}  {m:%H:%M}  {kb:>9}{marca}")

        pie = tk.Frame(cont, bg=BG)
        pie.pack(fill="x", pady=(2, 0))
        tk.Label(pie, text="🔒 El archivo elegido nunca se modifica, mueve ni renombra.",
                 bg=BG, fg=SUCCESS, font=("Segoe UI", 9)).pack(side="left")
        tk.Label(pie, text="Las síntesis anteriores no se listan.",
                 bg=BG, fg=DIM, font=("Segoe UI", 9)).pack(side="right")

    def _seccion_agrupamiento(self, cont):
        tk.Label(cont, text="2. Agrupamiento temporal:", **SEMIBOLD).pack(anchor="w", pady=(10, 2))
        caja = tk.Frame(cont, bg=PANEL)
        caja.pack(fill="x")
        fila = tk.Frame(caja, bg=PANEL)
        fila.pack(fill="x", padx=12, pady=(8, 2))
        for minutos in INTERVALS:
            tk.Radiobutton(
                fila, text=ETIQUETAS[minutos], variable=self.var_interval, value=minutos,
                command=self._refresh, bg=PANEL, fg=FG, selectcolor=BG, activebackground=PANEL,
                activeforeground=ACC, font=("Segoe UI", 10),
            ).pack(side="left", padx=(0, 18))
        tk.Label(
            caja,
            text="Cada bloque pasa a ser un encabezado como ## 09:30 - 09:45 con sus líneas debajo. "
            "«Sin agrupar» solo aplica la limpieza.",
            bg=PANEL, fg=DIM, font=("Segoe UI", 9), wraplength=700, justify="left",
        ).pack(fill="x", padx=12, pady=(0, 8))

    def _seccion_limpieza(self, cont):
        tk.Label(cont, text="3. Limpieza:", **SEMIBOLD).pack(anchor="w", pady=(10, 2))
        rejilla = tk.Frame(cont, bg=BG)
        rejilla.pack(fill="x")
        rejilla.columnconfigure(0, minsize=356)
        rejilla.columnconfigure(1, minsize=356)
        casillas = [
            ("Unir líneas seguidas del mismo hablante", self.var_merge, 0, 0),
            ("Quitar marcas de tiempo dentro de cada bloque", self.var_strip_stamps, 0, 1),
            ("Conservar capturas incrustadas 📸", self.var_captures, 1, 0),
            (f"Descartar líneas de menos de {PALABRAS_MINIMAS} palabras", self.var_drop, 1, 1),
        ]
        self.chk_stamps = None
        for texto, var, f, c in casillas:
            chk = tk.Checkbutton(
                rejilla, text=texto, variable=var, command=self._refresh, bg=BG, fg=FG,
                selectcolor=PANEL, activebackground=BG, activeforeground=FG, font=("Segoe UI", 10),
                anchor="w",
            )
            chk.grid(row=f, column=c, sticky="w")
            if var is self.var_strip_stamps:
                self.chk_stamps = chk

    def _seccion_preview(self, cont):
        fila = tk.Frame(cont, bg=BG)
        fila.pack(fill="x", pady=(10, 2))
        tk.Label(fila, text="4. Vista previa (cambia al tocar cualquier opción):", **SEMIBOLD).pack(side="left")
        self.btn_ampliar = tk.Button(
            fila, text="⤢ Ampliar", command=self._toggle_ampliar, bg=PANEL, fg=ACC,
            relief="flat", font=("Segoe UI", 8), padx=6, pady=1,
        )
        self.btn_ampliar.pack(side="right")
        tk.Label(fila, textvariable=self.var_stats, bg=BG, fg=DIM,
                 font=("Segoe UI", 9)).pack(side="right", padx=(0, 10))

        self.preview = tk.Text(
            cont, height=LINEAS_NORMAL, bg=PANEL, fg=FG, relief="flat", wrap="word",
            font=("Consolas", 9), padx=8, pady=4, highlightthickness=0,
        )
        self.preview.pack(fill="both", expand=True)
        self.preview.tag_config("cab", foreground=ACC)
        self.preview.tag_config("meta", foreground=DIM)
        self.preview.tag_config("img", foreground=MIC)
        self.preview.config(state="disabled")

    def _aviso(self, cont):
        caja = tk.Frame(cont, bg=PANEL, highlightthickness=1, highlightbackground=ACC)
        caja.pack(side="bottom", fill="x", pady=(10, 0))
        tk.Label(caja, text="⚠ Las síntesis son derivadas y con pérdida", bg=PANEL, fg=ACC,
                 font=("Segoe UI Semibold", 9), anchor="w").pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(
            caja,
            text="Una nota agrupada por hora ya no se puede volver a partir por minutos ni recuperar lo "
            "que se quitó. Para cambiar el agrupamiento, regenera siempre desde la nota original, nunca "
            "a partir de otra síntesis.",
            bg=PANEL, fg=FG, font=("Segoe UI", 9), wraplength=690, justify="left", anchor="w",
        ).pack(fill="x", padx=12, pady=(2, 8))

    def _salida(self, cont):
        bloque = tk.Frame(cont, bg=BG)
        bloque.pack(side="bottom", fill="x")
        tk.Label(bloque, text="Archivo que se creará (misma carpeta; si ya existe se numera, nunca se sobrescribe):",
                 **SEMIBOLD).pack(anchor="w", pady=(10, 2))
        fila = tk.Frame(bloque, bg=BG)
        fila.pack(fill="x")
        chip = tk.Frame(fila, bg=PANEL)
        chip.pack(side="left", ipady=4, padx=(0, 10))
        self.lbl_base = tk.Label(chip, text="", bg=PANEL, fg=FG, font=("Consolas", 10))
        self.lbl_base.pack(side="left", padx=(8, 0))
        self.lbl_sufijo = tk.Label(chip, text="", bg=PANEL, fg=ACC, font=("Consolas", 10))
        self.lbl_sufijo.pack(side="left")
        self.lbl_ext = tk.Label(chip, text=".md", bg=PANEL, fg=FG, font=("Consolas", 10))
        self.lbl_ext.pack(side="left", padx=(0, 8))
        tk.Label(fila, text=str(self.config.notes_dir), bg=BG, fg=DIM,
                 font=("Segoe UI", 8)).pack(side="left")

    def _botonera(self):
        acciones = tk.Frame(self, bg=BG)
        acciones.pack(side="bottom", fill="x", padx=16, pady=(8, 16))
        tk.Button(acciones, text="Cancelar", command=self.destroy, bg=PANEL, fg=DIM,
                  relief="flat", padx=12, font=("Segoe UI", 9)).pack(side="right", padx=(8, 0))
        self.btn_generar = tk.Button(
            acciones, text="📑 Generar síntesis", command=self._generar,
            **{**BTN_STYLE, "fg": ACC, "font": ("Segoe UI Semibold", 10)},
        )
        self.btn_generar.pack(side="right")
        tk.Label(acciones, textvariable=self.var_estado, bg=BG, fg=DIM, font=("Segoe UI", 9),
                 anchor="w", wraplength=430, justify="left").pack(side="left", fill="x", expand=True)

    # -------------------------------------------------------------- acciones
    def _toggle_ampliar(self):
        self.ampliado = not self.ampliado
        self.geometry(f"760x{ALTO_AMPLIADO if self.ampliado else ALTO_NORMAL}")
        self.preview.config(height=LINEAS_AMPLIADO if self.ampliado else LINEAS_NORMAL)
        self.btn_ampliar.config(text="⤡ Reducir" if self.ampliado else "⤢ Ampliar")

    def _refresh(self, *_):
        origen = self._origen()
        agrupa = bool(self.var_interval.get())
        if self.chk_stamps is not None:  # sin agrupar, quitar marcas no tiene sentido
            self.chk_stamps.config(state="normal" if agrupa else "disabled")
        if origen is None:
            self.btn_generar.config(state="disabled", fg=DIM)
            return
        self.btn_generar.config(state="normal", fg=ACC)

        opts = self._opciones()
        destino = unique_digest_path(origen, opts)
        base = destino.stem
        sufijo = "_" + opts.slug()
        if sufijo in base:
            corte = base.index(sufijo)
            self.lbl_base.config(text=base[:corte])
            self.lbl_sufijo.config(text=base[corte:])

        try:
            md = build_digest(origen, opts)
        except (DerivedSourceError, OSError) as e:
            self._set_preview(str(e))
            self.var_stats.set("")
            return
        lineas = md.splitlines()
        bloques = sum(1 for l in lineas if l.startswith("## "))
        origen_lineas = len(origen.read_text(encoding="utf-8").splitlines())
        self.var_stats.set(
            f"{origen_lineas} líneas → {bloques} bloques · {len(lineas)} líneas · ~{len(md) // 1024} KB"
        )
        self._set_preview(md)

    def _set_preview(self, texto: str):
        self.preview.config(state="normal")
        self.preview.delete("1.0", "end")
        for i, linea in enumerate(texto.splitlines(), start=1):
            tag = ""
            if linea.startswith("## ") or linea.startswith("# "):
                tag = "cab"
            elif linea.startswith(">") or linea.startswith("---") or ": " in linea[:20] and i < 8:
                tag = "meta"
            elif "![](" in linea:
                tag = "img"
            self.preview.insert("end", linea + "\n", tag)
        self.preview.config(state="disabled")

    def _generar(self):
        origen = self._origen()
        if origen is None:
            return
        try:
            destino = write_digest(origen, self._opciones())
        except (DerivedSourceError, OSError) as e:
            self.var_estado.set(f"No se generó: {e}")
            return
        self.var_estado.set(f"✅ Creada {destino.name}. El original sigue intacto.")
        self._refresh()  # el siguiente nombre libre cambia tras crear este

