"""La consola que comparten todos los comandos de terminal: mismos colores y mismo modo ASCII."""
import os
import re
import sys
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from rich.console import Console
from rich.theme import Theme

from .. import paleta
from . import vt

# Los tres juegos de símbolos (docs/plan-pulido-terminal.md §3): el color se decide aparte.
JUEGO_COMPLETO = "completo"  # Windows Terminal, VS Code, terminales que no son de Windows: todos, emoji incluidos
JUEGO_CONSOLA = "consola"  # conhost con VT (cmd y Windows PowerShell): solo lo que dibuja Consolas
JUEGO_ASCII = "ascii"  # consola sin VT, salida redirigida o --ascii
ELIDIDO, ELIDIDO_ASCII = "…", "..."  # lo que sustituye al texto cortado (ASCII no tiene «…»)
VARIABLE_WT = "WT_SESSION"  # la define Windows Terminal
VARIABLE_PROGRAMA, PROGRAMA_VSCODE = "TERM_PROGRAM", "vscode"

# Estilo de rich -> token de la paleta que comparte con la ventana (recorder/paleta.py, sin tkinter).
ESTILOS = {
    "texto": "texto", "tenue": "texto_tenue", "acento": "acento", "mic": "mic",
    "error": "error", "ok": "ok", "borde": "borde", "aviso": "aviso",
}
# Con 16 colores (consola sin VT o `--ascii`) la paleta no se puede pintar: se usan los colores
# de la consola que se leen bien sobre negro y sobre el azul de PowerShell (docs/terminal-especificacion.md §3.4).
# Nunca `magenta` ni `yellow`: ese acceso directo redefine las dos casillas.
ESTILOS_16 = {
    "texto": "bright_white", "tenue": "white", "acento": "bright_yellow", "mic": "bright_cyan",
    "error": "bold bright_red", "ok": "bright_green", "borde": "white", "aviso": "bright_yellow",
    "elegido": "bold bright_yellow", "fondo": "", "fila": "",
}


def tema_rich(nombre: str = paleta.POR_DEFECTO, dieciseis: bool = False) -> Theme:
    """Los colores de la ventana para el tema `nombre` de config («sistema» se resuelve); con
    `dieciseis`, los 16 colores de la consola en vez de la paleta."""
    if dieciseis:
        return Theme(ESTILOS_16)
    colores = paleta.TEMAS[paleta.resolver(nombre)]
    estilos = {estilo: colores[token] for estilo, token in ESTILOS.items()}
    estilos["elegido"] = f"bold {colores['acento']}"  # la fila elegida de un menú
    estilos["fondo"] = f"on {colores['fondo']}"  # el fondo propio de las pantallas completas
    estilos["fila"] = f"on {colores['superficie']}"  # la fila elegida (su fondo)
    return Theme(estilos)

# Equivalentes para la consola clásica (conhost), que pinta mal los emoji y los bloques. Los pares
# de flechas van antes que las sueltas: en el pie, «←→» es «<>» y no «<->».
ASCII = {
    "↑↓": "^v", "←→": "<>",
    "🔊": "OUT", "🎤": "MIC", "🔇": "(mudo)", "📸": "[cap]", "⚠": "!", "⛔": "x", "✅": "OK", "✔": "OK",
    "●": "*", "⏸": "||", "▶": ">", "►": ">", "⏳": "...", "☕": "(despierto)", "🖥": "", "💻": "", "⚙": "", "🔧": "",
    "🎯": "", "🧪": "", "🧹": "", "📝": "", "📑": "", "█": "#", "░": ".", "→": "->", "➔": "->", "…": "...",
    "↑": "^", "↓": "v", "←": "<", "‹": "<", "›": ">", "─": "-",
    "▌": "_", "○": "o", "▲": "!", "√": "OK", "‖": "||", "■": "[cap]", "▄": ".", "│": "|", "•": "*", "∙": ".",
}
# Desde U+2000 (salvo las rayas – y —) y el espacio que lo siga.
FUERA_DE_ASCII = re.compile("[^\\x00-\\u1fff–—] ?")

