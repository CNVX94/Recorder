"""El logotipo de la terminal: el de la introducción, en el primer `daily`.

Dura como mucho `terminal.duracion_ms` del contrato (recorder/assets/intro/intro.json), sale con el
juego de símbolos de la consola (completo, consola o ASCII: un archivo por juego) y se salta con
cualquier tecla. Son tres repintados en el mismo sitio (subir el cursor y volver a escribir) y solo
el último cambia un carácter: nada destella. Sin cursor que subir (la consola clásica sin VT, la
salida redirigida) o con movimiento reducido, se imprime una sola vez el último paso. Al terminar
queda impreso el último paso y el cursor en la línea siguiente: el prompt queda limpio.
"""
import re
import sys
import time
from typing import Callable, Dict, List, Optional

from rich.style import Style
from rich.text import Text

from .. import intro
from ..config.manager import ConfigManager
from . import vt
from .consola import juego_de
from .teclas import teclado

ESPERA_S = 0.02  # cada cuánto se mira si hubo una tecla mientras se espera al siguiente paso
SUBIR_LINEAS = "\x1b[{n}A\r"  # el cursor n líneas arriba y al principio de la línea


def _estilo(consola, nombre: str) -> Style:
    """«bold acento» → negrita sobre el estilo «acento» de la consola. Cada palabra puede ser un
    estilo del tema de la consola o uno de rich (bold…)."""
    return Style.combine(consola.get_style(palabra) for palabra in nombre.split())


def pintar_paso(consola, lineas: List[str], estilos: Dict[str, str]) -> List[Text]:
    """Las líneas del logotipo con el estilo de cada papel en este paso; «oculto» se imprime como
    espacios (así el dibujo no se mueve cuando aparece)."""
    resueltos = {papel: None if nombre == intro.OCULTO else _estilo(consola, nombre) for papel, nombre in estilos.items()}
    textos = []
    for linea in lineas:
        texto = Text(no_wrap=True, overflow="ignore")
        resto = 0
        for m in re.finditer(intro.MARCADO_PAPEL, linea):
            texto.append(linea[resto:m.start()])
            papel, tramo = m.group(1), m.group(2)
            estilo = resueltos[papel]
            texto.append(" " * len(tramo) if estilo is None else tramo, style=estilo)
            resto = m.end()
        texto.append(linea[resto:])
        textos.append(texto)
    return textos


def _imprimir(consola, textos: List[Text]) -> None:
    for texto in textos:
        consola.print(texto, soft_wrap=True)


def hay_cursor(consola) -> bool:
    """Si se puede subir el cursor para repintar: una terminal real, y en Windows con VT activo."""
    if not consola.is_terminal:
        return False
    return sys.platform != "win32" or vt.hay_vt()


def mostrar_logo(
    consola,
    animaciones: str,
    *,
    contrato: Optional[dict] = None,
    leer_tecla: Optional[Callable[[], Optional[str]]] = None,
    reloj: Callable[[], float] = time.monotonic,
    esperar: Callable[[float], None] = time.sleep,
) -> bool:
    """Imprime el logotipo. Devuelve False si no se pudo (faltan los archivos): se omite sin error.

    `leer_tecla` devuelve la tecla pulsada o None; sin él se usa el teclado de la terminal.
    """
    contrato = contrato or intro.cargar_contrato()
    if contrato is None:
        return False
    lineas = intro.lineas_logo_terminal(contrato, juego_de(consola))
    if lineas is None:
        return False
    terminal = contrato["terminal"]
    pasos = terminal["pasos"]
    final = pintar_paso(consola, lineas, pasos[-1]["estilos"])
    if animaciones != intro.COMPLETAS or not hay_cursor(consola):
        _imprimir(consola, final)
        return True

    def repintar(textos: List[Text], primera: bool = False) -> None:
        if not primera:
            consola.file.write(SUBIR_LINEAS.format(n=len(textos)))
        _imprimir(consola, textos)
        consola.file.flush()

    def animar(leer: Callable[[], Optional[str]]) -> None:
        inicio = reloj()
        siguiente = 0  # el próximo paso por pintar
        while True:
            ms = (reloj() - inicio) * 1000
            if leer() is not None:
                break  # una tecla: el último paso, ya
            while siguiente < len(pasos) and ms >= pasos[siguiente]["inicio_ms"]:
                repintar(pintar_paso(consola, lineas, pasos[siguiente]["estilos"]), primera=siguiente == 0)
                siguiente += 1
            if ms >= terminal["duracion_ms"]:
                break
            esperar(ESPERA_S)
        if siguiente < len(pasos):  # saltó antes del último: se deja ese
            repintar(final, primera=siguiente == 0)

    if leer_tecla is not None:
        animar(leer_tecla)
    else:
        with teclado() as leer:
            animar(leer)
    return True


def primer_daily(consola, gestor: Optional[ConfigManager] = None) -> bool:
    """El logotipo de la primera vez en una terminal (`intro_terminal_seen`); lo anota para no repetirlo.
    Devuelve si se mostró. No sale con la salida redirigida: ahí no hay nadie mirando."""
    if not consola.is_terminal:
        return False
    gestor = gestor or ConfigManager()
    config = gestor.load()
    if not intro.debe_mostrarse(config.animations, config.intro_terminal_seen):
        return False
    if not mostrar_logo(consola, config.animations):
        return False
    intro.marcar_vista(gestor, config, "intro_terminal_seen")
    return True
