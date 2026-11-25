"""«Medir mi equipo»: una prueba corta de qué configuración de transcripción aguanta este equipo.

Sin interfaz (ni tkinter ni rich): la ventana (`ui/dialogs/medir_dialog.py`), la terminal
(`cli/pantallas/medir.py`) y `tools/medir_rendimiento.py` comparten esta lógica. Tiene tres partes:

- **La muestra y la medida**: una daily ficticia con la voz de Windows, partida como `capture.py`
  (`generar_muestra`, `trocear`), y la transcripción con el mismo vocabulario y filtros que la grabación;
  velocidad en múltiplos del tiempo real y WER frente al guion (`wer`, `CargaAjena`).
- **Qué probar** (`candidatos`): solo lo que tiene sentido en este equipo: el procesador con varios hilos,
  la tarjeta gráfica dedicada si hay motor para ella y la integrada únicamente si el usuario la permite
  (`allow_igpu`). Nunca descarga un modelo ni instala nada.
- **La prueba** (`Prueba`, `Medidor`): corre en su hilo, con tope de tiempo (`PRESUPUESTO_S`), cancelable, y
  deja un `Informe` que se guarda junto al config.json (`medicion.json`): la recomendación del equipo lo
  tiene en cuenta (`recomendar`). Aplicar el mejor sobre la configuración (`aplicar_candidato`) escribe solo
  las claves de esa prueba y siempre tras la confirmación de quien lo pide: aquí no se guarda nada solo.

«La mejor» es la de más calidad entre las que aguantan dos fuentes a la vez (>= `VELOCIDAD_DOS_FUENTES`) y,
a igual calidad, la más rápida (`elegir_mejor`); si ninguna las aguanta, la más rápida.
"""
import dataclasses
import datetime
import html
import json
import pathlib
import subprocess
import tempfile
import threading
import time
import unicodedata
import wave
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

from . import ayuda
from .config.hardware import GpuInfo, HardwareProfile
from .config.schema import (
    EXTRA_MIN_VRAM_MB,
    INTEGRATED_MAX_MODEL,
    QUALITY_PRESETS,
    AppConfig,
    Recommendation,
    cpu_tier,
    model_cost,
    recommend_config,
    recommended_cpu_threads,
)
from .engine.whispercpp import vulkan_readiness, whispercpp_ready
from .metricas import hilos_efectivos, tiempos_sistema
from .rutas import ruta_config

RATE = 16000
CARPETA_MUESTRA = pathlib.Path(tempfile.gettempdir()) / "recorder-rendimiento"
NOMBRE_INFORME = "medicion.json"
VERSION_INFORME = 1

# Qué cuenta como «aguanta» y cuánto dura la prueba
VELOCIDAD_DOS_FUENTES = 2.0  # veces el tiempo real para transcribir dos fuentes a la vez (docs/rendimiento.md)
VELOCIDAD_AL_RITMO = 1.0  # por debajo, la cola crece aunque haya una sola fuente
WER_MAXIMO = 35.0  # % de palabras erradas en la muestra a partir del cual una prueba «transcribe mal»
PRESUPUESTO_S = 150.0  # lo que dura la prueba entera, como mucho (2 o 3 minutos)
MARGEN_CANDIDATO_S = 30.0  # no se empieza una prueba si no queda al menos esto del presupuesto
TOPE_CANDIDATO_S = 30.0  # lo que se cronometra de cada prueba, como mucho
REPOSO_S = 2.0  # lo que se mira cuánto procesador gastan los demás antes de empezar
REPOSO_MAXIMO_PCT = 15  # por encima, el equipo no está en reposo y lo medido saldría peor de lo real
TURNOS_PRUEBA = 3  # turnos del guion que forman la muestra corta de la app (~30 s de voz)

# Estados de una prueba (fila de la tabla)
EN_ESPERA, MIDIENDO, LISTA, OMITIDA, FALLO = "en_espera", "midiendo", "lista", "omitida", "fallo"
# Por qué se omite una prueba: la clave de ayuda es «medir_omitida_» + el motivo
MOTIVO_MODELO, MOTIVO_TIEMPO, MOTIVO_PODA, MOTIVO_CANCELADA = "modelo", "tiempo", "poda", "cancelada"
# Fases del flujo entero
PREPARANDO, OCUPADO, EN_CURSO, TERMINADA, CANCELADA, ERROR = (
    "preparando", "ocupado", "en_curso", "terminada", "cancelada", "error"
)

