"""La introducción de Recorder, sin tkinter ni rich: el contrato, el guion y cuándo se muestra.

Todo sale de `recorder/assets/intro/intro.json` (docs/intro/especificacion.md): cada tiempo, medida,
token de paleta y clave de texto. Aquí no hay valores propios; el texto de cada clave está en
`recorder/ayuda.py` (INTRO). La ventana (ui/intro.py) y la terminal (cli/intro.py) pintan lo que
este módulo calcula:

- `cargar_contrato` lee el contrato y comprueba que están los fotogramas; sin ellos devuelve None y
  la introducción se omite sin error (ejecución desde el código sin los assets, o instalación rota).
- `Guion.estado(t)` dice, para el instante `t` (ms), qué hay y con qué opacidad. Es una función del
  reloj y no de un contador de pasos: si un tic llega tarde, la animación salta adelante y dura lo
  mismo en un equipo lento. Con «reducidas» (`reducido=True`) solo hay fundidos, cada uno con el
  techo `corto_ms`, y las formas pasan de un estado al siguiente sin recorrido ni escalonado.
- `debe_mostrarse` decide si toca: la primera vez, bajo demanda o nunca (`--sin-intro`, «ninguna»).
"""
import json
import math
import pathlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from . import ayuda
from .rutas import recurso

RUTA_ASSETS = "recorder/assets/intro"
ARCHIVO_CONTRATO = "intro.json"
COMPLETAS, REDUCIDAS, NINGUNA = "completas", "reducidas", "ninguna"  # valores de «animations»
MEDIA_ALTURA = 0.5  # la barra quieta de «reducidas»: la mitad de lo que alcanza al latir
OCULTO = "oculto"  # el estilo de un papel que se imprime como espacios (terminal)
OPCION_SIN_INTRO = "--sin-intro"
MARCADO_PAPEL = r"\[(\w+)\](.*?)\[/\]"  # `[capsula]███[/]` en los archivos del logotipo de terminal


# ---------------------------------------------------------------------------------- contrato
def carpeta_assets() -> pathlib.Path:
    return recurso(RUTA_ASSETS)


def cargar_contrato() -> Optional[dict]:
    """El contrato de la introducción, o None si no se puede reproducir: falta el contrato, no se
    lee o falta algún fotograma (o el estático). Quien llama la omite sin error."""
    base = carpeta_assets()
    try:
        contrato = json.loads((base / ARCHIVO_CONTRATO).read_text(encoding="utf-8"))
        logo = contrato["logotipo"]
        archivos = [logo["estatico"]] + [logo["patron"].format(n=n) for n in range(1, logo["fotogramas"] + 1)]
    except (OSError, ValueError, KeyError):
        return None
    if not all((base / archivo).is_file() for archivo in archivos):
        return None
    return contrato


def ruta_asset(relativa: str) -> pathlib.Path:
    """Un archivo de la introducción a partir de la ruta que da el contrato."""
    return carpeta_assets() / relativa


def debe_mostrarse(animaciones: str, vista: bool, sin_intro: bool = False, bajo_demanda: bool = False) -> bool:
    """Si toca la introducción: nunca con `--sin-intro` ni con animaciones «ninguna»; bajo demanda
    («Ver introducción»), siempre; si no, solo la primera vez (`vista` False)."""
    if sin_intro or animaciones == NINGUNA:
        return False
    return bajo_demanda or not vista


def marcar_vista(gestor, config, campo: str = "intro_seen") -> None:
    """Anota en `config` (`campo`: «intro_seen» para la ventana, «intro_terminal_seen» para la terminal)
    que la introducción ya se mostró, y lo guarda si se puede.

    No crea config.json: sin él es el primer arranque y el archivo lo escribe la recomendación del
    equipo (session.py), que ya llevará esta marca porque `config` es el mismo objeto. Tampoco guarda
    si el archivo no se pudo leer: sería pisarlo con los valores de fábrica (config/manager.py).
    """
    setattr(config, campo, True)
    if not gestor.path.exists() or gestor.last_error:
        return
    try:
        gestor.save(config)
    except OSError:
        pass  # no se pudo guardar: la introducción volverá a salir, nada más


