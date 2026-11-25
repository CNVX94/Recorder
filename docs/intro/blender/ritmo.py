"""El ritmo del revelado del logotipo: lo comparten la escena de Blender (escena_logotipo.py) y
el preparador de assets (preparar_assets.py). Sin dependencias.

Los tramos van en fotogramas (primero, último), contando desde 1.
"""

FPS = 24
FOTOGRAMAS = 36  # 1,5 s
LADO_PX = 480

GIRO = (1, 24)  # el logotipo gira hasta quedar de frente
GIRO_INICIAL = -78.0  # grados alrededor del eje vertical
CABECEO_INICIAL = 14.0  # grados de inclinación hacia la cámara
ESCALA_INICIAL = 0.72
MICROFONO = (5, 22)  # el micrófono sale de la baldosa
PUNTO = (22, 31)  # se enciende el punto de «grabando»

REBOTE = 1.3  # cuánto se pasa ease_out_rebote antes de asentarse (≈ 6 %)


def avance(fotograma: int, primero: int, ultimo: int) -> float:
    """Cuánto lleva recorrido un tramo en `fotograma`, de 0 a 1."""
    return min(1.0, max(0.0, (fotograma - primero) / (ultimo - primero)))


def ease_out(t: float) -> float:
    """La misma cúbica que recorder/ui/animacion.py: arranca rápida y frena al final."""
    return 1 - (1 - t) ** 3


def ease_out_rebote(t: float) -> float:
    """Ease-out que se pasa un poco del final y vuelve (ease-out-back)."""
    return 1 + (REBOTE + 1) * (t - 1) ** 3 + REBOTE * (t - 1) ** 2
