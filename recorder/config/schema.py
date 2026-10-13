import dataclasses
import pathlib
from typing import Tuple, Dict, List, Optional, Sequence

from .hardware import VENDOR_NVIDIA, GpuInfo, HardwareProfile, describe_gpu, gb, short_cpu_name


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
    # GPU. "gpu"/"float16" (preset Extra) usa la GPU que haya: CUDA con faster-whisper o,
    # si no, whisper.cpp con Vulkan (AMD). "cuda" y "vulkan" fuerzan uno de los dos. Un
    # config.json viejo no trae estos dos campos y cae en estos valores por defecto, que es
    # el comportamiento de siempre. Ver QUALITY_PRESETS mas abajo, docs/presets-calidad.md
    # y docs/gpu-amd-vulkan.md.
    device: str = "cpu"  # "cpu", "gpu", "cuda" o "vulkan"
    compute_type: str = "int8"  # "int8" en cpu; "float16" en gpu (en vulkan tambien "q8_0", "q5_0")

    # Carpeta de whisper.cpp compilado con Vulkan (bin\whisper-server.exe y models\ggml-*.bin),
    # la que prepara tools/instalar_whispercpp.ps1. Vacia = no hay motor Vulkan.
    whispercpp_dir: str = ""
    # Flash attention en whisper.cpp. Apagada por defecto: en Radeon con Windows hay reportes
    # de repeticiones y cierres del driver con ella. Encenderla solo si la medicion sale limpia.
    # La recomendacion para una GPU dedicada la enciende (medida limpia en una RX 6700 XT).
    whispercpp_flash_attn: bool = False
    # GPU de Vulkan que usa whisper.cpp (`whisper-server -dev N`). -1 = automatico: la dedicada
    # con mas VRAM, nunca una integrada. Un numero >= 0 la fuerza, integrada incluida (entonces
    # el modelo se limita a large-v3-turbo). Ver docs/recomendacion-hardware.md.
    whispercpp_device: int = -1

    # Hilos de CPU que usa CTranslate2 en la inferencia. 0 = valor por defecto de
    # faster-whisper (4 hilos), que se queda corto en una CPU con mas nucleos. El primer
    # arranque pone el recomendado para la CPU (`recommended_cpu_threads`).
    # Como afinarlo midiendo en tu equipo: docs/rendimiento.md.
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
    device: str  # "cpu" o "gpu"
    compute_type: str  # "int8" (cpu) o "float16" (gpu)
    summary: str  # que modelo es y si arriesga retraso en una CPU como la medida

    @property
    def requires_gpu(self) -> bool:
        return self.device != "cpu"


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
        device="gpu",
        compute_type="float16",
        summary=(
            "Modelo large-v3 en GPU (float16): la mejor calidad disponible. Usa una GPU "
            "NVIDIA con CUDA o, si no la hay, una AMD con whisper.cpp y Vulkan "
            "(docs/gpu-amd-vulkan.md). Sin GPU, large-v3 no llega al tiempo real en CPU, "
            "asi que este preset solo tiene sentido en un equipo con GPU."
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


def preset_availability(key: str, cuda_device_count: int, vulkan_ready: bool = False) -> PresetAvailability:
    """Si el preset `key` se puede usar ya mismo en este equipo.

    Funcion pura: recibe lo ya detectado (GPUs CUDA y si whisper.cpp con Vulkan esta
    instalado con el modelo del preset) en vez de preguntarle al hardware, para poder
    testear la politica sin GPU. Los datos reales los dan `detect_cuda_device_count()` y
    `engine.whispercpp.whispercpp_ready()`. Un preset que no depende de GPU esta siempre
    disponible: hoy solo Extra la requiere.
    """
    preset = QUALITY_PRESETS[key]
    if not preset.requires_gpu:
        return PresetAvailability(True, "")
    if cuda_device_count > 0 or vulkan_ready:
        return PresetAvailability(True, "")
    return PresetAvailability(
        False,
        "Requiere una GPU NVIDIA con CUDA, o whisper.cpp con Vulkan instalado para una GPU AMD "
        "(docs/gpu-amd-vulkan.md); no se detecto ninguna de las dos en este equipo.",
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


@dataclasses.dataclass(frozen=True)
class VulkanChoice:
    """Qué GPU de Vulkan usará whisper.cpp, decidido antes de arrancar `whisper-server`."""

    index: int = -1  # valor de `-dev`; -1 = no pasarlo (whisper.cpp toma su dispositivo 0)
    name: str = ""
    integrated: bool = False
    usable: bool = True
    reason: str = ""  # por qué no se puede usar; vacío si `usable`


# Modelos que en una GPU integrada no se piden nunca: large-v3-turbo como mucho.
INTEGRATED_MAX_MODEL = "large-v3-turbo"


def choose_vulkan_device(requested: int, devices: Sequence[GpuInfo]) -> VulkanChoice:
    """La GPU para whisper.cpp: la pedida (`whispercpp_device` >= 0) o, en automático, la
    dedicada con más VRAM. Función pura sobre la lista de ggml-vulkan (`vulkan_index`).

    En automático **nunca** se elige una integrada: su "VRAM" es RAM del sistema, con el mismo
    ancho de banda que ya usa la CPU, y comparte con la CPU (y con Teams) el presupuesto de
    potencia. Si es lo único que hay, no es utilizable sin pedirla a mano. Sin lista (Vulkan no
    se pudo consultar) no se pasa `-dev`; lo que eligió whisper.cpp se comprueba después en su
    registro (`engine.whispercpp.parse_vulkan_log`).
    """
    if requested >= 0:
        dev = next((d for d in devices if d.vulkan_index == requested), None)
        if dev is None and devices:
            nombres = ", ".join(f"{d.vulkan_index} = {d.name}" for d in devices)
            return VulkanChoice(requested, usable=False, reason=(
                f"whispercpp_device = {requested}, pero Vulkan solo lista: {nombres}."
            ))
        return VulkanChoice(requested, dev.name if dev else "", bool(dev and dev.integrated))
    if not devices:
        return VulkanChoice()
    dedicadas = [d for d in devices if not d.integrated]
    if not dedicadas:
        nombres = ", ".join(d.name for d in devices)
        return VulkanChoice(-1, nombres, True, usable=False, reason=(
            f"Vulkan solo ve una GPU integrada ({nombres}): comparte la memoria y la potencia con "
            f"la CPU y Recorder no la usa sin pedírsela. Para probarla tras medir, elige su número "
            f"en ⚙ Opciones (whispercpp_device)."
        ))
    best = max(dedicadas, key=lambda d: (d.vram_mb, -d.vulkan_index))
    return VulkanChoice(best.vulkan_index, best.name, False)


def vulkan_model_for(model: str, choice: Optional[VulkanChoice]) -> str:
    """En una GPU integrada, nunca large-v3: como mucho large-v3-turbo."""
    if choice is not None and choice.integrated and model_cost(model) > model_cost(INTEGRATED_MAX_MODEL):
        return INTEGRATED_MAX_MODEL
    return model


def resolve_runtime(
    config: AppConfig,
    cuda_device_count: int,
    vulkan_ready: bool = False,
    vulkan: Optional[VulkanChoice] = None,
) -> Tuple[str, str, str, int, str]:
    """Parámetros efectivos del modelo según el hardware: (modelo, dispositivo, compute_type, haz, aviso).

    El dispositivo devuelto es siempre concreto: "cpu" o "cuda" (faster-whisper) o "vulkan"
    (whisper.cpp). "gpu" prefiere CUDA y después Vulkan; "cuda" y "vulkan" solo aceptan el
    suyo. Si la GPU pedida no está, cae al preset de CPU **entero**, modelo incluido, y no
    solo al dispositivo. Mantener `large-v3` en CPU sería peor que no tener preset: la
    librería descargaría varios GB y lo ejecutaría a un tercio del tiempo real. El aviso
    queda vacío cuando no hace falta caer.

    `vulkan` es la GPU elegida con `choose_vulkan_device` (None = no se sabe): si no es
    utilizable (solo hay una integrada y nadie la pidió) Vulkan cuenta como ausente, y si es
    integrada el modelo se limita a large-v3-turbo.
    """
    vulkan_ok = vulkan_ready and (vulkan is None or vulkan.usable)
    device = config.device
    if device == "gpu":
        device = "cuda" if cuda_device_count > 0 else "vulkan" if vulkan_ok else ""
    elif device == "cuda" and cuda_device_count <= 0:
        device = ""
    elif device == "vulkan" and not vulkan_ok:
        device = ""
    if device:
        model = vulkan_model_for(config.model, vulkan) if device == "vulkan" else config.model
        aviso = ""
        if model != config.model:
            aviso = f"⚠ La GPU elegida ({vulkan.name}) es integrada: se usa {model} en vez de {config.model}."
        return model, device, config.compute_type, config.beam_size, aviso
    cpu = QUALITY_PRESETS[CPU_FALLBACK_PRESET]
    if vulkan_ready and vulkan is not None and not vulkan.usable and config.device in ("gpu", "vulkan"):
        return cpu.model, cpu.device, cpu.compute_type, cpu.beam_size, (
            f"⚠ {vulkan.reason} En vez de {config.model} se usa el preset {cpu.label} ({cpu.model} en CPU)."
        )
    falta = {
        "cuda": "GPU NVIDIA",
        "vulkan": "whisper.cpp con Vulkan instalado",
    }.get(config.device, "GPU utilizable (ni NVIDIA ni whisper.cpp con Vulkan)")
    aviso = (
        f"⚠ Este equipo no tiene {falta}: en vez de {config.model} se usa el preset "
        f"{cpu.label} ({cpu.model} en CPU). Elige un preset de CPU en Opciones para no ver este aviso."
    )
    return cpu.model, cpu.device, cpu.compute_type, cpu.beam_size, aviso


# ---------------------------------------------------------------------------------
# Recomendacion segun el hardware detectado (config/hardware.py).
#
# `recommend_config` es pura: recibe el perfil ya detectado y si whisper.cpp esta listo, y
# decide una gama. Los umbrales son [estimado] salvo donde se dice; las cifras de velocidad
# que se citan en los motivos son las de docs/rendimiento.md y docs/gpu-amd-vulkan.md.
# Detalle y justificacion: docs/recomendacion-hardware.md.
# ---------------------------------------------------------------------------------

EXTRA_MIN_VRAM_MB = 5632  # "6 GB" con margen: large-v3 float16 con haz 5 ocupo 4,5 GB [terceros]
CPU_ALTA_MIN_PHYSICAL = 8  # CPU no hibrida
CPU_ALTA_MIN_P = 6  # CPU hibrida: cuentan los nucleos P; los E rinden ~35-45 % de un P en AVX2
CPU_MEDIA_MIN_PHYSICAL = 4
MIN_RAM_MB = 7680  # un equipo "de 8 GB" reporta algo menos (memoria reservada por el firmware/iGPU)

# Modelos medidos en este proyecto: su gama dice "medida" en vez de "estimada".
MEASURED_CPUS = ("i7-1255U",)  # docs/rendimiento.md
MEASURED_VULKAN_GPUS = ("RX 6700 XT",)  # docs/gpu-amd-vulkan.md
CPU_TIERS: List[str] = ["baja", "media", "alta"]

# Coste relativo de cada modelo en CPU (orden medido: medium 1,2x es mas rapido que turbo 1,0x).
_MODEL_COST = {
    "tiny": 0, "base": 1, "small": 2, "medium": 3, "distil-large-v3": 4,
    "large-v3-turbo": 4, "turbo": 4, "large-v1": 5, "large-v2": 5, "large-v3": 5, "large": 5,
}


def model_cost(model: str) -> int:
    """Rango de coste de un modelo (los ".en" cuestan lo mismo); desconocido = como medium."""
    return _MODEL_COST.get(model.removesuffix(".en"), 3)


@dataclasses.dataclass(frozen=True)
class Recommendation:
    """La configuracion que conviene a este equipo y por que."""

    preset: Optional[str]  # clave de QUALITY_PRESETS, o None si es una combinacion propia
    model: str
    beam_size: int
    device: str  # como AppConfig.device: "cpu", "gpu", "cuda" o "vulkan"
    compute_type: str
    cpu_threads: int
    engine: str  # "faster-whisper" o "whisper.cpp"
    tier: str  # "gpu-nvidia", "gpu-vulkan", "cpu-alta", "cpu-media" o "cpu-baja"
    reason: str  # legible, para la interfaz
    confidence: str  # "medida" (hay medicion en este modelo de CPU/GPU) o "estimada"
    flash_attn: bool = False  # whispercpp_flash_attn; solo cuenta con el motor whisper.cpp

    @property
    def label(self) -> str:
        return QUALITY_PRESETS[self.preset].label if self.preset else "Personalizado"


def _measured(name: str, models: Sequence[str]) -> bool:
    return any(m.lower() in name.lower() for m in models)


def recommended_cpu_threads(profile: HardwareProfile) -> int:
    """Hilos para CTranslate2 (y whisper.cpp). 0 si no se sabe cuantos nucleos hay.

    No hibrida: max(4, fisicos - 1), dejando un nucleo a la videollamada. Hibrida con 4 o mas
    nucleos P: los P (en un bucle OpenMP el hilo mas lento marca el paso, y un E rinde menos de
    la mitad). Hibrida con menos de 4 P: fisicos - 1, porque solo con los P se quedaria por
    debajo de los 4 de la biblioteca. Nunca mas que nucleos fisicos. [estimado; afinar con
    tools/medir_rendimiento.py]
    """
    fisicos = profile.physical_cores
    if fisicos <= 0:
        return 0
    if profile.hybrid:
        hilos = profile.p_cores if profile.p_cores >= 4 else fisicos - 1
    else:
        hilos = max(4, fisicos - 1)
    return max(1, min(hilos, fisicos))


def _cpu_description(p: HardwareProfile) -> str:
    nucleos = f"{p.physical_cores} núcleos" if p.physical_cores else "núcleos desconocidos"
    if p.hybrid:
        nucleos += f", {p.p_cores}P+{p.e_cores}E"
    isa = "AVX-512" if p.avx512 else "AVX2" if p.avx2 else "sin AVX2"
    ram = f", {p.ram_total_mb / 1024:.0f} GB" if p.ram_total_mb else ""
    return f"{short_cpu_name(p.cpu_name)} ({nucleos}, {isa}{ram})"


def cpu_tier(p: HardwareProfile) -> Tuple[str, str]:
    """Gama de la CPU ("baja", "media" o "alta") sin contar la bateria, y el motivo si no es obvio."""
    fisicos = p.physical_cores or p.logical_cores // 2
    if not p.avx2:
        return "baja", "sin AVX2, CTranslate2 pierde su camino rápido en int8"
    if p.ram_total_mb and p.ram_total_mb < MIN_RAM_MB:
        return "baja", "menos de 8 GB de RAM"
    if fisicos and fisicos < CPU_MEDIA_MIN_PHYSICAL:
        return "baja", f"solo {fisicos} núcleos"
    if p.hybrid:
        if p.p_cores >= CPU_ALTA_MIN_P:
            return "alta", ""
        return "media", f"solo {p.p_cores} núcleos de rendimiento (los E rinden menos de la mitad)"
    if fisicos >= CPU_ALTA_MIN_PHYSICAL:
        return "alta", ""
    return "media", "" if fisicos else "núcleos desconocidos"


_CPU_TIER_TEXT = {
    "alta": (
        "Alta (large-v3-turbo) da la mejor calidad sin GPU: un i7-1255U (2P+8E) iba a ~1,0x con 4 "
        "hilos [medido] y esta CPU tiene más margen [estimado]. Si la cola de pendientes crece en las "
        "reuniones, baja a Media."
    ),
    "media": (
        "Media (small, haz 5) va a ~3,0x el tiempo real medido en un i7-1255U, holgada aun con la "
        "videollamada abierta; Alta iría al límite."
    ),
    "baja": "Baja (small, haz 1) va a ~5,4x medido: la única que no acumula retraso en un equipo así.",
}


def _from_preset(key: str, hilos: int, **kw) -> Recommendation:
    p = QUALITY_PRESETS[key]
    return Recommendation(key, p.model, p.beam_size, p.device, p.compute_type, hilos, **kw)


def _vulkan_candidate(p: HardwareProfile) -> Optional[GpuInfo]:
    """La GPU dedicada que usaria whisper.cpp; si Vulkan no respondio, la dedicada de DXGI."""
    if p.vulkan_devices:
        return p.best_vulkan_discrete
    return max(p.discrete_gpus, key=lambda g: g.vram_mb, default=None)


def recommend_config(
    profile: HardwareProfile, vulkan_turbo_ready: bool = False, vulkan_large_ready: bool = False
) -> Recommendation:
    """Configuracion recomendada para `profile`. Funcion pura (no toca hardware ni disco).

    En orden: NVIDIA con CUDA (6 GB o mas: Extra; menos: large-v3-turbo en CUDA); GPU dedicada
    con whisper.cpp listo (large-v3-turbo en Vulkan con flash attention); y si no, la gama de
    la CPU (Alta, Media o Baja), una gama menos con bateria. Una NVIDIA sin CUDA, una GPU
    dedicada sin whisper.cpp o una iGPU sola caen a CPU explicando por que y que hacer.
    `vulkan_*_ready` son `engine.whispercpp.whispercpp_ready` para cada modelo.
    """
    hilos = recommended_cpu_threads(profile)
    nvidias = [g for g in profile.gpus if g.vendor_id == VENDOR_NVIDIA]

    if profile.cuda_devices > 0:
        gpu = max(nvidias, key=lambda g: g.vram_mb, default=None)
        nombre = describe_gpu(gpu) if gpu else "GPU NVIDIA"
        if gpu and gpu.vram_mb >= EXTRA_MIN_VRAM_MB:
            return _from_preset(
                "extra", hilos, engine="faster-whisper", tier="gpu-nvidia", confidence="estimada",
                reason=(
                    f"{nombre} con CUDA: large-v3 en float16, la mejor calidad. Con 6 GB o más va a "
                    f"8x-15x el tiempo real según terceros y deja la CPU libre para la videollamada."
                ),
            )
        motivo = "VRAM desconocida" if not (gpu and gpu.vram_mb) else f"{gb(gpu.vram_mb)} de VRAM"
        return Recommendation(
            None, "large-v3-turbo", 5, "cuda", "float16", hilos, "faster-whisper", "gpu-nvidia",
            reason=(
                f"{nombre} con CUDA y {motivo}: large-v3-turbo en float16 (~2,5 GB). large-v3 pide "
                f"~4,5 GB y por debajo de 6 GB no deja margen [terceros]."
            ),
            confidence="estimada",
        )

    vk = _vulkan_candidate(profile)
    if vk is not None and (vulkan_turbo_ready or vulkan_large_ready):
        medida = _measured(vk.name, MEASURED_VULKAN_GPUS)
        donde = "en esta GPU" if medida else "en una RX 6700 XT (en esta GPU es una estimación)"
        if vulkan_turbo_ready:
            return Recommendation(
                None, "large-v3-turbo", 5, "vulkan", "float16", hilos, "whisper.cpp", "gpu-vulkan",
                reason=(
                    f"{describe_gpu(vk)} con whisper.cpp y Vulkan: large-v3-turbo en float16 con flash "
                    f"attention, 8,5x el tiempo real y 6,8 % de WER medidos {donde}. large-v3 (Extra) "
                    f"iba a 2,6x con 7,7 %: poco margen sobre el 2x de dos fuentes, y se queda corto si "
                    f"la GPU se comparte (streaming, escritorio remoto). Si ves frases repetidas o "
                    f"cierres del driver, desactiva flash attention."
                ),
                confidence="medida" if medida else "estimada",
                flash_attn=True,
            )
        return _from_preset(
            "extra", hilos, engine="whisper.cpp", tier="gpu-vulkan",
            confidence="medida" if medida else "estimada", flash_attn=True,
            reason=(
                f"{describe_gpu(vk)} con whisper.cpp, pero solo está descargado large-v3: Extra, 2,6x "
                f"medido {donde}. large-v3-turbo iría 3,3x más rápido con el mismo WER: descárgalo "
                f"con tools\\instalar_whispercpp.ps1 -Modelos large-v3-turbo."
            ),
        )

    tier, motivo = cpu_tier(profile)
    enchufado = tier
    if profile.on_battery and tier != "baja":
        tier = CPU_TIERS[CPU_TIERS.index(tier) - 1]
    reason = f"{_cpu_description(profile)}: {motivo + ', ' if motivo else ''}gama {enchufado}. {_CPU_TIER_TEXT[tier]}"
    if tier != enchufado:
        reason += (
            f" Con batería se baja una gama (la CPU limita su potencia); enchufado se recomendaría "
            f"{QUALITY_PRESETS[enchufado].label}."
        )
    notas = []
    nvidia_sin_cuda = [g for g in nvidias if not g.integrated]
    if nvidia_sin_cuda:
        notas.append(
            f"Hay una {describe_gpu(nvidia_sin_cuda[0])} pero CUDA no responde (driver, o faltan las "
            f"bibliotecas de CUDA 12 y cuDNN 9 que usa faster-whisper): hasta resolverlo, CPU. También "
            f"puede usarse con whisper.cpp y Vulkan (tools\\instalar_whispercpp.ps1)."
        )
    if vk is not None and vk.vendor_id != VENDOR_NVIDIA:
        notas.append(
            f"La GPU {describe_gpu(vk)} solo se aprovecha con whisper.cpp y Vulkan: ejecuta "
            f"tools\\instalar_whispercpp.ps1 (docs/gpu-amd-vulkan.md) y vuelve a pulsar «Usar recomendado»."
        )
    elif vk is None and profile.has_igpu:
        notas.append(
            "La GPU integrada no se usa por defecto: su memoria es la RAM del sistema (el mismo ancho "
            "de banda que ya usa la CPU) y comparte con la CPU, y con Teams, la potencia. Se puede "
            "probar a mano (whispercpp_device) tras medirla."
        )
    if notas:
        reason += " " + " ".join(notas)
    return _from_preset(
        tier, hilos, engine="faster-whisper", tier=f"cpu-{tier}", reason=reason,
        confidence="medida" if _measured(profile.cpu_name, MEASURED_CPUS) else "estimada",
    )


def apply_recommendation(config: AppConfig, rec: Recommendation) -> None:
    """Aplica `rec` sobre `config`, en el sitio. No toca rutas, vocabulario ni filtros."""
    config.model = rec.model
    config.beam_size = rec.beam_size
    config.device = rec.device
    config.compute_type = rec.compute_type
    config.cpu_threads = rec.cpu_threads
    if rec.engine == "whisper.cpp":
        config.whispercpp_flash_attn = rec.flash_attn


def recommendation_matches(config: AppConfig, rec: Recommendation) -> bool:
    """Si `config` ya es la recomendacion (modelo, haz, dispositivo, precision e hilos)."""
    return (config.model, config.beam_size, config.device, config.compute_type, config.cpu_threads) == (
        rec.model, rec.beam_size, rec.device, rec.compute_type, rec.cpu_threads
    )


_DEVICE_TEXT = {
    "cpu": "CPU",
    "cuda": "GPU NVIDIA con CUDA",
    "vulkan": "GPU con whisper.cpp y Vulkan",
    "gpu": "GPU (CUDA o Vulkan)",
}


def describe_runtime(model: str, beam_size: int, device: str, compute_type: str) -> str:
    """"large-v3-turbo, haz 5, GPU con whisper.cpp y Vulkan, float16"."""
    return f"{model}, haz {beam_size}, {_DEVICE_TEXT.get(device, device)}, {compute_type}"


def describe_recommendation(rec: Recommendation) -> str:
    """"Media (small, haz 5, CPU int8, 5 hilos)"."""
    partes = describe_runtime(rec.model, rec.beam_size, rec.device, rec.compute_type)
    if rec.engine == "whisper.cpp" and rec.flash_attn:
        partes += " + flash attention"
    hilos = f"{rec.cpu_threads} hilos" if rec.cpu_threads else "hilos de la biblioteca"
    return f"{rec.label} ({partes}, {hilos})"


def config_heavier_than(config: AppConfig, rec: Recommendation) -> bool:
    """Si `config` pide mas trabajo del que este equipo aguanta segun `rec`.

    En el mismo tipo de dispositivo compara el modelo y despues el haz. Una configuracion de GPU
    frente a una recomendacion de CPU no cuenta: si la GPU no esta, `resolve_runtime` ya cae a
    CPU y avisa. Una de CPU frente a una de GPU solo es mas pesada si es un large-v3, que en
    ninguna CPU llega al tiempo real (0,3x-0,4x [terceros]).
    """
    cfg_gpu, rec_gpu = config.device != "cpu", rec.device != "cpu"
    if cfg_gpu and not rec_gpu:
        return False
    if not cfg_gpu and rec_gpu:
        return model_cost(config.model) > model_cost("large-v3-turbo")
    cfg, ref = model_cost(config.model), model_cost(rec.model)
    return cfg > ref or (cfg == ref and config.beam_size > rec.beam_size)


def startup_notices(config: AppConfig, profile: HardwareProfile, rec: Recommendation) -> List[str]:
    """Avisos para el visor al arrancar, contrastando la configuracion con el equipo.

    * Una GPU dedicada que solo se aprovecha con whisper.cpp (AMD, Intel, NVIDIA sin CUDA) y
      `whispercpp_dir` vacio: es como un usuario perdio la GPU sin enterarse.
    * Una configuracion mas pesada que la recomendada (`config_heavier_than`).
    * Una recomendacion de GPU con la configuracion en CPU: informativo.
    """
    avisos = []
    vk = _vulkan_candidate(profile)
    if vk is not None and profile.cuda_devices <= 0 and not config.whispercpp_dir.strip():
        avisos.append(
            f"⚠ Hay una GPU dedicada, {describe_gpu(vk)}, que Recorder solo usa con whisper.cpp y "
            f"Vulkan, pero «whispercpp_dir» está vacío: ejecuta tools\\instalar_whispercpp.ps1 o "
            f"indica la carpeta en ⚙ Opciones."
        )
    actual = describe_runtime(config.model, config.beam_size, config.device, config.compute_type)
    if config_heavier_than(config, rec):
        avisos.append(
            f"⚠ La configuración actual ({actual}) es más pesada que la recomendada para este equipo, "
            f"{describe_recommendation(rec)}: la cola de pendientes puede crecer. ⚙ Opciones → «Usar recomendado»."
        )
    elif rec.device != "cpu" and config.device == "cpu" and not avisos:
        avisos.append(
            f"💡 Este equipo puede transcribir en la GPU: {describe_recommendation(rec)}. "
            f"⚙ Opciones → «Usar recomendado»."
        )
    return avisos
