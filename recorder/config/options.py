"""Lógica de la ventana de Opciones sin Tkinter: qué se muestra y qué se guarda.

Una interfaz (hoy la ventana ⚙ Opciones; mañana el comando `daily config` en la terminal)
recoge valores planos -- textos tal como se escriben, etiquetas elegidas de una lista, un
número -- en un `SettingsForm`, y este módulo decide qué significan: a qué dispositivo o
pantalla corresponde una etiqueta, qué preset es, cuántos hilos son válidos y qué cambió al
guardar para que la ventana principal reaccione (mover las notas, reabrir el audio). Todo son
funciones puras: nada de aquí toca widgets, disco ni hardware; las listas de dispositivos,
pantallas y ventanas abiertas las consulta quien llama y las pasa como datos.
"""

import dataclasses
from typing import Dict, List, Optional, Sequence, Tuple

from ..rutas import citar_documentos
from .hardware import GpuInfo, HardwareProfile, describe_gpu
from .schema import (
    AppConfig,
    CUSTOM_PRESET,
    QUALITY_PRESETS,
    Recommendation,
    apply_preset,
    describe_recommendation,
    describe_runtime,
    preset_availability,
    preset_key_for_config,
    recommended_cpu_threads,
)

DEFAULT_DEV = "(predeterminado de Windows)"
WINDOW_PREFIX = "Ventana: "  # distingue en el selector una ventana de aplicación de una pantalla
AUTO_GPU = "Automática (dedicada)"
MAX_THREADS = 256

RuntimeValues = Tuple[str, int, str, str]  # (modelo, haz, dispositivo, precisión)


@dataclasses.dataclass
class SettingsForm:
    """Los campos de Opciones tal como los ve el usuario: textos y etiquetas, no valores de config.

    Se traducen a `AppConfig` en `apply_settings`; hasta entonces se pueden editar y probar sin
    tocar la configuración real.
    """

    notes_dir: str
    caps_dir: str
    keywords: str  # separadas por coma, tal como se escriben
    out_dev: str  # etiqueta del selector; DEFAULT_DEV = el predeterminado de Windows
    mic_dev: str
    mic: bool
    target: str  # una pantalla de `screens` o WINDOW_PREFIX + título de la ventana
    quality: str  # clave de QUALITY_PRESETS, o CUSTOM_PRESET
    custom_values: Optional[RuntimeValues]  # lo puesto por «Usar recomendado» cuando no es un preset
    cpu_threads: str  # texto: se valida al guardar (`parse_threads`)
    whispercpp_dir: str
    whispercpp_flash_attn: bool
    whispercpp_device: int  # -1 = automática (ver `gpu_choices`)


@dataclasses.dataclass(frozen=True)
class SettingsChanges:
    """Qué cambió al guardar, para que la ventana principal mueva las notas o reabra el audio."""

    notes_changed: bool
    devices_changed: bool


def settings_form(config: AppConfig, screens: Sequence[str]) -> SettingsForm:
    """El formulario con los valores actuales de `config`, listo para editar."""
    return SettingsForm(
        notes_dir=config.notes_dir,
        caps_dir=config.caps_dir,
        keywords=", ".join(config.keywords),
        out_dev=device_choice(config.out_dev),
        mic_dev=device_choice(config.mic_dev),
        mic=config.mic,
        target=target_choice(config.window, config.screen, screens),
        quality=preset_key_for_config(config) or CUSTOM_PRESET,
        custom_values=None,
        cpu_threads=str(config.cpu_threads),
        whispercpp_dir=config.whispercpp_dir,
        whispercpp_flash_attn=config.whispercpp_flash_attn,
        whispercpp_device=config.whispercpp_device,
    )


