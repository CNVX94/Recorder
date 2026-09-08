import unicodedata


def normalize(s: str) -> str:
    """Normaliza un texto eliminando acentos y convirtiéndolo a minúsculas para búsquedas flexibles."""
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower())
        if not unicodedata.combining(c)
    )
