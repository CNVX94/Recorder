"""Recorder: transcribe en vivo la salida de audio (Teams, etc.) y tu micrófono a un .md,
con capturas de pantalla automáticas al oír palabras clave.

Instalar:  pip install faster-whisper pyaudiowpatch pillow numpy
Usar:      escribe `daily` en PowerShell (función en $PROFILE) o python recorder.py
Opciones:  botón ⚙ (Opciones) o 🎯 (Calibrar) -> rutas, palabras clave, dispositivos, anti-alucinaciones
Tester:    los medidores 🔊/🎤 de la cabecera muestran el nivel en vivo de cada fuente
Pausa:     botón ⏸ deja de tomar nota sin cambiar de archivo; ▶ continúa en el mismo .md
Selftest:  python recorder.py --selftest
"""
import pathlib
import sys
import tempfile
from types import SimpleNamespace as S

import numpy as np
import pyaudiowpatch as pa

from recorder.actions import md_ref, monitors, screen_labels, take_screenshot, NotesSession
from recorder.audio import bars, rms, to_16k, wasapi_devices, resolve_wasapi_device
from recorder.config import AppConfig, ConfigManager
from recorder.filters import clean_segments, find_keywords, fix, normalize, parse_fixes
from recorder.ui import MainWindow

# Valores por defecto para compatibilidad
DEFAULTS = AppConfig().to_dict()


def clean(segs, ignore):
    """Función de compatibilidad con versión 1.0."""
    return clean_segments(segs, ignore)


def screenshot(tag, caps_dir=None, screen=0):
    cfg_mgr = ConfigManager()
    cfg = cfg_mgr.load()
    target_caps = caps_dir or cfg.caps_dir
    p = take_screenshot(tag, target_caps, screen or cfg.screen)
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
    print("selftest ok (Fase 2 Modular)")


def main():
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
