from typing import Iterable
from .normalizer import normalize


def contains_blacklisted_phrase(text: str, blacklist: Iterable[str]) -> bool:
    """Comprueba si el texto contiene alguna de las frases alucinativas prohibidas."""
    norm_text = normalize(text)
    for phrase in blacklist:
        p = normalize(phrase.strip())
        if p and p in norm_text:
            return True
    return False


def filter_blacklisted_segments(texts: Iterable[str], blacklist: Iterable[str]) -> list:
    """Filtra una lista de cadenas descartando aquellas que contengan frases de la lista negra."""
    clean_blacklist = [normalize(h) for h in blacklist if h.strip()]
    return [
        t for t in texts
        if t and not any(h in normalize(t) for h in clean_blacklist)
    ]
