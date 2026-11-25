import functools
import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from tkinter import messagebox, scrolledtext
from typing import Callable, Optional, Tuple

from .. import ayuda, paleta, registro
from ..config.manager import ConfigManager
from ..config.options import THEME_LABELS
from ..config.schema import AppConfig
from ..session import (
    ACTION_DEVICES, ACTION_RECOMMEND, ACTION_SETTINGS, LIVE_STATUS,
    Event, Line, Notice, RecorderSession, SourceChanged, SourceMuted, StatusSnapshot, with_action,
)
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.digest_dialog import DigestDialog
from .dialogs.tuning_dialog import TuningDialog
from . import animacion, tooltip
from .rendimiento import COLUMNAS, Historial, PanelRendimiento
from .theme import (
    BTN_STYLE, HEADER_STYLE, LABEL_STYLE, P, aplicar_tema, app_icon, boton_vivo, con_anillo, fit_window, scroll_nativo,
)
from .tooltip import con_ayuda

POLL_MS = 200  # sondeo con la ventana a la vista
POLL_HIDDEN_MS = 1000  # minimizada: no hay nada que pintar; basta vaciar la cola y decidir el ☕
MAX_LINES = 5000  # líneas que conserva el visor; la nota en disco guarda la reunión entera
TRIM_LINES = 500  # cuántas se borran de golpe al pasarse, para no recortar en cada inserción

TEMA_MS = 250  # fundido cruzado al cambiar de tema
RESALTE_MS = 1500  # la última línea transcrita se resalta y se desvanece en este tiempo
PULSO_MS = 2400  # periodo del pulso del indicador de grabación: lento, sin parpadeo
TOAST_MS = 2600  # lo que se ve un toast antes de irse

# Puntos de corte de la cabecera por ancho, en píxeles a 100 % de escala.
AMPLIO, COMPACTO = 1000, 700
MIN_ANCHO, MIN_ALTO = 480, 320  # tamaño mínimo de la ventana a 100 %
FUENTE_ESTADO = ("Segoe UI Semibold", 11)

# Lo que la ventana añade a un aviso según su `action`: aquí la acción está en ⚙ Opciones.
ACCIONES = {
    ACTION_DEVICES: "Si hablaste, elige el dispositivo que usa Teams en ⚙ Opciones.",
    ACTION_SETTINGS: "Se cambia en ⚙ Opciones.",
    ACTION_RECOMMEND: "⚙ Opciones → «Usar recomendado».",
}

# Atajos de teclado: (clave de ayuda, cómo se muestra, secuencias de Tk, método). La misma tabla
# pone los atajos en los tooltips, en el menú «Más» y en la ventana de ayuda (F1). Las letras van
# en minúscula y mayúscula para que funcionen también con Bloq Mayús.
ATAJOS = (
    ("pausar", "Ctrl+P", ("<Control-p>", "<Control-P>"), "toggle_pause"),
    ("captura", "Ctrl+K", ("<Control-k>", "<Control-K>"), "manual_screenshot"),
    ("abrir_nota", "Ctrl+O", ("<Control-o>", "<Control-O>"), "abrir_nota"),
    ("opciones", "Ctrl+,", ("<Control-comma>",), "open_options"),
    ("rendimiento", "Ctrl+Shift+R", ("<Control-Shift-KeyPress-R>", "<Control-Shift-KeyPress-r>"), "toggle_rendimiento"),
    ("tema_alternar", "Ctrl+Shift+T", ("<Control-Shift-KeyPress-T>", "<Control-Shift-KeyPress-t>"), "alternar_tema"),
    ("ayuda", "F1", ("<F1>",), "abrir_ayuda"),
)
ATAJO = {clave: atajo for clave, atajo, _secuencias, _metodo in ATAJOS}


def con_accion(texto: str, action: str) -> str:
    """El texto del aviso con lo que puede hacer el usuario, dicho como lo ofrece la ventana."""
    return with_action(texto, ACCIONES.get(action, ""))


def punto_de_corte(ancho_px: int, escala: float) -> str:
    """«amplio» (botones con icono y texto), «compacto» (solo icono, el nombre en el tooltip) o
    «estrecho» (cabecera en dos filas) para una ventana de `ancho_px` píxeles físicos con la
    escala de Windows `escala` (1.0 = 100 %, 1.25 = 125 %…)."""
    ancho = ancho_px / escala
    if ancho >= AMPLIO:
        return "amplio"
    return "compacto" if ancho >= COMPACTO else "estrecho"


