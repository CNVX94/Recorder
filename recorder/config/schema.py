import dataclasses
import pathlib
from typing import Tuple, Dict, List, Optional


@dataclasses.dataclass
class AppConfig:
    notes_dir: str = dataclasses.field(
        default_factory=lambda: str(pathlib.Path.home() / "Documents" / "Dailies")
    )
    caps_dir: str = dataclasses.field(
        default_factory=lambda: str(pathlib.Path.home() / "Documents" / "Dailies" / "capturas")
    )
    keywords: List[str] = dataclasses.field(
        default_factory=lambda: ["pendiente", "bloqueo", "captura"]
    )
    mic: bool = True
    out_dev: str = ""   # Nombre WASAPI de la salida a capturar ("" = predeterminada)
    mic_dev: str = ""   # Nombre WASAPI del micrófono ("" = predeterminado)
    screen: int = 0     # 0 = todas las pantallas; 1..n = monitor n
    window: str = ""    # Título de la ventana de aplicación a capturar; "" = capturar según `screen`.
                        # Si la ventana ya no está abierta se captura según `screen` (ver screenshot.py).
    model: str = "small"  # tiny, base, small, medium, large-v3-turbo, large-v3
    beam_size: int = 5

    # Dispositivo y precision de la inferencia. "cpu"/"int8" es lo unico que corre sin
    # GPU; "cuda"/"float16" es lo que usa el preset Extra. Un config.json viejo no trae
    # estos dos campos y cae en estos valores por defecto, que es el comportamiento de
    # siempre. Ver QUALITY_PRESETS mas abajo y docs/presets-calidad.md.
    device: str = "cpu"  # "cpu" o "cuda"
    compute_type: str = "int8"  # "int8" en cpu; "float16" en cuda

    # Hilos de CPU que usa CTranslate2 en la inferencia. 0 = valor por defecto de
    # faster-whisper (4 hilos), que se queda corto en una CPU con mas nucleos.
    # Como elegirlo midiendo en tu equipo: docs/rendimiento.md.
    cpu_threads: int = 0

    # Vocabulario de contexto (Initial prompt) para guiar terminos tecnicos y nombres.
    # Vacio a proposito: cada usuario pone el suyo. Ver config.example.json.
    vocab: str = ""

    # Frases fantasma que Whisper inventa en silencios/ruido (lista negra)
    ignore: List[str] = dataclasses.field(
        default_factory=lambda: [
            "suscríbete",
            "próximo vídeo",
            "gracias por ver",
            "hasta la próxima",
            "subtítulos",
            "amara.org",
            "gracias por estar aquí",
            "dale like",
            "nos vemos en el próximo",
        ]
    )

    # Correcciones personales post-transcripcion: palabra completa (mal -> bien).
    # Vacio a proposito: se llena con lo que tu Whisper confunda. Ver config.example.json.
    fixes: Dict[str, str] = dataclasses.field(default_factory=dict)

    # Umbrales heurísticos anti-alucinaciones
    no_speech_threshold: float = 0.6  # Descartar si probabilidad de no-voz >= umbral
    logprob_threshold: float = -1.0    # Descartar si confianza logarítmica <= umbral
    compression_ratio_threshold: float = 2.4  # Descartar repeticiones si zlib ratio excede umbral
    repetition_penalty: float = 1.1

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        valid_fields = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


# ---------------------------------------------------------------------------------
# Presets de calidad de transcripcion.
#
# Cada preset es un punto en el mapa modelo/haz/dispositivo de docs/rendimiento.md y
# docs/hardware-y-modelos.md. No hay un campo "preset" guardado en el config: que
# preset corresponde a una configuracion se calcula comparando sus 4 campos contra
# esta tabla (`preset_key_for_config`), asi que una configuracion vieja o retocada a
# mano se reconoce igual, y si no coincide con ninguno se trata como Personalizado sin
# tocarla. Todo esto son funciones puras: no importan Tkinter ni tocan hardware, salvo
# `detect_cuda_device_count`, que es la unica que sale a preguntar y siempre puede
# devolver 0 sin reventar nada.
# ---------------------------------------------------------------------------------

CUSTOM_PRESET = "personalizado"


@dataclasses.dataclass(frozen=True)
class QualityPreset:
    """Que modelo, haz, dispositivo y precision usa un preset, y que implica elegirlo."""

    label: str
    model: str
    beam_size: int
    device: str  # "cpu" o "cuda"
    compute_type: str  # "int8" (cpu) o "float16" (cuda)
    summary: str  # que modelo es y si arriesga retraso en una CPU como la medida

    @property
    def requires_cuda(self) -> bool:
        return self.device == "cuda"


