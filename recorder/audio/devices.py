from typing import Any, Dict, List, Optional
import pyaudiowpatch as pa


def wasapi_devices(p: pa.PyAudio, kind: str) -> List[str]:
    """Nombres WASAPI: 'out' = salidas (captura loopback), 'mic' = entradas físicas reales."""
    api = p.get_host_api_info_by_type(pa.paWASAPI)["index"]
    key = "maxOutputChannels" if kind == "out" else "maxInputChannels"
    return [
        d["name"]
        for d in p.get_device_info_generator()
        if d["hostApi"] == api and d[key] > 0 and not d.get("isLoopbackDevice")
    ]


def resolve_wasapi_device(
    p: pa.PyAudio, kind: str, preferred_name: Optional[str] = None
) -> Dict[str, Any]:
    """Encuentra el dispositivo WASAPI adecuado (físico o loopback)."""
    api = p.get_host_api_info_by_type(pa.paWASAPI)
    want = (preferred_name or "").strip()

    if kind == "out":
        default_dev_info = p.get_device_info_by_index(api["defaultOutputDevice"])
        name = want or default_dev_info["name"]
        dev = next(
            (d for d in p.get_loopback_device_info_generator() if name in d["name"]),
            None,
        )
    elif want:
        dev = next(
            (
                d for d in p.get_device_info_generator()
                if d["hostApi"] == api["index"] and d["name"] == want
            ),
            None,
        )
    else:
        dev = p.get_device_info_by_index(api["defaultInputDevice"])

    if dev is None:
        raise ValueError(f"No se encontró el dispositivo de audio '{want or kind}'")
    return dev
