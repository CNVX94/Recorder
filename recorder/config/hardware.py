"""Que equipo es este: CPU, memoria, energia y GPUs, sin dependencias nuevas.

Todo sale de APIs de Windows por ctypes que responden en milisegundos; ni WMI ni
`vulkaninfo.exe` (tardan segundos) ni `Win32_VideoController.AdapterRAM`, que es un uint32
y se queda en 4 GB: para una RX 6700 XT de 12 GB devuelve 4293918720.

* CPU: nombre (registro), nucleos fisicos y logicos y clases P/E
  (`GetLogicalProcessorInformationEx`, `EfficiencyClass`), AVX2/AVX-512
  (`IsProcessorFeaturePresent` 40/41, con `numpy.__cpu_features__` de respaldo) y VNNI
  (numpy solo informa AVX512-VNNI, no AVX-VNNI).
* RAM: `GlobalMemoryStatusEx`.
* Energia: `GetSystemPowerStatus` (bateria, enchufado) y `PowerDeterminePlatformRoleEx`
  (sobremesa o portatil).
* GPUs: DXGI (`EnumAdapters1` + `GetDesc1`: memoria dedicada fiable de 64 bits) y Vulkan
  (`vkEnumeratePhysicalDevices`: tipo DISCRETE/INTEGRATED y heaps DEVICE_LOCAL). Vulkan se
  pregunta en un proceso aparte: crear una instancia carga el driver de video y las capas de
  terceros (superposiciones de Steam, OBS...), y un fallo ahi no debe tumbar la ventana. Es la
  misma razon por la que whisper.cpp corre como `whisper-server` aparte.
* CUDA: `detect_cuda_device_count()` (ctranslate2, ~300 ms), solo si hay una NVIDIA.

`detect_hardware()` no lanza nunca: cada bloque va en su try/except, deja un valor neutro y
apunta el motivo en `detection_errors`. Las piezas que interpretan datos crudos
(`parse_core_topology`, `dedupe_dxgi_adapters`, `ggml_vulkan_order`, `classify_power`) son
puras para poder probarlas sin el hardware. Ver docs/recomendacion-hardware.md.

Este modulo solo importa la biblioteca estandar en su nivel superior: se ejecuta tambien como
script (`python -I hardware.py --vulkan`) para la consulta de Vulkan. Instalado (PyInstaller) no
hay interprete ni archivo que ejecutar: se relanza el propio ejecutable con `--vulkan`, que
recorder.py atiende con `sonda_vulkan()` antes de importar nada pesado.
"""

import ctypes
import dataclasses
import json
import os
import re
import struct
import subprocess
import sys
import threading
from typing import Dict, List, Optional, Sequence, Tuple

VENDOR_NVIDIA = 0x10DE
VENDOR_AMD = 0x1002
VENDOR_INTEL = 0x8086
VENDOR_MICROSOFT = 0x1414  # "Microsoft Basic Render Driver"
VENDOR_NAMES = {VENDOR_NVIDIA: "nvidia", VENDOR_AMD: "amd", VENDOR_INTEL: "intel"}

# Sin Vulkan, DXGI no dice si una GPU es integrada. Una iGPU reserva poca memoria "dedicada"
# (128-512 MB tipicos); una dedicada de los ultimos anos trae 2 GB o mas. [estimado]
IGPU_MAX_DEDICATED_MB = 1024

VULKAN_PROBE_TIMEOUT_SEC = 10.0
VULKAN_MARKER = "VULKAN_JSON "


@dataclasses.dataclass(frozen=True)
class GpuInfo:
    name: str
    vendor_id: int = 0
    device_id: int = 0
    vram_mb: int = 0  # memoria propia: DXGI DedicatedVideoMemory o el heap DEVICE_LOCAL de Vulkan
    shared_mb: int = 0  # RAM del sistema que puede usar (DXGI SharedSystemMemory)
    integrated: bool = False  # comparte la RAM del sistema (Vulkan INTEGRATED_GPU o heuristica DXGI)
    vulkan_index: int = -1  # su numero para `whisper-server -dev`; -1 si ggml-vulkan no la registra
    luid: int = 0  # identifica el adaptador en DXGI y en Vulkan (VkPhysicalDeviceIDProperties)

    @property
    def vendor(self) -> str:
        return VENDOR_NAMES.get(self.vendor_id, "otro")


