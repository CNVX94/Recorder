"""Recorder: transcribe en vivo la salida de audio (Teams, etc.) y tu micrófono a un .md,
con capturas de pantalla automáticas al oír palabras clave.

Instalar:  pip install faster-whisper pyaudiowpatch pillow numpy rich
Usar:      escribe `daily` en PowerShell (función en $PROFILE) o python recorder.py
           Desde la terminal graba ahí mismo (teclas: p pausa, c captura, r reconectar, a abrir nota,
           q salir); `daily menu` lista todo lo demás; `daily --gui` o `daily ventana` abre la ventana,
           que es también lo que se abre sin consola (pythonw). `daily -h` para los subcomandos.
Opciones:  botón ⚙ (Opciones) o 🎯 (Calibrar) -> rutas, palabras clave, dispositivos, anti-alucinaciones
Tester:    los medidores 🔊/🎤 de la cabecera muestran el nivel en vivo de cada fuente
Pausa:     botón ⏸ deja de tomar nota sin cambiar de archivo; ▶ continúa en el mismo .md
Selftest:  python recorder.py --selftest
Equipo:    python recorder.py --recomendar [--aplicar]  -> qué se detecta, qué se recomienda y por qué;
           con --aplicar lo escribe en config.json (lo usa install.ps1 al crear la configuración)
Instalado: Recorder.exe (ventana) y daily.exe (terminal) son este archivo congelado con PyInstaller;
           config.json va a %APPDATA%\\Recorder y los fallos a %LOCALAPPDATA%\\Recorder\\logs
           (ver recorder/rutas.py y recorder/registro.py)
"""
import sys

if __name__ == "__main__" and "--vulkan" in sys.argv:
    # La consulta de Vulkan en otro proceso (config/hardware.py). Instalado no hay intérprete con
    # el que ejecutar hardware.py como script, así que se relanza este ejecutable; va antes de
    # importar numpy o PyAudio para que tarde milisegundos y no cargue nada en ese proceso.
    from recorder.config.hardware import sonda_vulkan

    sys.exit(sonda_vulkan())

import pathlib
import tempfile
from types import SimpleNamespace as S

import numpy as np
import pyaudiowpatch as pa

from recorder.actions import (
    NotesSession, find_window, md_ref, monitors, pick_window, screen_labels, take_screenshot, windows,
)
from recorder.actions import should_stay_awake
from recorder.audio import (
    bars, meter_label, pending_summary, resolve_wasapi_device, retry_delay, rms, to_16k, wasapi_devices,
)
from recorder.config import AppConfig, ConfigManager
from recorder.filters import clean_segments, find_keywords, fix, normalize, parse_fixes
# A propósito no se importa recorder.ui aquí: carga tkinter, y desde la terminal no hace falta.

# Valores por defecto para compatibilidad
DEFAULTS = AppConfig().to_dict()


def clean(segs, ignore):
    """Función de compatibilidad con versión 1.0."""
    return clean_segments(segs, ignore)


def screenshot(tag, caps_dir=None, screen=0):
    cfg_mgr = ConfigManager()
    cfg = cfg_mgr.load()
    target_caps = caps_dir or cfg.caps_dir
    p = take_screenshot(tag, target_caps, screen or cfg.screen, "" if screen else cfg.window)
    return md_ref(p, cfg.notes_dir)


