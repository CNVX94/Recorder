"""Con qué motor y dispositivo se transcribe de verdad y cuánto le cuesta al equipo.

Sin interfaz: la sesión pone una `Metricas` en `StatusSnapshot.metricas` para que la ventana y la
terminal la pinten, y al cerrar deja `Muestreador.resumen()` en el registro (registro.py).

- `MotorEfectivo`: lo que cargó el transcriptor tras resolver el hardware y las caídas a CPU
  (whisper_worker._load_model), no lo que pide config.json.
- `Velocidad`: factor de tiempo real por fragmento (s de audio / s de proceso). La anota el
  transcriptor en su hilo al acabar cada fragmento: por encima de 1 va por delante; por debajo,
  la cola crece.
- `Muestreador`: un hilo propio que cada INTERVALO s lee la CPU del proceso (más whisper-server si
  está en marcha) y del sistema, la RAM, la GPU y la cola. Las lecturas son llamadas de Windows
  por ctypes (como tools/medir_rendimiento.py) y se inyectan en las pruebas; lo que no se pueda
  leer queda en None («n/d»), sin error. Nada de esto corre en el hilo de audio.
"""
import ctypes
import dataclasses
import os
import re
import statistics
import threading
import time
from typing import Callable, List, Optional, Sequence, Tuple

INTERVALO = 2.0  # segundos entre muestras
VENTANA = 10  # fragmentos de la media móvil de la velocidad
CT2_HILOS_POR_DEFECTO = 4  # cpu_threads 0 = lo que pone CTranslate2 (docs/rendimiento.md)


def hilos_efectivos(cpu_threads: int) -> int:
    return cpu_threads if cpu_threads > 0 else CT2_HILOS_POR_DEFECTO


def factor(x: float) -> str:
    """2.14 → «2,1×»."""
    return f"{x:.1f}×".replace(".", ",")


def na(x: Optional[float], fmt: str = "{:.0f} %") -> str:
    return "n/d" if x is None else fmt.format(x)


# ---------------------------------------------------------------------------
# Motor efectivo
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class MotorEfectivo:
    motor: str  # "faster-whisper" o "whisper.cpp"
    dispositivo: str  # "cpu", "cuda" o "vulkan"
    modelo: str
    haz: int
    hilos: int = 0  # hilos de CPU efectivos; solo en CPU
    gpu: str = ""  # nombre de la GPU de Vulkan; vacío si no se sabe
    integrada: bool = False
    caida: str = ""  # por qué se cayó a CPU; vacío si no hubo caída

    @property
    def donde(self) -> str:
        if self.dispositivo == "cpu":
            return f"CPU, {self.hilos} hilos"
        if self.dispositivo == "cuda":
            return "GPU NVIDIA (dedicada, CUDA)"
        tipo = "integrada" if self.integrada else "dedicada"
        return f"GPU {self.gpu} ({tipo}, Vulkan)" if self.gpu else "GPU (Vulkan)"

    @property
    def texto(self) -> str:
        """«faster-whisper · CPU, 4 hilos · small · haz 5»; el motivo de una caída va en `caida`."""
        caida = " · ⚠ caída a CPU" if self.caida else ""
        return f"{self.motor} · {self.donde} · {self.modelo} · haz {self.haz}{caida}"


# ---------------------------------------------------------------------------
# Velocidad del transcriptor
# ---------------------------------------------------------------------------

