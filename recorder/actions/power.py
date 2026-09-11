"""Retener el equipo despierto mientras Recorder tiene trabajo (Windows).

Solo evita la suspensión por inactividad. La acción de cerrar la tapa es una directiva de
energía de Windows y ningún proceso de usuario la anula: ver README, sección de auriculares
y suspensión.
"""
import ctypes

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001
AWAKE_GRACE_SEC = 15 * 60


def should_stay_awake(now: float, last_audio_at: float, pending: int, busy: bool, paused: bool) -> bool:
    """Política pura: retener el equipo si hay trabajo (cola o fragmento en curso), o si se oyó
    audio hace menos de AWAKE_GRACE_SEC y no está en pausa.

    Se suelta tras ese silencio para que un Recorder olvidado abierto no deje el portátil
    encendido toda la noche, que sería peor que el problema que resuelve.
    """
    if pending > 0 or busy:
        return True
    return not paused and (now - last_audio_at) < AWAKE_GRACE_SEC


def keep_awake(on: bool) -> None:
    """Pide (o deja de pedir) a Windows que no suspenda por inactividad.

    El estado es por hilo: llamarlo siempre desde el hilo de la interfaz. Al terminar el proceso
    se libera solo. No impide cerrar la tapa ni una suspensión manual.
    """
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(
            ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if on else 0)
        )
    except Exception:  # ponytail: sin kernel32 (otro SO) simplemente no se retiene nada
        pass