# Daily ficticia con vocabulario técnico genérico. Entre turnos hay 0,8 s de silencio para que
# el segmentador tenga dónde cortar, como en una reunión de verdad.
GUION = [
    "Buenos días a todos, empezamos la daily de desarrollo. Hoy revisamos el despliegue del API Gateway y las incidencias del entorno de staging.",
    "Ayer terminé la migración del esquema en PostgreSQL. La réplica de lectura ya sincroniza bien y la latencia del endpoint de pedidos bajó a doscientos milisegundos.",
    "Perfecto. Ana, ¿qué pasó con el pipeline de integración continua? Anoche vi dos ejecuciones fallidas en Jenkins.",
    "Fue un problema del certificado TLS del registro de contenedores. Ya lo renové y el pipeline vuelve a publicar las imágenes en Kubernetes sin errores.",
    "Tengo un bloqueo con el microservicio de facturación. El webhook de pagos devuelve un token JWT caducado y el balanceador reintenta la petición tres veces.",
    "Eso lo vemos después de la daily. Mientras tanto, Luis, revisa la configuración de Redis en el servidor doce, puerto seis mil trescientos setenta y nueve.",
    "Sobre el frontend, la PWA ya funciona sin conexión. Guardamos las peticiones en IndexedDB y las reenviamos cuando vuelve la red.",
    "Marta, ¿cómo va la parte de observabilidad? Necesitamos los paneles de Grafana antes del despliegue canario del viernes.",
    "Ya están los dashboards de Prometheus con la latencia p noventa y cinco y la tasa de errores por endpoint. Falta la alerta de consumo de memoria en los pods.",
    "Pendiente: documentar el rollback del despliegue canario y actualizar el manifiesto de Helm con los nuevos límites de CPU.",
    "Otra cosa. El SDK de OAuth que usamos en el backend tiene una vulnerabilidad publicada. Hay que subir a la versión cuatro punto dos esta semana.",
    "De acuerdo, lo meto en el sprint. También hay que revisar la caché del catálogo, porque el TTL de cinco minutos está generando datos inconsistentes en el carrito.",
    "El equipo de QA reportó una incidencia en el formulario de recolección. Cuando el transportista escanea un código de barras duplicado, la aplicación se queda en blanco.",
    "Lo reproduje en el entorno de pruebas. Es una excepción no controlada en el servicio de embarques; el log muestra un error de clave duplicada en la tabla de bultos.",
    "Vale, asigno la corrección a Ana. Y Luis, prepara el script de SQL Server para limpiar los registros huérfanos antes de la migración a la nube.",
    "Una pregunta rápida: ¿el balanceador de carga sigue en modo round robin o ya activamos las sesiones persistentes para el portal de clientes?",
    "Sigue en round robin. Para activar la afinidad de sesión necesitamos que el token de sesión viva en Redis y no en memoria del proceso de IIS.",
    "Recordatorio: el viernes hay ventana de mantenimiento en el clúster de producción de las diez a las once de la noche. Avisen a soporte con anticipación.",
    "Por último, la retrospectiva del sprint queda para el jueves a las cuatro. Traigan métricas de tiempo de ciclo y de despliegues fallidos del mes.",
    "Ah, se me olvidaba: la integración con el servicio de mensajería por AMQP está lista. La cola de eventos ya procesa los pedidos en orden y con reintentos exponenciales.",
    "Y el contenedor de la API en el servidor veinte, puerto ocho mil ochenta, ya escala automáticamente hasta seis réplicas cuando la cola supera los mil mensajes.",
    "Genial. Entonces resumo: certificado renovado, migración terminada, bloqueo con el webhook de pagos y la alerta de memoria pendiente. Nos vemos mañana.",
]


class SinVoz(RuntimeError):
    """Windows no tiene ninguna voz en español con la que crear la muestra."""


class ModeloNoDisponible(RuntimeError):
    """El modelo de una prueba no está en el equipo: no se descarga nada sin avisar."""


