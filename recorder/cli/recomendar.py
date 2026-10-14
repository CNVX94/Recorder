"""`daily recomendar`: qué equipo se detecta, qué configuración se recomienda y por qué.

Es lo que hacía `recorder.py --recomendar` (que sigue funcionando y llama aquí). Vive en el
paquete de terminal para que ni `daily` ni el instalador carguen tkinter por pedirlo.
"""
import argparse
from typing import Optional

from rich.console import Console

from ..config.manager import ConfigManager
from .consola import asciify, make_console

NOMBRE = "recomendar"
AYUDA = "qué equipo se detecta y qué configuración se recomienda (--aplicar la guarda)"


def agregar_argumentos(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--aplicar", action="store_true", help="guarda la recomendación en config.json")


def ejecutar(args: argparse.Namespace, consola: Console) -> int:
    return recomendar(args.aplicar, consola)


def recomendar(
    aplicar: bool, consola: Optional[Console] = None, config_manager: Optional[ConfigManager] = None
) -> int:
    """Imprime el equipo detectado y la configuración recomendada; con `aplicar`, la guarda."""
    from ..config.hardware import cached_hardware, describe_hardware
    from ..config.schema import apply_recommendation, describe_recommendation, recommend_config
    from ..engine.whispercpp import vulkan_readiness

    consola = consola or make_console()
    ascii_mode = getattr(consola, "ascii_mode", False)

    def decir(texto: str) -> None:
        # Sin marcado: "[alta]" (la confianza) se tomaría por una etiqueta de estilo
        consola.print(asciify(texto) if ascii_mode else texto, markup=False)

    mgr = config_manager or ConfigManager()
    cfg = mgr.load()
    perfil = cached_hardware()  # en un proceso nuevo detecta; si ya se detectó, no repite
    rec = recommend_config(perfil, *vulkan_readiness(cfg.whispercpp_dir))
    decir(f"Equipo:      {describe_hardware(perfil)}")
    for err in perfil.detection_errors:
        decir(f"             (sin detectar) {err}")
    decir(f"Recomendado: {describe_recommendation(rec)} [{rec.confidence}]")
    decir(f"Motivo:      {rec.reason}")
    if not aplicar:
        return 0
    if mgr.last_error:
        decir(f"No se aplica: {mgr.last_error}")
        return 1
    apply_recommendation(cfg, rec)
    mgr.save(cfg)
    decir(f"Aplicado en {mgr.path}")
    return 0