class Velocidad:
    """(s de audio, s de proceso) de cada fragmento de la sesión. Escribe el hilo del transcriptor
    y leen el muestreo y la interfaz: `append` y el corte de una lista son atómicos en CPython."""

    def __init__(self, ventana: int = VENTANA):
        self.ventana = ventana
        self.fragmentos: List[Tuple[float, float]] = []

    def registrar(self, audio_s: float, proceso_s: float) -> None:
        if audio_s > 0 and proceso_s > 0:
            self.fragmentos.append((audio_s, proceso_s))

    @staticmethod
    def _ponderada(frs: Sequence[Tuple[float, float]]) -> Optional[float]:
        # Audio total / proceso total: un fragmento de 1 s no pesa como uno de 20 s.
        return sum(a for a, _ in frs) / sum(p for _, p in frs) if frs else None

    @property
    def media(self) -> Optional[float]:
        """Media móvil de los últimos `ventana` fragmentos; None hasta el primero."""
        return self._ponderada(self.fragmentos[-self.ventana:])

    @property
    def ultimo_s(self) -> Optional[float]:
        frs = self.fragmentos[-1:]
        return frs[0][1] if frs else None

    def resumen(self) -> Tuple[Optional[float], Optional[float], int]:
        """(media de la sesión, p95, fragmentos). El p95 se toma por el lado lento: el 95 % de los
        fragmentos fue al menos así de rápido."""
        frs = list(self.fragmentos)
        if not frs:
            return None, None, 0
        factores = [a / p for a, p in frs]
        p95 = statistics.quantiles(factores, n=20, method="inclusive")[0] if len(factores) > 1 else factores[0]
        return self._ponderada(frs), p95, len(frs)


# ---------------------------------------------------------------------------
# Lecturas de Windows (ctypes). Instancias propias de las DLL: fijar restype/argtypes aquí no
# cambia las de ctypes.windll que usa el resto de Recorder.
# ---------------------------------------------------------------------------

class _FT(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]

    @property
    def v(self) -> int:
        return (self.hi << 32) | self.lo


class _Memoria(ctypes.Structure):  # PROCESS_MEMORY_COUNTERS
    _fields_ = [("cb", ctypes.c_uint32), ("PageFaultCount", ctypes.c_uint32)] + [
        (n, ctypes.c_size_t) for n in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
        )
    ]


_k32 = None


def _kernel32():
    global _k32
    if _k32 is None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.GetProcessTimes.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(_FT)] * 4
        k.K32GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Memoria), ctypes.c_uint32]
        _k32 = k
    return _k32


def tiempos_sistema() -> Optional[Tuple[int, int]]:
    """(reposo, total) acumulados del sistema en unidades de 100 ns; None si no se pueden leer."""
    try:
        idle, kern, user = _FT(), _FT(), _FT()
        if not _kernel32().GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
            return None
        return idle.v, kern.v + user.v  # el tiempo de núcleo incluye el de reposo
    except (OSError, AttributeError):
        return None


def leer_procesos(pids: Sequence[int]) -> Tuple[float, int]:
    """(s de CPU acumulados, bytes de RAM en uso) sumando esos procesos; uno que no se deja abrir
    (ya terminó) suma 0."""
    try:
        k = _kernel32()
    except (OSError, AttributeError):
        return 0.0, 0
    cpu, ram = 0, 0
    for pid in pids:
        h = k.OpenProcess(0x1000 | 0x0010, False, pid)  # QUERY_LIMITED_INFORMATION | VM_READ
        if not h:
            continue
        try:
            c, e, kern, user = _FT(), _FT(), _FT(), _FT()
            if k.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kern), ctypes.byref(user)):
                cpu += kern.v + user.v
            m = _Memoria()
            if k.K32GetProcessMemoryInfo(h, ctypes.byref(m), ctypes.sizeof(m)):
                ram += m.WorkingSetSize
        finally:
            k.CloseHandle(h)
    return cpu / 1e7, ram


class _EstadoMemoria(ctypes.Structure):  # MEMORYSTATUSEX
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32)] + [
        (n, ctypes.c_uint64) for n in (
            "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
            "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual",
        )
    ]


def leer_ram_sistema() -> Optional[Tuple[float, float]]:
    """(usada, total) de la memoria física del equipo en MB; None si no se puede leer."""
    try:
        k = _kernel32()
        k.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_EstadoMemoria)]
        estado = _EstadoMemoria()
        estado.dwLength = ctypes.sizeof(estado)
        if not k.GlobalMemoryStatusEx(ctypes.byref(estado)) or not estado.ullTotalPhys:
            return None
        return (estado.ullTotalPhys - estado.ullAvailPhys) / 2**20, estado.ullTotalPhys / 2**20
    except (OSError, AttributeError):
        return None


