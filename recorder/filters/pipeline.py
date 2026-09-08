from typing import Any, Dict, Iterable, List, Sequence, Tuple
from .blacklist import contains_blacklisted_phrase
from .keywords import find_keywords
from .lexicon import fix
from .normalizer import normalize
from .quality import is_segment_valid


def clean_segments(
    segs: Iterable[Any],
    ignore: Sequence[str],
    no_speech_thresh: float = 0.6,
    logprob_thresh: float = -1.0,
    compression_ratio_thresh: float = 2.4,
) -> str:
    """Une segmentos descartando los dudosos (sin voz, baja confianza o bucles) y las frases prohibidas."""
    keep: List[str] = []
    for s in segs:
        if not is_segment_valid(s, no_speech_thresh, logprob_thresh, compression_ratio_thresh):
            continue
        text = getattr(s, "text", "").strip()
        if not text:
            continue
        if contains_blacklisted_phrase(text, ignore):
            continue
        keep.append(text)
    return " ".join(keep).strip()


class TextPipeline:
    """Pipeline de procesamiento y calibración de texto post-inferencia."""

    def __init__(
        self,
        keywords: Sequence[str],
        ignore: Sequence[str],
        fixes: Dict[str, str],
        no_speech_thresh: float = 0.6,
        logprob_thresh: float = -1.0,
        compression_ratio_thresh: float = 2.4,
    ):
        self.keywords = list(keywords)
        self.ignore = list(ignore)
        self.fixes = dict(fixes)
        self.no_speech_thresh = no_speech_thresh
        self.logprob_thresh = logprob_thresh
        self.compression_ratio_thresh = compression_ratio_thresh

    def process_segments(self, segs: Iterable[Any]) -> Tuple[str, List[str]]:
        """Procesa una secuencia de segmentos de Whisper devolviendo el texto limpio y las palabras clave halladas."""
        raw_text = clean_segments(
            segs,
            self.ignore,
            no_speech_thresh=self.no_speech_thresh,
            logprob_thresh=self.logprob_thresh,
            compression_ratio_thresh=self.compression_ratio_thresh,
        )
        if not raw_text:
            return "", []

        fixed_text = fix(raw_text, self.fixes)
        hits = find_keywords(fixed_text, self.keywords)
        return fixed_text, hits

    def test_sample(self, sample_text: str) -> Dict[str, Any]:
        """Prueba una muestra de texto en el sandbox para ver el resultado de filtros y reemplazos."""
        is_ignored = contains_blacklisted_phrase(sample_text, self.ignore)
        fixed_text = fix(sample_text, self.fixes)
        hits = find_keywords(fixed_text, self.keywords)
        return {
            "original": sample_text,
            "is_ignored": is_ignored,
            "processed": "" if is_ignored else fixed_text,
            "hits": hits,
        }
