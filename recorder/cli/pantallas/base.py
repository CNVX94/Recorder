"""Lo común de todas las pantallas: la clase base, las constantes de tiempos y tamaños y la
lógica pura (recorte, barras, tendencia, nota de hoy, motor previsto, detección del entorno)."""
import datetime
import pathlib
from typing import List, Optional, Sequence, Tuple

from rich.text import Text

from ... import ayuda
from ...config.hardware import HardwareProfile, cached_hardware
from ...config.schema import AppConfig, choose_vulkan_device, resolve_runtime, vulkan_model_for
from ...engine.whispercpp import whispercpp_ready
from ...metricas import MotorEfectivo, hilos_efectivos
from .. import configurar
from ..consola import JUEGO_ASCII, JUEGO_COMPLETO, JUEGO_CONSOLA
from ..teclas import ABAJO, ARRIBA

INTERVALO = 0.05  # s entre lecturas del teclado
TIC = 1.0  # s entre refrescos de la cabecera (y de las cifras de Rendimiento)
HISTORIA = 60  # muestras de la tendencia de Rendimiento: 2 minutos con una cada 2 s
MARCA = "▶"  # la fila elegida; `presentar` la deja en «►» en el juego «consola» y en «>» en ASCII
# La tendencia, de 0 a 100 %, en cada juego de símbolos (en «consola», solo lo que dibuja Consolas).
CHISPAS = {JUEGO_COMPLETO: "▁▂▃▄▅▆▇█", JUEGO_CONSOLA: "·░▄█", JUEGO_ASCII: "_.:-=+*#"}

Partes = Sequence[Tuple[str, str]]
Teclas = Sequence[Tuple[str, str]]  # (tecla, palabra) tal como van en el pie


# ------------------------------------------------------------------ lógica pura
def recorte(n: int, foco: int, sitio: int) -> range:
    """Las filas de `n` que se ven en `sitio` líneas, con `foco` dentro (centrado si se puede)."""
    inicio = min(max(0, foco - sitio // 2), max(0, n - sitio))
    return range(inicio, min(n, inicio + sitio))


def barra(valor: float, ancho: int) -> Tuple[str, str]:
    """(lleno, vacío) de una barra de `ancho` celdas para un % de 0 a 100."""
    llenos = round(max(0.0, min(100.0, valor)) / 100 * ancho)
    return "█" * llenos, "░" * (ancho - llenos)


def tendencia(valores: Sequence[Optional[float]], ancho: int, juego: str = JUEGO_COMPLETO) -> str:
    """Las últimas `ancho` muestras (% de 0 a 100) como una línea de bloques; un hueco sin dato."""
    if ancho <= 0:
        return ""
    chispas = CHISPAS[juego]
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
        vulkan = choose_vulkan_device(config.whispercpp_device, hw.vulkan_devices, config.allow_igpu)
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


def mover(sel: int, n: int, k: str) -> Optional[int]:
    """La fila elegida tras ↑/↓ (o k/j), dando la vuelta; None si `k` no mueve."""
    if k in (ARRIBA, "k"):
        return (sel - 1) % n
    if k in (ABAJO, "j"):
        return (sel + 1) % n
    return None


def pie(*pares: Tuple[str, str]) -> List[Tuple[str, str]]:
    """((tecla, clave_pie), …) → ((tecla, palabra), …): la palabra sale de recorder/ayuda.py («pie_» + clave)."""
    return [(tecla, ayuda.entrada("pie_" + clave)[0]) for tecla, clave in pares]


# ------------------------------------------------------------------ la pantalla
class Pantalla:
    """Lo común: un título, un cuerpo de líneas, la línea de ayuda, el pie y sus teclas."""

    titulo = ""
    TECLAS: Sequence[Tuple[str, str]] = (("Esc", "volver"), ("?", "ayuda"), ("t", "tema"))  # (tecla, clave de pie_)
    escribiendo = False  # True mientras se teclea un texto: las letras llegan tal cual, sin atajos
    abre_ayuda = True  # False en la propia Ayuda: ahí «?» no hace nada

    def __init__(self, terminal: "Terminal"):  # noqa: F821
        self.app = terminal

    def cuerpo(self, ancho: int, sitio: int) -> Tuple[List[Text], int]:
        """(líneas, la que debe quedar a la vista). `sitio`: las líneas que caben."""
        return [], 0

    def ayuda(self) -> Tuple[str, str]:
        return "", "tenue"

    def marca(self) -> Tuple[str, str]:
        """Lo que va a la derecha de la ruta («● cambios sin guardar»): (texto, estilo), o vacío."""
        return "", "tenue"

    def teclas(self) -> Teclas:
        return pie(*self.TECLAS)

    def tecla(self, k: str) -> bool:
        """True si la atendió; si no, la atiende la terminal (Esc, q, ?, t)."""
        return False

    def al_salir(self) -> None:
        pass