class _ValorPdh(ctypes.Structure):  # PDH_FMT_COUNTERVALUE con doubleValue
    _fields_ = [("estado", ctypes.c_uint32), ("valor", ctypes.c_double)]


class _ItemPdh(ctypes.Structure):  # PDH_FMT_COUNTERVALUE_ITEM_W
    _fields_ = [("nombre", ctypes.c_wchar_p), ("v", _ValorPdh)]


_PDH_FMT_DOUBLE = 0x200
_PDH_MORE_DATA = 0x800007D2


class LectorGpu:
    """Contadores PDH «GPU Engine\\Utilization Percentage» de todos los procesos: [(instancia, %)].

    La consulta se abre en la primera llamada (en el hilo del muestreo): una vez, ~0,6-0,9 s de CPU
    en el i7-1255U mientras PDH enumera los contadores; cada lectura después, ~3 ms. Es un contador de tasa:
    la primera lectura no tiene valor y devuelve None, como cualquier fallo. Si PDH o los
    contadores de GPU no existen, se deja de intentar.
    """

    CONTADOR = "\\GPU Engine(*)\\Utilization Percentage"

    def __init__(self):
        self._pdh = None
        self._contador = None
        self._roto = False

    def _abrir(self) -> bool:
        pdh = ctypes.WinDLL("pdh")
        for f in ("PdhOpenQueryW", "PdhAddEnglishCounterW", "PdhCollectQueryData", "PdhGetFormattedCounterArrayW"):
            getattr(pdh, f).restype = ctypes.c_uint32
        pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)]
        pdh.PdhAddEnglishCounterW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_void_p)]
        pdh.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
        pdh.PdhGetFormattedCounterArrayW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32), ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p,
        ]
        consulta, contador = ctypes.c_void_p(), ctypes.c_void_p()
        if pdh.PdhOpenQueryW(None, 0, ctypes.byref(consulta)):
            return False
        if pdh.PdhAddEnglishCounterW(consulta, self.CONTADOR, 0, ctypes.byref(contador)):
            return False  # ponytail: la consulta abierta se queda; solo pasa una vez por proceso
        self._pdh, self._consulta, self._contador = pdh, consulta, contador
        return True

    def __call__(self) -> Optional[List[Tuple[str, float]]]:
        if self._roto:
            return None
        try:
            if self._pdh is None and not self._abrir():
                self._roto = True
                return None
            pdh = self._pdh
            if pdh.PdhCollectQueryData(self._consulta):
                return None
            tam, n = ctypes.c_uint32(0), ctypes.c_uint32(0)
            if pdh.PdhGetFormattedCounterArrayW(self._contador, _PDH_FMT_DOUBLE, ctypes.byref(tam), ctypes.byref(n), None) != _PDH_MORE_DATA:
                return None
            buf = (ctypes.c_byte * tam.value)()
            if pdh.PdhGetFormattedCounterArrayW(self._contador, _PDH_FMT_DOUBLE, ctypes.byref(tam), ctypes.byref(n), buf):
                return None  # entre las dos llamadas aparecieron instancias: se lee en la próxima
            items = ctypes.cast(buf, ctypes.POINTER(_ItemPdh * n.value)).contents
            validos = [(i.nombre, i.v.valor) for i in items if i.v.estado <= 1]  # VALID_DATA o NEW_DATA
            return validos or None
        except (OSError, AttributeError):
            self._roto = True
            return None


_INSTANCIA = re.compile(r"pid_(\d+)_(luid_\w+?_phys_\d+_eng_\d+)")


def gpu_pct(items: Sequence[Tuple[str, float]], pids: Sequence[int] = ()) -> Tuple[float, float]:
    """(% de la GPU, % de esos procesos) a partir de las instancias de «GPU Engine».

    Como el Administrador de tareas: el uso de cada motor (3D, Compute, Copy…) es la suma de los
    procesos, y el de la GPU, el de su motor más ocupado.
    """
    motores, nuestros = {}, {}
    for nombre, valor in items:
        m = _INSTANCIA.match(nombre)
        if not m:
            continue
        motores[m[2]] = motores.get(m[2], 0.0) + valor
        if int(m[1]) in pids:
            nuestros[m[2]] = nuestros.get(m[2], 0.0) + valor
    return min(100.0, max(motores.values(), default=0.0)), min(100.0, max(nuestros.values(), default=0.0))