def apply_settings(config: AppConfig, form: SettingsForm, screens: Sequence[str]) -> SettingsChanges:
    """Vuelca el formulario sobre `config`, en el sitio, y dice qué cambió.

    `screens` son las etiquetas de pantalla entre las que se eligió `form.target`.
    """
    new_notes = form.notes_dir.strip()
    notes_changed = new_notes != config.notes_dir

    new_out = device_from_choice(form.out_dev)
    new_mic = device_from_choice(form.mic_dev)
    devices_changed = new_out != config.out_dev or new_mic != config.mic_dev or form.mic != config.mic

    config.notes_dir = new_notes
    config.caps_dir = form.caps_dir.strip()
    config.keywords = parse_keywords(form.keywords)
    config.out_dev = new_out
    config.mic_dev = new_mic
    config.mic = form.mic
    window, screen = parse_target(form.target, screens)
    config.window = window
    if screen is not None:
        config.screen = screen

    if form.quality != CUSTOM_PRESET:
        apply_preset(config, form.quality)
    elif form.custom_values:
        config.model, config.beam_size, config.device, config.compute_type = form.custom_values
    # Personalizado sin «Usar recomendado»: no se toca ningun campo de modelo/haz/dispositivo/precision.

    config.cpu_threads = parse_threads(form.cpu_threads, config.cpu_threads)
    config.whispercpp_dir = form.whispercpp_dir.strip()
    config.whispercpp_flash_attn = form.whispercpp_flash_attn
    config.whispercpp_device = form.whispercpp_device
    return SettingsChanges(notes_changed, devices_changed)


# ------------------------------------------------------------------ dispositivos
def device_choices(names: Sequence[str]) -> List[str]:
    """Opciones del selector de un dispositivo WASAPI: el predeterminado y los nombres detectados."""
    return [DEFAULT_DEV] + list(names)


def device_choice(saved: str) -> str:
    """Etiqueta que corresponde a lo guardado ("" = predeterminado)."""
    return saved or DEFAULT_DEV


def device_from_choice(choice: str) -> str:
    """Lo que se guarda para una etiqueta: "" si es el predeterminado."""
    return "" if choice == DEFAULT_DEV else choice


# ------------------------------------------------------------------ captura
def target_choices(screens: Sequence[str], titles: Sequence[str], saved_window: str = "") -> List[str]:
    """Opciones de captura: las pantallas y las ventanas abiertas ahora (más la guardada, aunque esté cerrada)."""
    titles = list(titles)
    if saved_window and saved_window not in titles:
        titles.insert(0, saved_window)
    return list(screens) + [WINDOW_PREFIX + t for t in titles]


def target_choice(window: str, screen: int, screens: Sequence[str]) -> str:
    """Etiqueta de lo guardado: la ventana si hay, o la pantalla (la 0 si ya no existe tal monitor)."""
    if window:
        return WINDOW_PREFIX + window
    screen_idx = screen if screen < len(screens) else 0
    return screens[screen_idx]


def parse_target(choice: str, screens: Sequence[str]) -> Tuple[str, Optional[int]]:
    """(ventana, pantalla) que significa una etiqueta del selector.

    Con una ventana la pantalla es None: la guardada se conserva como plan B para cuando la
    ventana no esté abierta. Una etiqueta que ya no es ninguna pantalla cae a la 0 (todas).
    """
    if choice.startswith(WINDOW_PREFIX):
        return choice[len(WINDOW_PREFIX):], None
    return "", screens.index(choice) if choice in screens else 0


# ------------------------------------------------------------------ texto -> valores
def parse_keywords(text: str) -> List[str]:
    """"pendiente, bloqueo" -> ["pendiente", "bloqueo"], sin vacíos."""
    return [k.strip() for k in text.split(",") if k.strip()]


def parse_threads(text: str, previous: int) -> int:
    """Hilos de CPU: entero entre 0 y MAX_THREADS. Un texto no numérico conserva `previous`."""
    try:
        return min(max(int(text.strip()), 0), MAX_THREADS)
    except ValueError:
        return previous  # texto no numerico: se conserva el valor anterior


