"""Eco del vocabulario (initial_prompt): Whisper, ante silencio o ruido, "transcribe" su propio contexto.

Visto en una daily real de 2 h 39 min: 15 renglones con el rótulo "Términos" que nadie dijo
("Términos.", "Términos, ¿sabes?" ×3), "Nombres del equipo." y listas de nombres del vocabulario,
concentrados en un tramo de silencio; y el rótulo pegado al inicio de frases reales
("Términos crearon tres endpoints nuevos"). Ver docs/auditoria-daily-2026-09-25.md.

Dos reglas, puras:

1. El rótulo ("Términos", "Nombres del equipo", y su cruce "Términos del equipo") se quita al
   inicio de la frase o tras un punto. Nunca si sigue "de", "y" o "e": "Términos de pago" y
   "Términos y condiciones" son frases legítimas. Si al quitarlo solo queda relleno
   ("¿sabes? ¿sabes?", "Ok."), el renglón entero era eco.
2. Un renglón que es una lista de elementos del vocabulario se descarta: todos conocidos si son
   dos ("Luis, Marta."), tres cuartas partes si son tres o más (Whisper recita la lista con
   alguna variación, y el primer término suele ir pegado a la frase inicial del vocabulario), o
   uno solo si tiene cuatro palabras o más (la frase inicial entera). Un término suelto
   ("API Gateway.", "Programa de embarques.") se conserva: puede ser una respuesta real.
"""
import re

from .normalizer import normalize

# ponytail: rótulos fijos, los de los vocabularios con rótulos vistos hasta hoy. La cura de
# fondo es escribir el vocabulario sin rótulos (config.example.json); si aparece otro, va aquí.
_LABEL = re.compile(
    r"(?:^|(?<=[.?!]\s))¿?"
    r"(?:(?:nombres|t[eé]rminos) del equipo|t[eé]rminos(?!\s+(?:de|y|e)\b))"
    r"[.,:;?!]*(?:\s+|$)",
    re.I,
)
_ITEM_SPLIT = re.compile(r"[,.;:¿?¡!]|\s+[ye]\s+")
LIST_KNOWN_RATIO = 0.75


def _items(text: str) -> list:
    """Elementos de una lista escrita: separa por puntuación y por la conjunción "y"/"e"."""
    return [i.strip() for i in _ITEM_SPLIT.split(normalize(text)) if i.strip()]


def strip_prompt_echo(text: str, vocab: str = "") -> str:
    """Texto sin el eco del vocabulario; "" si el renglón entero era eco."""
    original = text.strip()
    text = _LABEL.sub("", original).strip()
    items = _items(text)
    if text != original:
        if len({w for i in items for w in i.split()}) < 2:
            return ""  # quitado el rótulo, solo queda relleno
        text = text[:1].upper() + text[1:]
    known = set(_items(vocab))
    n, k = len(items), sum(i in known for i in items)
    if (n == 2 and k == 2) or (n >= 3 and k >= LIST_KNOWN_RATIO * n) or (n == 1 and k and len(items[0].split()) >= 4):
        return ""
    return text
