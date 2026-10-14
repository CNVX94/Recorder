import re
from typing import List, Optional, Sequence
from .normalizer import normalize

# Muletillas del español de México que no pueden ser palabra clave: disparan en casi cada frase.
# "este" disparó 60 de 212 capturas de una daily de 2 h 39 min (126 apariciones, casi todas
# muletilla). Se ignoran aunque estén en config.json. Ver docs/auditoria-daily-2026-09-25.md.
MULETILLAS = frozenset({"este"})


def _patterns(keywords: Sequence[str]):
    """(palabra clave, regex de palabra completa sin acentos) de las que cuentan."""
    for k in keywords:
        nk = normalize(k).strip()
        if nk and nk not in MULETILLAS:
            yield k, re.compile(rf"\b{re.escape(nk)}\b")


def find_keywords(text: str, keywords: Sequence[str]) -> List[str]:
    """Busca palabras clave en el texto aplicando normalización de acentos y límites de palabra."""
    if not text or not keywords:
        return []
    t = normalize(text)
    return [k for k, p in _patterns(keywords) if p.search(t)]


def first_keyword_pos(text: str, keywords: Sequence[str]) -> Optional[int]:
    """Posición (en caracteres) de la primera palabra clave del texto, o None."""
    t = normalize(text or "")
    pos = [m.start() for _, p in _patterns(keywords) if (m := p.search(t))]
    return min(pos) if pos else None