@dataclasses.dataclass
class HardwareProfile:
    """Lo detectado. 0, "" o None significan "no se pudo saber", nunca "no hay"."""

    cpu_name: str = ""
    physical_cores: int = 0
    logical_cores: int = 0
    p_cores: int = 0  # nucleos de la clase mas rapida; en una CPU no hibrida, todos
    e_cores: int = 0  # el resto (E y LP-E); 0 en una CPU no hibrida
    avx2: bool = False
    avx512: bool = False
    vnni: bool = False  # AVX512-VNNI (numpy no distingue AVX-VNNI)
    ram_total_mb: int = 0
    ram_free_mb: int = 0
    desktop: Optional[bool] = None  # None = Windows no lo sabe
    has_battery: bool = False
    on_battery: bool = False
    gpus: List[GpuInfo] = dataclasses.field(default_factory=list)  # sin duplicados ni adaptadores de software
    vulkan_devices: List[GpuInfo] = dataclasses.field(default_factory=list)  # en el orden de ggml-vulkan
    cuda_devices: int = 0
    detection_errors: List[str] = dataclasses.field(default_factory=list)

    @property
    def hybrid(self) -> bool:
        return self.p_cores > 0 and self.e_cores > 0

    @property
    def has_igpu(self) -> bool:
        return any(g.integrated for g in self.gpus + self.vulkan_devices)

    @property
    def discrete_gpus(self) -> List[GpuInfo]:
        return [g for g in self.gpus if not g.integrated]

    @property
    def best_vulkan_discrete(self) -> Optional[GpuInfo]:
        """La GPU dedicada con mas VRAM que registra ggml-vulkan (la que usa whisper.cpp en "auto")."""
        dedicadas = [g for g in self.vulkan_devices if not g.integrated]
        return max(dedicadas, key=lambda g: (g.vram_mb, -g.vulkan_index), default=None)


# ---------------------------------------------------------------------------------- CPU
RELATION_PROCESSOR_CORE = 0


def parse_core_topology(buf: bytes) -> Tuple[int, int, int, int]:
    """(fisicos, logicos, P, E) a partir del bufer de GetLogicalProcessorInformationEx(RelationProcessorCore).

    Cada registro SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX de un nucleo lleva en el byte 9 su
    `EfficiencyClass` (mayor = mas rapido), en el 30 cuantos GROUP_AFFINITY siguen y desde el
    32 las mascaras de 16 bytes con sus procesadores logicos. Si todas las clases son iguales
    la CPU no es hibrida y todos sus nucleos cuentan como P.
    """
    nucleos = []  # (clase de eficiencia, procesadores logicos)
    off = 0
    while off + 8 <= len(buf):
        relacion, tam = struct.unpack_from("<II", buf, off)
        if tam == 0:
            break
        if relacion == RELATION_PROCESSOR_CORE and off + 32 <= len(buf):
            clase = buf[off + 9]
            grupos = struct.unpack_from("<H", buf, off + 30)[0]
            logicos = 0
            for g in range(grupos):
                if off + 40 + 16 * g <= len(buf):
                    logicos += bin(struct.unpack_from("<Q", buf, off + 32 + 16 * g)[0]).count("1")
            nucleos.append((clase, logicos))
        off += tam
    if not nucleos:
        return 0, 0, 0, 0
    fisicos = len(nucleos)
    logicos = sum(n for _, n in nucleos)
    mejor = max(c for c, _ in nucleos)
    if mejor == min(c for c, _ in nucleos):
        return fisicos, logicos, fisicos, 0
    p = sum(1 for c, _ in nucleos if c == mejor)
    return fisicos, logicos, p, fisicos - p


def _core_topology_buffer() -> bytes:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    needed = ctypes.c_uint32(0)
    k32.GetLogicalProcessorInformationEx(RELATION_PROCESSOR_CORE, None, ctypes.byref(needed))
    if not needed.value:
        raise OSError(ctypes.get_last_error(), "GetLogicalProcessorInformationEx no dio tamano")
    buf = ctypes.create_string_buffer(needed.value)
    if not k32.GetLogicalProcessorInformationEx(RELATION_PROCESSOR_CORE, buf, ctypes.byref(needed)):
        raise OSError(ctypes.get_last_error(), "GetLogicalProcessorInformationEx fallo")
    return buf.raw[: needed.value]


def _cpu_name() -> str:
    import winreg

    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
        return " ".join(str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).split())


def _numpy_cpu_features() -> Dict[str, bool]:
    try:
        from numpy._core._multiarray_umath import __cpu_features__ as feats  # numpy 2
    except ImportError:
        from numpy.core._multiarray_umath import __cpu_features__ as feats  # numpy 1
    return dict(feats)


PF_AVX2_INSTRUCTIONS_AVAILABLE = 40
PF_AVX512F_INSTRUCTIONS_AVAILABLE = 41


def _fill_cpu(p: HardwareProfile) -> None:
    p.physical_cores, p.logical_cores, p.p_cores, p.e_cores = parse_core_topology(_core_topology_buffer())


