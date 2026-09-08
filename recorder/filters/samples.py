"""Generador de frases de prueba para el sandbox, armadas con el glosario del propio usuario.

Sirve para calibrar sin tener que inventar ejemplos a mano: cada frase ejercita uno de los
caminos del pipeline (limpia, palabra clave, corrección de léxico o alucinación descartada).
"""

import random
import re
from typing import Dict, List, Optional, Sequence

from .normalizer import normalize

# Frases de relleno cuando el usuario aún no ha escrito vocabulario propio.
FALLBACK_TERMS = ["el módulo de reportes", "la base de datos", "el despliegue"]

# ponytail: heurística simple para separar términos de la prosa del prompt.
# Un fragmento es "término" si es corto; si trae más de MAX_WORDS palabras es narrativa.
MAX_WORDS = 4
_STOP = {"terminos", "daily", "nombres", "vocabulario", "contexto", "palabras"}

_TPL_LIMPIA = [
    "Ayer terminé la parte de {t} y hoy sigo con {t2}.",
    "{t} ya quedó desplegado, falta probar {t2}.",
    "Revisé {t} con el equipo y no encontramos nada raro.",
    "Estuvimos viendo {t} y {t2} toda la mañana.",
    "Del lado de {t} no hay novedades, sigo con {t2}.",
]

_TPL_CLAVE = [
    "Tengo un {k} con {t}, necesito apoyo para resolverlo.",
    "Queda como {k} revisar {t} antes de liberar.",
    "Marco esto como {k}: {t} no está respondiendo.",
    "Ojo con {t}, ahí tenemos un {k} desde ayer.",
]

_TPL_CORRECCION = [
    "Desplegamos {t} en {f} y quedó arriba.",
    "Revisa {f} porque {t} no está respondiendo.",
    "Hay que mover {t} al {f} de una vez.",
    "En {f} ya probamos {t} y funcionó.",
]


def extract_terms(vocab: str) -> List[str]:
    """Saca los términos cortos del prompt de contexto y descarta la prosa que los rodea."""
    terms = []
    for frag in re.split(r"[,.;:]", vocab or ""):
        frag = frag.strip()
        if len(frag) < 2 or len(frag.split()) > MAX_WORDS:
            continue
        if normalize(frag) in _STOP:
            continue
        terms.append(frag)
    return terms


def sample_kinds(fixes: Dict[str, str], ignore: Sequence[str], keywords: Sequence[str]) -> List[str]:
    """Caminos del pipeline que se pueden ejercitar con lo que hay configurado ahora."""
    kinds = ["limpia"]
    if keywords:
        kinds.append("clave")
    if fixes:
        kinds.append("correccion")
    if ignore:
        kinds.append("alucinacion")
    return kinds


def random_sample(
    vocab: str,
    fixes: Dict[str, str],
    ignore: Sequence[str],
    keywords: Sequence[str],
    rng: Optional[random.Random] = None,
    kind: Optional[str] = None,
) -> str:
    """Arma una frase de prueba con el glosario del usuario.

    `kind` fuerza un camino concreto; si se omite se elige al azar entre los disponibles.
    """
    rng = rng or random
    terms = extract_terms(vocab) or FALLBACK_TERMS
    if len(terms) >= 2:
        t, t2 = rng.sample(terms, 2)
    else:
        t = t2 = terms[0]

    kind = kind or rng.choice(sample_kinds(fixes, ignore, keywords))

    if kind == "clave":
        return rng.choice(_TPL_CLAVE).format(k=rng.choice(list(keywords)), t=t)
    if kind == "correccion":
        return rng.choice(_TPL_CORRECCION).format(t=t, f=rng.choice(list(fixes)))
    if kind == "alucinacion":
        base = rng.choice(_TPL_LIMPIA).format(t=t, t2=t2)
        return f"{base} {rng.choice(list(ignore)).capitalize()}."
    return rng.choice(_TPL_LIMPIA).format(t=t, t2=t2)
