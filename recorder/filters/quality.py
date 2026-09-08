import zlib
from typing import Any


def calculate_compression_ratio(text: str) -> float:
    """Calcula el ratio de compresión zlib. Cadenas con bucles repetitivos tienen ratios anormalmente altos."""
    if not text:
        return 0.0
    raw_bytes = text.encode("utf-8")
    if not raw_bytes:
        return 0.0
    compressed = zlib.compress(raw_bytes)
    return len(raw_bytes) / len(compressed)


def is_segment_valid(
    seg: Any,
    no_speech_thresh: float = 0.6,
    logprob_thresh: float = -1.0,
    compression_ratio_thresh: float = 2.4,
) -> bool:
    """Valida si un segmento de Whisper supera los umbrales de voz, confianza y no-repetición."""
    # Descartar si probabilidad de no-voz excede umbral
    no_speech = getattr(seg, "no_speech_prob", 0.0)
    if no_speech >= no_speech_thresh:
        return False

    # Descartar si la confianza promedio es demasiado baja (alta incertidumbre / balbuceo)
    avg_logprob = getattr(seg, "avg_logprob", 0.0)
    if avg_logprob <= logprob_thresh:
        return False

    # Descartar si el segmento tiene bucles de repetición (ratio de compresión)
    ratio = getattr(seg, "compression_ratio", None)
    if ratio is None:
        text = getattr(seg, "text", "")
        ratio = calculate_compression_ratio(text)
    if ratio > compression_ratio_thresh:
        return False

    return True