def _fill_isa(p: HardwareProfile, errors: List[str]) -> None:
    try:
        k32 = ctypes.WinDLL("kernel32")
        p.avx2 = bool(k32.IsProcessorFeaturePresent(PF_AVX2_INSTRUCTIONS_AVAILABLE))
        p.avx512 = bool(k32.IsProcessorFeaturePresent(PF_AVX512F_INSTRUCTIONS_AVAILABLE))
    except Exception as e:
        errors.append(f"AVX (IsProcessorFeaturePresent): {e!r}")
    # Un Windows 10 antiguo no conoce las constantes 40/41 y responde FALSE: numpy mira CPUID.
    try:
        feats = _numpy_cpu_features()
        p.avx2 = p.avx2 or bool(feats.get("AVX2"))
        p.avx512 = p.avx512 or bool(feats.get("AVX512F"))
        p.vnni = bool(feats.get("AVX512VNNI"))
    except Exception as e:
        errors.append(f"AVX (numpy): {e!r}")


# ---------------------------------------------------------------------------------- RAM
class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_uint32), ("dwMemoryLoad", ctypes.c_uint32)] + [
        (n, ctypes.c_uint64)
        for n in (
            "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
            "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual",
        )
    ]


def _fill_ram(p: HardwareProfile) -> None:
    st = _MemoryStatusEx(dwLength=ctypes.sizeof(_MemoryStatusEx))
    if not ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(st)):
        raise OSError("GlobalMemoryStatusEx fallo")
    p.ram_total_mb = st.ullTotalPhys // 2**20
    p.ram_free_mb = st.ullAvailPhys // 2**20


# ---------------------------------------------------------------------------------- energia
class _PowerStatus(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_uint8),
        ("BatteryFlag", ctypes.c_uint8),
        ("BatteryLifePercent", ctypes.c_uint8),
        ("SystemStatusFlag", ctypes.c_uint8),
        ("BatteryLifeTime", ctypes.c_uint32),
        ("BatteryFullLifeTime", ctypes.c_uint32),
    ]


DESKTOP_ROLES = {1, 3, 4, 5, 6, 7}  # Desktop, Workstation y servidores/appliance
MOBILE_ROLES = {2, 8}  # Mobile, Slate


def classify_power(ac_line: int, battery_flag: int, role: Optional[int]) -> Tuple[Optional[bool], bool, bool]:
    """(sobremesa, tiene bateria, va con bateria) a partir de lo que dice Windows.

    `battery_flag` 128 = sin bateria y 255 = desconocido; `ac_line` 0 = desenchufado. El rol de
    plataforma manda para sobremesa/portatil (un sobremesa con SAI puede "tener bateria"); si
    Windows no lo sabe (0), se deduce de la bateria.
    """
    has_battery = battery_flag != 255 and not battery_flag & 128
    on_battery = has_battery and ac_line == 0
    if role in DESKTOP_ROLES:
        desktop: Optional[bool] = True
    elif role in MOBILE_ROLES:
        desktop = False
    elif battery_flag == 255:
        desktop = None
    else:
        desktop = not has_battery
    return desktop, has_battery, on_battery


def _fill_power(p: HardwareProfile, errors: List[str]) -> None:
    st = _PowerStatus()
    if not ctypes.WinDLL("kernel32").GetSystemPowerStatus(ctypes.byref(st)):
        raise OSError("GetSystemPowerStatus fallo")
    role = None
    try:
        role = ctypes.WinDLL("powrprof").PowerDeterminePlatformRoleEx(2)  # POWER_PLATFORM_ROLE_V2
    except Exception as e:
        errors.append(f"rol de plataforma: {e!r}")
    p.desktop, p.has_battery, p.on_battery = classify_power(st.ACLineStatus, st.BatteryFlag, role)


# ---------------------------------------------------------------------------------- DXGI
class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32), ("Data2", ctypes.c_uint16), ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_uint8 * 8),
    ]


class _AdapterDesc1(ctypes.Structure):
    _fields_ = [
        ("Description", ctypes.c_wchar * 128),
        ("VendorId", ctypes.c_uint32),
        ("DeviceId", ctypes.c_uint32),
        ("SubSysId", ctypes.c_uint32),
        ("Revision", ctypes.c_uint32),
        ("DedicatedVideoMemory", ctypes.c_size_t),
        ("DedicatedSystemMemory", ctypes.c_size_t),
        ("SharedSystemMemory", ctypes.c_size_t),
        ("LuidLow", ctypes.c_uint32),
        ("LuidHigh", ctypes.c_int32),
        ("Flags", ctypes.c_uint32),
    ]


@dataclasses.dataclass(frozen=True)
class DxgiAdapter:
    """Un DXGI_ADAPTER_DESC1 tal cual, antes de quitar duplicados."""

    name: str
    vendor_id: int
    device_id: int
    subsys_id: int
    dedicated_mb: int
    shared_mb: int
    luid: int
    flags: int


