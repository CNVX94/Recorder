"""El registro de pantallas: acción del menú → (módulo, clase). Cada pantalla se importa al abrirla, así que
añadir una es crear su módulo en este paquete y una línea aquí (y, si es una entrada nueva del inicio, su fila
en `inicio.EXTRA`)."""
import importlib
from typing import Dict, Optional, Tuple, Type

from .base import Pantalla

PANTALLAS: Dict[str, Tuple[str, str]] = {
    "config": ("opciones", "Opciones"),
    "rendimiento": ("rendimiento", "Rendimiento"),
    "ayuda": ("ayuda", "Ayuda"),
    "calibrar": ("calibrar", "Calibrar"),
    "sintesis": ("reagrupar", "ReagruparNota"),
}


def clase_de(accion: str) -> Optional[Type[Pantalla]]:
    """La clase de la pantalla de `accion`, o None si esa acción no es una pantalla (grabar, un comando…)."""
    if accion not in PANTALLAS:
        return None
    modulo, clase = PANTALLAS[accion]
    return getattr(importlib.import_module(f".{modulo}", __package__), clase)
