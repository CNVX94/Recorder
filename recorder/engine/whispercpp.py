"""Motor whisper.cpp con Vulkan, para GPUs sin CUDA (p. ej. AMD Radeon).

CTranslate2 (el motor de faster-whisper) no tiene camino para una Radeon RDNA2 en Windows, asi
que la GPU se aprovecha con `whisper-server.exe` de whisper.cpp compilado con Vulkan
(tools/instalar_whispercpp.ps1). Corre como proceso aparte y se le habla por HTTP en
127.0.0.1: un fallo del driver de video mata ese proceso, no la ventana ni la cola pendiente.

`WhisperCppModel.transcribe()` imita a `faster_whisper.WhisperModel.transcribe()` (mismos
argumentos, segmentos con `text`, `avg_logprob` y `no_speech_prob`), asi que
`whisper_worker._process()` y los filtros no distinguen un motor del otro. El servidor no
devuelve `compression_ratio`; `filters/quality.py` lo calcula cuando falta.

Ver docs/gpu-amd-vulkan.md.
"""

import ctypes
import dataclasses
import io
import json
import pathlib
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import wave
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

SERVER_EXE = "whisper-server.exe"
VAD_MODEL = "ggml-silero-v6.2.0.bin"
LOAD_TIMEOUT_SEC = 180.0  # large-v3 son 3 GB que leer de disco y subir a la VRAM
REQUEST_TIMEOUT_SEC = 300.0  # un fragmento no deberia pasar de segundos; esto solo evita colgarse
SAMPLE_RATE = 16000


class EngineUnavailable(RuntimeError):
    """El servidor murio y no se pudo volver a arrancar: hay que cambiar de motor."""


@dataclasses.dataclass
class Segment:
    text: str
    avg_logprob: float
    no_speech_prob: float
    compression_ratio: Optional[float] = None  # el servidor no lo da; quality.py lo calcula


# ------------------------------------------------------------------ rutas
def model_filename(model: str, compute_type: str) -> str:
    """Nombre del modelo ggml: `float16` es el archivo sin sufijo; `q8_0`, `q5_0`... llevan sufijo."""
    if compute_type in ("", "float16", "f16"):
        return f"ggml-{model}.bin"
    return f"ggml-{model}-{compute_type}.bin"


def server_exe_path(root: pathlib.Path) -> pathlib.Path:
    return root / "bin" / SERVER_EXE


def model_path(root: pathlib.Path, model: str, compute_type: str) -> pathlib.Path:
    return root / "models" / model_filename(model, compute_type)


def whispercpp_ready(whispercpp_dir: str, model: str, compute_type: str) -> bool:
    """Si hay un whisper-server compilado y el modelo pedido en `whispercpp_dir`.

    Solo mira el disco: que Vulkan arranque de verdad se sabe al lanzar el servidor, y si
    no arranca el worker cae a CPU igual que cuando una GPU CUDA no carga.
    """
    if not whispercpp_dir:
        return False
    root = pathlib.Path(whispercpp_dir)
    return server_exe_path(root).is_file() and model_path(root, model, compute_type).is_file()


# ------------------------------------------------------------------ peticion y respuesta
def wav_bytes(audio: np.ndarray, rate: int = SAMPLE_RATE) -> bytes:
    """float32 mono en [-1, 1] -> WAV PCM de 16 bits en memoria (lo que lee whisper-server sin ffmpeg)."""
    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def multipart_body(fields: Dict[str, str], wav: bytes) -> Tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8")
        )
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.wav"\r\n'
        f"Content-Type: audio/wav\r\n\r\n".encode("utf-8")
    )
    parts.append(wav)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def request_fields(language: str, beam_size: int, initial_prompt: Optional[str], vad: bool) -> Dict[str, str]:
    """Campos del formulario de /inference equivalentes a la llamada de whisper_worker._process().

    `condition_on_previous_text=False` no hace falta: el servidor usa `no_context=true` por
    defecto. `repetition_penalty` no existe en whisper.cpp; los bucles los sigue atrapando el
    filtro de `compression_ratio`.
    """
    fields = {
        "response_format": "verbose_json",
        "language": language,
        "beam_size": str(beam_size),
        "vad": "true" if vad else "false",
        # Por defecto verbose_json calcula la deteccion de idioma y las marcas por token:
        # trabajo extra que Recorder no usa (el idioma va fijo).
        "no_language_probabilities": "true",
        "token_timestamps": "false",
    }
    if initial_prompt:
        fields["prompt"] = initial_prompt
    return fields


def parse_segments(payload: Dict[str, Any]) -> List[Segment]:
    return [
        Segment(
            text=str(s.get("text", "")),
            avg_logprob=float(s.get("avg_logprob", 0.0)),
            no_speech_prob=float(s.get("no_speech_prob", 0.0)),
        )
        for s in payload.get("segments", [])
    ]


# ------------------------------------------------------------------ proceso
def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _IoCounters(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint64) for n in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
    )]


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimits),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _kill_with_parent(proc: subprocess.Popen) -> Optional[int]:
    """Mete el hijo en un Job Object que Windows cierra al morir Recorder, aunque sea de golpe.

    Sin esto, un Recorder que revienta deja un whisper-server huerfano ocupando 3 GB de VRAM,
    y el siguiente arranque lanza otro. Devuelve el handle (hay que mantenerlo abierto) o None
    si no se pudo; es una proteccion extra, no un requisito para transcribir.
    """
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.CreateJobObjectW.restype = ctypes.c_void_p
        k32.SetInformationJobObject.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        k32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        job = k32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _ExtendedLimits()
        info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))  # ExtendedLimitInformation
        if ok and k32.AssignProcessToJobObject(job, int(proc._handle)):
            return job
        k32.CloseHandle(ctypes.c_void_p(job))
    except Exception:
        pass
    return None