DXGI_ADAPTER_FLAG_SOFTWARE = 2
DXGI_ERROR_NOT_FOUND = -2005270526  # 0x887A0002 como HRESULT con signo
_IID_IDXGIFactory1 = _GUID(0x770AAE78, 0xF26F, 0x4DBA, (ctypes.c_uint8 * 8)(0xA8, 0x29, 0x25, 0x3C, 0x83, 0xD1, 0xB3, 0x87))


def _com_call(obj: ctypes.c_void_p, index: int, argtypes: list, *args) -> int:
    """Llama al metodo `index` de la vtable de un objeto COM; devuelve el HRESULT o ULONG."""
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return proto(vtable[index])(obj, *args)


def _luid(low: int, high: int) -> int:
    return ((high & 0xFFFFFFFF) << 32) | (low & 0xFFFFFFFF)


def _dxgi_adapters() -> List[DxgiAdapter]:
    dxgi = ctypes.WinDLL("dxgi")
    factory = ctypes.c_void_p()
    hr = dxgi.CreateDXGIFactory1(ctypes.byref(_IID_IDXGIFactory1), ctypes.byref(factory))
    if hr < 0 or not factory:
        raise OSError(f"CreateDXGIFactory1: HRESULT {hr & 0xFFFFFFFF:#x}")
    out = []
    try:
        for i in range(64):
            adapter = ctypes.c_void_p()
            # IDXGIFactory1::EnumAdapters1 = 12; IDXGIAdapter1::GetDesc1 = 10; IUnknown::Release = 2
            hr = _com_call(factory, 12, [ctypes.c_uint32, ctypes.POINTER(ctypes.c_void_p)], i, ctypes.byref(adapter))
            if hr == DXGI_ERROR_NOT_FOUND:
                break
            if hr < 0:
                raise OSError(f"EnumAdapters1: HRESULT {hr & 0xFFFFFFFF:#x}")
            try:
                d = _AdapterDesc1()
                if _com_call(adapter, 10, [ctypes.POINTER(_AdapterDesc1)], ctypes.byref(d)) >= 0:
                    out.append(DxgiAdapter(
                        name=d.Description.strip(), vendor_id=d.VendorId, device_id=d.DeviceId,
                        subsys_id=d.SubSysId, dedicated_mb=d.DedicatedVideoMemory // 2**20,
                        shared_mb=d.SharedSystemMemory // 2**20, luid=_luid(d.LuidLow, d.LuidHigh),
                        flags=d.Flags,
                    ))
            finally:
                _com_call(adapter, 2, [])
    finally:
        _com_call(factory, 2, [])
    return out


def dedupe_dxgi_adapters(adapters: Sequence[DxgiAdapter]) -> List[GpuInfo]:
    """GPUs reales a partir de la lista de DXGI.

    Fuera los adaptadores de software (bandera SOFTWARE, "Microsoft Basic Render Driver").
    Los adaptadores de pantalla indirectos (monitores virtuales de Meta, SudoMaker, Amyuni...)
    hacen que DXGI liste la misma GPU varias veces: se queda una por (VendorId, DeviceId,
    SubSysId), la de mas memoria. Sin Vulkan no hay tipo, asi que integrada = poca memoria
    dedicada (IGPU_MAX_DEDICATED_MB).
    """
    vistas: Dict[Tuple[int, int, int], DxgiAdapter] = {}
    for a in adapters:
        if a.flags & DXGI_ADAPTER_FLAG_SOFTWARE or a.vendor_id == VENDOR_MICROSOFT:
            continue
        clave = (a.vendor_id, a.device_id, a.subsys_id)
        if clave not in vistas or a.dedicated_mb > vistas[clave].dedicated_mb:
            vistas[clave] = a
    return [
        GpuInfo(
            name=a.name, vendor_id=a.vendor_id, device_id=a.device_id, vram_mb=a.dedicated_mb,
            shared_mb=a.shared_mb, integrated=a.dedicated_mb < IGPU_MAX_DEDICATED_MB, luid=a.luid,
        )
        for a in vistas.values()
    ]


# ---------------------------------------------------------------------------------- Vulkan
VK_TYPE_OTHER, VK_TYPE_INTEGRATED, VK_TYPE_DISCRETE, VK_TYPE_VIRTUAL, VK_TYPE_CPU = range(5)
VK_DRIVER_AMD_PROPRIETARY, VK_DRIVER_AMD_OPEN_SOURCE, VK_DRIVER_MESA_RADV = 1, 2, 3
VK_DRIVER_NVIDIA_PROPRIETARY, VK_DRIVER_INTEL_PROPRIETARY_WINDOWS, VK_DRIVER_INTEL_MESA = 4, 5, 6
VK_DRIVER_QUALCOMM_PROPRIETARY, VK_DRIVER_MOLTENVK, VK_DRIVER_MESA_TURNIP = 8, 14, 18
VK_DRIVER_MESA_DOZEN, VK_DRIVER_MESA_NVK = 23, 24
VENDOR_QUALCOMM = 0x5143