def recortar(texto: str, ancho: int, medir: Callable[[str], int]) -> str:
    """`texto` si cabe en `ancho` píxeles; si no, el trozo más largo que cabe seguido de «…».
    Con `ancho` <= 1 (la etiqueta aún no tiene tamaño) no se recorta."""
    if ancho <= 1 or medir(texto) <= ancho:
        return texto
    lo, hi = 0, len(texto)
    while lo < hi:  # búsqueda binaria: ~7 medidas para un estado largo
        mitad = (lo + hi + 1) // 2
        if medir(texto[:mitad].rstrip() + "…") <= ancho:
            lo = mitad
        else:
            hi = mitad - 1
    return texto[:lo].rstrip() + "…"


def separar_icono(texto: str) -> Tuple[str, str]:
    """("●", "Escuchando…") si el estado empieza por un símbolo de estado (va al indicador, que
    late mientras graba); ("", texto) si es un aviso, que se muestra tal cual."""
    if texto[:1] and texto[0] in LIVE_STATUS:
        return texto[0], texto[1:].lstrip()
    return "", texto


class MainWindow:
    """Ventana principal de la aplicación Recorder: pinta la sesión y le pasa lo que pide el usuario.

    Toda la lógica (núcleo, pausa, cierre, cabecera, equipo despierto) vive en `RecorderSession`;
    aquí solo hay widgets, diálogos y el sondeo cada 200 ms.

    Cabecera: indicador y estado a la izquierda (el estado cede sitio y se recorta con «…»),
    medidores, y las acciones de cada reunión siempre a la vista (Pausar, Capturar, Abrir nota);
    lo demás va en el menú «Más». Según el ancho, los botones pierden el texto o la cabecera pasa
    a dos filas (`punto_de_corte`).
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
        self._estado: Tuple[str, str] = ("Iniciando…", P.texto_tenue)  # texto completo y color del estado
        self._icono: Optional[str] = None  # símbolo del indicador pintado; None = sin pintar (o minimizada)
        self._modo: Optional[str] = None  # punto de corte aplicado
        self._toast = None  # (ventana, after) del toast a la vista
        self._ayuda: Optional[tk.Toplevel] = None
        self._panel_visible = False
        self.historial = Historial()

        self._build_gui()

        # Iniciar hilos en segundo plano (captura, detección del equipo, transcriptor)
        self.session.start()

        # Iniciar sondeo de eventos de interfaz
        self.poll()

    def _render(self, ev: Event):
        """Pinta un evento de la sesión. Status y HardwareReady no se pintan: la cabecera sale de `status`."""
        if isinstance(ev, Line):
            self.add_line(ev.stamp, ev.kind, ev.text, ev.hits)
            if ev.kind == "info" and ev.hits == ["manual"]:
                self.aviso("📸 Captura guardada en la nota")
        elif isinstance(ev, Notice):
            self._visor(ev.stamp, con_accion(ev.text, ev.action), ev.level)
        elif isinstance(ev, SourceMuted):
            self.add_line(ev.stamp, "info", con_accion(ev.text, ev.action), [])
        elif isinstance(ev, SourceChanged):
            self.add_line(ev.stamp, "info", ev.text, [])

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

    # ------------------------------------------------------------------ construcción
    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("Recorder · Daily")
        animacion.modo = tooltip.animaciones = self.session.config.animations
        animacion.preparar_entrada(self.root)  # transparente hasta el fundido de entrada
        aplicar_tema(self.root, self.session.config.theme)  # antes de crear widgets: ya nacen con su paleta
        self.root.configure(bg=P.fondo)
        app_icon(self.root)  # el icono de la ventana y de sus diálogos, si viene con el programa
        # Una excepción en un botón o en el sondeo la atrapa Tk: queda en el registro de fallos
        self.root.report_callback_exception = self._fallo_en_callback
        self._escala = self.root.tk.call("tk", "scaling") / (96 / 72)  # 1.0 a 100 %, 1.25 a 125 %…

        # El orden de creación es el orden de Tab: medidores, botones, panel, visor.
        self._build_cabecera()
        self.panel = PanelRendimiento(self.root, self.historial, self.toggle_rendimiento, ATAJO["rendimiento"])

        # Etiqueta de ruta de archivo
        self.lbl_path = tk.Label(
            self.root,
            text=str(self.session.file_path),
            bg=P.fondo,
            fg=P.texto_tenue,
            anchor="w",
            font=("Segoe UI", 8),
        )
        self.lbl_path.pack(fill="x", padx=14, pady=(2, 0))
        con_ayuda(self.lbl_path, "nota_hoy")

        # Área de texto desplazable
        self.txt = scrolledtext.ScrolledText(
            self.root,
            bg=P.fondo,
            fg=P.texto,
            insertbackground=P.texto,
            wrap="word",
            relief="flat",
            font=("Segoe UI", 11),
            padx=10,
            pady=8,
            spacing3=6,
            height=10,
            highlightthickness=1,
            highlightbackground=P.fondo,
            highlightcolor=P.foco,
        )
        self.txt.pack(fill="both", expand=True, padx=14, pady=(10, 14))
        con_ayuda(self.txt, "visor", "atraso")
        scroll_nativo(self.txt.vbar)
        self.txt.tag_config("t", foreground=P.texto_tenue, font=("Consolas", 10))
        self.txt.tag_config("kw", foreground=P.acento)
        self.txt.tag_config("mic", foreground=P.mic)
        self.txt.tag_config("err", foreground=P.error)
        self.txt.tag_config("info", foreground=P.texto_tenue)
        self.txt.tag_config("nueva")
        self.txt.tag_lower("nueva")  # por debajo de la selección
        # Tab sale del visor en vez de escribir un tabulador: el foco sigue su orden
        self.txt.bind("<Tab>", lambda e: (e.widget.tk_focusNext().focus_set(), "break")[1])

        self._build_menu()
        for _clave, _atajo, secuencias, metodo in ATAJOS:
            accion = getattr(self, metodo)
            for secuencia in secuencias:
                self.root.bind(secuencia, lambda _e, a=accion: a())
                # En el visor, antes que las teclas propias de Text (Ctrl+K borraría una línea)
                self.txt.bind(secuencia, lambda _e, a=accion: (a(), "break")[1])

        ancho, _alto = fit_window(self.root, 1040, 560)
        self.root.minsize(int(MIN_ANCHO * self._escala), int(MIN_ALTO * self._escala))
        self._aplicar_modo(punto_de_corte(ancho, self._escala))

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # Al volver de la barra de tareas se repinta ya, sin esperar al sondeo lento (ver _tick)
        self.root.bind("<Map>", self._on_map)
        self.root.bind("<Configure>", self._al_redimensionar, add="+")

    def _build_cabecera(self):
        # Rejilla: indicador | estado (el único que cede sitio) | medidores | botones
        self.top = top = tk.Frame(self.root, bg=P.fondo)
        top.pack(fill="x", padx=14, pady=(12, 0))
        top.columnconfigure(1, weight=1)

        self.lbl_icono = tk.Label(top, text="", bg=P.fondo, fg=P.texto_tenue, font=FUENTE_ESTADO)
        # width=1: la etiqueta no pide el ancho de su texto; toma el que sobra y el texto se recorta
        self.lbl_status = tk.Label(
            top, text="Iniciando…", width=1, bg=P.fondo, fg=P.texto_tenue, anchor="w", font=FUENTE_ESTADO
        )
        # Medir un texto con emojis cuesta ~4 ms en Windows (sustitución de fuentes): cada texto
        # se mide una vez. Sin la caché, el recorte del estado en cada sondeo se comía ~2 % de un núcleo.
        self._medir = functools.lru_cache(maxsize=512)(tkfont.Font(root=self.root, font=FUENTE_ESTADO).measure)
        self.lbl_status.bind("<Configure>", lambda _e: self._pintar_estado())
        # Medidores: barras por fuente, ⛔ si está caída y 🔇 si lleva 10 min sin audio (ver
        # session.StatusSnapshot). Clic, Enter o Espacio reconectan el audio.
        self.lbl_meter = con_anillo(top, lambda marco: tk.Label(
            marco, text="", bg=P.fondo, fg=P.texto_tenue, font=("Consolas", 10), cursor="hand2", takefocus=1,
        ))
        for evento in ("<Button-1>", "<Return>", "<space>"):
            self.lbl_meter.bind(evento, lambda _e: self.reconnect_audio())
        con_ayuda(self.lbl_icono, "estado")
        con_ayuda(self.lbl_status, "estado", "cola", "cafe", "fallos")
        con_ayuda(self.lbl_meter, "medidores", "reintento", "mudo")

        self.botonera = tk.Frame(top, bg=P.fondo)
        self._botones: dict = {}  # botón -> [icono, texto]

        def boton(icono: str, texto: str, comando, clave: str) -> tk.Button:
            b = con_anillo(self.botonera, lambda marco: tk.Button(
                marco, text=f"{icono} {texto}", command=comando, **BTN_STYLE
            ))
            b.master.pack(side="left", padx=(4, 0))
            con_ayuda(boton_vivo(b), clave, atajo=ATAJO.get(clave, ""))
            self._botones[b] = [icono, texto]
            return b

        self.btn_pause = boton("⏸", "Pausar", self.toggle_pause, "pausar")
        self.btn_shot = boton("📸", "Capturar", self.manual_screenshot, "captura")
        self.btn_nota = boton("📄", "Abrir nota", self.abrir_nota, "abrir_nota")
        self.btn_mas = boton("☰", "Más", self.abrir_menu, "mas")

    def _build_menu(self):
        """«Más»: lo que no hace falta en cada reunión, con su atajo a la derecha."""
        estilo = dict(
            tearoff=0, bg=P.superficie_elevada, fg=P.texto, activebackground=P.acento,
            activeforeground=P.texto_sobre_acento, selectcolor=P.texto, font=("Segoe UI", 10),
        )
        m = self.menu_mas = tk.Menu(self.root, **estilo)
        m.add_command(label="⚙ Opciones…", accelerator=ATAJO["opciones"], command=self.open_options)
        m.add_command(label="🎯 Calibrar…", command=self.open_tuning)
        m.add_command(label="📑 Reagrupar nota…", command=self.open_digest)
        m.add_separator()
        self.v_rendimiento = tk.BooleanVar(master=self.root, value=False)
        m.add_checkbutton(
            label="📊 Rendimiento", accelerator=ATAJO["rendimiento"], variable=self.v_rendimiento,
            command=lambda: self.mostrar_rendimiento(self.v_rendimiento.get()),
        )
        temas = tk.Menu(m, **estilo)
        self.v_tema = tk.StringVar(master=self.root, value=self.session.config.theme)
        for clave, etiqueta in THEME_LABELS.items():
            temas.add_radiobutton(label=etiqueta, value=clave, variable=self.v_tema, command=lambda c=clave: self.cambiar_tema(c))
        temas.add_separator()
        temas.add_command(label="Alternar claro / oscuro", accelerator=ATAJO["tema_alternar"], command=self.alternar_tema)
        m.add_cascade(label="🎨 Tema", menu=temas)
        m.add_separator()
        # Aquí irá «Ver introducción» cuando llegue la introducción animada (plan, paso 8).
        m.add_command(label="❓ Ayuda", accelerator=ATAJO["ayuda"], command=self.abrir_ayuda)

    def _fallo_en_callback(self, tipo, valor, tb):
        """Lo que Tk hace con una excepción en un callback (imprimirla en stderr), más dejarla en
        el registro: sin consola es la única huella. La ventana sigue, como siempre."""
        registro.anotar("en la ventana", (tipo, valor, tb))
        if sys.stderr is not None:
            tk.Tk.report_callback_exception(self.root, tipo, valor, tb)

    # ------------------------------------------------------------------ responsive
    def _al_redimensionar(self, ev):
        if ev.widget is self.root:  # los hijos también mandan <Configure> a la ventana
            self._aplicar_modo(punto_de_corte(ev.width, self._escala))

    def _aplicar_modo(self, modo: str):
        """Recoloca la cabecera para el punto de corte `modo`; nada si ya estaba en él."""
        if modo == self._modo:
            return
        self._modo = modo
        for b in self._botones:
            self._rotular(b)
        dos_filas = modo == "estrecho"
        self.lbl_icono.grid(row=0, column=0, sticky="w")
        self.lbl_status.grid(row=0, column=1, columnspan=3 if dos_filas else 1, sticky="ew")
        medidores = self.lbl_meter.master  # su marco del anillo de foco
        if dos_filas:
            medidores.grid(row=1, column=0, columnspan=2, sticky="w", padx=0, pady=(6, 0))
            self.botonera.grid(row=1, column=2, columnspan=2, sticky="e", pady=(6, 0))
        else:
            medidores.grid(row=0, column=2, columnspan=1, sticky="e", padx=(12, 4), pady=0)
            self.botonera.grid(row=0, column=3, columnspan=1, sticky="e", pady=0)
        self.panel.columnas(COLUMNAS[modo])

    def _rotular(self, boton: tk.Button):
        icono, texto = self._botones[boton]
        boton.config(text=f"{icono} {texto}" if self._modo == "amplio" else icono)

    # ------------------------------------------------------------------ visor
    def add_line(self, stamp: str, kind: str, text: str, hits: list):
        inicio = self.txt.index("end-1c")
        self.txt.insert("end", f"{stamp}  ", "t")
        if kind == "mic":
            self.txt.insert("end", "🎤 ", "mic")
        self.txt.insert("end", text + "\n", "kw" if hits else "")
        if hits:
            self.txt.insert("end", f"          📸 captura: {', '.join(hits)}\n", "t")
        self._show_end()
        if kind != "info":
            self._resaltar(inicio)

    def _resaltar(self, inicio: str):
        """La última línea transcrita, con fondo de selección que se desvanece en RESALTE_MS.
        Una sola a la vez: la nueva cancela el fundido de la anterior. Sin verse, nada."""
        if not animacion.duracion(RESALTE_MS) or not self._visible():
            return
        self.txt.tag_remove("nueva", "1.0", "end")
        self.txt.tag_add("nueva", inicio, "end-1c")
        animacion.animar(
            self.txt, "nueva", RESALTE_MS,
            lambda v: self.txt.tag_configure("nueva", background=animacion.mezclar(P.seleccion, P.fondo, v)),
            fin=lambda: self.txt.tag_remove("nueva", "1.0", "end"),
            cada_ms=50,  # 20 fps para un fundido de 1,5 s: no se nota y cuesta un tercio
        )

    # ------------------------------------------------------------------ acciones
    def manual_screenshot(self):
        """La sesión captura en un hilo y la línea llega por el sondeo; un clic con otra en curso se ignora."""
        self.session.manual_screenshot()

    def toggle_pause(self):
        if str(self.btn_pause.cget("state")) == "disabled":
            return  # cerrando: el atajo tampoco pausa
        line = self.session.toggle_pause()
        self._botones[self.btn_pause] = ["▶", "Continuar"] if self.session.paused else ["⏸", "Pausar"]
        self._rotular(self.btn_pause)
        self._render(line)

    def abrir_nota(self):
        """Abre la nota de hoy con el programa de Windows para los .md."""
        try:
            os.startfile(self.session.file_path)
        except OSError as e:
            self.aviso(f"⚠ No se pudo abrir la nota: {e.strerror or e}")

    def abrir_menu(self):
        """El menú «Más» bajo su botón, alineado a su borde derecho para no salirse de la ventana."""
        b, m = self.btn_mas, self.menu_mas
        m.update_idletasks()
        try:
            m.tk_popup(b.winfo_rootx() + b.winfo_width() - m.winfo_reqwidth(), b.winfo_rooty() + b.winfo_height())
        finally:
            m.grab_release()

    def open_digest(self):
        """Abre «Reagrupar nota» (copia ordenada y agrupada). Solo lee notas; nunca modifica el original."""
        DigestDialog(self.root, self.session.config, active_note=self.session.file_path)

    def open_options(self):
        def handle_save(new_config: AppConfig, notes_changed: bool, devices_changed: bool):
            self.session.apply_settings(new_config, notes_changed, devices_changed)
            self._pintar_tema(new_config.theme)  # en caliente, también a los diálogos abiertos
            if notes_changed:
                self.lbl_path.config(text=str(self.session.file_path))
            self.aviso("✔ Opciones guardadas")

        SettingsDialog(self.root, self.session.config, self.session.pa, on_save=handle_save)

    def open_tuning(self):
        def guardar(new_config: AppConfig):
            self.session.apply_tuning(new_config)
            self.aviso("✔ Calibración guardada")

        TuningDialog(self.root, self.session.config, on_save=guardar)

    def reconnect_audio(self):
        """Clic en los medidores: reabre las dos fuentes con los dispositivos configurados."""
        self.session.reconnect_audio()

    # ------------------------------------------------------------------ tema
    def _pintar_tema(self, nombre: str) -> str:
        """Aplica el tema con fundido cruzado si la ventana se ve (oculta, al momento)."""
        resuelto = aplicar_tema(self.root, nombre, transicion_ms=TEMA_MS if self._visible() else 0)
        self.v_tema.set(nombre)
        self.panel.repintar()
        return resuelto

    def cambiar_tema(self, nombre: str):
        """Tema elegido en «Más» → Tema: se guarda en config.json y se pinta ya."""
        self.session.config.theme = nombre
        try:
            self.session.config_manager.save(self.session.config)
        except OSError as e:
            self.aviso(f"⚠ No se pudo guardar el tema: {e.strerror or e}")
            self._pintar_tema(nombre)
            return
        resuelto = self._pintar_tema(nombre)
        self.aviso(f"🎨 Tema del sistema ({resuelto})" if nombre == paleta.SISTEMA else f"🎨 Tema {resuelto}")

    def alternar_tema(self):
        self.cambiar_tema("claro" if paleta.resolver(self.session.config.theme) == "oscuro" else "oscuro")

    # ------------------------------------------------------------------ rendimiento, ayuda y toasts
    def toggle_rendimiento(self):
        self.mostrar_rendimiento(not self._panel_visible)

    def mostrar_rendimiento(self, visible: bool):
        """Despliega o pliega el panel bajo la cabecera. Plegado no se redibuja."""
        self._panel_visible = visible
        self.v_rendimiento.set(visible)
        if visible:
            self.panel.pack(fill="x", padx=14, pady=(10, 0), after=self.top)
            self.panel.actualizar(self.session.status.metricas)
        else:
            self.panel.pack_forget()

    def abrir_ayuda(self):
        """Los atajos de teclado, con el título y la explicación de cada uno (recorder/ayuda.py)."""
        if self._ayuda is not None and self._ayuda.winfo_exists():
            self._ayuda.lift()
            self._ayuda.focus_set()
            return
        d = self._ayuda = tk.Toplevel(self.root, bg=P.fondo)
        d.title("Ayuda de Recorder")
        d.transient(self.root)
        k = self._escala
        tk.Label(d, text="Atajos de teclado", anchor="w", **HEADER_STYLE).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=16, pady=(14, 6)
        )
        for fila, (clave, atajo, _secuencias, _metodo) in enumerate(ATAJOS, start=1):
            titulo, explicacion = ayuda.entrada(clave)
            tk.Label(d, text=atajo, bg=P.fondo, fg=P.acento, font=("Consolas", 10)).grid(
                row=fila, column=0, sticky="nw", padx=(16, 12), pady=4
            )
            tk.Label(d, text=f"{titulo}. {explicacion}", anchor="w", justify="left",
                     wraplength=int(440 * k), **LABEL_STYLE).grid(row=fila, column=1, sticky="w", padx=(0, 16), pady=4)
        tk.Label(d, text="Pasa el ratón o llega con Tab a cualquier control para ver qué hace.", anchor="w",
                 **LABEL_STYLE).grid(row=len(ATAJOS) + 1, column=0, columnspan=2, sticky="w", padx=16, pady=(10, 0))

        def cerrar(_e=None):
            animacion.cerrar(d)

        boton = con_anillo(d, lambda marco: tk.Button(marco, text="Cerrar", command=cerrar, **BTN_STYLE))
        con_ayuda(boton_vivo(boton), "cancelar")
        boton.master.grid(row=len(ATAJOS) + 2, column=1, sticky="e", padx=14, pady=12)
        d.protocol("WM_DELETE_WINDOW", cerrar)
        d.bind("<Escape>", cerrar)
        fit_window(d, 600, 380)
        boton.focus_set()

    def aviso(self, texto: str):
        """Una confirmación que no pide decidir nada (toast): abajo a la derecha de la ventana, se
        va sola a los TOAST_MS y sustituye a la anterior. Con la ventana sin verse, no sale."""
        viejo, self._toast = self._toast, None
        if viejo is not None:
            ventana, espera = viejo
            try:
                ventana.after_cancel(espera)
                ventana.destroy()
            except tk.TclError:
                pass
        if not self._visible():
            return
        k = self._escala
        t = tk.Toplevel(self.root, bg=P.superficie_elevada, highlightthickness=1, highlightbackground=P.borde)
        t.withdraw()  # se coloca antes de verse
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        tk.Label(t, text=texto, bg=P.superficie_elevada, fg=P.texto, font=("Segoe UI", 10),
                 padx=int(14 * k), pady=int(8 * k)).pack()
        t.update_idletasks()
        margen = int(18 * k)
        x = self.root.winfo_rootx() + self.root.winfo_width() - t.winfo_reqwidth() - margen
        y = self.root.winfo_rooty() + self.root.winfo_height() - t.winfo_reqheight() - margen
        t.geometry(f"+{x}+{y}")
        animacion.preparar_entrada(t)
        t.deiconify()
        animacion.entrar(t)
        self._toast = (t, t.after(TOAST_MS, lambda: animacion.cerrar(t)))

    # ------------------------------------------------------------------ cabecera y sondeo
    def _set_label(self, lbl: tk.Label, **opts):
        """Escribe en la etiqueta solo si algo cambió: cada config() cuesta aunque el texto sea el
        mismo (dos por tic suman ~1 % de CPU) y en silencio los medidores no cambian."""
        if self._painted.get(lbl) != opts:
            lbl.config(**opts)
            self._painted[lbl] = opts

    def _paint_header(self, st: StatusSnapshot):
        icono, texto = separar_icono(st.status_text)
        self._pintar_indicador(icono)
        self._estado = (texto, P.texto if st.status_highlight else P.texto_tenue)
        self._pintar_estado()
        self._set_label(self.lbl_meter, text=st.meter_text)

    def _pintar_estado(self):
        """El estado recortado con «…» al ancho que le deja la cabecera."""
        texto, color = self._estado
        ancho = self.lbl_status.winfo_width() - 6  # bordes y margen interno de la etiqueta
        self._set_label(self.lbl_status, text=recortar(texto, ancho, self._medir), fg=color)

    def _pintar_indicador(self, icono: str):
        """El símbolo del estado: ● (escuchando) late despacio en rojo; ⏸ y ⏳ quedan quietos."""
        if icono == self._icono:
            return
        self._icono = icono
        self._set_label(self.lbl_icono, text=icono)
        if icono == "●":
            animacion.latir(
                self.lbl_icono, "pulso", PULSO_MS,
                lambda v: self.lbl_icono.configure(fg=animacion.mezclar(P.error, P.fondo, 0.55 * v)),
            )
        else:
            animacion.cancelar(self.lbl_icono, "pulso")
            self.lbl_icono.configure(fg=P.aviso if icono == "⏸" else P.texto_tenue)

    def _visible(self) -> bool:
        """False con la ventana minimizada o retirada: pintar ahí es trabajo que nadie ve."""
        return self.root.state() not in ("iconic", "withdrawn")

    def _tick(self) -> Optional[int]:
        """Un sondeo. Devuelve en cuántos ms toca el siguiente, o None si hay que cerrar.

        La sesión se sondea siempre (vacía la cola de los hilos, decide el ☕ y detecta el final
        del vaciado) y las líneas se insertan siempre, para que no se pierda nada; minimizada,
        solo se deja de pintar (cabecera, pulso y panel) y se sondea más despacio.
        """
        for ev in self.session.poll():
            self._render(ev)

        st = self.session.status
        self.historial.anotar(st.metricas)  # un append cada 2 s; el panel lo pinta al abrirse
        visible = self._visible()
        if visible:
            self._paint_header(st)
            if self._panel_visible:
                self.panel.actualizar(st.metricas)
        elif self._icono is not None:
            animacion.cancelar(self.lbl_icono, "pulso")  # nadie lo ve: al volver se repinta
            self._icono = None

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
        # La sesión para los hilos sin tocar PortAudio (ver RecorderSession.shutdown); la ventana
        # se va después, con su fundido de salida.
        if self._poll_id is not None:
            self.root.after_cancel(self._poll_id)
            self._poll_id = None
        self.session.shutdown()
        animacion.cerrar(self.root)

    def run(self):
        animacion.entrar(self.root)  # el fundido de entrada arranca con el bucle de Tk, no antes
        self.root.mainloop()
