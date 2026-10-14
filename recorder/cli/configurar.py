"""`daily config`: la ventana ⚙ Opciones en la terminal, sobre la misma lógica (config/options.py).

Sin argumentos pregunta por secciones (carpetas, audio, capturas con la calidad del buffer de
capturas por palabra clave, calidad y motor), enseña qué cambió y guarda solo al confirmar. `--ver` muestra la configuración, `--editor` abre config.json
en el editor del sistema y `--recomendado` aplica la configuración recomendada para el equipo
(lo mismo que `daily recomendar --aplicar`). No importa tkinter.

Una grabación ya abierta en otra ventana no relee config.json: lo que se guarda aquí vale desde
el próximo arranque, y así se avisa al guardar.
"""

import argparse
import copy
import dataclasses
import os
from typing import Callable, List, Optional, Tuple

import pyaudiowpatch as pa
from rich import box
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text

from ..actions.screenshot import screen_labels, window_titles
from ..audio.devices import wasapi_devices
from ..config.hardware import HardwareProfile, cached_hardware, peek_hardware
from ..config.manager import ConfigManager
from ..config.options import (
    AUTO_GPU,
    MAX_THREADS,
    WINDOW_PREFIX,
    SettingsForm,
    apply_settings,
    capture_choice,
    capture_choices,
    custom_runtime,
    device_choice,
    device_choices,
    gpu_choice,
    gpu_choices,
    parse_threads,
    quality_description,
    quality_display,
    recommendation_text,
    settings_form,
    target_choices,
    threads_hint,
    use_recommendation,
)
from ..config.schema import (
    AppConfig,
    CUSTOM_PRESET,
    PRESET_ORDER,
    QUALITY_PRESETS,
    describe_runtime,
    preset_availability,
    preset_key_for_config,
    recommend_config,
)
from ..engine.whispercpp import vulkan_readiness, whispercpp_ready, whispercpp_status
from ..filters.lexicon import format_fixes
from .preguntas import Cancelado, confirmar, contar, elegir, imprimir, preguntar_entero, preguntar_texto, texto
from .recomendar import recomendar as recomendar_equipo

NOMBRE = "config"
AYUDA = "configuración: carpetas, audio, capturas, calidad y motor (se guarda en config.json)"

AVISO_REINICIO = (
    "Los cambios valen desde el próximo arranque: una grabación ya abierta sigue con lo anterior."
)
# Estilo del estado de la carpeta de whisper.cpp según su nivel (ver `whispercpp_status`).
ESTILO_ESTADO = {"ok": "ok", "warning": "error", "info": "tenue"}

# Cómo se llama cada campo de AppConfig al enseñar qué cambió.
ETIQUETAS = {
    "notes_dir": "Carpeta de notas", "caps_dir": "Carpeta de capturas", "keywords": "Palabras clave",
    "mic": "Transcribir el micrófono", "out_dev": "Salida a capturar", "mic_dev": "Micrófono",
    "screen": "Pantalla", "window": "Ventana a capturar", "captures": "Capturas por palabra clave",
    "model": "Modelo", "beam_size": "Haz",
    "device": "Dispositivo", "compute_type": "Precisión", "whispercpp_dir": "Carpeta de whisper.cpp",
    "whispercpp_flash_attn": "Flash attention", "whispercpp_device": "GPU de whisper.cpp",
    "cpu_threads": "Hilos de CPU", "vocab": "Vocabulario", "ignore": "Frases a ignorar",
    "fixes": "Correcciones", "no_speech_threshold": "Umbral de silencio",
    "logprob_threshold": "Umbral de confianza", "compression_ratio_threshold": "Umbral anti-bucles",
    "repetition_penalty": "Penalización de repetición",
}


