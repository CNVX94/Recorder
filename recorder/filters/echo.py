"""Eco del vocabulario (initial_prompt): Whisper, ante silencio o ruido, "transcribe" su propio contexto.

Visto en una daily real de 2 h 39 min: 15 renglones con el rótulo "Términos" que nadie dijo
("Términos.", "Términos, ¿sabes?" ×3), "Nombres del equipo." y listas de nombres del vocabulario,
concentrados en un tramo de silencio; y el rótulo pegado al inicio de frases reales
("Términos crearon tres endpoints nuevos"). Ver docs/auditoria-daily-2026-09-25.md.

Reglas, puras, y todas condicionadas al vocabulario con que se grabó (sin vocabulario no hay eco
que quitar y el texto se devuelve intacto):

1. Un rótulo ("Términos", "Nombres del equipo", y su cruce "Términos del equipo") se quita al
   inicio de la frase o tras un punto **solo si ese rótulo aparece en el vocabulario**. Nunca si lo
   que sigue lo convierte en una frase normal ("Términos de pago", "Términos del contrato",
   "Términos y condiciones"). Si al quitarlo solo queda relleno ("¿sabes? ¿sabes?", "Ok."), el
   renglón entero era eco.
2. Un renglón entero se descarta solo cuando es, con claridad, el vocabulario recitado y no una
   respuesta: una lista larga (cinco elementos o más) en la que tres cuartas partes son términos
   del vocabulario; un tramo literal del vocabulario, en su mismo orden y separado por comas o
   puntos sin ninguna conjunción ("Luis, Marta." con «Ana, Luis, Marta» en el vocab; "Luis. Luis.");
   o la frase inicial entera del vocabulario (cuatro palabras o más). Lo que una persona diría se
   conserva: un término suelto ("API Core.", "Puerto 7100."), dos o más unidos con "y"/"e"
   ("Ana y Luis.", "QA e IIS.", "Puerto 7100 y 7200.") o con algo que no está en el vocabulario
   ("Ana, Luis, Marta y Pedro.").
"""
import functools
import re
from typing import List, Optional, Sequence, Tuple

from .normalizer import normalize

# Rótulos vistos en vocabularios con rótulos; se activan solo los que están en el vocabulario.
LABELS = ("nombres del equipo", "términos del equipo", "términos")
# Lo que, tras el rótulo, lo hace parte de una frase normal: no se toca.
_CONTINUATION = r"(?!\s+(?:de|del|y|e|o|u|a|al|en|con|para|por|que|sin|sobre|entre|como|es|son)\b)"
_ITEM_SPLIT = re.compile(r"[,.;:¿?¡!]|\s+[ye]\s+")
_CONJUNCTION = re.compile(r"\s[ye]\s")
LIST_MIN_ITEMS = 5  # una lista recitada tiene al menos estos elementos
LIST_KNOWN_RATIO = 0.75  # ... y esta parte de ellos está en el vocabulario
SENTENCE_MIN_WORDS = 4  # un solo elemento del vocabulario es eco si es una frase entera de este largo

_ACCENTS = {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}


def _flexible(label: str) -> str:
    """Regex de un rótulo que admite vocales con o sin tilde y cualquier blanco entre palabras."""
    out = []
    for ch in normalize(label):
        if ch == " ":
            out.append(r"\s+")
        elif ch in _ACCENTS:
            out.append(f"[{ch}{_ACCENTS[ch]}]")
        else:
            out.append(re.escape(ch))
    return "".join(out)


def labels_in(vocab: str) -> Tuple[str, ...]:
    """Los rótulos de LABELS que hay que quitar con este vocabulario: los que aparecen en él (y el
    cruce "términos del equipo" cuando están los dos)."""
    nv = normalize(vocab or "")
    found = [l for l in LABELS if normalize(l) in nv]
    if "términos" in found and "nombres del equipo" in found and "términos del equipo" not in found:
        found.append("términos del equipo")
    return tuple(sorted(found, key=len, reverse=True))  # el más largo primero: "términos del equipo" antes que "términos"


@functools.lru_cache(maxsize=32)
def _label_pattern(labels: Tuple[str, ...]) -> Optional["re.Pattern"]:
    if not labels:
        return None
    alternation = "|".join(_flexible(l) for l in labels)
    return re.compile(
        r"(?:^|(?<=[.?!]\s))¿?(?:" + alternation + r")" + _CONTINUATION + r"[.,:;?!]*(?:\s+|$)",
        re.I,
    )


def _items(text: str) -> List[str]:
    """Elementos de una lista escrita: separa por puntuación y por la conjunción "y"/"e"."""
    return [i.strip() for i in _ITEM_SPLIT.split(normalize(text)) if i.strip()]


def _contiguous(items: Sequence[str], sequence: Sequence[str]) -> bool:
    """Si `items` aparece tal cual, seguido y en el mismo orden, dentro de `sequence`."""
    n = len(items)
    return any(list(sequence[i:i + n]) == list(items) for i in range(len(sequence) - n + 1))


def strip_prompt_echo(text: str, vocab: str = "") -> str:
    """Texto sin el eco del vocabulario `vocab`; "" si el renglón entero era eco. Sin vocabulario
    no se toca nada."""
    original = text.strip()
    if not (vocab or "").strip():
        return original
    pattern = _label_pattern(labels_in(vocab))
    text = pattern.sub("", original).strip() if pattern else original
    items = _items(text)
    if text != original:
        if len({w for i in items for w in i.split()}) < 2:
            return ""  # quitado el rótulo, solo queda relleno
        text = text[:1].upper() + text[1:]
    vocab_items = _items(vocab)
    known = set(vocab_items)
    n, k = len(items), sum(i in known for i in items)
    if n >= LIST_MIN_ITEMS and k >= LIST_KNOWN_RATIO * n:
        return ""  # la lista del vocabulario recitada, con alguna variación
    if n == 1 and k and len(items[0].split()) >= SENTENCE_MIN_WORDS:
        return ""  # la frase inicial del vocabulario, entera
    if n >= 2 and k == n and not _CONJUNCTION.search(normalize(text)):
        if len(set(items)) == 1 or _contiguous(items, vocab_items):
            return ""  # "Luis. Luis." o un tramo literal del vocabulario, sin "y": nadie habla así
    return text