def threads_hint(hardware: Optional[HardwareProfile]) -> str:
    """Lo que acompaña al campo de hilos: qué significa 0 y cuántos se recomiendan para esta CPU."""
    if hardware is None:
        return "0 = 4 de la biblioteca"
    p = hardware
    nucleos = f"{p.physical_cores} núcleos" if p.physical_cores else f"{p.logical_cores} hilos"
    return f"0 = 4 de la biblioteca · recomendado: {recommended_cpu_threads(p)} ({nucleos})"


# ------------------------------------------------------------------ GPU de whisper.cpp
def gpu_choices(vulkan_devices: Sequence[GpuInfo], current: int) -> Dict[str, int]:
    """Etiqueta del desplegable -> whispercpp_device. La guardada sigue en la lista aunque ya no se detecte."""
    opciones = {AUTO_GPU: -1}
    for g in vulkan_devices:
        opciones[f"{g.vulkan_index}: {describe_gpu(g)}"] = g.vulkan_index
    if current >= 0 and current not in opciones.values():
        opciones[f"{current}: (no detectada ahora)"] = current
    return opciones


def gpu_choice(choices: Dict[str, int], device: int) -> str:
    """La etiqueta de `device` en `choices`, o la automática si no está."""
    return next((k for k, v in choices.items() if v == device), AUTO_GPU)


# ------------------------------------------------------------------ calidad
def quality_display(key: str, cuda_devices: int, vulkan_ready: bool) -> str:
    """Texto del desplegable para un preset: el nombre, o por qué no está disponible aquí."""
    if key == CUSTOM_PRESET:
        return "Personalizado"
    preset = QUALITY_PRESETS[key]
    if preset_availability(key, cuda_devices, vulkan_ready).available:
        return preset.label
    return f"{preset.label} (no disponible en este equipo)"


def custom_runtime(config: AppConfig, custom_values: Optional[RuntimeValues]) -> RuntimeValues:
    """Lo que se guarda con «Personalizado»: lo de «Usar recomendado» o lo que ya había."""
    return custom_values or (config.model, config.beam_size, config.device, config.compute_type)


def quality_description(
    key: str,
    custom_values: RuntimeValues,
    rec: Optional[Recommendation],
    cuda_devices: int,
    vulkan_ready: bool,
) -> str:
    """La línea que explica el preset elegido; para Personalizado, `custom_values` (ver `custom_runtime`)."""
    if key == CUSTOM_PRESET:
        es_rec = rec is not None and custom_values == (rec.model, rec.beam_size, rec.device, rec.compute_type)
        return (
            f"Personalizado: {describe_runtime(*custom_values)}"
            f"{' (la recomendada para este equipo)' if es_rec else ''}. "
            "No coincide con ningún preset; se guarda tal cual si no eliges otro."
        )
    preset = QUALITY_PRESETS[key]
    avail = preset_availability(key, cuda_devices, vulkan_ready)
    text = citar_documentos(preset.summary)  # instalado, los docs/… del resumen pasan a su URL
    if not avail.available:
        text += f" ⚠ {avail.reason} Si se guarda igual, Recorder cae a CPU solo, sin romperse."
    return text


# ------------------------------------------------------------------ recomendación
def recommendation_text(rec: Optional[Recommendation]) -> str:
    """La línea de «Recomendado para este equipo», o que aún se está detectando."""
    if rec is None:
        return "Recomendado para este equipo: detectando el equipo…"
    return f"Recomendado para este equipo: {describe_recommendation(rec)} — {rec.reason} [{rec.confidence}]"


def use_recommendation(form: SettingsForm, rec: Recommendation) -> None:
    """«Usar recomendado»: pone en el formulario la calidad, los hilos y, con whisper.cpp, flash attention.

    Una recomendación que no es un preset va como Personalizado con sus 4 valores. No toca
    rutas, dispositivos ni palabras clave.
    """
    if rec.preset:
        form.custom_values = None
        form.quality = rec.preset
    else:
        form.custom_values = (rec.model, rec.beam_size, rec.device, rec.compute_type)
        form.quality = CUSTOM_PRESET
    form.cpu_threads = str(rec.cpu_threads)
    if rec.engine == "whisper.cpp":
        form.whispercpp_flash_attn = rec.flash_attn
