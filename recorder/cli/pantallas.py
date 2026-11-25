"""`daily menu` en una terminal de verdad: pantallas navegables por teclado, vivas y con botones.

Cuatro pantallas en una pila: Inicio (el menú), Opciones, Rendimiento y Ayuda. ↑/↓ (o j/k)
mueven, Enter abre (en Opciones, edita un texto), ←/→ cambian un ajuste de lista, Esc o q
vuelven a la anterior (en el inicio, salen) y los números del menú siguen siendo atajos. [?]
abre la ayuda y [t] pasa del tema oscuro al claro o al revés y lo guarda, como en la ventana.

Se pinta con rich.Live en la pantalla alternativa: al salir, la terminal queda como estaba.
Cada INTERVALO s se lee una tecla; el cuadro se recompone al pulsar algo, en el tic de TIC s
(la cabecera: nota de hoy, calidad, motor que se usaría y equipo), al cambiar el tamaño de la
ventana o mientras gira un spinner, y solo se redibuja si cambió: quieto no escribe nada. El
cuadro ocupa la altura entera: cabecera arriba; lista en medio (recortada alrededor de lo elegido
si no cabe); abajo la línea de ayuda de lo elegido (recorder/ayuda.py), un aviso si lo hay y el
pie de teclas. En la consola clásica (ASCII) los símbolos pasan por `presentar`.

Lo que usa la terminal entera (Calibrar, Reagrupar, Recomendación) se ejecuta fuera de la pantalla
alternativa, como en el menú numerado, y se vuelve al pulsar una tecla. Grabar y la ventana
terminan el menú. Fuera de Windows las dos están desactivadas, con el motivo en la ayuda.

Las pruebas inyectan el lector de teclas, la espera, el reloj, la plataforma, la detección de
Opciones y el muestreo de Rendimiento (tests/test_cli_pantallas.py).
"""
import collections
import contextlib
import dataclasses
import datetime
import os
import pathlib
import threading
import time
from typing import Callable, Deque, Dict, List, Optional, Sequence, Tuple

from rich.cells import cell_len
from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from .. import ayuda, paleta
from ..config.hardware import HardwareProfile, cached_hardware, describe_hardware, peek_hardware
from ..config.manager import ConfigManager
from ..config.options import (
    MAX_THREADS,
    THEME_LABELS,
    capture_choices,
    device_choices,
    gpu_choices,
    quality_display,
    recommendation_text,
    settings_form,
    target_choices,
    use_recommendation,
)
from ..config.schema import (
    CUSTOM_PRESET,
    PRESET_ORDER,
    QUALITY_PRESETS,
    AppConfig,
    choose_vulkan_device,
    describe_quality,
    recommend_config,
    resolve_runtime,
    vulkan_model_for,
)
from ..engine.whispercpp import vulkan_readiness, whispercpp_ready
from ..metricas import INTERVALO as INTERVALO_METRICAS
from ..metricas import MotorEfectivo, Muestreador, hilos_efectivos
from . import app as despacho, configurar, teclas
from .consola import partes_teclas, presentar, tema_rich
from .menu import opciones_disponibles
from .teclas import ABAJO, ARRIBA, DERECHA, ENTER, ESC, IZQUIERDA, RETROCESO

INTERVALO = 0.05  # s entre lecturas del teclado
TIC = 1.0  # s entre refrescos de la cabecera (y de las cifras de Rendimiento)
HISTORIA = 60  # muestras de la tendencia de Rendimiento: 2 minutos con una cada 2 s
MARCA = "▶"  # la fila elegida (en ASCII, «>»)
CHISPAS, CHISPAS_ASCII = "▁▂▃▄▅▆▇█", "_.:-=+*#"  # la tendencia, de 0 a 100 %

# Las pantallas propias del inicio, entre lo del menú numerado y Salir.
EXTRA = (
    ("7", "Rendimiento", "rendimiento", "motor que se usaría y lo que gasta el equipo"),
    ("8", "Ayuda", "ayuda", "teclas y glosario"),
)
SOLO_WINDOWS = ("grabar", "ventana")  # necesitan WASAPI (y la ventana, la sesión entera)

# Las teclas de este menú, para la Ayuda (las de la grabación salen de ayuda.TERMINAL).
ATAJOS = (
    ("↑ ↓  j k", "moverse"),
    ("Enter", "abrir; en Opciones, editar un texto"),
    ("← →", "cambiar el valor de un ajuste de lista"),
    ("Esc  q", "volver a la pantalla anterior; en el inicio, salir"),
    ("1-8  0", "abrir una opción del inicio directamente"),
    ("?", "esta ayuda"),
    ("t", "tema claro u oscuro (se guarda)"),
    ("g", "guardar las opciones"),
)

Partes = Sequence[Tuple[str, str]]


