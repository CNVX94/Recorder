"""Imprime los símbolos del juego «consola» con su uso, para verlos (y capturarlos) en la consola real.

Sirve para decidir qué entra en `consola.SEGUROS_CONSOLA`: lo que aquí se dibuja con la fuente de la consola
(Consolas) puede quedarse; lo que sale como un hueco o con otra letra pasa a su reserva. Abre una consola de
PowerShell, lanza `python tools/simbolos_consola.py` y mira (o captura la ventana con tools/capturar_terminal.py).
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from recorder.cli import consola  # noqa: E402

USOS = (
    ("marca de fila", "►"), ("flechas", "↑ ↓ ← →"), ("recorte", "abc…"), ("cursor", "a▌b"), ("interruptor", "● sí  ○ no"),
    ("pausa", "‖"), ("terminando", "…"), ("correcto", "√"), ("aviso", "▲"), ("error", "×"), ("captura", "■"),
    ("tendencia", "· ░ ▄ █"), ("separador", "a │ b"), ("spinner", "".join(f"{c} " for c in consola.FOTOGRAMAS[consola.JUEGO_CONSOLA])),
    ("barras", "████░░░░"), ("ruta y valor", "› ‹ › ─── « »"),
)

if __name__ == "__main__":
    for uso, simbolos in USOS:
        print(f"{uso:<16}{simbolos}")
    print()
    print("juego «consola»:", consola.consolificar("▶ ✔ ⚠ ⛔ ⏸ ⏳ 📸 ✅ 🎯 Calibrar"))
    print("seguros:", consola.SEGUROS_CONSOLA)