# ---------------------------------------------------------------------------
# Muestreo
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Metricas:
    """Lo que la interfaz pinta del coste de la transcripción. Los % son de todo el equipo, como
    el Administrador de tareas; None = «n/d» (aún sin muestra o no se puede leer)."""

    motor: Optional[MotorEfectivo]  # None mientras se carga el modelo
    velocidad: Optional[float]  # media móvil del factor de tiempo real; None hasta el primer fragmento
    ultimo_fragmento_s: Optional[float]  # lo que tardó el último fragmento
    cpu_proceso: Optional[float]  # Recorder + whisper-server
    cpu_sistema: Optional[float]
    ram_mb: Optional[float]  # Recorder + whisper-server
    gpu_proceso: Optional[float]
    gpu_sistema: Optional[float]
    cola: int  # fragmentos esperando
    atraso_s: float  # segundos de audio esperando
    ram_sistema_mb: Optional[float] = None  # memoria ocupada en todo el equipo
    ram_total_mb: Optional[float] = None  # memoria física del equipo

    @property
    def linea(self) -> str:
        """La línea mínima del pie de la terminal: motor efectivo y velocidad; vacía mientras carga."""
        if self.motor is None:
            return ""
        vel = f" · {factor(self.velocidad)} tiempo real" if self.velocidad is not None else ""
        return f"{self.motor.texto}{vel}"