# Copia de la prioridad de ggml-vulkan.cpp (ggml_vk_instance_init, whisper.cpp v1.9.4) para
# decidir cual de dos drivers de la misma GPU se queda: menor = preferido.
_GGML_DRIVER_PRIORITY = {
    VENDOR_AMD: {VK_DRIVER_MESA_RADV: 1, VK_DRIVER_AMD_OPEN_SOURCE: 2, VK_DRIVER_AMD_PROPRIETARY: 3},
    VENDOR_INTEL: {VK_DRIVER_INTEL_MESA: 1, VK_DRIVER_INTEL_PROPRIETARY_WINDOWS: 2},
    VENDOR_NVIDIA: {VK_DRIVER_NVIDIA_PROPRIETARY: 1, VK_DRIVER_MESA_NVK: 2},
    VENDOR_QUALCOMM: {VK_DRIVER_QUALCOMM_PROPRIETARY: 1, VK_DRIVER_MESA_TURNIP: 2},
}


def _driver_priority(vendor_id: int, driver_id: int) -> int:
    prio = dict(_GGML_DRIVER_PRIORITY.get(vendor_id, {}))
    prio[VK_DRIVER_MESA_DOZEN] = 100
    return prio.get(driver_id, 2**31)


def _same_gpu(a: dict, b: dict) -> bool:
    misma = a["uuid"] == b["uuid"] or (a["luid_valid"] and b["luid_valid"] and a["luid"] == b["luid"])
    return misma and not (a["driver_id"] == b["driver_id"] == VK_DRIVER_MOLTENVK)


def ggml_vulkan_order(devs: Sequence[dict]) -> List[int]:
    """Posiciones de `vkEnumeratePhysicalDevices` que registra ggml-vulkan, en su orden.

    Reproduce ggml_vk_instance_init sin GGML_VK_VISIBLE_DEVICES: GPUs dedicadas E integradas
    con `storageBuffer16BitAccess`, en el orden de enumeracion; si dos son la misma GPU (mismo
    UUID o LUID, p. ej. el driver propio y Dozen) se queda la de driver preferido, que pasa al
    final de la lista. Si no queda ninguna, el primer dispositivo que no sea CPU. El numero de
    `-dev` de whisper-server es la posicion en esta lista (whisper.cpp cuenta GPU e IGPU por
    igual: src/whisper.cpp, whisper_backend_init_gpu).
    """
    elegidos: List[int] = []
    for i, d in enumerate(devs):
        if d["type"] not in (VK_TYPE_DISCRETE, VK_TYPE_INTEGRATED) or not d["supported"]:
            continue
        previo = next((k for k in elegidos if _same_gpu(devs[k], d)), None)
        if previo is None:
            elegidos.append(i)
        elif _driver_priority(devs[previo]["vendor_id"], d["driver_id"]) < _driver_priority(
            devs[previo]["vendor_id"], devs[previo]["driver_id"]
        ):
            elegidos.remove(previo)
            elegidos.append(i)
    if not elegidos:
        elegidos = [i for i, d in enumerate(devs) if d["type"] != VK_TYPE_CPU][:1]
    return elegidos


def vulkan_gpus_from_raw(devs: Sequence[dict]) -> List[GpuInfo]:
    return [
        GpuInfo(
            name=devs[i]["name"], vendor_id=devs[i]["vendor_id"], device_id=devs[i]["device_id"],
            vram_mb=devs[i]["device_local_mb"], integrated=devs[i]["type"] == VK_TYPE_INTEGRATED,
            vulkan_index=n, luid=devs[i]["luid"] if devs[i]["luid_valid"] else 0,
        )
        for n, i in enumerate(ggml_vulkan_order(devs))
    ]