QUALITY_PRESETS: Dict[str, QualityPreset] = {
    "baja": QualityPreset(
        label="Baja",
        model="small",
        beam_size=1,
        device="cpu",
        compute_type="int8",
        summary=(
            "Modelo small, haz 1. La mas rapida en CPU (~5,4x tiempo real medido en "
            "reposo): no acumula retraso ni compartiendo el equipo con una "
            "videollamada. Es la que menos acierta con nombres propios y anglicismos "
            "tecnicos."
        ),
    ),
    "media": QualityPreset(
        label="Media",
        model="small",
        beam_size=5,
        device="cpu",
        compute_type="int8",
        summary=(
            "Modelo small, haz 5. Sigue yendo holgada en CPU (~3,0x tiempo real "
            "medido) y acierta mas que Baja gracias al haz mayor."
        ),
    ),
    "alta": QualityPreset(
        label="Alta",
        model="large-v3-turbo",
        beam_size=5,
        device="cpu",
        compute_type="int8",
        summary=(
            "Modelo large-v3-turbo, haz 5: la mejor calidad sin GPU. En una CPU como "
            "la medida va justo al ritmo del tiempo real (~1,0x en reposo) y se "
            "atrasa si hay otra carga (videollamada, IDE); ver docs/rendimiento.md si "
            "la cola crece."
        ),
    ),
    "extra": QualityPreset(
        label="Extra",
        model="large-v3",
        beam_size=5,
        device="cuda",
        compute_type="float16",
        summary=(
            "Modelo large-v3 en GPU NVIDIA (float16): la mejor calidad disponible. "
            "Requiere una GPU NVIDIA con CUDA; sin GPU, large-v3 no llega al tiempo "
            "real en CPU, asi que este preset solo tiene sentido en un equipo con GPU."
        ),
    ),
}

# Orden de presentacion, de menor a mayor calidad. CUSTOM_PRESET no esta aqui: no es
# un preset, es lo que se muestra cuando ninguno de estos coincide.
PRESET_ORDER: List[str] = ["baja", "media", "alta", "extra"]


def preset_key_for_config(config: AppConfig) -> Optional[str]:
    """Que preset corresponde a `config`, o None si es una combinacion personalizada.

    Compara solo los 4 campos que definen un preset (modelo, haz, dispositivo,
    compute_type); el resto de la configuracion (vocabulario, filtros, rutas...) no
    influye. Funcion pura, sin acceso a disco ni a hardware.
    """
    for key in PRESET_ORDER:
        preset = QUALITY_PRESETS[key]
        if (
            config.model == preset.model
            and config.beam_size == preset.beam_size
            and config.device == preset.device
            and config.compute_type == preset.compute_type
        ):
            return key
    return None


def apply_preset(config: AppConfig, key: str) -> None:
    """Aplica sobre `config`, en el sitio, los 4 valores del preset `key`."""
    preset = QUALITY_PRESETS[key]
    config.model = preset.model
    config.beam_size = preset.beam_size
    config.device = preset.device
    config.compute_type = preset.compute_type


@dataclasses.dataclass(frozen=True)
class PresetAvailability:
    available: bool
    reason: str  # vacio si `available`; explica por que no si no lo esta


def preset_availability(key: str, cuda_device_count: int) -> PresetAvailability:
    """Si el preset `key` se puede usar ya mismo, dado que el equipo ve `cuda_device_count` GPUs CUDA.

    Funcion pura: recibe el numero de GPUs ya detectado en vez de preguntarle al
    hardware, para poder testear la politica sin GPU. El dato real lo da
    `detect_cuda_device_count()`. Un preset que no depende de GPU esta siempre
    disponible: hoy solo Extra la requiere.
    """
    preset = QUALITY_PRESETS[key]
    if not preset.requires_cuda:
        return PresetAvailability(True, "")
    if cuda_device_count > 0:
        return PresetAvailability(True, "")
    return PresetAvailability(
        False,
        "Requiere una GPU NVIDIA con CUDA; no se detecto ninguna en este equipo.",
    )


def detect_cuda_device_count() -> int:
    """Cuantas GPUs CUDA ve `ctranslate2` ahora mismo; 0 si no hay o algo falla.

    No hace falta `torch` para esto (ctranslate2.get_cuda_device_count basta). Se trata
    cualquier fallo -- biblioteca ausente, driver roto, lo que sea -- como "no hay GPU"
    en lugar de dejar que rompa la interfaz: es una consulta informativa, nunca debe
    tirar el dialogo de Opciones.
    """
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 0


CPU_FALLBACK_PRESET = "alta"  # el mejor preset que corre en CPU; su modelo suele estar ya en caché


def resolve_runtime(config: AppConfig, cuda_device_count: int) -> Tuple[str, str, str, int, str]:
    """Parámetros efectivos del modelo según el hardware: (modelo, dispositivo, compute_type, haz, aviso).

    Si la configuración pide GPU y no hay ninguna, cae al preset de CPU **entero**, modelo
    incluido, y no solo al dispositivo. Mantener `large-v3` en CPU sería peor que no tener
    preset: la librería descargaría varios GB y lo ejecutaría a un tercio del tiempo real.
    El aviso queda vacío cuando no hace falta caer.
    """
    if config.device != "cuda" or cuda_device_count > 0:
        return config.model, config.device, config.compute_type, config.beam_size, ""
    cpu = QUALITY_PRESETS[CPU_FALLBACK_PRESET]
    aviso = (
        f"⚠ Este equipo no tiene GPU NVIDIA: en vez de {config.model} se usa el preset "
        f"{cpu.label} ({cpu.model} en CPU). Elige un preset de CPU en Opciones para no ver este aviso."
    )
    return cpu.model, cpu.device, cpu.compute_type, cpu.beam_size, aviso