# Los símbolos fuera de ASCII que Consolas dibuja bien en la consola clásica; el resto se sustituye.
# Visto en captura de la consola de PowerShell (docs/capturas-terminal/powershell/): ver el resultado
# del paso 3 en docs/plan-pulido-terminal.md. Si alguno se ve mal, basta quitarlo de aquí: pasa a su reserva.
SEGUROS_CONSOLA = "─█░‹›●·«»►↑↓←→…▲○■▌▄│√‖•∙"
# Lo que el juego «consola» pone en lugar de cada símbolo del juego completo (columna «consola» de la
# especificación, §2), y su reserva si ese símbolo no está en SEGUROS_CONSOLA.
PROPIOS_CONSOLA = {"▶": "►", "✔": "√", "✅": "√", "⚠": "▲", "⛔": "×", "⏸": "‖", "⏳": "…", "📸": "■"}
RESERVA_CONSOLA = {"►": "›", "√": "OK", "▲": "!", "‖": "=", "…": "...", "■": "·"}
LATIN1 = 0x100  # lo que está por debajo (×, ·, «») lo dibuja cualquier fuente


def construir_consola() -> Dict[str, str]:
    """La tabla del juego «consola»: lo mismo que ASCII salvo lo seguro, con sus propios símbolos (o su
    reserva, si el propio no está en SEGUROS_CONSOLA)."""
    tabla = {k: v for k, v in ASCII.items() if not all(c in SEGUROS_CONSOLA for c in k)}
    tabla.update({k: v for k, v in RESERVA_CONSOLA.items() if k not in SEGUROS_CONSOLA})
    tabla.update({
        k: v if v in SEGUROS_CONSOLA or ord(v) < LATIN1 else RESERVA_CONSOLA[v] for k, v in PROPIOS_CONSOLA.items()
    })
    return tabla


CONSOLA = construir_consola()
FUERA_DE_CONSOLA = re.compile(f"[^\\x00-\\u1fff–—{re.escape(SEGUROS_CONSOLA)}] ?")

# El spinner de cada juego, un fotograma cada TIC_ANIMACION s (el braille de rich no está en Consolas).
TIC_ANIMACION = 0.2
FOTOGRAMAS = {JUEGO_COMPLETO: "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏", JUEGO_CONSOLA: "∙•●•", JUEGO_ASCII: "-\\|/"}


def fotograma(juego: str, ahora: float) -> str:
    """El fotograma del spinner de `juego` en el instante `ahora` (s)."""
    cuadros = FOTOGRAMAS[juego]
    return cuadros[int(ahora / TIC_ANIMACION) % len(cuadros)]

# Símbolos con presentación de texto (✔ ⚙ 🖥: Emoji_Presentation=No) que rich mide a una celda
# pero Windows Terminal dibuja con un glifo de dos (el de Segoe UI Symbol/Emoji), pisando el
# espacio que sigue: «✔vuelve», «⚙Opciones». Su equivalente con presentación emoji mide dos celdas
# para los dos. Los demás símbolos de Recorder (⚠ ● ⏸ ▶ ⏳ ☕ y los emoji) ya se miden igual.
EMOJI_SEGURO = {"✔": "✅", "⚙": "🔧", "🖥": "💻"}


def _sustituir(texto: str, tabla: Mapping[str, str], fuera: "re.Pattern[str]") -> str:
    """`texto` con cada símbolo de `tabla` sustituido; un símbolo que desaparece se lleva el espacio
    que lo seguía: «🎯 Calibrar» queda «Calibrar», no « Calibrar». Lo que quede fuera de lo que
    admite el juego (emoji, flechas, bloques) se quita."""
    texto = texto.replace("️", "")  # selector de presentación emoji: no ocupa nada
    for simbolo, sustituto in tabla.items():
        if not sustituto:
            texto = texto.replace(simbolo + " ", "")
        texto = texto.replace(simbolo, sustituto)
    return fuera.sub("", texto)


def asciify(texto: str) -> str:
    """El texto con los símbolos de Recorder en ASCII y sin emoji; los acentos se quedan."""
    return _sustituir(texto, ASCII, FUERA_DE_ASCII)


def consolificar(texto: str) -> str:
    """El texto con solo los símbolos que Consolas dibuja bien: sin emoji ni ▶ (ver SEGUROS_CONSOLA)."""
    return _sustituir(texto, CONSOLA, FUERA_DE_CONSOLA)