class Muestreador:
    """El hilo del muestreo. Las lecturas, el reloj y el número de CPUs se inyectan en las pruebas.

    `transcriptor` es el TranscriberWorker: de él se leen `motor`, `velocidad` y `modelo` (para el
    pid de whisper-server); `cola()` da (fragmentos, s de audio) en cola.
    """

    def __init__(
        self,
        transcriptor,
        cola: Callable[[], Tuple[int, float]],
        *,
        intervalo: float = INTERVALO,
        reloj: Callable[[], float] = time.monotonic,
        sistema: Callable[[], Optional[Tuple[int, int]]] = tiempos_sistema,
        procesos: Callable[[Sequence[int]], Tuple[float, int]] = leer_procesos,
        gpu: Optional[Callable[[], Optional[List[Tuple[str, float]]]]] = None,
        ram_sistema: Callable[[], Optional[Tuple[float, float]]] = leer_ram_sistema,
        n_cpus: Optional[int] = None,
        pid: Optional[int] = None,
    ):
        self.transcriptor = transcriptor
        self._cola = cola
        self.intervalo = intervalo
        self._reloj, self._sistema, self._procesos = reloj, sistema, procesos
        self._gpu = gpu or LectorGpu()
        self._ram_sistema = ram_sistema
        self._n_cpus = n_cpus or os.cpu_count() or 1
        self._pid = pid or os.getpid()
        self._previa = None  # (reloj, s de CPU, tiempos del sistema, pids)
        self._parar = threading.Event()
        self._hilo: Optional[threading.Thread] = None
        self.cpu_proceso = self.cpu_sistema = self.ram_mb = self.gpu_proceso = self.gpu_sistema = None
        self.ram_sistema_mb = self.ram_total_mb = None
        self.cola, self.atraso_s = 0, 0.0
        self.suma_cpu = self.suma_cpu_sistema = 0.0
        self.muestras_cpu = self.muestras_cpu_sistema = 0
        self.pico_cola, self.pico_atraso_s = 0, 0.0

    def _pids(self) -> Tuple[int, ...]:
        servidor = getattr(getattr(self.transcriptor, "modelo", None), "pid", None)
        return (self._pid,) if servidor is None else (self._pid, servidor)

    def muestrear(self) -> None:
        """Una muestra: % de CPU desde la anterior, RAM, GPU y cola. La llama el hilo; las pruebas, a mano."""
        pids = self._pids()
        ahora, sis = self._reloj(), self._sistema()
        cpu_s, ram = self._procesos(pids)
        if self._previa is not None:
            t0, cpu0, sis0, pids0 = self._previa
            dt = ahora - t0
            # Si whisper-server arrancó, se cayó o cambió, su tiempo acumulado no es de este tramo.
            if dt > 0 and pids == pids0:
                self.cpu_proceso = min(100.0, max(0.0, 100 * (cpu_s - cpu0) / (dt * self._n_cpus)))
                self.suma_cpu += self.cpu_proceso
                self.muestras_cpu += 1
            if sis and sis0 and sis[1] > sis0[1]:
                self.cpu_sistema = 100 * (1 - (sis[0] - sis0[0]) / (sis[1] - sis0[1]))
                self.suma_cpu_sistema += self.cpu_sistema
                self.muestras_cpu_sistema += 1
        self._previa = (ahora, cpu_s, sis, pids)
        self.ram_mb = ram / 2**20 if ram else None
        items = self._gpu()
        self.gpu_sistema, self.gpu_proceso = gpu_pct(items, pids) if items else (None, None)
        self.ram_sistema_mb, self.ram_total_mb = self._ram_sistema() or (None, None)
        self.cola, self.atraso_s = self._cola()
        self.pico_cola = max(self.pico_cola, self.cola)
        self.pico_atraso_s = max(self.pico_atraso_s, self.atraso_s)

    def _bucle(self) -> None:
        # La primera muestra llega tras un intervalo: es la base de los % y una sesión que se
        # cierra antes (las pruebas) no llega a tocar PDH.
        while not self._parar.wait(self.intervalo):
            self.muestrear()

    def iniciar(self) -> None:
        if self._hilo is None:
            self._hilo = threading.Thread(target=self._bucle, daemon=True, name="metricas")
            self._hilo.start()

    def parar(self) -> bool:
        """Para el hilo (sin esperarlo). True la primera vez: cuándo toca escribir el resumen."""
        primera = not self._parar.is_set()
        self._parar.set()
        return primera

    def foto(self) -> Metricas:
        vel = getattr(self.transcriptor, "velocidad", None)
        return Metricas(
            motor=getattr(self.transcriptor, "motor", None),
            velocidad=vel.media if vel else None,
            ultimo_fragmento_s=vel.ultimo_s if vel else None,
            cpu_proceso=self.cpu_proceso,
            cpu_sistema=self.cpu_sistema,
            ram_mb=self.ram_mb,
            gpu_proceso=self.gpu_proceso,
            gpu_sistema=self.gpu_sistema,
            cola=self.cola,
            atraso_s=self.atraso_s,
            ram_sistema_mb=self.ram_sistema_mb,
            ram_total_mb=self.ram_total_mb,
        )

    def resumen(self) -> str:
        """Una línea para el registro al cerrar: motor efectivo, velocidad media y p95, CPU media y pico de cola."""
        motor = getattr(self.transcriptor, "motor", None)
        partes = [f"{motor.texto}{f' ({motor.caida})' if motor.caida else ''}" if motor else "modelo sin cargar"]
        vel = getattr(self.transcriptor, "velocidad", None)
        media, p95, n = vel.resumen() if vel else (None, None, 0)
        partes.append(
            f"velocidad media {factor(media)} tiempo real, p95 {factor(p95)} ({n} fragmentos)" if n else "sin fragmentos transcritos"
        )
        cpu = self.suma_cpu / self.muestras_cpu if self.muestras_cpu else None
        cpu_sis = self.suma_cpu_sistema / self.muestras_cpu_sistema if self.muestras_cpu_sistema else None
        partes.append(f"CPU media {na(cpu)} (sistema {na(cpu_sis)})")
        partes.append(f"pico de cola {self.pico_cola} fragmentos (~{self.pico_atraso_s:.0f} s de audio)")
        return "resumen de la grabación: " + " · ".join(partes)