class WhisperCppServer:
    """Arranca `whisper-server` en un puerto libre de 127.0.0.1 y espera a que cargue el modelo.

    `command` es el ejecutable con sus argumentos, sin `--host`/`--port`, que se anaden aqui.
    """

    def __init__(self, command: Sequence[str], log_path: pathlib.Path, load_timeout: float = LOAD_TIMEOUT_SEC):
        self.command = list(command)
        self.log_path = log_path
        self.load_timeout = load_timeout
        self.proc: Optional[subprocess.Popen] = None
        self.port = 0
        self._job = None
        self._log = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self) -> None:
        self.stop()
        self.port = _free_port()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_path, "wb")
        self.proc = subprocess.Popen(
            self.command + ["--host", "127.0.0.1", "--port", str(self.port)],
            stdin=subprocess.DEVNULL,
            stdout=self._log,
            stderr=subprocess.STDOUT,  # a un archivo, no a una tuberia: una tuberia llena lo congelaria
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self._job = _kill_with_parent(self.proc)
        self._wait_ready()

    def _wait_ready(self) -> None:
        # El servidor carga el modelo ANTES de escuchar: hasta entonces la conexion se rechaza.
        deadline = time.monotonic() + self.load_timeout
        while time.monotonic() < deadline:
            code = self.proc.poll()
            if code is not None:
                self.stop()
                raise RuntimeError(f"whisper-server termino al arrancar (codigo {code}); ver {self.log_path}")
            try:
                with urllib.request.urlopen(self.base_url + "/health", timeout=2) as r:
                    if r.status == 200:
                        return
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.25)
        self.stop()
        raise RuntimeError(f"whisper-server no respondio en {self.load_timeout:.0f} s; ver {self.log_path}")

    def stop(self) -> None:
        if self._job:
            # Termina el arbol entero, no solo el proceso lanzado (p. ej. un lanzador que a su
            # vez crea el proceso real y hereda el log abierto).
            k32 = ctypes.WinDLL("kernel32")
            k32.TerminateJobObject(ctypes.c_void_p(self._job), 1)
            k32.CloseHandle(ctypes.c_void_p(self._job))
            self._job = None
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        if self._log is not None:
            self._log.close()
            self._log = None


def server_command(
    whispercpp_dir: str,
    model: str,
    compute_type: str,
    language: str,
    threads: int,
    flash_attn: bool,
) -> List[str]:
    root = pathlib.Path(whispercpp_dir)
    cmd = [str(server_exe_path(root)), "-m", str(model_path(root, model, compute_type)), "-l", language]
    if threads > 0:
        cmd += ["-t", str(threads)]
    # Apagada por defecto: en Radeon con Windows hay reportes de frases repetidas sin fin y de
    # cierres en amdvlk64.dll con flash attention. Se enciende solo si la medicion sale limpia.
    cmd.append("-fa" if flash_attn else "-nfa")
    vad = root / "models" / VAD_MODEL
    if vad.is_file():
        cmd += ["--vad", "-vm", str(vad)]
    return cmd


# ------------------------------------------------------------------ modelo
class WhisperCppModel:
    """Adaptador con la forma de `faster_whisper.WhisperModel` sobre un `WhisperCppServer`."""

    def __init__(self, server: WhisperCppServer, has_vad: bool, request_timeout: float = REQUEST_TIMEOUT_SEC):
        self.server = server
        self.has_vad = has_vad
        self.request_timeout = request_timeout

    def transcribe(
        self,
        audio: np.ndarray,
        language: str = "es",
        beam_size: int = 5,
        vad_filter: bool = True,
        initial_prompt: Optional[str] = None,
        **_ignored: Any,
    ) -> Tuple[List[Segment], Dict[str, Any]]:
        fields = request_fields(language, beam_size, initial_prompt, vad_filter and self.has_vad)
        body, content_type = multipart_body(fields, wav_bytes(audio))
        try:
            payload = self._post(body, content_type)
        except (urllib.error.URLError, OSError):
            if not self._died():
                raise  # servidor vivo pero con fallo: se pierde este fragmento, no el motor
            try:
                self.server.start()
            except Exception as e:
                raise EngineUnavailable(f"whisper-server se cayo y no volvio a arrancar: {e}") from e
            payload = self._post(body, content_type)  # el fragmento que lo tumbo se reintenta una vez
        return parse_segments(payload), payload

    def _died(self) -> bool:
        """Tras un error de conexion, da un momento al proceso para terminar de morir."""
        proc = self.server.proc
        if proc is None:
            return True
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        return not self.server.alive()

    def _post(self, body: bytes, content_type: str) -> Dict[str, Any]:
        req = urllib.request.Request(
            self.server.base_url + "/inference", data=body, headers={"Content-Type": content_type}, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.request_timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Respuesta de un servidor vivo: no es motivo para reiniciarlo.
            raise RuntimeError(f"whisper-server respondio {e.code}: {e.read()[:200]!r}") from None

    def close(self) -> None:
        self.server.stop()


def load_whispercpp_model(
    whispercpp_dir: str,
    model: str,
    compute_type: str,
    language: str,
    threads: int,
    flash_attn: bool,
) -> WhisperCppModel:
    """Arranca el servidor y devuelve el modelo listo. Lanza excepcion si no arranca."""
    cmd = server_command(whispercpp_dir, model, compute_type, language, threads, flash_attn)
    server = WhisperCppServer(cmd, pathlib.Path(whispercpp_dir) / "logs" / "whisper-server.log")
    server.start()
    return WhisperCppModel(server, has_vad="--vad" in cmd)