def emoji_seguro(texto: str) -> str:
    """El texto con los símbolos que la terminal pintaría encima del espacio siguiente sustituidos
    por su versión emoji (ver EMOJI_SEGURO). La nota y la ventana conservan los originales."""
    for simbolo, sustituto in EMOJI_SEGURO.items():
        texto = texto.replace(simbolo, sustituto)
    return texto


def tema_de(consola, nombre: str = paleta.POR_DEFECTO) -> Theme:
    """El tema de rich que le toca a `consola`: la paleta, o los 16 colores en ASCII."""
    return tema_rich(nombre, juego_de(consola) == JUEGO_ASCII)


def juego_de(consola) -> str:
    """El juego de símbolos de `consola` («completo» si no dice: una consola de rich cualquiera)."""
    juego = getattr(consola, "juego", None)
    if juego:
        return juego
    return JUEGO_ASCII if getattr(consola, "ascii_mode", False) else JUEGO_COMPLETO


def presentar(texto: str, consola) -> str:
    """`texto` tal como lo pinta esta consola según su juego de símbolos: ASCII, «consola» o completo
    (con los símbolos seguros). Es por donde pasa todo lo que la terminal escribe con símbolos."""
    juego = juego_de(consola)
    if juego == JUEGO_ASCII:
        return asciify(texto)
    return consolificar(texto) if juego == JUEGO_CONSOLA else emoji_seguro(texto)


def elegir_juego(
    es_terminal: bool, vt_activo: bool, entorno: Optional[Mapping[str, str]] = None, windows: Optional[bool] = None
) -> str:
    """El juego de símbolos que pide el entorno: ASCII si la salida no es una terminal o es una consola
    de Windows sin VT; completo en Windows Terminal, VS Code y fuera de Windows; «consola» en conhost con VT."""
    entorno = os.environ if entorno is None else entorno
    windows = sys.platform == "win32" if windows is None else windows
    if not es_terminal:
        return JUEGO_ASCII
    if entorno.get(VARIABLE_WT) or entorno.get(VARIABLE_PROGRAMA) == PROGRAMA_VSCODE or not windows:
        return JUEGO_COMPLETO
    return JUEGO_CONSOLA if vt_activo else JUEGO_ASCII


def _es_terminal(kwargs: Mapping[str, object]) -> bool:
    """Si la salida que va a usar la consola (`file` o la estándar) es una terminal."""
    if kwargs.get("force_terminal") is not None:
        return bool(kwargs["force_terminal"])
    salida = kwargs.get("file") or sys.stdout
    try:
        return bool(salida is not None and salida.isatty())
    except (AttributeError, ValueError):
        return False


def partes_teclas(ayudas: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """(("p", "pausar"), …) → trozos (texto, estilo) de «[p] pausar · [c] captura…», con la
    tecla en acento: el pie de botones de la grabación y del menú."""
    partes: List[Tuple[str, str]] = []
    for tecla, ayuda in ayudas:
        if partes:
            partes.append((" · ", "tenue"))
        partes += [(f"[{tecla}]", "acento"), (f" {ayuda}", "tenue")]
    return partes


def make_console(ascii_mode: Optional[bool] = None, tema: str = paleta.POR_DEFECTO, **kwargs) -> Console:
    """Consola de rich con el tema de Recorder (`tema`: el «theme» de config).

    El color lo decide rich según lo que admita la consola (con el modo VT activo, `vt.activar`, la
    consola clásica llega a color real). Los símbolos van aparte, en tres juegos (`console.juego`):
    `ascii_mode` True fuerza ASCII, False el completo y None lo decide `elegir_juego` según el
    entorno. Quien pinte símbolos debe pasarlos por `presentar`.
    """
    if "file" not in kwargs and sys.stdout is not None:
        # Redirigida a un pipe o archivo, la salida va en cp1252 y un emoji la tumbaría; en la
        # consola real no pasa (Python escribe con WriteConsoleW). Se sustituye en vez de fallar.
        try:
            sys.stdout.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if ascii_mode is None:
        juego = elegir_juego(_es_terminal(kwargs), vt.hay_vt())
    else:
        juego = JUEGO_ASCII if ascii_mode else JUEGO_COMPLETO
    console = Console(theme=tema_rich(tema, juego == JUEGO_ASCII), highlight=False, emoji=juego == JUEGO_COMPLETO, **kwargs)
    console.juego = juego  # atributos propios: los consultan los comandos al pintar
    console.ascii_mode = juego == JUEGO_ASCII
    return console
