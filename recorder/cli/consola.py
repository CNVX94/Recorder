"""La consola que comparten todos los comandos de terminal: mismos colores y mismo modo ASCII."""
import sys
from typing import Optional

from rich.console import Console, detect_legacy_windows
from rich.theme import Theme

from .. import paleta

# Estilo de rich -> token de la paleta que comparte con la ventana (recorder/paleta.py, sin tkinter).
ESTILOS = {
    "texto": "texto", "tenue": "texto_tenue", "acento": "acento", "mic": "mic",
    "error": "error", "ok": "ok", "borde": "borde",
}


def tema_rich(nombre: str = paleta.POR_DEFECTO) -> Theme:
    """Los colores de la ventana para el tema `nombre` de config («sistema» se resuelve)."""
    colores = paleta.TEMAS[paleta.resolver(nombre)]
    return Theme({estilo: colores[token] for estilo, token in ESTILOS.items()})

# Equivalentes para la consola clásica (conhost), que pinta mal los emoji y los bloques.
ASCII = {
    "🔊": "OUT", "🎤": "MIC", "🔇": "(mudo)", "📸": "[cap]", "⚠": "!", "⛔": "x", "✅": "OK", "✔": "OK",
    "●": "*", "⏸": "||", "▶": ">", "⏳": "...", "☕": "(despierto)", "🖥": "", "💻": "", "⚙": "", "🔧": "",
    "🎯": "", "🧪": "", "🧹": "", "📝": "", "📑": "", "█": "#", "░": ".", "→": "->", "➔": "->", "…": "...",
}

# Símbolos con presentación de texto (✔ ⚙ 🖥: Emoji_Presentation=No) que rich mide a una celda
# pero Windows Terminal dibuja con un glifo de dos (el de Segoe UI Symbol/Emoji), pisando el
# espacio que sigue: «✔vuelve», «⚙Opciones». Su equivalente con presentación emoji mide dos celdas
# para los dos. Los demás símbolos de Recorder (⚠ ● ⏸ ▶ ⏳ ☕ y los emoji) ya se miden igual.
EMOJI_SEGURO = {"✔": "✅", "⚙": "🔧", "🖥": "💻"}


def asciify(texto: str) -> str:
    """El texto con los símbolos de Recorder en ASCII y sin emoji; los acentos se quedan."""
    for simbolo, sustituto in ASCII.items():
        texto = texto.replace(simbolo, sustituto)
    # Lo que quede fuera de los alfabetos latinos (emoji, flechas, bloques) no se ve en conhost.
    return "".join(c for c in texto if ord(c) < 0x2000 or c in "–—·").replace("️", "")


def emoji_seguro(texto: str) -> str:
    """El texto con los símbolos que la terminal pintaría encima del espacio siguiente sustituidos
    por su versión emoji (ver EMOJI_SEGURO). La nota y la ventana conservan los originales."""
    for simbolo, sustituto in EMOJI_SEGURO.items():
        texto = texto.replace(simbolo, sustituto)
    return texto


def presentar(texto: str, consola) -> str:
    """`texto` tal como lo pinta esta consola: ASCII en la clásica (conhost); si no, con los
    símbolos seguros. Es por donde pasa todo lo que la terminal escribe con símbolos."""
    return asciify(texto) if getattr(consola, "ascii_mode", False) else emoji_seguro(texto)


def make_console(ascii_mode: Optional[bool] = None, tema: str = paleta.POR_DEFECTO, **kwargs) -> Console:
    """Consola de rich con el tema de Recorder (`tema`: el «theme» de config).

    `ascii_mode`: None lo decide solo (sí en la consola clásica sin secuencias VT, donde los emoji
    salen rotos; no en Windows Terminal). Quien pinte texto con emoji o medidores debe pasarlo por
    `asciify` cuando `console.ascii_mode` sea True.
    """
    if "file" not in kwargs and sys.stdout is not None:
        # Redirigida a un pipe o archivo, la salida va en cp1252 y un emoji la tumbaría; en la
        # consola real no pasa (Python escribe con WriteConsoleW). Se sustituye en vez de fallar.
        try:
            sys.stdout.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if ascii_mode is None:
        ascii_mode = detect_legacy_windows()
    console = Console(theme=tema_rich(tema), highlight=False, emoji=not ascii_mode, **kwargs)
    console.ascii_mode = ascii_mode  # atributo propio: lo consultan los comandos al pintar
    return console