# ---------------------------------------------------------------------------------- curvas
def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out(t: float) -> float:
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


CURVAS = {"ease_out": ease_out, "ease_in_out": ease_in_out, "lineal": lambda t: t}


# ---------------------------------------------------------------------------------- guion
@dataclass(frozen=True)
class Trazo:
    """Uno de los doce trazos de la ilustración, en unidades de diseño relativas a su origen: `x` es el
    borde izquierdo, `y` el centro vertical. Su color es la mezcla de tres tokens: de la onda al de
    la línea (`teñido`) y de ahí al de la nota (`en_nota`); todo con `opacidad` sobre el fondo."""

    x: float
    y: float
    ancho: float
    alto: float
    tokens: Tuple[str, str, str]  # onda, línea, nota
    teñido: float
    en_nota: float
    opacidad: float


@dataclass(frozen=True)
class Estado:
    """Lo que se ve en un instante: opacidades de 0 a 1 y posiciones en unidades de diseño."""

    logo: int  # número de fotograma (1…); 0 = el estático
    logo_centro: Tuple[float, float]
    rotulo: float
    titulo: Tuple[Optional[str], float]  # (clave de texto, opacidad)
    subtitulo: Tuple[Optional[str], float]
    equipo: float
    base: float
    trazos: Tuple[Trazo, ...]
    captura: float
    boton: float  # 0 = «Saltar», 1 = «Comenzar»


