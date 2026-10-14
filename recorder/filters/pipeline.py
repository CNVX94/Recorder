from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from .blacklist import contains_blacklisted_phrase
from .echo import strip_prompt_echo
from .keywords import find_keywords, first_keyword_pos
from .lexicon import fix
from .normalizer import normalize
from .quality import is_segment_valid


def keep_segments(
    segs: Iterable[Any],
    ignore: Sequence[str],
    no_speech_thresh: float = 0.6,
    logprob_thresh: float = -1.0,
    compression_ratio_thresh: float = 2.4,
    vocab: str = "",
) -> List[Tuple[Any, str]]:
    """(segmento, texto) de los que sobreviven: sin los dudosos (sin voz, baja confianza o bucles),
    sin las frases prohibidas y sin el eco del vocabulario."""
    keep: List[Tuple[Any, str]] = []
    for s in segs:
        if not is_segment_valid(s, no_speech_thresh, logprob_thresh, compression_ratio_thresh):
            continue
        text = getattr(s, "text", "").strip()
        if not text or contains_blacklisted_phrase(text, ignore):
            continue
        text = strip_prompt_echo(text, vocab)
        if text:
            keep.append((s, text))
    return keep


def clean_segments(
    segs: Iterable[Any],
    ignore: Sequence[str],
    no_speech_thresh: float = 0.6,
    logprob_thresh: float = -1.0,
    compression_ratio_thresh: float = 2.4,
    vocab: str = "",
) -> str:
    """Une segmentos descartando los dudosos (sin voz, baja confianza o bucles) y las frases prohibidas."""
    kept = keep_segments(segs, ignore, no_speech_thresh, logprob_thresh, compression_ratio_thresh, vocab)
    return " ".join(t for _, t in kept).strip()


def hit_offset(kept: Sequence[Tuple[Any, str]], fixes: Dict[str, str], keywords: Sequence[str]) -> Optional[float]:
    """Segundos desde el inicio del audio en que se dijo la primera palabra clave, o None.

    Un segmento de Whisper es una frase y puede durar más de 10 s, así que `start` solo no basta:
    se interpola por la posición del carácter, con el ritmo de habla dentro de la frase como
    aproximadamente uniforme (docs/captura-diferida.md, paso 1).
    """
    for s, text in kept:
        t = fix(text, fixes)
        pos = first_keyword_pos(t, keywords)
        if pos is not None:
            start = float(getattr(s, "start", 0.0) or 0.0)
            end = float(getattr(s, "end", start) or start)
            return start + pos / max(1, len(normalize(t))) * max(0.0, end - start)
    return None


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
        vocab: str = "",
    ):
        self.keywords = list(keywords)
        self.ignore = list(ignore)
        self.fixes = dict(fixes)
        self.no_speech_thresh = no_speech_thresh
        self.logprob_thresh = logprob_thresh
        self.compression_ratio_thresh = compression_ratio_thresh
        self.vocab = vocab or ""

    def process(self, segs: Iterable[Any]) -> Tuple[str, List[str], Optional[float]]:
        """(texto limpio, palabras clave, segundos desde el inicio del audio hasta la primera clave)."""
        kept = keep_segments(
            segs,
            self.ignore,
            no_speech_thresh=self.no_speech_thresh,
            logprob_thresh=self.logprob_thresh,
            compression_ratio_thresh=self.compression_ratio_thresh,
            vocab=self.vocab,
        )
        raw_text = " ".join(t for _, t in kept).strip()
        if not raw_text:
            return "", [], None

        fixed_text = fix(raw_text, self.fixes)
        hits = find_keywords(fixed_text, self.keywords)
        return fixed_text, hits, hit_offset(kept, self.fixes, self.keywords) if hits else None

    def process_segments(self, segs: Iterable[Any]) -> Tuple[str, List[str]]:
        """Procesa una secuencia de segmentos de Whisper devolviendo el texto limpio y las palabras clave halladas."""
        text, hits, _ = self.process(segs)
        return text, hits

    def test_sample(self, sample_text: str) -> Dict[str, Any]:
        """Prueba una muestra de texto en el sandbox para ver el resultado de filtros y reemplazos."""
        is_ignored = contains_blacklisted_phrase(sample_text, self.ignore)
        echo_free = strip_prompt_echo(sample_text, self.vocab)
        fixed_text = fix(echo_free, self.fixes)
        hits = find_keywords(fixed_text, self.keywords)
        return {
            "original": sample_text,
            "is_ignored": is_ignored,
            "is_echo": not is_ignored and not echo_free,
            "processed": "" if is_ignored else fixed_text,
            "hits": hits,
        }
