import re
from typing import List, Sequence
from .normalizer import normalize


def find_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    """Busca palabras clave en el texto aplicando normalización de acentos y límites de palabra."""
    if not text or not keywords:
        return []
    t = normalize(text)
    return [
        k for k in keywords
        if k and re.search(rf"\b{re.escape(normalize(k))}\b", t)
    ]