# ------------------------------------------------------------------ muestra de audio
def generar_muestra(turnos: Optional[int] = None, carpeta: pathlib.Path = CARPETA_MUESTRA) -> pathlib.Path:
    """Sintetiza el guion (o sus primeros `turnos`) con la voz de Windows en español a 16 kHz mono.

    Se escribe a un archivo: no suena por los altavoces. Solo se crea la primera vez; después se reutiliza.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    nombre = "muestra" if turnos is None else f"muestra-{turnos}"
    wav, ssml = carpeta / f"{nombre}.wav", carpeta / f"{nombre}.ssml"
    if wav.exists():
        return wav
    cuerpo = "".join(f"<s>{html.escape(t)}</s><break time=\"800ms\"/>" for t in GUION[:turnos])
    ssml.write_text(
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-MX">' + cuerpo + "</speak>",
        encoding="utf-8",
    )
    entre_comillas = lambda ruta: "'" + str(ruta).replace("'", "''") + "'"  # noqa: E731  (PowerShell: '' dentro de '…')
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1; "
        "if (-not $v) { Write-Error 'SIN_VOZ'; exit 3 }; "
        "$s.SelectVoice($v.VoiceInfo.Name); "
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); "
        f"$s.SetOutputToWaveFile({entre_comillas(wav)}, $fmt); "
        f"$s.SpeakSsml((Get-Content -LiteralPath {entre_comillas(ssml)} -Raw -Encoding UTF8)); $s.Dispose()"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True, text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if r.returncode != 0 or not wav.exists():
        wav.unlink(missing_ok=True)  # un archivo a medias no debe quedar como si fuera la muestra
        if "SIN_VOZ" in r.stderr:
            raise SinVoz()
        raise RuntimeError((r.stderr or r.stdout).strip().splitlines()[0] if (r.stderr or r.stdout).strip() else "PowerShell falló")
    return wav


def cargar_wav(path: pathlib.Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        if w.getframerate() != RATE or w.getnchannels() != 1:
            raise ValueError("la muestra debe ser mono a 16 kHz")
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


def trocear(pcm: np.ndarray, min_sec: Optional[float] = None, max_sec: Optional[float] = None) -> List[np.ndarray]:
    """Misma política que `_read_loop` en capture.py: corta en pausa tras `min_sec` o forzado a `max_sec`."""
    from .audio.capture import (
        DEFAULT_MAX_SEC, DEFAULT_MIN_SEC, DEFAULT_PAUSE_SEC, DEFAULT_SILENCE_RMS, FRAMES_PER_BUFFER,
    )

    min_sec = DEFAULT_MIN_SEC if min_sec is None else min_sec
    max_sec = DEFAULT_MAX_SEC if max_sec is None else max_sec
    cola = max(1, int(DEFAULT_PAUSE_SEC * RATE / FRAMES_PER_BUFFER))
    trozos, buf, hablando = [], [], False
    for i in range(0, len(pcm) - FRAMES_PER_BUFFER + 1, FRAMES_PER_BUFFER):
        raw = pcm[i : i + FRAMES_PER_BUFFER]
        hablando = hablando or rms(raw) > DEFAULT_SILENCE_RMS
        buf.append(raw)
        secs = len(buf) * FRAMES_PER_BUFFER / RATE
        if (secs >= min_sec and rms(np.concatenate(buf[-cola:])) < DEFAULT_SILENCE_RMS) or secs >= max_sec:
            if hablando:
                trozos.append(np.concatenate(buf))
            buf, hablando = [], False
    if buf and hablando and len(buf) * FRAMES_PER_BUFFER / RATE >= 1.0:
        trozos.append(np.concatenate(buf))
    return [t / 32768.0 for t in trozos]  # float32 en [-1, 1], como to_16k()


def fusionar(trozos: Sequence[np.ndarray], tope_sec: float) -> List[np.ndarray]:
    """Une fragmentos consecutivos mientras no pasen de tope_sec (lo que haría un worker con cola pendiente)."""
    out, actual = [], []
    for t in trozos:
        if actual and (sum(len(a) for a in actual) + len(t)) / RATE > tope_sec:
            out.append(np.concatenate(actual))
            actual = []
        actual.append(t)
    if actual:
        out.append(np.concatenate(actual))
    return out


# ------------------------------------------------------------------ calidad
def palabras(texto: str) -> List[str]:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return "".join(c if c.isalnum() or c.isspace() else " " for c in t).split()


def wer(referencia: str, hipotesis: str) -> float:
    """Word Error Rate clásico (Levenshtein sobre palabras normalizadas), en %."""
    r, h = palabras(referencia), palabras(hipotesis)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        previo, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            actual = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, previo + (r[i - 1] != h[j - 1]))
            previo = actual
    return 100.0 * d[len(h)] / max(1, len(r))


# ------------------------------------------------------------------ carga del sistema
def _ocupado(antes: Optional[Tuple[int, int]], despues: Optional[Tuple[int, int]]) -> Optional[float]:
    """% de procesador ocupado entre dos lecturas de `tiempos_sistema`; None si falta alguna."""
    if antes is None or despues is None:
        return None
    return 100.0 * (1.0 - (despues[0] - antes[0]) / max(1, despues[1] - antes[1]))


class CargaAjena:
    """% de CPU del sistema que consumen OTROS procesos durante un tramo (para saber si la medida es limpia).

    Resta el tiempo de procesador del propio Python: un whisper-server aparte cuenta como ajeno, así que
    con whisper.cpp la cifra es un tope, no una medida exacta."""

    def __enter__(self):
        self.antes = tiempos_sistema()
        self.p0, self.w0 = time.process_time(), time.perf_counter()
        return self

    def __exit__(self, *_):
        import os

        ocupado = _ocupado(self.antes, tiempos_sistema())
        nuestro = (time.process_time() - self.p0) / max(1e-9, (time.perf_counter() - self.w0) * (os.cpu_count() or 1))
        self.otros_pct = round(max(0.0, (ocupado or 0.0) / 100.0 - nuestro) * 100)


def cpu_ocupada_pct(segundos: float = REPOSO_S, dormir: Callable[[float], None] = time.sleep) -> int:
    """% de procesador del equipo entero durante `segundos` (antes de medir: si no es bajo, no hay reposo)."""
    antes = tiempos_sistema()
    dormir(segundos)
    ocupado = _ocupado(antes, tiempos_sistema())
    return 0 if ocupado is None else round(ocupado)


# ------------------------------------------------------------------ qué probar
@dataclasses.dataclass(frozen=True)
class Candidato:
    """Una configuración que se puede medir: qué modelo, con qué motor y dónde."""

    modelo: str
    haz: int
    motor: str  # "faster-whisper" o "whisper.cpp"
    dispositivo: str  # "cpu", "cuda" o "vulkan"
    precision: str  # compute_type: "int8" en CPU, "float16" en GPU
    hilos: int = 0  # cpu_threads; en GPU, los de CPU que acompañan (no se guardan al aplicar)
    gpu_index: int = -1  # -dev de whisper.cpp
    gpu_nombre: str = ""
    integrada: bool = False
    flash_attn: bool = False

    @property
    def clave(self) -> str:
        return f"{self.modelo}-{self.haz}-{self.dispositivo}-{self.hilos if self.dispositivo == 'cpu' else 0}-{self.gpu_index}"

    @property
    def rango(self) -> Tuple[int, int]:
        """La calidad como orden: el modelo y, a igual modelo, el haz (base < media < alta < extra)."""
        return model_cost(self.modelo), self.haz

    @property
    def preset(self) -> Optional[str]:
        """La clave de QUALITY_PRESETS con este modelo y haz, o None si es una combinación propia."""
        return next((k for k, p in QUALITY_PRESETS.items() if (p.model, p.beam_size) == (self.modelo, self.haz)), None)

    def etiqueta(self, corta: bool = False) -> str:
        """«Media · procesador, 9 hilos» (corta: «Media · CPU, 9 hilos»): calidad y con qué se transcribe."""
        calidad = QUALITY_PRESETS[self.preset].label if self.preset else self.modelo
        sufijo = "_corto" if corta else ""
        if self.dispositivo == "cpu":
            donde = ayuda.entrada("medir_donde_cpu" + sufijo)[0].format(n=self.hilos)
        elif self.integrada:
            donde = ayuda.entrada("medir_donde_igpu" + sufijo)[0]
        else:
            donde = ayuda.entrada("medir_donde_gpu" + sufijo)[0]
        return f"{calidad} · {donde}"


def hilos_a_probar(perfil: HardwareProfile) -> List[int]:
    """Los hilos de CPU con sentido en este equipo: los de la biblioteca (el punto de partida) y los
    recomendados para su procesador (`recommended_cpu_threads`, que en una CPU híbrida deja fuera los
    núcleos lentos). Uno solo si coinciden; nunca más que los hilos del equipo."""
    base = hilos_efectivos(0)
    recomendado = recommended_cpu_threads(perfil) or base
    if perfil.logical_cores:
        base, recomendado = min(base, perfil.logical_cores), min(recomendado, perfil.logical_cores)
    return sorted({base, recomendado})


def _calidades_cpu(perfil: HardwareProfile) -> Tuple[str, ...]:
    """Qué calidades merece la pena probar en el procesador según su gama: no se mide Alta en un equipo de gama baja."""
    return {"baja": ("baja", "media"), "media": ("baja", "media", "alta"), "alta": ("media", "alta")}[cpu_tier(perfil)[0]]


def candidatos(
    perfil: HardwareProfile, config: AppConfig, turbo_listo: bool = False, large_listo: bool = False,
) -> List[Candidato]:
    """Lo que se mide en `perfil`, de menos a más calidad (y de menos a más hilos), sin repetir.

    - Procesador (faster-whisper, int8): las calidades de su gama con los hilos de `hilos_a_probar`; la más
      ligera solo con los recomendados.
    - NVIDIA con CUDA: large-v3-turbo en CUDA, y large-v3 si la tarjeta tiene VRAM de sobra.
    - GPU dedicada de Vulkan con whisper.cpp listo (`turbo_listo`, `large_listo`): large-v3-turbo con flash
      attention, y large-v3 si está descargado.
    - GPU integrada: solo con `config.allow_igpu` y large-v3-turbo (el máximo en una integrada) en whisper.cpp.
    Una GPU que Recorder no puede usar (sin motor, sin permiso) no genera ninguna prueba."""
    hilos = hilos_a_probar(perfil)
    out: List[Candidato] = []
    for clave in _calidades_cpu(perfil):
        p = QUALITY_PRESETS[clave]
        for n in ([hilos[-1]] if clave == "baja" else hilos):
            out.append(Candidato(p.model, p.beam_size, "faster-whisper", "cpu", p.compute_type, n))

    turbo, extra = QUALITY_PRESETS["alta"], QUALITY_PRESETS["extra"]
    acompanan = hilos_efectivos(config.cpu_threads)
    if perfil.cuda_devices > 0:
        nvidia = max((g for g in perfil.gpus if not g.integrated), key=lambda g: g.vram_mb, default=None)
        out.append(Candidato(turbo.model, turbo.beam_size, "faster-whisper", "cuda", extra.compute_type))
        if nvidia is not None and nvidia.vram_mb >= EXTRA_MIN_VRAM_MB:
            out.append(Candidato(extra.model, extra.beam_size, "faster-whisper", "cuda", extra.compute_type))
    else:
        dedicada = perfil.best_vulkan_discrete
        if dedicada is not None:
            if turbo_listo:
                out.append(_en_vulkan(turbo.model, dedicada, acompanan, True))
            if large_listo:
                out.append(_en_vulkan(extra.model, dedicada, acompanan, True))
        integrada = _integrada(perfil)
        if config.allow_igpu and turbo_listo and integrada is not None:
            out.append(_en_vulkan(INTEGRATED_MAX_MODEL, integrada, acompanan, config.whispercpp_flash_attn))
    return sorted(out, key=lambda c: (c.rango, c.dispositivo != "cpu", c.dispositivo, c.hilos))


def _en_vulkan(modelo: str, gpu: GpuInfo, hilos: int, flash: bool) -> Candidato:
    return Candidato(
        modelo, QUALITY_PRESETS["extra"].beam_size, "whisper.cpp", "vulkan", QUALITY_PRESETS["extra"].compute_type, hilos,
        gpu.vulkan_index, gpu.name, gpu.integrated, flash,
    )


def _integrada(perfil: HardwareProfile) -> Optional[GpuInfo]:
    """La GPU integrada que lista Vulkan (la que tendría número de `-dev`), la de más memoria compartida."""
    return max((g for g in perfil.vulkan_devices if g.integrated and g.vulkan_index >= 0), key=lambda g: g.shared_mb, default=None)


def igpu_sin_permiso(perfil: HardwareProfile, config: AppConfig, turbo_listo: bool) -> bool:
    """Si hay una GPU integrada que se podría probar (con whisper.cpp listo) pero `allow_igpu` está apagado:
    para decirlo en los resultados en vez de callarlo."""
    return not config.allow_igpu and turbo_listo and _integrada(perfil) is not None


# ------------------------------------------------------------------ resultados
@dataclasses.dataclass
class Resultado:
    candidato: Candidato
    estado: str = EN_ESPERA
    velocidad: Optional[float] = None  # veces el tiempo real
    cpu_pct: Optional[float] = None  # procesador del equipo entero durante la prueba
    wer: Optional[float] = None  # % frente al guion; None si no se completó la muestra
    motivo: str = ""  # OMITIDA: MOTIVO_*; FALLO: el texto del error
    segundos: float = 0.0  # lo que costó medirla, con la carga del modelo

    @property
    def calidad_ok(self) -> bool:
        return self.wer is None or self.wer <= WER_MAXIMO

    @property
    def dos_fuentes(self) -> bool:
        return self.estado == LISTA and self.calidad_ok and (self.velocidad or 0.0) >= VELOCIDAD_DOS_FUENTES

    @property
    def veredicto(self) -> str:
        """«si», «justo» (sirve con una fuente), «atrasa» o «mal» (rápida pero con demasiados errores)."""
        if not self.calidad_ok:
            return "mal"
        v = self.velocidad or 0.0
        return "si" if v >= VELOCIDAD_DOS_FUENTES else "justo" if v >= VELOCIDAD_AL_RITMO else "atrasa"


def elegir_mejor(resultados: Sequence[Resultado]) -> Tuple[Optional[Resultado], bool]:
    """(la mejor, si aguanta dos fuentes). La de más calidad entre las que aguantan dos fuentes y, a igual
    calidad, la más rápida; si ninguna las aguanta, la más rápida de las medidas bien. (None, False) sin medidas."""
    medidas = [r for r in resultados if r.estado == LISTA and r.calidad_ok and r.velocidad]
    buenas = [r for r in medidas if r.dos_fuentes]
    if buenas:
        return max(buenas, key=lambda r: (r.candidato.rango, r.velocidad)), True
    if medidas:
        return max(medidas, key=lambda r: r.velocidad), False
    return None, False


# ------------------------------------------------------------------ aplicar
def claves_afectadas(c: Candidato) -> List[str]:
    """Las claves de config.json que escribe aplicar `c`: solo las de esa prueba, nada más."""
    claves = ["model", "beam_size", "device", "compute_type"]
    if c.dispositivo == "cpu":
        claves.append("cpu_threads")
    elif c.dispositivo == "vulkan":
        claves += ["whispercpp_flash_attn", "whispercpp_device"]
    return claves


def aplicar_candidato(config: AppConfig, c: Candidato) -> List[str]:
    """Pone en `config`, en el sitio, la configuración de `c` y devuelve las claves que tocó."""
    config.model, config.beam_size, config.device, config.compute_type = c.modelo, c.haz, c.dispositivo, c.precision
    if c.dispositivo == "cpu":
        config.cpu_threads = c.hilos
    elif c.dispositivo == "vulkan":
        config.whispercpp_flash_attn, config.whispercpp_device = c.flash_attn, c.gpu_index
    return claves_afectadas(c)


def candidato_actual(config: AppConfig, c: Candidato) -> bool:
    """Si `config` ya tiene la configuración de `c` (todas sus claves)."""
    copia = dataclasses.replace(config)
    aplicar_candidato(copia, c)
    return all(getattr(copia, k) == getattr(config, k) for k in claves_afectadas(c))


# ------------------------------------------------------------------ la prueba de un candidato y de todos
@dataclasses.dataclass(frozen=True)
class Instantanea:
    """Lo que ven las interfaces de una prueba en curso: una copia, sin candados."""

    fase: str
    resultados: Tuple[Resultado, ...]
    actual: int  # la prueba que se mide ahora; -1 si ninguna
    progreso: float  # 0 a 1
    queda_s: Optional[float]  # lo que falta, aproximado; None hasta que haya con qué calcularlo
    reposo_pct: Optional[int] = None  # el procesador ocupado al empezar (fase OCUPADO)
    error: str = ""


class Medidor:
    """Mide los `candidatos` uno tras otro sobre las mismas muestras.

    `cargar(candidato)` devuelve un modelo con `transcribe(audio, **kw)` (faster-whisper o el adaptador de
    whisper.cpp) y, si lo tiene, `close()`; puede lanzar `ModeloNoDisponible` (la prueba se omite) o
    cualquier otro error (la prueba falla y se sigue). `reloj` y `tiempos` se inyectan en las pruebas.
    Se puede cancelar en cualquier momento (`cancelar`): corta entre fragmentos y deja lo que haya.
    """

    def __init__(
        self, candidatos: Sequence[Candidato], trozos: Sequence[np.ndarray], referencia: str,
        cargar: Callable[[Candidato], object], *, vocab: Optional[str] = None, repetition_penalty: float = 1.1,
        reloj: Callable[[], float] = time.monotonic,
        tiempos: Callable[[], Optional[Tuple[int, int]]] = tiempos_sistema,
        presupuesto_s: float = PRESUPUESTO_S, tope_candidato_s: float = TOPE_CANDIDATO_S,
    ):
        self.resultados = [Resultado(c) for c in candidatos]
        self.trozos, self.referencia, self._cargar = list(trozos), referencia, cargar
        self.vocab, self.repetition_penalty = vocab, repetition_penalty
        self._reloj, self._tiempos = reloj, tiempos
        self.presupuesto_s, self.tope_candidato_s = presupuesto_s, tope_candidato_s
        self._cancelado = threading.Event()
        self._lock = threading.Lock()
        self.actual, self.parte, self.terminado = -1, 0.0, False
        self._inicio: Optional[float] = None
        self._fin: Optional[float] = None

    @property
    def cancelado(self) -> bool:
        return self._cancelado.is_set()

    def cancelar(self) -> None:
        self._cancelado.set()

    def instantanea(self) -> Tuple[Tuple[Resultado, ...], int, float, Optional[float]]:
        """(resultados, la que se mide, progreso de 0 a 1, lo que queda en segundos)."""
        with self._lock:
            n = max(1, len(self.resultados))
            hechas = sum(r.estado in (LISTA, OMITIDA, FALLO) for r in self.resultados)
            progreso = 1.0 if self.terminado else min(1.0, (hechas + (self.parte if self.actual >= 0 else 0.0)) / n)
            queda = None
            if self._inicio is not None and 0.0 < progreso < 1.0:
                fin = self._fin if self._fin is not None else self._reloj()
                transcurrido = fin - self._inicio
                queda = max(0.0, min(transcurrido / progreso - transcurrido, self.presupuesto_s - transcurrido))
            return tuple(dataclasses.replace(r) for r in self.resultados), self.actual, progreso, queda

    # ------------------------------------------------------------ el trabajo
    def ejecutar(self) -> None:
        """Mide todas las pruebas (bloquea; `Prueba` lo corre en su hilo). Nunca lanza: lo que falla queda en su fila."""
        self._inicio = self._reloj()
        try:
            for i, r in enumerate(self.resultados):
                if self.cancelado:
                    break
                self._medir(i, r)
        finally:
            with self._lock:
                self.actual, self.terminado = -1, True
                self._fin = self._reloj()

    def _omitir(self, r: Resultado, motivo: str) -> None:
        with self._lock:
            r.estado, r.motivo = OMITIDA, motivo

    def _innecesaria(self, c: Candidato) -> bool:
        """Una prueba más pesada que otra del mismo tipo de dispositivo que ya iba más lenta que el habla,
        con los mismos hilos o más, iría peor: no se gasta tiempo en ella."""
        return any(
            r.estado == LISTA and r.candidato.dispositivo == c.dispositivo and r.candidato.rango < c.rango
            and (r.velocidad or 0.0) < VELOCIDAD_AL_RITMO and r.candidato.hilos >= c.hilos
            for r in self.resultados
        )

    def _medir(self, i: int, r: Resultado) -> None:
        c = r.candidato
        if self._reloj() - self._inicio > self.presupuesto_s - MARGEN_CANDIDATO_S:
            return self._omitir(r, MOTIVO_TIEMPO)
        if self._innecesaria(c):
            return self._omitir(r, MOTIVO_PODA)
        with self._lock:
            self.actual, self.parte, r.estado = i, 0.0, MIDIENDO
        empezo = self._reloj()
        modelo = None
        try:
            modelo = self._cargar(c)
            self._probar(modelo, r)
        except ModeloNoDisponible:
            self._omitir(r, MOTIVO_MODELO)
        except Exception as e:  # una prueba que falla no tira las demás
            with self._lock:
                r.estado, r.motivo = FALLO, f"{e.__class__.__name__}: {e}"[:120]
        finally:
            getattr(modelo, "close", lambda: None)()  # whisper.cpp: parar el servidor
            with self._lock:
                self.actual, self.parte = -1, 0.0
                r.segundos = self._reloj() - empezo
                if r.estado == MIDIENDO:  # cancelada a medias: no hay medida que enseñar
                    r.estado, r.motivo = OMITIDA, MOTIVO_CANCELADA

    def _probar(self, modelo, r: Resultado) -> None:
        kw = dict(
            language="es", beam_size=r.candidato.haz, vad_filter=True, condition_on_previous_text=False,
            initial_prompt=self.vocab, repetition_penalty=self.repetition_penalty,  # como _process() en whisper_worker.py
        )

        def transcribir(audio: np.ndarray) -> str:
            segs, _ = modelo.transcribe(audio, **kw)
            return " ".join(s.text.strip() for s in segs)  # el generador es perezoso: hay que consumirlo

        textos = [transcribir(self.trozos[0])]  # calentamiento: no cuenta para la velocidad
        medidos = self.trozos[1:] or self.trozos[:1]
        audio_s, completa = 0.0, True
        antes, t0 = self._tiempos(), self._reloj()
        for k, trozo in enumerate(medidos):
            if self.cancelado:
                return
            textos.append(transcribir(trozo))
            audio_s += len(trozo) / RATE
            with self._lock:
                self.parte = (k + 1) / len(medidos)
            if self._reloj() - t0 >= self.tope_candidato_s and k + 1 < len(medidos):
                completa = False  # se corta: la velocidad vale, el WER (de la muestra entera) no
                break
        transcurrido = max(1e-6, self._reloj() - t0)
        ocupado = _ocupado(antes, self._tiempos())
        with self._lock:
            r.velocidad = audio_s / transcurrido
            r.cpu_pct = None if ocupado is None else round(ocupado)
            r.wer = wer(self.referencia, " ".join(textos)) if completa else None
            r.estado = LISTA


# ------------------------------------------------------------------ cargar el modelo de una prueba
def cargar_modelo(config: AppConfig) -> Callable[[Candidato], object]:
    """Cómo se carga el modelo de cada prueba en la app: como el transcriptor, pero sin descargar nada."""

    def cargar(c: Candidato):
        if c.motor == "whisper.cpp":
            from .engine.whispercpp import load_whispercpp_model

            return load_whispercpp_model(
                config.whispercpp_dir, c.modelo, c.precision, "es", c.hilos, c.flash_attn, device=c.gpu_index
            )
        from faster_whisper import WhisperModel

        try:
            return WhisperModel(
                c.modelo, device=c.dispositivo, compute_type=c.precision, cpu_threads=c.hilos if c.dispositivo == "cpu" else 0,
                local_files_only=True,
            )
        except Exception as e:
            if _es_modelo_ausente(e):
                raise ModeloNoDisponible(c.modelo) from e
            raise

    return cargar


def _es_modelo_ausente(e: Exception) -> bool:
    """Si el error de faster-whisper dice que el modelo no está en la caché local (y no es otro fallo)."""
    nombre = e.__class__.__name__
    return isinstance(e, FileNotFoundError) or "NotFound" in nombre or "LocalEntry" in nombre or "snapshot" in str(e).lower()


# ------------------------------------------------------------------ el informe guardado
@dataclasses.dataclass
class Informe:
    """La última medición: cuándo, en qué equipo, cada prueba y cuál salió mejor."""

    fecha: str  # ISO, hora local
    huella: str  # qué equipo era (`huella`): una medición de otro equipo no vale
    resultados: List[Resultado]
    mejor: Optional[str]  # clave del Candidato mejor; None si no hubo ninguna medida
    dos_fuentes: bool  # si la mejor aguanta dos fuentes
    reposo_pct: Optional[int] = None  # procesador ocupado por otros al empezar
    forzada: bool = False  # se midió aunque el equipo no estaba en reposo

    @property
    def mejor_resultado(self) -> Optional[Resultado]:
        return next((r for r in self.resultados if r.candidato.clave == self.mejor), None)

    def to_dict(self) -> dict:
        return {"version": VERSION_INFORME, **dataclasses.asdict(self)}

    @classmethod
    def from_dict(cls, d: dict) -> "Informe":
        campos = {f.name for f in dataclasses.fields(Candidato)}
        resultados = [
            Resultado(**{**r, "candidato": Candidato(**{k: v for k, v in r["candidato"].items() if k in campos})})
            for r in d["resultados"]
        ]
        return cls(d["fecha"], d["huella"], resultados, d.get("mejor"), bool(d.get("dos_fuentes")), d.get("reposo_pct"), bool(d.get("forzada")))


def huella(perfil: HardwareProfile) -> str:
    """Qué equipo es, para saber si una medición guardada sigue valiendo: procesador, núcleos y tarjetas con Vulkan."""
    gpus = ",".join(sorted(g.name for g in perfil.vulkan_devices))
    return f"{perfil.cpu_name}|{perfil.physical_cores}|{perfil.logical_cores}|{gpus}"


def ruta_informe(config_path: Optional[pathlib.Path] = None) -> pathlib.Path:
    """Dónde se guarda la última medición: `medicion.json` junto al config.json (el que se use)."""
    return (config_path or ruta_config()).with_name(NOMBRE_INFORME)


def guardar_informe(informe: Informe, ruta: pathlib.Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(informe.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_informe(ruta: pathlib.Path) -> Optional[Informe]:
    """La medición guardada, o None si no hay ninguna o no se puede leer (nunca falla: es solo una ayuda)."""
    try:
        d = json.loads(ruta.read_text(encoding="utf-8"))
        return Informe.from_dict(d) if isinstance(d, dict) and d.get("version") == VERSION_INFORME else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def formato_fecha(iso: str) -> str:
    """«25/11/2026» de una fecha ISO; la cadena tal cual si no se entiende."""
    try:
        return datetime.datetime.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso


# ------------------------------------------------------------------ la recomendación con la medición
TIER_MEDIDO = "medido"  # el `tier` de una recomendación que sale de una medición en este equipo


def recomendacion_medida(
    informe: Optional[Informe], perfil: HardwareProfile, config: AppConfig, base: Recommendation,
) -> Optional[Recommendation]:
    """La recomendación que sale de `informe` (la mejor prueba medida en ESTE equipo), o None si no vale:
    es de otro equipo, no hubo medida, o la prueba pide algo que ya no está (whisper.cpp, el permiso de la integrada)."""
    if informe is None or informe.huella != huella(perfil):
        return None
    mejor = informe.mejor_resultado
    if mejor is None or mejor.estado != LISTA:
        return None
    c = mejor.candidato
    if c.motor == "whisper.cpp" and not whispercpp_ready(config.whispercpp_dir, c.modelo, c.precision):
        return None
    if c.integrada and not config.allow_igpu:
        return None
    if c.dispositivo == "cuda" and perfil.cuda_devices <= 0:
        return None
    clave = "medir_motivo_dos" if informe.dos_fuentes else "medir_motivo_una"
    motivo = ayuda.entrada(clave)[1].format(
        fecha=formato_fecha(informe.fecha), prueba=c.etiqueta(), velocidad=f"{mejor.velocidad:.1f}".replace(".", ","),
    )
    return Recommendation(
        c.preset if c.dispositivo == "cpu" else None, c.modelo, c.haz, c.dispositivo, c.precision,
        c.hilos if c.dispositivo == "cpu" else base.cpu_threads, c.motor, TIER_MEDIDO, motivo, "medida",
        flash_attn=c.flash_attn, gpu_index=c.gpu_index if c.dispositivo == "vulkan" else -1,
    )


def recomendar(
    perfil: HardwareProfile, config: AppConfig, config_path: Optional[pathlib.Path] = None,
    whispercpp_dir: Optional[str] = None,
) -> Recommendation:
    """La recomendación del equipo: la de `recommend_config` (hardware, whisper.cpp) o, si hay una medición
    de este equipo que sirve, la mejor prueba medida. Es lo que usan `daily recomendar`, el asistente, Opciones
    y la pantalla de recomendación: así todos dicen lo mismo. `whispercpp_dir` es la carpeta que se está
    editando, si no es la guardada."""
    if whispercpp_dir is not None:
        config = dataclasses.replace(config, whispercpp_dir=whispercpp_dir)
    base = recommend_config(perfil, *vulkan_readiness(config.whispercpp_dir))
    medida = recomendacion_medida(cargar_informe(ruta_informe(config_path)), perfil, config, base)
    return medida or base


# ------------------------------------------------------------------ el flujo entero
class Prueba:
    """«Medir mi equipo» de principio a fin, en su hilo: prepara la muestra, mira si el equipo está en reposo,
    mide y guarda el informe. Las interfaces la crean, llaman a `iniciar` y consultan `instantanea` mientras
    pintan; `cancelar` la para y no guarda nada.

    `cargar`, `generar`, `reposo` y `reloj` se inyectan en las pruebas (motores y SAPI de mentira).
    """

    def __init__(
        self, perfil: HardwareProfile, config: AppConfig, config_path: Optional[pathlib.Path] = None, *,
        cargar: Optional[Callable[[Candidato], object]] = None,
        generar: Callable[[Optional[int]], pathlib.Path] = generar_muestra,
        reposo: Callable[[], int] = cpu_ocupada_pct,
        reloj: Callable[[], float] = time.monotonic,
        ahora: Callable[[], datetime.datetime] = datetime.datetime.now,
        **medidor,
    ):
        self.perfil, self.config, self.config_path = perfil, config, config_path
        self._cargar = cargar or cargar_modelo(config)
        self._generar, self._reposo, self._reloj, self._ahora = generar, reposo, reloj, ahora
        self._medidor_kw = medidor
        self.medidor: Optional[Medidor] = None
        self.informe: Optional[Informe] = None
        self.fase, self.error, self.reposo_pct = PREPARANDO, "", None
        self._forzar = False
        self._hilo: Optional[threading.Thread] = None
        self._cancelada = threading.Event()
        self._muestra: Optional[Tuple[List[np.ndarray], str]] = None
        turbo, large = vulkan_readiness(config.whispercpp_dir)
        self.candidatos = candidatos(perfil, config, turbo, large)
        self.igpu_sin_permiso = igpu_sin_permiso(perfil, config, turbo)

    def iniciar(self, forzar: bool = False) -> None:
        """Empieza (o vuelve a empezar tras `OCUPADO`, con `forzar` para medir aunque haya carga)."""
        if self._hilo is not None and self._hilo.is_alive():
            return
        self._forzar = forzar
        self.fase, self.error = PREPARANDO, ""
        self._hilo = threading.Thread(target=self._correr, daemon=True, name="medir")
        self._hilo.start()

    def cancelar(self) -> None:
        self._cancelada.set()
        if self.medidor is not None:
            self.medidor.cancelar()
        if self.fase in (PREPARANDO, OCUPADO, EN_CURSO):
            self.fase = CANCELADA

    def esperar(self, timeout: Optional[float] = None) -> None:
        if self._hilo is not None:
            self._hilo.join(timeout)

    def instantanea(self) -> Instantanea:
        if self.medidor is None:
            filas = tuple(Resultado(c) for c in self.candidatos)
            return Instantanea(self.fase, filas, -1, 0.0, None, self.reposo_pct, self.error)
        resultados, actual, progreso, queda = self.medidor.instantanea()
        return Instantanea(self.fase, resultados, actual, progreso, queda, self.reposo_pct, self.error)

    # ------------------------------------------------------------ el hilo
    def _correr(self) -> None:
        try:
            if not self.candidatos:
                return self._fallar("medir_sin_pruebas")
            if self._muestra is None:
                try:
                    wav = self._generar(TURNOS_PRUEBA)
                except SinVoz:
                    return self._fallar("medir_sin_voz")
                self._muestra = (trocear(cargar_wav(wav)), " ".join(GUION[:TURNOS_PRUEBA]))
            if self._cancelada.is_set():
                return
            if not self._forzar:
                self.reposo_pct = self._reposo()
                if self.reposo_pct > REPOSO_MAXIMO_PCT:
                    self.fase = OCUPADO
                    return
            if not self._muestra[0]:
                return self._fallar("medir_sin_pruebas")
            self.medidor = Medidor(
                self.candidatos, self._muestra[0], self._muestra[1], self._cargar, vocab=self.config.vocab.strip() or None,
                repetition_penalty=self.config.repetition_penalty, reloj=self._reloj, **self._medidor_kw,
            )
            if self._cancelada.is_set():  # se canceló mientras se creaba: `cancelar` aún no veía el medidor
                return
            self.fase = EN_CURSO
            self.medidor.ejecutar()
            if self._cancelada.is_set():
                self.fase = CANCELADA
                return
            self._terminar()
        except Exception as e:  # nada de lo que falle aquí debe dejar la interfaz esperando
            self.fase, self.error = ERROR, ayuda.entrada("medir_error")[1].format(motivo=f"{e.__class__.__name__}: {e}")

    def _fallar(self, clave: str) -> None:
        self.fase, self.error = ERROR, ayuda.entrada(clave)[1]

    def _terminar(self) -> None:
        resultados = self.medidor.instantanea()[0]
        mejor, dos = elegir_mejor(resultados)
        self.informe = Informe(
            self._ahora().isoformat(timespec="seconds"), huella(self.perfil), list(resultados),
            mejor.candidato.clave if mejor else None, dos, self.reposo_pct, self._forzar,
        )
        if mejor is not None:  # una medición sin ninguna medida no sustituye a la anterior
            try:
                guardar_informe(self.informe, ruta_informe(self.config_path))
            except OSError:
                pass  # no poder guardarlo no quita lo medido: se ve y se puede aplicar
        self.fase = TERMINADA
