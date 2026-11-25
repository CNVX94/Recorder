"""`daily menu` en una terminal de verdad: pantallas navegables por teclado, vivas y con botones.

Un módulo por cosa: `terminal` (el bucle y el marco), `base` (la pantalla base y la lógica pura), `marco` (el
reparto del cuadro), `componentes` (lo que comparten las pantallas), `registro` (acción → pantalla) y una
pantalla por módulo: `inicio`, `opciones`, `rendimiento` y `ayuda`. Añadir una pantalla es crear su módulo y
una línea en `registro.PANTALLAS`. `from recorder.cli.pantallas import Terminal` es lo que usa el menú.

Teclas de las pantallas (docs/terminal-especificacion.md, sección 5): ↑/↓ (o j/k) mueven, Enter abre o
edita, ←/→ cambian un valor, Esc o q vuelven (en el inicio, salen), [?] abre la ayuda y [t] pasa del tema
oscuro al claro y lo guarda, como en la ventana.
"""
from .ayuda import Ayuda
from .base import Pantalla, barra, motor_previsto, nota_de_hoy, recorte, tendencia
from .inicio import Inicio
from .opciones import Opciones
from .rendimiento import Rendimiento
from .terminal import Terminal

__all__ = [
    "Ayuda", "Inicio", "Opciones", "Pantalla", "Rendimiento", "Terminal",
    "barra", "motor_previsto", "nota_de_hoy", "recorte", "tendencia",
]