class Guion:
    """El contrato convertido en `estado(t)`. `reducido`: «reducidas», solo fundidos de `corto_ms` como mucho."""

    def __init__(self, contrato: dict, reducido: bool = False, corto_ms: int = 0):
        self.c = contrato
        self.reducido = reducido
        self.corto_ms = corto_ms
        self.total_ms: int = contrato["duraciones_ms"]["total"]
        self._pasos: Dict[Tuple[str, str, str], dict] = {}
        for escena in contrato["escenas"]:
            for p in escena["pasos"]:
                self._pasos[(escena["id"], p["elemento"], p["accion"])] = {**p, "t0": escena["inicio_ms"] + p["inicio_ms"]}

    # --- piezas
    def duracion(self, nombre: str) -> float:
        """Lo que dura la duración con nombre `nombre`: con «reducidas», nunca más de `corto_ms`."""
        ms = self.c["duraciones_ms"][nombre]
        return min(ms, self.corto_ms) if self.reducido else ms

    def paso(self, escena: str, elemento: str, accion: str) -> dict:
        return self._pasos[(escena, elemento, accion)]

    def avance(self, p: dict, t: float, retraso: float = 0.0) -> float:
        """De 0 a 1, ya con su curva, cuánto lleva el paso `p` en el instante `t`. Sin escalonado con «reducidas»."""
        if self.reducido:
            retraso = 0.0
        crudo = (t - p["t0"] - retraso) / max(1.0, self.duracion(p["duracion"]))
        return CURVAS[p["curva"]](min(1.0, max(0.0, crudo)))

    def texto_en(self, t: float, elemento: str) -> Tuple[Optional[str], float]:
        """(clave, opacidad) del título o el subtítulo: el anterior se va y después entra el nuevo."""
        clave, opacidad = None, 0.0
        for escena in self.c["escenas"]:
            for original in escena["pasos"]:
                if original["elemento"] != elemento or escena["inicio_ms"] + original["inicio_ms"] > t:
                    continue
                p = self._pasos[(escena["id"], elemento, original["accion"])]
                if p["accion"] == "fundido_entrada":
                    clave, opacidad = p["texto"], self.avance(p, t)
                elif p["accion"] == "fundido_cruzado":
                    salida = self.avance(p, t)
                    if salida < 1:
                        opacidad *= 1 - salida
                    else:
                        entra = {**p, "t0": p["t0"] + self.duracion(p["duracion"]), "duracion": "fundido_texto"}
                        clave, opacidad = p["texto"], self.avance(entra, t)
        return clave, opacidad

    def _trazos(self, t: float) -> Tuple[Trazo, ...]:
        ilu = self.c["ilustracion"]
        onda, lineas, nota = ilu["onda"], ilu["lineas"], ilu["nota"]
        entra = self.paso("graba", "onda", "fundido_entrada")
        a_onda = self.avance(entra, t)
        if a_onda <= 0:
            return ()
        conv = self.paso("graba", "onda", "convertir_en_lineas")
        tenir = self.paso("transcribe", "lineas", "teñir")
        reord = self.paso("notas", "lineas", "reordenar_en_nota")
        dur = self.c["duraciones_ms"]
        grosor = ilu["grosor_trazo"]
        por_linea = len(lineas["trazos"]) // 3
        trazos: List[Trazo] = []
        for i, (lin, nt) in enumerate(zip(lineas["trazos"], nota["trazos"])):
            if self.reducido:
                latido = MEDIA_ALTURA
            else:
                fase = 2 * math.pi * (t - entra["t0"]) / dur["onda_periodo"] + i * onda["desfase_rad"]
                latido = 0.5 + 0.5 * math.sin(fase)
            alto = onda["alto_min"] + (onda["alto_max"] - onda["alto_min"]) * onda["envolvente"][i] * latido
            barra = (onda["x_primera"] + i * onda["paso"], onda["centro_y"], onda["ancho"], alto)
            a = self.avance(conv, t, i * dur[conv["escalonado"]])
            b = self.avance(reord, t)
            if self.reducido:  # sin recorrido: la forma cambia a mitad del fundido y el color lo acompaña
                a_forma, b_forma = float(a >= 0.5), float(b >= 0.5)
            else:
                a_forma, b_forma = a, b
            x, y, w, h = (barra[k] + ((lin + [grosor])[k] - barra[k]) * a_forma for k in range(4))
            x, y, w = x + (nt[0] - x) * b_forma, y + (nt[1] - y) * b_forma, w + (nt[2] - w) * b_forma
            token_linea = lineas["color_clave"] if i == lineas["trazo_clave"] else lineas["color"]
            token_nota = {nota["trazo_marca"]: nota["color_marca"], nota["trazo_titulo"]: nota["color_titulo"]}.get(i, nota["color"])
            teñido = self.avance(tenir, t, (i // por_linea) * dur[tenir["escalonado"]])
            trazos.append(Trazo(x, y, w, h, (onda["color"], token_linea, token_nota), teñido, b, a_onda))
        return tuple(trazos)

    # --- el instante
    def estado(self, t: float) -> Estado:
        logo = self.c["logotipo"]
        if self.reducido:
            n, centro = 0, tuple(logo["centro_final"])
            rotulo = 0.0
        else:
            n = min(logo["fotogramas"], int(t * logo["fps"] / 1000) + 1)
            mov = self.avance(self.paso("graba", "logotipo", "desplazar"), t)
            centro = tuple(a + (b - a) * mov for a, b in zip(logo["centro_inicial"], logo["centro_final"]))
            rotulo = self.avance(self.paso("logotipo", "rotulo", "fundido_entrada"), t) * (
                1 - self.avance(self.paso("graba", "rotulo", "fundido_salida"), t))
        equipo = self.avance(self.paso("transcribe", "equipo", "fundido_entrada"), t)
        base = equipo * (1 - self.avance(self.paso("notas", "equipo_base", "fundido_salida"), t))
        return Estado(
            logo=n, logo_centro=centro, rotulo=rotulo,
            titulo=self.texto_en(t, "titulo"), subtitulo=self.texto_en(t, "subtitulo"),
            equipo=equipo, base=base, trazos=self._trazos(t),
            captura=self.avance(self.paso("notas", "captura", "fundido_entrada"), t),
            boton=self.avance(self.paso("comenzar", "boton", "pasar_a_principal"), t),
        )


# ---------------------------------------------------------------------------------- terminal
def lineas_logo_terminal(contrato: dict, juego: str) -> Optional[List[str]]:
    """Las líneas del logotipo de terminal del juego de símbolos `juego` (completo, consola, ascii),
    con el lema ya puesto y el marcado por papeles intacto; None si falta el archivo."""
    try:
        archivo = ruta_asset(contrato["terminal"]["juegos"][juego])
        texto = archivo.read_text(encoding="utf-8")
    except (OSError, KeyError):
        return None
    return texto.replace("{lema}", ayuda.texto_intro("intro.terminal.lema")).split("\n")