# ------------------------------------------------------------------ lógica pura
def recorte(n: int, foco: int, sitio: int) -> range:
    """Las filas de `n` que se ven en `sitio` líneas, con `foco` dentro (centrado si se puede)."""
    inicio = min(max(0, foco - sitio // 2), max(0, n - sitio))
    return range(inicio, min(n, inicio + sitio))


def barra(valor: float, ancho: int) -> Tuple[str, str]:
    """(lleno, vacío) de una barra de `ancho` celdas para un % de 0 a 100."""
    llenos = round(max(0.0, min(100.0, valor)) / 100 * ancho)
    return "█" * llenos, "░" * (ancho - llenos)


def tendencia(valores: Sequence[Optional[float]], ancho: int, ascii_mode: bool = False) -> str:
    """Las últimas `ancho` muestras (% de 0 a 100) como una línea de bloques; un hueco sin dato."""
    if ancho <= 0:
        return ""
    chispas = CHISPAS_ASCII if ascii_mode else CHISPAS
    tope = len(chispas) - 1
    return "".join(
        " " if v is None else chispas[min(tope, int(max(0.0, v) / 100 * len(chispas)))] for v in list(valores)[-ancho:]
    )


def nota_de_hoy(notes_dir: str, hoy: Optional[datetime.date] = None) -> str:
    """El nombre de la última nota de hoy en `notes_dir` (las copias reagrupadas no cuentan)."""
    hoy = hoy or datetime.date.today()
    notas = sorted(pathlib.Path(notes_dir).glob(f"daily_{hoy:%Y-%m-%d}_??-??.md"))
    return notas[-1].name if notas else "aún no hay (se crea al grabar)"


def motor_previsto(config: AppConfig, hw: HardwareProfile) -> MotorEfectivo:
    """El motor con que cargaría el modelo una grabación ahora: lo mismo que resuelve
    `TranscriberWorker._load_model` con este equipo, antes de cargar nada."""
    vulkan = None
    if config.whispercpp_dir.strip() and (config.device == "vulkan" or (config.device == "gpu" and hw.cuda_devices <= 0)):
        vulkan = choose_vulkan_device(config.whispercpp_device, hw.vulkan_devices)
    listo = whispercpp_ready(config.whispercpp_dir, vulkan_model_for(config.model, vulkan), config.compute_type)
    modelo, disp, _precision, haz, aviso = resolve_runtime(config, hw.cuda_devices, listo, vulkan)
    if disp == "vulkan":
        return MotorEfectivo(
            "whisper.cpp", disp, modelo, haz, gpu=vulkan.name if vulkan else "", integrada=bool(vulkan and vulkan.integrated),
        )
    caida = aviso.removeprefix("⚠ ") if disp == "cpu" and config.device != "cpu" else ""
    return MotorEfectivo("faster-whisper", disp, modelo, haz, hilos_efectivos(config.cpu_threads) if disp == "cpu" else 0, caida=caida)


def _o(fn, defecto):
    """fn() o `defecto` si esta plataforma no lo tiene (sin WASAPI ni Win32 fuera de Windows)."""
    try:
        return fn()
    except (ImportError, AttributeError, OSError):  # ponytail: un fallo de PortAudio en Windows también da la lista vacía
        return defecto


def detectar_entorno() -> configurar.Entorno:
    """Lo que Opciones ofrece elegir: pantallas, ventanas, dispositivos WASAPI y el equipo."""
    salidas, micros = _o(configurar.dispositivos_audio, ([], []))
    pantallas = _o(configurar.screen_labels, []) or ["(todas las pantallas)"]
    return configurar.Entorno(pantallas, _o(configurar.window_titles, []), salidas, micros, cached_hardware())


# ------------------------------------------------------------------ pantallas
class Pantalla:
    """Lo común: un título, un cuerpo de líneas, la línea de ayuda, el pie y sus teclas."""

    titulo = ""
    TECLAS: Sequence[Tuple[str, str]] = (("Esc", "Volver"), ("?", "Ayuda"), ("t", "Tema"))
    escribiendo = False  # True mientras se teclea un texto: las letras llegan tal cual, sin atajos

    def __init__(self, terminal: "Terminal"):
        self.app = terminal

    def cuerpo(self, ancho: int, sitio: int) -> Tuple[List[Text], int]:
        """(líneas, la que debe quedar a la vista). `sitio`: las líneas que caben."""
        return [], 0

    def ayuda(self) -> Tuple[str, str]:
        return "", "tenue"

    def teclas(self) -> Sequence[Tuple[str, str]]:
        return self.TECLAS

    def tecla(self, k: str) -> bool:
        """True si la atendió; si no, la atiende la terminal (Esc, q, ?, t)."""
        return False

    def al_salir(self) -> None:
        pass


def _mover(sel: int, n: int, k: str) -> Optional[int]:
    """La fila elegida tras ↑/↓ (o k/j), dando la vuelta; None si `k` no mueve."""
    if k in (ARRIBA, "k"):
        return (sel - 1) % n
    if k in (ABAJO, "j"):
        return (sel + 1) % n
    return None


class Inicio(Pantalla):
    titulo = "Inicio"
    TECLAS = (("Enter", "Abrir"), ("Esc", "Salir"), ("?", "Ayuda"), ("t", "Tema"))

    def __init__(self, terminal: "Terminal"):
        super().__init__(terminal)
        disponibles = opciones_disponibles(terminal.comandos)
        self.filas = [f for f in disponibles if f[2] != "salir"] + list(EXTRA) + [f for f in disponibles if f[2] == "salir"]
        self.ancho = max(len(f[1]) for f in self.filas)
        self.sel = 0

    def apagada(self, accion: str) -> bool:
        return accion in SOLO_WINDOWS and not self.app.windows

    def cuerpo(self, ancho, sitio):
        lineas = []
        for i, (numero, etiqueta, accion, descripcion) in enumerate(self.filas):
            elegida, apagada = i == self.sel, self.apagada(accion)
            estilo = "tenue" if apagada else "elegido" if elegida else "texto"
            lineas.append(self.app.t(
                (MARCA if elegida else " ", "acento"), (f" {numero}  ", "tenue" if apagada else "acento"),
                (etiqueta.ljust(self.ancho) + "  ", estilo), ("(solo Windows)" if apagada else descripcion, "tenue"),
            ))
        return lineas, self.sel

    def ayuda(self):
        accion = self.filas[self.sel][2]
        return ayuda.linea("solo_windows" if self.apagada(accion) else "menu_" + accion), "tenue"

    def tecla(self, k):
        movida = _mover(self.sel, len(self.filas), k)
        if movida is not None:
            self.sel = movida
        elif k == ENTER:
            self.abrir(self.filas[self.sel][2])
        elif any(f[0] == k for f in self.filas):  # los números siguen siendo atajos
            self.sel = next(i for i, f in enumerate(self.filas) if f[0] == k)
            self.abrir(self.filas[self.sel][2])
        else:
            return False
        return True

    def abrir(self, accion: str) -> None:
        if self.apagada(accion):
            self.app.avisar(f"⚠ {ayuda.entrada('solo_windows')[0]}: no se puede aquí.", "error")
        elif accion == "salir":
            self.app.salir()
        elif accion in ("config", "rendimiento", "ayuda"):
            self.app.abrir({"config": Opciones, "rendimiento": Rendimiento, "ayuda": Ayuda}[accion](self.app))
        else:
            self.app.salir(accion)  # grabar, la ventana y los comandos usan la terminal entera


@dataclasses.dataclass
class Ajuste:
    """Una fila de Opciones: un campo de `SettingsForm`, su etiqueta y su clave de ayuda.
    `opciones` (etiqueta, valor) para los de lista; None para los de texto."""

    campo: str
    etiqueta: str
    clave: str
    opciones: Optional[List[Tuple[str, object]]] = None


RECOMENDADA = "recomendada"  # la fila que no es un campo: aplica la recomendación


class Opciones(Pantalla):
    """⚙ Opciones sobre la lógica de `daily config` (configurar.py y config/options.py): el mismo
    formulario, lo mismo guardado y la misma tabla de cambios antes de guardar."""

    titulo = "Opciones"
    TECLAS = (("↑↓", "Mover"), ("←→", "Cambiar"), ("Enter", "Editar"), ("g", "Guardar"), ("Esc", "Volver"))

    def __init__(self, terminal: "Terminal"):
        super().__init__(terminal)
        self.config = terminal.mgr.load()
        self.error = terminal.mgr.last_error  # ilegible: se ve y se edita, pero no se guarda
        self.entorno: Optional[configurar.Entorno] = None
        self.form = None
        self.ajustes: List[Ajuste] = []
        self.sel = 0
        self.editando: Optional[str] = None  # el texto que se teclea, mientras se edita
        self.confirmando = False  # enseñando los cambios antes de guardar
        self.avisado = False  # ya se dijo que hay cambios sin guardar: el siguiente Esc sale

    @property
    def escribiendo(self) -> bool:
        return self.editando is not None

    def _preparado(self) -> bool:
        if self.form is None:
            self.entorno = self.app.entorno()
            if self.entorno is None:
                return False
            self.form = settings_form(self.config, self.entorno.screens)
            self._componer()
        return True

    def _componer(self) -> None:
        e, f, hw = self.entorno, self.form, self.entorno.hardware
        si_no = [("sí", True), ("no", False)]

        def lista(valores: Sequence[str], actual: str) -> List[Tuple[str, object]]:
            valores = list(valores)
            if actual not in valores:
                valores.insert(min(1, len(valores)), actual)  # lo guardado que ya no se detecta sigue elegible
            return [(v, v) for v in valores]

        extra = QUALITY_PRESETS["extra"]
        vulkan_listo = whispercpp_ready(f.whispercpp_dir.strip(), extra.model, extra.compute_type)
        self.ajustes = [
            Ajuste("notes_dir", "Carpeta de notas", "carpeta_notas"),
            Ajuste("caps_dir", "Carpeta de capturas", "carpeta_capturas"),
            Ajuste("keywords", "Palabras clave", "palabras_clave"),
            Ajuste("out_dev", "Salida a capturar 🔊", "salida_audio", lista(device_choices(e.out_devs), f.out_dev)),
            Ajuste("mic", "Transcribir mi micrófono", "transcribir_mic", si_no),
            Ajuste("mic_dev", "Micrófono 🎤", "microfono", lista(device_choices(e.mic_devs), f.mic_dev)),
            Ajuste("target", "Qué capturar 📸", "que_capturar", lista(target_choices(e.screens, e.windows, self.config.window), f.target)),
            Ajuste("captures", "Capturas por palabra clave", "capturas_clave", lista(capture_choices(), f.captures)),
            Ajuste("quality", "Calidad", "calidad", [
                (quality_display(k, hw.cuda_devices, vulkan_listo), k) for k in PRESET_ORDER + [CUSTOM_PRESET]
            ]),
            Ajuste("cpu_threads", "Hilos de CPU", "hilos"),
            Ajuste("whispercpp_dir", "Carpeta de whisper.cpp", "whispercpp"),
            Ajuste("whispercpp_device", "GPU de whisper.cpp", "gpu", list(gpu_choices(hw.vulkan_devices, self.config.whispercpp_device).items())),
            Ajuste("whispercpp_flash_attn", "Flash attention", "flash", si_no),
            Ajuste("theme", "Tema", "tema", [(v, k) for k, v in THEME_LABELS.items()]),
            Ajuste(RECOMENDADA, "Usar la recomendada para este equipo", "opciones_recomendada"),
        ]

    def valor(self, a: Ajuste) -> str:
        if a.campo == RECOMENDADA:
            return ""
        v = getattr(self.form, a.campo)
        if a.opciones is None:
            return v or "(vacío)"
        return next((etiqueta for etiqueta, valor in a.opciones if valor == v), str(v))

    def cambios(self) -> List[Tuple[str, str, str]]:
        if self.form is None:
            return []
        return configurar.diferencias(self.config, configurar.aplicado(self.config, self.form, self.entorno.screens))

    # ------------------------------------------------------------ pintar
    def cuerpo(self, ancho, sitio):
        if not self._preparado():
            if self.app.error_entorno:
                return [self.app.t((self.app.error_entorno, "error"))], 0
            return [self.app.spinner("detectando dispositivos, pantallas y equipo…")], 0
        if self.confirmando:
            lineas = [self.app.t(("Cambios que se guardarán en ", "tenue"), (self.app.mgr.path.name, "texto"), (":", "tenue"))]
            for etiqueta, antes, despues in self.cambios():
                lineas.append(self.app.t((f"  {etiqueta}: ", "texto"), (antes, "tenue"), (" → ", "tenue"), (despues, "acento")))
            return lineas, 0
        etiquetas = [presentar(a.etiqueta, self.app.consola) for a in self.ajustes]
        columna = max(cell_len(e) for a, e in zip(self.ajustes, etiquetas) if a.campo != RECOMENDADA)  # esa no lleva valor
        lineas = []
        for i, (a, etiqueta) in enumerate(zip(self.ajustes, etiquetas)):
            elegida = i == self.sel
            if elegida and self.editando is not None:
                valor = [(self.editando + "_", "acento")]
            elif elegida and a.opciones:
                valor = [("‹ ", "acento"), (self.valor(a), "texto"), (" ›", "acento")]
            else:
                valor = [(self.valor(a), "texto" if elegida else "tenue")]
            lineas.append(self.app.t(
                (MARCA if elegida else " ", "acento"),
                (" " + etiqueta + " " * (columna - cell_len(etiqueta)) + "  ", "elegido" if elegida else "texto"),
                *valor,
            ))
        return lineas, self.sel

    def ayuda(self):
        if self.form is None:
            return "", "tenue"
        if self.confirmando:
            return ayuda.linea("opciones_guardar"), "tenue"
        if self.editando is not None:
            return ayuda.linea("opciones_editar"), "tenue"
        return ayuda.linea(self.ajustes[self.sel].clave), "tenue"

    def teclas(self):
        if self.editando is not None:
            return (("Enter", "Aceptar"), ("Esc", "Cancelar"))
        if self.confirmando:
            return (("Enter", "Guardar"), ("Esc", "Seguir editando"))
        return self.TECLAS

    # ------------------------------------------------------------ teclas
    def tecla(self, k):
        if self.form is None:
            return False  # mientras detecta, solo se puede volver
        if self.editando is not None:
            # ponytail: se escribe y se borra al final del texto; cursor movible con ←/→ si hace falta
            if k == ENTER:
                self._aceptar()
            elif k == ESC:
                self.editando = None
            elif k == RETROCESO:
                self.editando = self.editando[:-1]
            elif len(k) == 1 and k.isprintable():
                self.editando += k
            return True
        if self.confirmando:
            if k == ENTER:
                self._guardar()
            elif k in (ESC, "q"):
                self.confirmando = False
            return True
        if k not in (ESC, "q"):
            self.avisado = False  # tras el aviso se siguió trabajando: el próximo Esc vuelve a avisar
        a = self.ajustes[self.sel]
        movida = _mover(self.sel, len(self.ajustes), k)
        if movida is not None:
            self.sel = movida
        elif k in (IZQUIERDA, DERECHA) and a.opciones:
            self._cambiar(a, -1 if k == IZQUIERDA else 1)
        elif k == ENTER:
            if a.campo == RECOMENDADA:
                self._recomendada()
            elif a.opciones:
                self._cambiar(a, 1)
            else:
                self.editando = getattr(self.form, a.campo)
        elif k == "g":
            self._pedir_guardar()
        elif k == "t":
            tema = self.app.alternar_tema()
            if not self.app.mgr.last_error:  # ya está en config.json: no es un cambio pendiente
                self.config.theme = self.form.theme = tema
        elif k in (ESC, "q") and self.cambios() and not self.avisado:
            self.avisado = True
            self.app.avisar("⚠ Hay cambios sin guardar: [g] los guarda · [Esc] sale sin guardarlos.", "error")
        else:
            return False
        return True

    def _cambiar(self, a: Ajuste, paso: int) -> None:
        valores = [v for _e, v in a.opciones]
        actual = getattr(self.form, a.campo)
        i = valores.index(actual) if actual in valores else -1
        setattr(self.form, a.campo, valores[(i + paso) % len(valores)])

    def _aceptar(self) -> None:
        a, texto = self.ajustes[self.sel], self.editando.strip()
        if a.campo == "cpu_threads" and not (texto.isdigit() and int(texto) <= MAX_THREADS):
            self.app.avisar(f"⚠ Hilos de CPU: escribe un número entre 0 y {MAX_THREADS}.", "error")
            return
        setattr(self.form, a.campo, texto)
        self.editando = None
        if a.campo == "whispercpp_dir":
            self._componer()  # de la carpeta depende que Extra esté disponible

    def _recomendada(self) -> None:
        rec = recommend_config(self.entorno.hardware, *vulkan_readiness(self.form.whispercpp_dir.strip()))
        use_recommendation(self.form, rec)
        self.app.avisar(recommendation_text(rec), "ok")

    def _pedir_guardar(self) -> None:
        if self.error:
            self.app.avisar(f"⚠ No se guarda: {self.error}", "error")
        elif not self.cambios():
            self.app.avisar("Sin cambios.", "tenue")
        else:
            self.confirmando = True

    def _guardar(self) -> None:
        nuevo = configurar.aplicado(self.config, self.form, self.entorno.screens)
        self.app.mgr.save(nuevo)
        self.config, self.form = nuevo, settings_form(nuevo, self.entorno.screens)
        self._componer()
        self.confirmando = self.avisado = False
        self.app.poner_tema(nuevo.theme)
        self.app.avisar(f"✔ Guardado en {self.app.mgr.path}. {configurar.AVISO_REINICIO}", "ok")


class Rendimiento(Pantalla):
    """El motor que se usaría y lo que gasta el equipo ahora, con barras y tendencia. Desde el
    menú no hay ninguna grabación en marcha: las cifras son las del equipo entero (`Muestreador`
    sin transcriptor), que es lo que dice si hay margen antes de grabar."""

    titulo = "Rendimiento"
    SERIES = (("cpu", "CPU del equipo"), ("gpu", "GPU del equipo"))

    def __init__(self, terminal: "Terminal"):
        super().__init__(terminal)
        self.muestreo = terminal.nuevo_muestreador()
        self.muestreo.iniciar()
        self.desde = terminal.reloj()
        self.ultima: Optional[float] = None
        self.historia: Dict[str, Deque[Optional[float]]] = {s: collections.deque(maxlen=HISTORIA) for s, _t in self.SERIES}

    def al_salir(self):
        self.muestreo.parar()

    def ayuda(self):
        return ayuda.linea("menu_rendimiento"), "tenue"

    def _anotar(self, valores: Dict[str, Optional[float]]) -> None:
        ahora = self.app.reloj()
        if self.ultima is None or ahora - self.ultima >= INTERVALO_METRICAS:
            self.ultima = ahora
            for serie, valor in valores.items():
                self.historia[serie].append(valor)

    def cuerpo(self, ancho, sitio):
        t, m = self.app.t, self.muestreo.foto()
        valores = {"cpu": m.cpu_sistema, "gpu": m.gpu_sistema}
        if any(v is not None for v in valores.values()):
            self._anotar(valores)
        lineas = [t(("No hay ninguna grabación en curso: las cifras son del equipo entero.", "tenue"))]
        hw = peek_hardware()
        if hw is None:
            lineas.append(self.app.spinner("detectando el equipo…"))
        else:
            motor = motor_previsto(self.app.config, hw)
            lineas.append(t(("Motor que se usaría: ", "tenue"), (motor.texto, "texto")))
            if motor.caida:
                lineas += self.app.parrafo([(f"⚠ {motor.caida}", "error")], ancho)
        lineas.append(Text())
        if all(v is None for v in valores.values()) and self.app.reloj() - self.desde < 3 * INTERVALO_METRICAS:
            lineas.append(self.app.spinner("midiendo…"))  # el primer % llega con la segunda muestra
            return lineas, 0
        etiqueta = max(len(titulo) for _s, titulo in self.SERIES) + 2
        celdas = max(10, min(30, (ancho - etiqueta - 9) // 2))
        for serie, titulo in self.SERIES:
            v = valores[serie]
            lleno, vacio = barra(v or 0.0, celdas)
            lineas.append(t(
                (titulo.ljust(etiqueta), "texto"), (lleno, "acento"), (vacio, "borde"),
                (f"{'n/d' if v is None else f'{v:.0f} %':>6}  ", "texto"),
                (tendencia(self.historia[serie], ancho - etiqueta - celdas - 8, self.app.ascii), "mic"),
            ))
        return lineas, 0


class Ayuda(Pantalla):
    """Las teclas de este menú y de la grabación, y el glosario de recorder/ayuda.py."""

    titulo = "Ayuda"
    TECLAS = (("↑↓", "Desplazar"), ("Esc", "Volver"), ("t", "Tema"))

    def __init__(self, terminal: "Terminal"):
        super().__init__(terminal)
        self.arriba = 0  # la primera línea a la vista

    def ayuda(self):
        return ayuda.linea("menu_ayuda"), "tenue"

    def tecla(self, k):
        if k in (ARRIBA, "k"):
            self.arriba = max(0, self.arriba - 1)
        elif k in (ABAJO, "j"):
            self.arriba += 1  # el tope se pone al pintar, cuando se sabe cuánto cabe
        else:
            return False
        return True

    def cuerpo(self, ancho, sitio):
        t, parrafo = self.app.t, self.app.parrafo
        lineas = [t(("Teclas de este menú", "bold"))]
        lineas += [t((f"  {presentar(tecla, self.app.consola):<10}", "acento"), (que, "texto")) for tecla, que in ATAJOS]
        lineas += [Text(), t(("Teclas de la grabación (daily)", "bold"))]
        for k in "pcraoq":
            titulo, texto = ayuda.entrada(f"tecla_{k}")
            lineas += parrafo([(f"  [{k}] {titulo}: ", "acento"), (texto, "tenue")], ancho, sangria=6)
        lineas += [Text(), t(("Glosario", "bold"))]
        for titulo, texto in ayuda.GLOSARIO.values():
            lineas += parrafo([(f"  {titulo}: ", "acento"), (texto, "tenue")], ancho)
        self.arriba = min(self.arriba, max(0, len(lineas) - sitio))
        return lineas[self.arriba:self.arriba + sitio], 0


# ------------------------------------------------------------------ la terminal
class Terminal:
    """El bucle: lee teclas, reparte entre la pantalla de arriba de la pila y las globales, y
    pinta el cuadro si cambió. `run` devuelve el código de salida, como el menú numerado."""

    def __init__(
        self,
        consola: Console,
        comandos: Dict,
        mgr: ConfigManager,
        *,
        leer_tecla: Optional[teclas.Lector] = None,  # None: el teclado de la terminal
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
        windows: bool = os.name == "nt",
        detectar: Callable[[], configurar.Entorno] = detectar_entorno,
        muestreador: Optional[Callable[[], Muestreador]] = None,
    ):
        self.consola, self.comandos, self.mgr = consola, comandos, mgr
        self._leer_tecla, self._dormir, self.reloj = leer_tecla, dormir, reloj
        self.windows = windows
        self._detectar = detectar
        self.nuevo_muestreador = muestreador or (lambda: Muestreador(None, lambda: (0, 0.0)))
        self.ascii = getattr(consola, "ascii_mode", False)
        self._spinner = Spinner("line" if self.ascii else "dots")
        self.config = mgr.load()
        self.pila: List[Pantalla] = [Inicio(self)]
        self.aviso: Tuple[str, str] = ("", "tenue")  # dura hasta la siguiente tecla
        self._fin, self._salida = False, None  # dejar la pantalla y, si hay, la acción a ejecutar fuera
        self._entorno: Optional[configurar.Entorno] = None
        self._hilo_entorno: Optional[threading.Thread] = None
        self.error_entorno = ""
        self._tema = self.config.theme  # el pintado: entra en la firma del cuadro
        self._tema_puesto = False
        self._cabecera: Tuple = ()
        self._ultimo_tic: Optional[float] = None
        self._firma = None
        self._animando = False  # el último cuadro tenía un spinner: se recompone en cada vuelta

    # ------------------------------------------------------------ para las pantallas
    def t(self, *partes: Tuple[str, str]) -> Text:
        """Trozos (texto, estilo) → una línea que no se parte: lo que sobra se corta (con «…»
        salvo en ASCII). Sin marcado de rich: un «[música]» en un título no desaparece."""
        texto = Text.assemble(*[(presentar(s, self.consola), e) for s, e in partes])
        texto.no_wrap, texto.overflow = True, "crop" if self.ascii else "ellipsis"
        return texto

    def parrafo(self, partes: Partes, ancho: int, sangria: int = 4) -> List[Text]:
        """Trozos → líneas partidas al ancho, con las de continuación sangradas."""
        texto = Text.assemble(*[(presentar(s, self.consola), e) for s, e in partes])
        lineas = texto.wrap(self.consola, max(20, ancho - sangria))
        return [linea if i == 0 else Text(" " * sangria) + linea for i, linea in enumerate(lineas)]

    def spinner(self, texto: str) -> Text:
        self._animando = True
        return self.t((self._spinner.render(self.reloj()).plain + " ", "acento"), (texto, "tenue"))

    def avisar(self, texto: str, estilo: str = "tenue") -> None:
        self.aviso = (texto, estilo)

    def abrir(self, pantalla: Pantalla) -> None:
        self.pila.append(pantalla)

    def volver(self) -> None:
        self.pila.pop().al_salir()
        if not self.pila:
            self.salir()

    def salir(self, accion: Optional[str] = None) -> None:
        self._fin, self._salida = True, accion

    def entorno(self) -> Optional[configurar.Entorno]:
        """Lo que Opciones ofrece elegir; None mientras se detecta. Una sola detección por menú y
        en su hilo: PortAudio no se puede inicializar dos veces a la vez."""
        if self._hilo_entorno is None:
            def detectar():
                try:
                    self._entorno = self._detectar()
                except Exception as e:  # que Opciones no se quede girando: lo dice y se puede volver
                    self.error_entorno = f"⚠ No se pudo detectar el entorno: {e.__class__.__name__}: {e}"

            self._hilo_entorno = threading.Thread(target=detectar, daemon=True, name="opciones")
            self._hilo_entorno.start()
        return self._entorno

    def poner_tema(self, nombre: str) -> None:
        if self._tema_puesto:
            self.consola.pop_theme()
        self.consola.push_theme(tema_rich(nombre))
        self._tema_puesto, self._tema = True, nombre

    def alternar_tema(self) -> str:
        """Del oscuro al claro o al revés («sistema» se resuelve primero), y se guarda como hace
        la ventana. Con config.json ilegible se cambia solo aquí: guardar pisaría lo del usuario."""
        nuevo = "claro" if paleta.resolver(self.config.theme) == "oscuro" else "oscuro"
        self.poner_tema(nuevo)
        config = self.mgr.load()
        if self.mgr.last_error:
            self.avisar("⚠ Tema cambiado solo en esta terminal: config.json no se puede leer y no se guarda.", "error")
        else:
            config.theme = nuevo
            self.mgr.save(config)
            self.config = config
            self.avisar(f"✔ Tema {nuevo} guardado: vale también para la ventana.", "ok")
        return nuevo

    # ------------------------------------------------------------ teclas
    def _tecla(self, k: str) -> None:
        self.aviso = ("", "tenue")
        pantalla = self.pila[-1]
        if len(k) == 1 and not pantalla.escribiendo:
            k = k.lower()  # Q, T y J valen como q, t y j
        if pantalla.tecla(k):
            return
        if k in (ESC, "q"):
            self.volver()
        elif k == "?" and not isinstance(pantalla, Ayuda):
            self.abrir(Ayuda(self))
        elif k == "t":
            self.alternar_tema()

    # ------------------------------------------------------------ pintar
    def _refrescar_cabecera(self) -> None:
        self.config = self.mgr.load()  # se relee: otra ventana u Opciones pueden haberla cambiado
        hw = peek_hardware()
        self._cabecera = (
            nota_de_hoy(self.config.notes_dir),
            describe_quality(self.config),
            motor_previsto(self.config, hw).texto if hw else "",
            describe_hardware(hw) if hw else "",
            self.mgr.last_error,
        )

    def _lineas_cabecera(self) -> List[Text]:
        nota, calidad, motor, equipo, error = self._cabecera
        uno = self.t(("Recorder", "bold"), (" · nota de hoy: ", "tenue"), (nota, "texto"))
        if error:
            dos = self.t((f"⚠ {error}", "error"))
        else:
            dos = self.t((calidad, "tenue"), (" · se usaría " if motor else "", "tenue"), (motor, "texto"))
        tres = self.t(("Equipo: ", "tenue"), (equipo, "tenue")) if equipo else self.spinner("detectando el equipo…")
        return [uno, dos, tres]

    def _partida(self, partes: Partes, ancho: int) -> List[Text]:
        if not partes or not "".join(s for s, _e in partes):
            return []
        return list(Text.assemble(*[(presentar(s, self.consola), e) for s, e in partes]).wrap(self.consola, ancho))

    def marco(self) -> List[Text]:
        """El cuadro entero, de la altura de la terminal: cabecera, título, cuerpo, ayuda, aviso y pie."""
        ancho, alto = self.consola.size
        pantalla = self.pila[-1]
        self._animando = False
        arriba = self._lineas_cabecera() + [
            self.t(("─" * ancho, "borde")),
            self.t((" › ".join(p.titulo for p in self.pila), "bold")),
        ]
        texto, estilo = pantalla.ayuda()
        abajo = (
            [Text()] + self._partida([(texto, estilo)], ancho) + self._partida([self.aviso], ancho)
            + self._partida(partes_teclas(pantalla.teclas()), ancho)
        )
        sitio = max(1, alto - len(arriba) - len(abajo))
        cuerpo, foco = pantalla.cuerpo(ancho, sitio)
        visibles = [cuerpo[i] for i in recorte(len(cuerpo), foco, sitio)]
        return arriba + visibles + [Text()] * (sitio - len(visibles)) + abajo

    def _pintar(self, live: Live, forzar: bool) -> None:
        ahora = self.reloj()
        tic = self._ultimo_tic is None or ahora - self._ultimo_tic >= TIC
        if tic:
            self._ultimo_tic = ahora
            self._refrescar_cabecera()
        if not (forzar or tic or self._animando):
            return
        lineas = self.marco()
        firma = (tuple(l.plain for l in lineas), self._tema, self.consola.size)
        if firma != self._firma:
            self._firma = firma
            live.update(Group(*lineas), refresh=True)

    # ------------------------------------------------------------ bucle
    def _teclado(self):
        return contextlib.nullcontext(self._leer_tecla) if self._leer_tecla else teclas.teclado()

    def _navegar(self) -> Optional[str]:
        """Las pantallas, hasta salir o hasta elegir algo que se ejecuta fuera (su acción)."""
        self._fin, self._salida, self._firma = False, None, None
        tam, tecla = None, None
        with self._teclado() as leer, Live(console=self.consola, screen=True, auto_refresh=False) as live:
            while True:
                self._pintar(live, forzar=tecla is not None or self.consola.size != tam)
                tam = self.consola.size
                tecla = leer()
                if tecla is None:
                    self._dormir(INTERVALO)
                    continue
                self._tecla(tecla)
                if self._fin:
                    return self._salida  # tras una tecla se repinta sin esperar


    def _ejecutar(self, accion: str) -> Optional[int]:
        """Lo elegido que usa la terminal entera. Grabar y la ventana terminan el menú (su código);
        un comando vuelve a las pantallas tras pulsar una tecla (None)."""
        if self._hilo_entorno is not None:
            self._hilo_entorno.join()  # su PyAudio debe estar cerrado antes de abrir otro
        if accion == "grabar":
            from .live import grabar

            return grabar(consola=self.consola)
        if accion == "ventana":
            return despacho.abrir_ventana()
        self.consola.print(*self._partida([(ayuda.linea("menu_" + accion), "tenue")], self.consola.width), sep="\n")
        despacho.ejecutar_comando(accion, (), self.consola, self.comandos)
        self.consola.print(self.t(*partes_teclas((("una tecla", "volver al menú"),))))
        with self._teclado() as leer:
            while leer() is None:
                self._dormir(INTERVALO)
        return None

    def run(self) -> int:
        if peek_hardware() is None:
            threading.Thread(target=cached_hardware, daemon=True, name="equipo").start()
        try:
            while True:
                accion = self._navegar()
                if accion is None:
                    return 0
                codigo = self._ejecutar(accion)
                if codigo is not None:
                    return codigo
        except KeyboardInterrupt:
            return 0
        finally:
            for pantalla in self.pila:
                pantalla.al_salir()
