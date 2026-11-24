"""Los colores de Recorder por tokens semánticos, sin tkinter: los usan la ventana (ui/theme.py) y
la terminal (cli/consola.py).

Temas: «oscuro» (Catppuccin Mocha) y «claro» (sobre Catppuccin Latte), más «sistema», que sigue el
modo de aplicaciones de Windows. Cada par que se pinta junto (PARES) cumple WCAG 2.2 AA: texto
>= 4,5:1; bordes de componentes y anillo de foco >= 3:1 (tests/test_paleta.py lo mide).

Del Mocha original cambian dos valores, por contraste: texto_tenue (#7f849c daba 4,4:1 sobre el
fondo y 3,4:1 sobre los paneles) y borde (#45475a daba 1,9:1).

Un mismo color puede servir a dos tokens (texto_sobre_acento y fondo) solo si coinciden en todos
los temas: ui/theme.py cambia de tema sustituyendo cada color por el del mismo token.
"""

TEMAS = {
    "oscuro": {
        "fondo": "#1e1e2e",  # base
        "superficie": "#313244",  # surface0: botones, campos, paneles
        "superficie_elevada": "#45475a",  # surface1: menús y tooltips
        "borde": "#6c7086",  # overlay0: contorno de campos y barras de desplazamiento
        "texto": "#cdd6f4",
        "texto_tenue": "#a6adc8",  # subtext0
        "acento": "#f9e2af",  # yellow: palabras clave, títulos, botón pulsado
        "texto_sobre_acento": "#1e1e2e",
        "mic": "#89b4fa",  # blue
        "error": "#f38ba8",  # red
        "ok": "#a6e3a1",  # green
        "aviso": "#fab387",  # peach
        "foco": "#b4befe",  # lavender
        "tooltip_fondo": "#45475a",
        "tooltip_texto": "#cdd6f4",
        "seleccion": "#585b70",  # surface2
    },
    "claro": {
        "fondo": "#eff1f5",  # base
        "superficie": "#dce0e8",  # crust
        "superficie_elevada": "#e6e9ef",  # mantle
        "borde": "#7c7f93",  # overlay2
        # Más oscuro que el text de Latte (#4c4f69): con él, el tenue apenas se distinguía.
        "texto": "#3c3f55",
        "texto_tenue": "#5c5f77",  # subtext1
        # Los acentos de Latte (yellow, green, peach, blue) no llegan a 4,5:1 sobre su base: se
        # oscurecen conservando el tono.
        "acento": "#8a5100",
        "texto_sobre_acento": "#eff1f5",
        "mic": "#1a55c9",
        "error": "#b5102f",
        "ok": "#2b6b1c",
        "aviso": "#a33f00",
        "foco": "#1e66f5",  # blue
        "tooltip_fondo": "#e6e9ef",
        "tooltip_texto": "#3c3f55",
        "seleccion": "#ccd0da",  # surface0
    },
}
POR_DEFECTO = "oscuro"
SISTEMA = "sistema"
NOMBRES = ("oscuro", "claro", SISTEMA)  # lo que acepta «theme» en config.json

# (primer plano, fondo, mínimo): lo que se pinta junto en la ventana y en los diálogos.
TEXTO, COMPONENTE = 4.5, 3.0
PARES = [
    ("texto", "fondo", TEXTO),
    ("texto", "superficie", TEXTO),
    ("texto", "superficie_elevada", TEXTO),
    ("texto", "seleccion", TEXTO),
    ("texto_tenue", "fondo", TEXTO),
    ("texto_tenue", "superficie", TEXTO),
    ("acento", "fondo", TEXTO),
    ("acento", "superficie", TEXTO),
    ("texto_sobre_acento", "acento", TEXTO),
    ("mic", "fondo", TEXTO),
    ("mic", "superficie", TEXTO),
    ("error", "fondo", TEXTO),
    ("ok", "fondo", TEXTO),
    ("ok", "superficie", TEXTO),
    ("aviso", "fondo", TEXTO),
    ("tooltip_texto", "tooltip_fondo", TEXTO),
    ("borde", "fondo", COMPONENTE),
    ("foco", "fondo", COMPONENTE),
    ("foco", "superficie", COMPONENTE),
]


def modo_windows() -> str:
    """«claro» u «oscuro» según el modo de aplicaciones de Windows; «oscuro» si no se puede leer."""
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as clave:
            claro = winreg.QueryValueEx(clave, "AppsUseLightTheme")[0]
        return "claro" if claro else "oscuro"
    except (ImportError, OSError):
        return POR_DEFECTO


def resolver(nombre: str) -> str:
    """El tema que se pinta para lo guardado en «theme»: «sistema» se resuelve; uno desconocido, el de fábrica."""
    if nombre == SISTEMA:
        return modo_windows()
    return nombre if nombre in TEMAS else POR_DEFECTO


def luminancia(color: str) -> float:
    """Luminancia relativa de un "#rrggbb" (WCAG 2.2)."""
    def canal(c: int) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(int(color[i:i + 2], 16)) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a: str, b: str) -> float:
    """Relación de contraste WCAG entre dos colores, de 1 a 21."""
    claro, oscuro = sorted((luminancia(a), luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


def es_oscuro(tema: dict) -> bool:
    return luminancia(tema["fondo"]) < 0.5
