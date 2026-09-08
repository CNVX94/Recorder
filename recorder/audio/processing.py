import numpy as np


def rms(pcm: np.ndarray) -> float:
    """Calcula el valor eficaz (RMS) de un buffer PCM."""
    if len(pcm) == 0:
        return 0.0
    return float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)))


def bars(v: float, n: int = 8) -> str:
    """Convierte un valor RMS int16 a un medidor de n bloques en escala logarítmica (-60 dB a 0 dB)."""
    if v < 1:
        k = 0
    else:
        db = 20 * np.log10(v / 32768.0)
        k = int(np.clip((db + 60.0) / 60.0 * n, 0, n))
    return "█" * k + "░" * (n - k)


def to_16k(pcm: np.ndarray, rate: int, channels: int) -> np.ndarray:
    """Convierte audio int16 intercalado a float32 mono a 16 kHz (formato requerido por Whisper)."""
    if len(pcm) == 0:
        return np.zeros(0, dtype=np.float32)
    a = pcm.astype(np.float32).reshape(-1, channels).mean(1) / 32768.0
    n = int(len(a) * 16000 / rate)
    return np.interp(np.linspace(0, len(a), n, endpoint=False), np.arange(len(a)), a).astype(np.float32)
