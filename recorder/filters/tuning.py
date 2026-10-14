"""Lógica de la ventana de Calibración sin Tkinter: qué se edita, cómo se prueba y qué se guarda.

La ventana 🎯 y el comando `daily calibrar` recogen los mismos campos tal como se escriben
(vocabulario, frases prohibidas separadas por coma, correcciones «mal=bien; ...», umbrales) en
un `TuningForm`. Aquí se interpretan, se pasa una frase por los filtros así escritos (el sandbox,
`test_phrase`) y se vuelcan sobre la configuración (`apply_tuning`). Nada de esto toca widgets,
disco ni el modelo.
"""

import dataclasses
from typing import Dict, List, Sequence, Tuple

from ..config.schema import AppConfig
from .lexicon import format_fixes, parse_fixes
from .pipeline import TextPipeline

# Frases fantasma típicas de vídeos de YouTube: lo que «+ Añadir comunes» suma a la lista negra.
COMMON_IGNORE = [
    "suscríbete",
    "gracias por ver",
    "amara.org",
    "hasta el próximo vídeo",
    "subtítulos por",
    "dale a la campanita",
]

# (mínimo, máximo, paso) de cada umbral: lo que recorren los deslizadores de la ventana y lo que
# una terminal debe admitir. Las claves son los campos de AppConfig.
THRESHOLD_RANGES: Dict[str, Tuple[float, float, float]] = {
    "no_speech_threshold": (0.1, 0.95, 0.05),
    "logprob_threshold": (-2.5, -0.2, 0.1),
    "compression_ratio_threshold": (1.5, 3.5, 0.1),
}


def parse_ignore(text: str) -> List[str]:
    """"suscríbete, gracias por ver" -> ["suscríbete", "gracias por ver"], sin vacíos."""
    return [x.strip() for x in text.split(",") if x.strip()]


def format_ignore(items: Sequence[str]) -> str:
    """La lista negra como se escribe en el campo: separada por coma y espacio."""
    return ", ".join(items)


def with_common_ignore(current: Sequence[str]) -> List[str]:
    """La lista negra más las frases comunes que aún no estaban, en ese orden."""
    salida = list(current)
    for c in COMMON_IGNORE:
        if c not in salida:
            salida.append(c)
    return salida


@dataclasses.dataclass
class TuningForm:
    """Los campos de Calibración tal como se escriben; los umbrales ya como números."""

    vocab: str
    ignore: str  # frases separadas por coma
    fixes: str  # 'oído_mal=escrito_bien; ...'
    no_speech_threshold: float
    logprob_threshold: float
    compression_ratio_threshold: float

    @property
    def ignore_list(self) -> List[str]:
        return parse_ignore(self.ignore)

    @property
    def fixes_dict(self) -> Dict[str, str]:
        return parse_fixes(self.fixes)


def tuning_form(config: AppConfig) -> TuningForm:
    """El formulario con los valores actuales de `config`, listo para editar."""
    return TuningForm(
        vocab=config.vocab,
        ignore=format_ignore(config.ignore),
        fixes=format_fixes(config.fixes),
        no_speech_threshold=config.no_speech_threshold,
        logprob_threshold=config.logprob_threshold,
        compression_ratio_threshold=config.compression_ratio_threshold,
    )


@dataclasses.dataclass(frozen=True)
class SandboxVerdict:
    """Qué pasó con una frase en el sandbox, y la línea que lo cuenta."""

    accepted: bool
    processed: str  # el texto tras las correcciones; vacío si se descartó
    hits: List[str]  # palabras clave que dispararían una captura
    message: str  # "⛔ DESCARTADA: ..." o "✅ ACEPTADA: ..."


def test_phrase(form: TuningForm, sample: str, keywords: Sequence[str]) -> SandboxVerdict:
    """Pasa `sample` por los filtros tal como están escritos en `form` (las palabras clave son las de config)."""
    pipeline = TextPipeline(
        keywords=keywords,
        ignore=form.ignore_list,
        fixes=form.fixes_dict,
        no_speech_thresh=form.no_speech_threshold,
        logprob_thresh=form.logprob_threshold,
        compression_ratio_thresh=form.compression_ratio_threshold,
    )
    res = pipeline.test_sample(sample)
    if res["is_ignored"]:
        return SandboxVerdict(
            False, "", [], "⛔ DESCARTADA: Contiene una frase de la lista negra de alucinaciones."
        )
    out = f"✅ ACEPTADA: \"{res['processed']}\""
    if res["hits"]:
        out += f"  (📸 Palabras clave detectadas: {', '.join(res['hits'])})"
    return SandboxVerdict(True, res["processed"], list(res["hits"]), out)


def apply_tuning(config: AppConfig, form: TuningForm) -> None:
    """Vuelca el formulario sobre `config`, en el sitio. No toca rutas, dispositivos ni palabras clave."""
    config.vocab = form.vocab.strip()
    config.ignore = form.ignore_list
    config.fixes = form.fixes_dict
    config.no_speech_threshold = float(form.no_speech_threshold)
    config.logprob_threshold = float(form.logprob_threshold)
    config.compression_ratio_threshold = float(form.compression_ratio_threshold)