def _vulkan_raw_devices() -> List[dict]:
    """Enumera Vulkan en ESTE proceso. Solo para el script (`--vulkan`), no para la interfaz."""
    c = ctypes
    vk = c.WinDLL("vulkan-1")

    class AppInfo(c.Structure):
        _fields_ = [("sType", c.c_int32), ("pNext", c.c_void_p), ("pApplicationName", c.c_char_p),
                    ("applicationVersion", c.c_uint32), ("pEngineName", c.c_char_p),
                    ("engineVersion", c.c_uint32), ("apiVersion", c.c_uint32)]

    class InstanceInfo(c.Structure):
        _fields_ = [("sType", c.c_int32), ("pNext", c.c_void_p), ("flags", c.c_uint32),
                    ("pApplicationInfo", c.POINTER(AppInfo)), ("enabledLayerCount", c.c_uint32),
                    ("ppEnabledLayerNames", c.c_void_p), ("enabledExtensionCount", c.c_uint32),
                    ("ppEnabledExtensionNames", c.c_void_p)]

    class Props(c.Structure):  # VkPhysicalDeviceProperties (824 bytes en x64)
        _fields_ = [("apiVersion", c.c_uint32), ("driverVersion", c.c_uint32), ("vendorID", c.c_uint32),
                    ("deviceID", c.c_uint32), ("deviceType", c.c_int32), ("deviceName", c.c_char * 256),
                    ("pipelineCacheUUID", c.c_uint8 * 16), ("limits", c.c_uint64 * 63),
                    ("sparseProperties", c.c_uint32 * 5)]

    class Props2(c.Structure):
        _fields_ = [("sType", c.c_int32), ("pNext", c.c_void_p), ("properties", Props), ("_holgura", c.c_uint8 * 256)]

    class IdProps(c.Structure):
        _fields_ = [("sType", c.c_int32), ("pNext", c.c_void_p), ("deviceUUID", c.c_uint8 * 16),
                    ("driverUUID", c.c_uint8 * 16), ("deviceLUID", c.c_uint8 * 8),
                    ("deviceNodeMask", c.c_uint32), ("deviceLUIDValid", c.c_uint32)]

    class DriverProps(c.Structure):
        _fields_ = [("sType", c.c_int32), ("pNext", c.c_void_p), ("driverID", c.c_uint32),
                    ("driverName", c.c_char * 256), ("driverInfo", c.c_char * 256),
                    ("conformanceVersion", c.c_uint8 * 4)]

    class Features2(c.Structure):
        _fields_ = [("sType", c.c_int32), ("pNext", c.c_void_p), ("features", c.c_uint32 * 55)]

    class Vk11Features(c.Structure):
        _fields_ = [("sType", c.c_int32), ("pNext", c.c_void_p), ("flags", c.c_uint32 * 12)]

    class MemType(c.Structure):
        _fields_ = [("propertyFlags", c.c_uint32), ("heapIndex", c.c_uint32)]

    class MemHeap(c.Structure):
        _fields_ = [("size", c.c_uint64), ("flags", c.c_uint32)]

    class MemProps(c.Structure):
        _fields_ = [("memoryTypeCount", c.c_uint32), ("memoryTypes", MemType * 32),
                    ("memoryHeapCount", c.c_uint32), ("memoryHeaps", MemHeap * 16)]

    api = c.c_uint32(1 << 22)  # 1.0 si el cargador es tan viejo que no tiene la funcion
    if hasattr(vk, "vkEnumerateInstanceVersion"):
        vk.vkEnumerateInstanceVersion(c.byref(api))
    if api.value < (1 << 22 | 2 << 12):
        raise OSError("el cargador de Vulkan es anterior a 1.2 (ggml-vulkan exige 1.2)")
    app = AppInfo(sType=0, pApplicationName=b"recorder", pEngineName=b"recorder", apiVersion=api.value)
    info = InstanceInfo(sType=1, pApplicationInfo=c.pointer(app))
    inst = c.c_void_p()
    res = vk.vkCreateInstance(c.byref(info), None, c.byref(inst))
    if res != 0:
        raise OSError(f"vkCreateInstance devolvio {res}")
    try:
        n = c.c_uint32(0)
        vk.vkEnumeratePhysicalDevices(inst, c.byref(n), None)
        handles = (c.c_void_p * n.value)()
        vk.vkEnumeratePhysicalDevices(inst, c.byref(n), handles)
        out = []
        for h in handles[: n.value]:
            ids, drv = IdProps(sType=1000071004), DriverProps(sType=1000196000)
            ids.pNext = c.cast(c.pointer(drv), c.c_void_p)
            props = Props2(sType=1000059001, pNext=c.cast(c.pointer(ids), c.c_void_p))
            vk.vkGetPhysicalDeviceProperties2(c.c_void_p(h), c.byref(props))
            pr = props.properties
            soportada = False
            if pr.apiVersion >= (1 << 22 | 2 << 12):  # Vulkan11Features es de 1.2
                f11 = Vk11Features(sType=49)
                feats = Features2(sType=1000059000, pNext=c.cast(c.pointer(f11), c.c_void_p))
                vk.vkGetPhysicalDeviceFeatures2(c.c_void_p(h), c.byref(feats))
                soportada = bool(f11.flags[0])  # storageBuffer16BitAccess, lo que pide ggml
            mem = MemProps()
            vk.vkGetPhysicalDeviceMemoryProperties(c.c_void_p(h), c.byref(mem))
            local = [mem.memoryHeaps[k].size for k in range(min(mem.memoryHeapCount, 16)) if mem.memoryHeaps[k].flags & 1]
            luid = bytes(ids.deviceLUID)
            out.append({
                "name": pr.deviceName.decode("utf-8", "replace"),
                "vendor_id": pr.vendorID,
                "device_id": pr.deviceID,
                "type": pr.deviceType,
                "api": pr.apiVersion,
                "driver_id": drv.driverID,
                "uuid": bytes(ids.deviceUUID).hex(),
                "luid": _luid(*struct.unpack("<Ii", luid)),
                "luid_valid": bool(ids.deviceLUIDValid),
                "device_local_mb": max(local, default=0) // 2**20,
                "supported": soportada,
            })
        return out
    finally:
        vk.vkDestroyInstance(inst, None)