def selftest():
    segs = [
        S(text=" Hola equipo. ", no_speech_prob=0.1, avg_logprob=-0.3),
        S(text="¡Suscríbete!", no_speech_prob=0.1, avg_logprob=-0.3),  # alucinación conocida
        S(text="mitalaka mitalaka", no_speech_prob=0.1, avg_logprob=-1.4),  # baja confianza
        S(text="ruido", no_speech_prob=0.9, avg_logprob=-0.2),  # sin voz
        S(text="Falta probar el flujo.", no_speech_prob=0.2, avg_logprob=-0.5),
    ]
    assert clean(segs, DEFAULTS["ignore"]) == "Hola equipo. Falta probar el flujo."
    assert fix("Desplegamos en Cuba y en el ayayas.", {"cuba": "QA", "ayayas": "IIS"}) == "Desplegamos en QA y en el IIS."
    assert fix("incubadora", {"cuba": "QA"}) == "incubadora"  # solo palabra completa
    assert parse_fixes(" cuba = QA ; ayayas=IIS; basura ; =x") == {"cuba": "QA", "ayayas": "IIS"}
    assert find_keywords("Hay un BLOQUEO con la base", ["bloqueo"]) == ["bloqueo"]
    assert find_keywords("bloqueos varios", ["bloqueo"]) == []  # palabra completa
    assert find_keywords("acción tomada", ["accion"]) == ["accion"]  # ignora acentos
    assert find_keywords("sin nada", ["", "x"]) == []
    a = to_16k(np.zeros(48000 * 2, np.int16), 48000, 2)
    assert a.shape == (16000,) and a.dtype == np.float32
    assert bars(0) == "░" * 8 and bars(32768) == "█" * 8 and bars(327.68) == "██░░░░░░"  # -40 dB
    assert retry_delay(1) == 1 and retry_delay(3) == 4 and retry_delay(99) == 30  # espera creciente acotada
    assert meter_label({"out": 0.0, "mic": 0.0}, {"out": 2, "mic": 0}) == "🔊 ⛔ reintento 2   🎤 ░░░░░░░░"
    assert pending_summary(150, 3000) == "150 fragmentos (~50 min de audio)"
    assert should_stay_awake(100.0, 0.0, pending=1, busy=False, paused=True)  # con cola, siempre despierto
    assert not should_stay_awake(9999.0, 0.0, pending=0, busy=False, paused=False)  # en silencio largo, no
    assert md_ref(r"C:\n\caps\x.png", r"C:\n") == "caps/x.png"
    assert md_ref(r"C:\otro\x.png", r"C:\n") == "../otro/x.png"
    assert md_ref(r"D:\x.png", r"C:\n") == "D:/x.png"

    with tempfile.TemporaryDirectory() as tmp:
        session = NotesSession(pathlib.Path(tmp) / "a", custom_name="d.md")
        session.write_line("hola")
        session.move_notes(pathlib.Path(tmp) / "b")
        assert session.file_path == pathlib.Path(tmp, "b", "d.md")
        content = session.file_path.read_text(encoding="utf-8")
        assert "hola\n" in content
        session.write_line("otra")
        content = session.file_path.read_text(encoding="utf-8")
        assert "otra\n" in content

    p = pa.PyAudio()
    assert wasapi_devices(p, "out") and wasapi_devices(p, "mic") and not any(
        "Loopback" in n for n in wasapi_devices(p, "mic")
    )
    m = monitors()
    assert m and all(r > l and b > t for l, t, r, b in m) and len(screen_labels()) == len(m) + 1
    assert all(isinstance(h, int) and t for h, t in windows())
    assert pick_window("Chat | Equipo | Microsoft Teams", ["x - Bloc de notas", "Reunión | Microsoft Teams"]) == "Reunión | Microsoft Teams"
    assert pick_window("Chat | Microsoft Teams", ["x - Bloc de notas"]) is None and find_window("") is None
    print("selftest ok (Fase 2 Modular)")


def recomendar(aplicar: bool) -> int:
    """Imprime el equipo detectado y la configuración recomendada; con `aplicar`, la guarda.

    Es el mismo `daily recomendar`; sigue aquí porque install.ps1 llama a `--recomendar --aplicar`.
    """
    from recorder.cli.recomendar import recomendar as recomendar_en_terminal

    return recomendar_en_terminal(aplicar)


def main() -> int:
    """`daily`: la terminal, o la ventana si no hay consola o se pide --gui (ver recorder/cli/app.py)."""
    from recorder.cli.app import arrancar

    return arrancar()


if __name__ == "__main__":
    from recorder.registro import instalar

    instalar()  # las excepciones sin atrapar quedan en %LOCALAPPDATA%\Recorder\logs (ver registro.py)
    if "--selftest" in sys.argv:
        selftest()
    elif "--recomendar" in sys.argv:
        sys.exit(recomendar("--aplicar" in sys.argv))
    else:
        sys.exit(main())