def agregar_argumentos(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--ver", action="store_true", help="muestra la configuración actual y sale")
    parser.add_argument("--editor", action="store_true", help="abre config.json en el editor del sistema")
    parser.add_argument(
        "--recomendado", action="store_true",
        help="aplica la configuración recomendada para este equipo (como daily recomendar --aplicar)",
    )


def ejecutar(args: argparse.Namespace, consola: Console, mgr: Optional[ConfigManager] = None) -> int:
    """Punto de entrada del comando. `mgr` se inyecta en las pruebas para no tocar el config.json real."""
    mgr = mgr or ConfigManager()
    config = mgr.load()
    if args.editor:
        return abrir_editor(mgr, config, consola)
    if mgr.last_error:
        # Config ilegible: se cargaron los valores de fábrica y guardarlos pisaría lo del usuario.
        imprimir(consola, f"[error]{escape(mgr.last_error)}[/]")
        if args.ver:
            ver(config, consola)
        return 1
    if args.ver:
        ver(config, consola)
        return 0
    if args.recomendado:
        return recomendar(mgr, consola)
    try:
        return asistente(mgr, config, consola)
    except Cancelado:
        imprimir(consola, "\n[tenue]Cancelado, no se guardó nada.[/]")
        return 1


# ------------------------------------------------------------------ lo que la ventana consulta al abrirse
@dataclasses.dataclass
class Entorno:
    """Pantallas, ventanas abiertas, dispositivos WASAPI y el perfil del equipo: datos para el asistente."""

    screens: List[str]
    windows: List[str]
    out_devs: List[str]
    mic_devs: List[str]
    hardware: HardwareProfile


def dispositivos_audio() -> Tuple[List[str], List[str]]:
    """(salidas, micrófonos) WASAPI, con un PyAudio propio que se cierra al terminar (no hay flujos abiertos)."""
    p = pa.PyAudio()
    try:
        return wasapi_devices(p, "out"), wasapi_devices(p, "mic")
    finally:
        p.terminate()


def detectar_entorno(consola: Console) -> Entorno:
    if peek_hardware() is None:
        imprimir(consola, "[tenue]Detectando el equipo…[/]")
    salidas, micros = dispositivos_audio()
    return Entorno(screen_labels(), window_titles(), salidas, micros, cached_hardware())


# ------------------------------------------------------------------ asistente
SECCIONES = [
    "Carpetas y palabras clave",
    "Audio: salida a capturar y micrófono",
    "Capturas: pantalla o ventana, y calidad de las capturas por palabra clave",
    "Calidad y motor: preset, hilos, whisper.cpp y GPU",
]
TODO, GUARDAR, SALIR = "Todo, paso a paso", "Guardar y salir", "Salir sin guardar"


def asistente(mgr: ConfigManager, config: AppConfig, consola: Console) -> int:
    """Pregunta por secciones sobre un `SettingsForm`; guarda solo al confirmar los cambios."""
    imprimir(consola, f"[acento]⚙ Configuración de Recorder[/]  [tenue]{escape(str(mgr.path))}[/]")
    imprimir(consola, "[tenue]Enter conserva el valor actual, «-» vacía un campo y Ctrl+C cancela sin guardar.[/]")
    entorno = detectar_entorno(consola)
    form = settings_form(config, entorno.screens)
    pasos: List[Callable[[Console, SettingsForm, AppConfig, Entorno], None]] = [
        paso_carpetas, paso_audio, paso_capturas, paso_calidad,
    ]
    opciones = SECCIONES + [TODO, GUARDAR, SALIR]
    while True:
        imprimir(consola)
        i = elegir(consola, "¿Qué quieres cambiar?", opciones)
        if opciones[i] == SALIR:
            if diferencias(config, aplicado(config, form, entorno.screens)):
                imprimir(consola, "[tenue]No se guardó nada.[/]")
                return 1
            return 0
        if opciones[i] != GUARDAR:
            for paso in pasos if opciones[i] == TODO else [pasos[i]]:
                paso(consola, form, config, entorno)
        codigo = guardar(mgr, config, form, entorno.screens, consola)
        if codigo is not None:
            return codigo


def aplicado(config: AppConfig, form: SettingsForm, screens: List[str]) -> AppConfig:
    """Una copia de `config` con el formulario volcado: lo que se guardaría."""
    nuevo = copy.deepcopy(config)
    apply_settings(nuevo, form, screens)
    return nuevo


def guardar(
    mgr: ConfigManager, config: AppConfig, form: SettingsForm, screens: List[str], consola: Console
) -> Optional[int]:
    """Enseña qué cambió y, si se confirma, guarda y devuelve 0. None = seguir en el menú."""
    nuevo = aplicado(config, form, screens)
    cambios = diferencias(config, nuevo)
    if not cambios:
        imprimir(consola, "[tenue]Sin cambios.[/]")
        return None
    imprimir(consola)
    consola.print(tabla_cambios(consola, cambios))
    if not confirmar(consola, f"¿Guardar en {mgr.path.name}?", True):
        return None
    mgr.save(nuevo)
    imprimir(consola, f"[ok]✔ Guardado en {escape(str(mgr.path))}.[/] {AVISO_REINICIO}")
    return 0


def paso_carpetas(consola: Console, form: SettingsForm, config: AppConfig, entorno: Entorno) -> None:
    imprimir(consola, "\n[acento]Carpetas y palabras clave[/]")
    form.notes_dir = preguntar_texto(consola, "Carpeta de notas (.md)", form.notes_dir)
    form.caps_dir = preguntar_texto(consola, "Carpeta de capturas", form.caps_dir)
    form.keywords = preguntar_texto(
        consola, "Palabras clave que disparan una captura (separadas por coma)", form.keywords
    )


def paso_audio(consola: Console, form: SettingsForm, config: AppConfig, entorno: Entorno) -> None:
    imprimir(consola, "\n[acento]Audio[/]")
    form.out_dev = elegir_dispositivo(consola, "Salida a capturar 🔊", device_choices(entorno.out_devs), form.out_dev)
    form.mic = confirmar(consola, "¿Transcribir también mi micrófono 🎤?", form.mic)
    if form.mic:
        form.mic_dev = elegir_dispositivo(consola, "Micrófono 🎤", device_choices(entorno.mic_devs), form.mic_dev)


def elegir_dispositivo(consola: Console, etiqueta: str, opciones: List[str], actual: str) -> str:
    if actual not in opciones:
        opciones = opciones[:1] + [actual] + opciones[1:]  # el guardado que ya no se detecta sigue elegible
    return opciones[elegir(consola, etiqueta, opciones, opciones.index(actual))]


def paso_capturas(consola: Console, form: SettingsForm, config: AppConfig, entorno: Entorno) -> None:
    imprimir(consola, "\n[acento]Capturas[/]")
    opciones = target_choices(entorno.screens, entorno.windows, config.window)
    if form.target not in opciones:
        opciones.append(form.target)
    form.target = opciones[elegir(consola, "Qué capturar 📸", opciones, opciones.index(form.target))]
    # Buffer de capturas por palabra clave (docs/captura-diferida.md): el mismo desplegable que la ventana
    calidades = capture_choices()
    imprimir(consola, (
        "  [tenue]La imagen es la del momento en que se dijo la palabra, aunque la transcripción vaya "
        "atrasada; el disco solo se ocupa mientras hay atraso.[/]"
    ))
    form.captures = calidades[elegir(consola, "Capturas por palabra clave", calidades, calidades.index(form.captures))]


def paso_calidad(consola: Console, form: SettingsForm, config: AppConfig, entorno: Entorno) -> None:
    hw = entorno.hardware
    imprimir(consola, "\n[acento]Calidad y motor[/]")
    # La carpeta de whisper.cpp va primero: de ella dependen que Extra esté disponible y la recomendación.
    form.whispercpp_dir = preguntar_texto(
        consola, "Carpeta de whisper.cpp (GPU AMD/Intel; vacía si no se usa)", form.whispercpp_dir
    )
    estado = whispercpp_status(form.whispercpp_dir, hw)
    imprimir(consola, f"  [{ESTILO_ESTADO[estado.level]}]{escape(estado.text)}[/]")
    carpeta = form.whispercpp_dir.strip()
    extra = QUALITY_PRESETS["extra"]
    vulkan_ready = whispercpp_ready(carpeta, extra.model, extra.compute_type)
    rec = recommend_config(hw, *vulkan_readiness(carpeta))

    imprimir(consola, f"  [ok]{escape(recommendation_text(rec))}[/]")
    if confirmar(consola, "¿Usar la recomendada (calidad, hilos y, con whisper.cpp, flash attention)?", False):
        use_recommendation(form, rec)
        imprimir(consola, f"  Calidad: {quality_display(form.quality, hw.cuda_devices, vulkan_ready)} · hilos: {form.cpu_threads}")
    else:
        claves = PRESET_ORDER + [CUSTOM_PRESET]
        etiquetas = [quality_display(k, hw.cuda_devices, vulkan_ready) for k in claves]
        form.quality = claves[elegir(
            consola, "Calidad de transcripción (se aplica al reiniciar)", etiquetas, claves.index(form.quality)
        )]
        disponible = form.quality == CUSTOM_PRESET or preset_availability(form.quality, hw.cuda_devices, vulkan_ready).available
        descripcion = quality_description(
            form.quality, custom_runtime(config, form.custom_values), rec, hw.cuda_devices, vulkan_ready
        )
        imprimir(consola, f"  [{'tenue' if disponible else 'error'}]{escape(descripcion)}[/]")
        form.cpu_threads = str(preguntar_entero(
            consola, "Hilos de CPU", parse_threads(form.cpu_threads, config.cpu_threads), 0, MAX_THREADS,
            ayuda=threads_hint(hw),
        ))

    if carpeta:  # la GPU de Vulkan y flash attention solo cuentan con whisper.cpp
        gpus = gpu_choices(hw.vulkan_devices, config.whispercpp_device)
        etiquetas = list(gpus)
        actual = gpu_choice(gpus, form.whispercpp_device)
        form.whispercpp_device = gpus[etiquetas[elegir(consola, "GPU de whisper.cpp", etiquetas, etiquetas.index(actual))]]
        form.whispercpp_flash_attn = confirmar(consola, "¿Flash attention en whisper.cpp?", form.whispercpp_flash_attn)


# ------------------------------------------------------------------ qué cambió
def formatear(campo: str, valor) -> str:
    """Un valor de AppConfig como se lee: listas por coma, sí/no, y el significado de los vacíos."""
    if campo in ("out_dev", "mic_dev"):
        return device_choice(valor)
    if campo == "whispercpp_device":
        return AUTO_GPU if valor < 0 else str(valor)
    if campo == "window":
        return valor or "(ninguna: se captura la pantalla)"
    if campo == "captures":
        return capture_choice(valor)
    if isinstance(valor, bool):
        return "sí" if valor else "no"
    if isinstance(valor, list):
        return ", ".join(str(v) for v in valor) or "(ninguna)"
    if isinstance(valor, dict):
        return format_fixes(valor) or "(ninguna)"
    if valor == "":
        return "(vacío)"
    return str(valor)


def diferencias(antes: AppConfig, despues: AppConfig) -> List[Tuple[str, str, str]]:
    """[(etiqueta, antes, después)] de los campos que cambian, en el orden de AppConfig."""
    a, d = antes.to_dict(), despues.to_dict()
    return [(ETIQUETAS.get(k, k), formatear(k, a[k]), formatear(k, d[k])) for k in a if a[k] != d[k]]


def tabla_cambios(consola: Console, cambios: List[Tuple[str, str, str]]) -> Table:
    tabla = Table(box=_caja(consola), show_header=True, header_style="tenue", title="Cambios", title_style="acento")
    tabla.add_column("Ajuste")
    tabla.add_column("Antes", style="tenue")
    tabla.add_column("Después", style="acento")
    for etiqueta, antes, despues in cambios:
        tabla.add_row(*(Text(texto(consola, s)) for s in (etiqueta, antes, despues)))
    return tabla


def _caja(consola: Console):
    """Bordes de tabla: ASCII en la consola clásica, que pinta mal las líneas."""
    return box.ASCII if getattr(consola, "ascii_mode", False) else box.SIMPLE


# ------------------------------------------------------------------ --ver
def filas_resumen(config: AppConfig) -> List[Tuple[str, str]]:
    """La configuración en pares (ajuste, valor) legibles, para `--ver`."""
    preset = preset_key_for_config(config)
    calidad = QUALITY_PRESETS[preset].label if preset else "Personalizado"
    if config.window:
        captura = WINDOW_PREFIX + config.window
    else:
        captura = f"Pantalla {config.screen}" if config.screen else "(todas las pantallas)"
    return [
        ("Carpeta de notas", config.notes_dir),
        ("Carpeta de capturas", config.caps_dir),
        ("Palabras clave", formatear("keywords", config.keywords)),
        ("Salida a capturar 🔊", device_choice(config.out_dev)),
        ("Micrófono 🎤", device_choice(config.mic_dev) if config.mic else "no se transcribe"),
        ("Qué capturar 📸", captura),
        ("Capturas por palabra clave", capture_choice(config.captures)),
        ("Calidad", f"{calidad}: {describe_runtime(config.model, config.beam_size, config.device, config.compute_type)}"),
        ("Hilos de CPU", str(config.cpu_threads) if config.cpu_threads else "0 (4 de la biblioteca)"),
        ("whisper.cpp", config.whispercpp_dir or "(vacía: sin motor Vulkan)"),
        ("GPU de whisper.cpp", formatear("whispercpp_device", config.whispercpp_device)),
        ("Flash attention", formatear("whispercpp_flash_attn", config.whispercpp_flash_attn)),
        ("Vocabulario", config.vocab or "(vacío)"),
        ("Frases a ignorar", contar(len(config.ignore), "frase", "frases")),
        ("Correcciones", contar(len(config.fixes), "corrección", "correcciones")),
        ("Umbrales", (
            f"silencio {config.no_speech_threshold} · confianza {config.logprob_threshold} · "
            f"anti-bucles {config.compression_ratio_threshold}"
        )),
    ]


def ver(config: AppConfig, consola: Console) -> None:
    tabla = Table(box=_caja(consola), show_header=False)
    tabla.add_column("Ajuste", style="tenue", no_wrap=True)
    tabla.add_column("Valor")
    for ajuste, valor in filas_resumen(config):
        tabla.add_row(Text(texto(consola, ajuste)), Text(texto(consola, valor)))
    consola.print(tabla)


# ------------------------------------------------------------------ --editor y --recomendado
def abrir_editor(mgr: ConfigManager, config: AppConfig, consola: Console) -> int:
    """Abre config.json con el programa asociado; si aún no existe, lo crea con los valores de fábrica."""
    if not mgr.path.exists():
        mgr.save(config)
    try:
        os.startfile(mgr.path)
    except OSError as e:
        imprimir(consola, f"[error]No se pudo abrir {escape(str(mgr.path))}: {escape(str(e))}[/]")
        return 1
    imprimir(consola, f"Abriendo {escape(str(mgr.path))} en el editor. [tenue]{AVISO_REINICIO}[/]")
    return 0


def recomendar(mgr: ConfigManager, consola: Console) -> int:
    """`--recomendado`: lo mismo que `daily recomendar --aplicar`, más el aviso de reinicio."""
    if peek_hardware() is None:
        imprimir(consola, "[tenue]Detectando el equipo…[/]")
    codigo = recomendar_equipo(True, consola, mgr)
    if codigo == 0:
        imprimir(consola, f"[tenue]{AVISO_REINICIO}[/]")
    return codigo