def vulkan_probe_command() -> List[str]:
    """La linea de comandos de la consulta de Vulkan en otro proceso.

    Desde el codigo, este archivo como script: basta la biblioteca estandar, con el interprete base
    (no el lanzador del venv) y -I, que no mira la carpeta actual ni variables de entorno de Python.
    Instalado, `__file__` apunta dentro del archivo de PyInstaller y no hay interprete: se relanza
    el ejecutable con `--vulkan` (el de consola, daily.exe, si esta junto al que corre; ver
    rutas.ejecutable_consola), y recorder.py lo atiende con `sonda_vulkan()` sin cargar nada mas.
    """
    if getattr(sys, "frozen", False):
        from ..rutas import ejecutable_consola

        return [ejecutable_consola(), "--vulkan"]
    python = getattr(sys, "_base_executable", "") or sys.executable
    return [python, "-I", os.path.abspath(__file__), "--vulkan"]


def _run_vulkan_probe(timeout: float = VULKAN_PROBE_TIMEOUT_SEC) -> List[dict]:
    """Ejecuta la consulta de Vulkan (`vulkan_probe_command`) en otro proceso y lee su JSON."""
    r = subprocess.run(
        vulkan_probe_command(),
        capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    for linea in reversed(r.stdout.splitlines()):  # una capa de terceros puede escribir antes
        if linea.startswith(VULKAN_MARKER):
            data = json.loads(linea[len(VULKAN_MARKER):])
            if "error" in data:
                raise OSError(data["error"])
            return data["devices"]
    raise OSError(f"la consulta de Vulkan termino con codigo {r.returncode} sin respuesta: {r.stderr.strip()[-200:]}")


# ---------------------------------------------------------------------------------- union
def merge_gpus(dxgi: Sequence[GpuInfo], vulkan: Sequence[GpuInfo]) -> List[GpuInfo]:
    """La lista de DXGI completada con lo que sabe Vulkan (tipo e indice para -dev).

    Se emparejan por LUID, que es el mismo en las dos APIs; si Vulkan no da LUID, por
    fabricante y modelo. El tipo de Vulkan manda sobre la heuristica de DXGI. Lo que solo ve
    Vulkan (DXGI fallo) se anade al final.
    """
    usadas = set()
    out = []
    for g in dxgi:
        par = next((v for v in vulkan if v.luid and v.luid == g.luid), None) or next(
            (v for v in vulkan if v.vulkan_index not in usadas and (v.vendor_id, v.device_id) == (g.vendor_id, g.device_id)),
            None,
        )
        if par is None:
            out.append(g)
            continue
        usadas.add(par.vulkan_index)
        out.append(dataclasses.replace(
            g, integrated=par.integrated, vulkan_index=par.vulkan_index, vram_mb=g.vram_mb or par.vram_mb,
        ))
    out += [v for v in vulkan if v.vulkan_index not in usadas]
    return out


def detect_hardware(vulkan: bool = True, cuda: bool = True) -> HardwareProfile:
    """Perfil de este equipo en ~1 s. No lanza: lo que falla queda neutro y en `detection_errors`."""
    p = HardwareProfile()
    errors = p.detection_errors

    def intentar(que: str, fn) -> None:
        try:
            fn()
        except Exception as e:  # un bloque que falla no se lleva por delante a los demas
            errors.append(f"{que}: {e.__class__.__name__}: {e}")

    intentar("nombre de la CPU", lambda: setattr(p, "cpu_name", _cpu_name()))
    intentar("nucleos (GetLogicalProcessorInformationEx)", lambda: _fill_cpu(p))
    if not p.logical_cores:
        p.logical_cores = os.cpu_count() or 0
    intentar("AVX", lambda: _fill_isa(p, errors))
    intentar("RAM (GlobalMemoryStatusEx)", lambda: _fill_ram(p))
    intentar("energia (GetSystemPowerStatus)", lambda: _fill_power(p, errors))
    dxgi: List[GpuInfo] = []

    def _dxgi():
        dxgi.extend(dedupe_dxgi_adapters(_dxgi_adapters()))

    intentar("GPUs (DXGI)", _dxgi)
    if vulkan:
        intentar("GPUs (Vulkan)", lambda: p.vulkan_devices.extend(vulkan_gpus_from_raw(_run_vulkan_probe())))
    p.gpus = merge_gpus(dxgi, p.vulkan_devices)
    # ctranslate2 tarda ~300 ms en importarse: solo si hay una NVIDIA o no se sabe que GPUs hay.
    if cuda and (not p.gpus or any(g.vendor_id == VENDOR_NVIDIA for g in p.gpus)):
        def _cuda():
            from .schema import detect_cuda_device_count

            p.cuda_devices = detect_cuda_device_count()

        intentar("CUDA", _cuda)
    return p


# ---------------------------------------------------------------------------------- cache
_cache_lock = threading.Lock()
_cache: Optional[HardwareProfile] = None


def cached_hardware() -> HardwareProfile:
    """El perfil de este proceso: se detecta la primera vez y se reutiliza.

    El hardware no cambia con Recorder abierto (salvo enchufar el cargador: `on_battery` es
    el del arranque). El cerrojo hace que dos hilos que lo piden a la vez esperen a una sola
    deteccion en vez de repetirla.
    """
    global _cache
    with _cache_lock:
        if _cache is None:
            _cache = detect_hardware()
        return _cache


def peek_hardware() -> Optional[HardwareProfile]:
    """El perfil si ya se detecto; None si todavia no (no espera)."""
    return _cache


def cached_vulkan_devices() -> List[GpuInfo]:
    return cached_hardware().vulkan_devices


# ---------------------------------------------------------------------------------- texto
def gb(mb: int) -> str:
    return f"{mb / 1024:.0f} GB" if mb >= 1024 else f"{mb} MB"


def short_cpu_name(name: str) -> str:
    """"Intel(R) Core(TM) i5-9500 CPU @ 3.00GHz" -> "Intel Core i5-9500"."""
    name = re.sub(r"\((R|TM)\)|®|™", "", name, flags=re.I)
    name = re.split(r"\s+(CPU\s+)?@|\s+with\s+|\s+\d+-Core\s+Processor", name)[0]
    return " ".join(name.replace(" Processor", "").split()) or "CPU desconocida"



def describe_gpu(g: GpuInfo) -> str:
    tipo = "integrada" if g.integrated else gb(g.vram_mb) if g.vram_mb else "dedicada"
    return f"{g.name} ({tipo})"


def describe_hardware(p: HardwareProfile) -> str:
    """Una linea legible: "Intel Core i5-9500 · 6 núcleos · AVX2 · 16 GB de RAM · sobremesa · GPU: ..."."""
    nucleos = f"{p.physical_cores} núcleos" if p.physical_cores else f"{p.logical_cores} hilos"
    if p.hybrid:
        nucleos += f" ({p.p_cores}P+{p.e_cores}E)"
    if p.physical_cores and p.logical_cores != p.physical_cores:
        nucleos += f", {p.logical_cores} hilos"
    partes = [short_cpu_name(p.cpu_name), nucleos, "AVX-512" if p.avx512 else "AVX2" if p.avx2 else "sin AVX2"]
    if p.ram_total_mb:
        partes.append(f"{p.ram_total_mb / 1024:.0f} GB de RAM")
    if p.desktop is not None:
        partes.append("sobremesa" if p.desktop else "portátil")
    if p.on_battery:
        partes.append("con batería")
    partes.append("GPU: " + (", ".join(describe_gpu(g) for g in p.gpus) if p.gpus else "ninguna detectada"))
    return " · ".join(partes)


def sonda_vulkan() -> int:
    """El proceso de la consulta (`--vulkan`): enumera Vulkan AQUI e imprime una linea
    `VULKAN_JSON {...}` que lee `_run_vulkan_probe`. Devuelve el codigo de salida (siempre 0: un
    fallo va en el JSON). Sin stdout (un ejecutable de ventana sin tuberias) print no hace nada."""
    try:
        linea = VULKAN_MARKER + json.dumps({"devices": _vulkan_raw_devices()})
    except Exception as e:
        linea = VULKAN_MARKER + json.dumps({"error": f"{e.__class__.__name__}: {e}"})
    print(linea, flush=True)
    return 0


if __name__ == "__main__" and "--vulkan" in sys.argv:
    sys.exit(sonda_vulkan())
