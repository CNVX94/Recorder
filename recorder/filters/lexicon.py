import re
from typing import Dict


def fix(text: str, fixes: Dict[str, str]) -> str:
    """Correcciones personales: reemplaza palabra completa, sin distinguir mayúsculas."""
    if not text or not fixes:
        return text
    for wrong, right in fixes.items():
        if wrong:
            text = re.sub(rf"\b{re.escape(wrong)}\b", right, text, flags=re.I)
    return text


def parse_fixes(s: str) -> Dict[str, str]:
    """Convierte una cadena como 'cuba=QA; ayayas=IIS' en un diccionario {'cuba': 'QA', 'ayayas': 'IIS'}."""
    if not s:
        return {}
    pairs = (p.split("=", 1) for p in s.split(";") if "=" in p)
    return {k.strip().lower(): v.strip() for k, v in pairs if k.strip()}


def format_fixes(fixes: Dict[str, str]) -> str:
    """Convierte un diccionario de correcciones en formato 'cuba=QA; ayayas=IIS'."""
    if not fixes:
        return ""
    return "; ".join(f"{k}={v}" for k, v in fixes.items())
