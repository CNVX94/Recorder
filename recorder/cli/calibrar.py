"""`daily calibrar`: la ventana 🎯 Calibrar en la terminal, sobre la misma lógica (filters/tuning.py).

Un menú corto edita el vocabulario, la lista negra, las correcciones y los umbrales de un
`TuningForm`, y el sandbox prueba frases contra lo escrito AHORA, antes de guardar (también el
eco del vocabulario: un renglón que solo es rótulo o lista del vocab sale «DESCARTADA: es eco»).
Se guarda solo con «Guardar y salir». `--probar "frase"` es la versión para scripts: imprime el
veredicto con los filtros guardados y sale con 0 si se acepta y 1 si se descarta. No importa tkinter.
"""

import argparse
from typing import List, Optional, Sequence

from rich.console import Console
from rich.markup import escape
from rich.text import Text

from ..config.manager import ConfigManager
from ..config.schema import AppConfig
from ..filters.samples import random_sample
from ..filters.tuning import (
    THRESHOLD_RANGES,
    VOCAB_HINT,
    SandboxVerdict,
    TuningForm,
    apply_tuning,
    format_ignore,
    test_phrase,
    tuning_form,
    with_common_ignore,
)
from .preguntas import (
    Cancelado,
    confirmar,
    contar,
    elegir,
    imprimir,
    leer_linea,
    preguntar_decimal,
    preguntar_texto,
    texto,
)

NOMBRE = "calibrar"
AYUDA = "calibra los filtros anti-alucinaciones y el vocabulario, con sandbox para probar frases"

AVISO_REINICIO = "Una grabación ya abierta sigue con los filtros anteriores; los nuevos valen desde el próximo arranque."
EJEMPLO = "?"  # en el sandbox, pide una frase de ejemplo armada con el glosario (🎲 de la ventana)

VOCABULARIO, IGNORAR, CORRECCIONES, UMBRALES, PROBAR, GUARDAR, SALIR = range(7)
OPCIONES = [
    "Vocabulario de contexto (guía a Whisper antes de oír)",
    "Frases a ignorar (lista negra de alucinaciones)",
    "Correcciones de léxico («oído_mal=escrito_bien; …»)",
    "Umbrales del decodificador",
    "Probar frases (sandbox, con lo escrito ahora)",
    "Guardar y salir",
    "Salir sin guardar",
]
# (campo de AppConfig, cómo se pregunta) de cada umbral; los rangos salen de THRESHOLD_RANGES.
TEXTO_UMBRAL = [
    ("no_speech_threshold", "Filtro de silencio (no_speech_prob > X descarta)"),
    ("logprob_threshold", "Confianza mínima (avg_logprob < X descarta)"),
    ("compression_ratio_threshold", "Anti-bucles (ratio de compresión > X descarta)"),
]


def agregar_argumentos(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--probar", metavar="FRASE",
        help="pasa una frase por los filtros guardados y sale: 0 si se acepta, 1 si se descarta",
    )


def ejecutar(args: argparse.Namespace, consola: Console, mgr: Optional[ConfigManager] = None) -> int:
    """Punto de entrada del comando. `mgr` se inyecta en las pruebas para no tocar el config.json real."""
    mgr = mgr or ConfigManager()
    config = mgr.load()
    if mgr.last_error:
        imprimir(consola, f"[error]{escape(mgr.last_error)}[/]")
        return 2  # ni probar con filtros de fábrica (veredicto engañoso) ni guardar encima
    if args.probar is not None:
        return probar(config, args.probar, consola)
    try:
        return menu(mgr, config, consola)
    except Cancelado:
        imprimir(consola, "\n[tenue]Cancelado, no se guardó nada.[/]")
        return 1


def probar(config: AppConfig, frase: str, consola: Console) -> int:
    veredicto = test_phrase(tuning_form(config), frase, config.keywords)
    pintar_veredicto(consola, veredicto)
    return 0 if veredicto.accepted else 1


def pintar_veredicto(consola: Console, veredicto: SandboxVerdict) -> None:
    consola.print(Text(texto(consola, veredicto.message), style="ok" if veredicto.accepted else "error"))


# ------------------------------------------------------------------ menú
def menu(mgr: ConfigManager, config: AppConfig, consola: Console) -> int:
    form = tuning_form(config)
    original = tuning_form(config)
    imprimir(consola, "[acento]🎯 Calibración anti-alucinaciones y léxico personal[/]")
    imprimir(consola, (
        "[tenue]Ajusta cómo Whisper interpreta tu vocabulario y filtra frases fantasma en silencios. "
        "Enter conserva el valor actual, «-» vacía un campo y Ctrl+C sale sin guardar.[/]"
    ))
    while True:
        imprimir(consola)
        i = elegir(consola, "¿Qué quieres hacer?", OPCIONES, detalles=detalles(form))
        if i == VOCABULARIO:
            form.vocab = preguntar_texto(consola, "Vocabulario de contexto", form.vocab, ayuda=VOCAB_HINT)
        elif i == IGNORAR:
            editar_ignore(consola, form)
        elif i == CORRECCIONES:
            form.fixes = preguntar_texto(consola, "Correcciones «oído_mal=escrito_bien; …»", form.fixes)
            imprimir(consola, f"  [tenue]{contar(len(form.fixes_dict), 'corrección', 'correcciones')}.[/]")
        elif i == UMBRALES:
            editar_umbrales(consola, form)
        elif i == PROBAR:
            sandbox(consola, form, config.keywords)
        elif i == GUARDAR:
            if form == original:
                imprimir(consola, "[tenue]Sin cambios.[/]")
                return 0
            apply_tuning(config, form)
            mgr.save(config)
            imprimir(consola, f"[ok]✔ Calibración guardada en {escape(str(mgr.path))}.[/] {AVISO_REINICIO}")
            return 0
        else:
            if form != original:
                imprimir(consola, "[tenue]No se guardó nada.[/]")
                return 1
            return 0


def detalles(form: TuningForm) -> List[str]:
    """Lo que hay ahora en cada campo, resumido junto a su opción del menú."""
    vocab = form.vocab.strip()
    return [
        (vocab[:40] + "…" if len(vocab) > 40 else vocab) or "(vacío)",
        contar(len(form.ignore_list), "frase", "frases"),
        contar(len(form.fixes_dict), "corrección", "correcciones"),
        f"silencio {form.no_speech_threshold} · confianza {form.logprob_threshold} · anti-bucles {form.compression_ratio_threshold}",
        "", "", "",
    ]


def editar_ignore(consola: Console, form: TuningForm) -> None:
    form.ignore = preguntar_texto(consola, "Frases a ignorar (separadas por coma)", form.ignore)
    if confirmar(consola, "¿Añadir las frases comunes de vídeos (suscríbete, gracias por ver…)?", False):
        form.ignore = format_ignore(with_common_ignore(form.ignore_list))
    imprimir(consola, f"  [tenue]{contar(len(form.ignore_list), 'frase', 'frases')} en la lista negra.[/]")


def editar_umbrales(consola: Console, form: TuningForm) -> None:
    for campo, etiqueta in TEXTO_UMBRAL:
        lo, hi, paso = THRESHOLD_RANGES[campo]
        setattr(form, campo, preguntar_decimal(consola, f"{etiqueta} [{lo} a {hi}]", getattr(form, campo), lo, hi, paso))


def sandbox(consola: Console, form: TuningForm, keywords: Sequence[str]) -> None:
    """Bucle `frase> `: cada frase pasa por los filtros tal como están escritos ahora; una línea vacía vuelve."""
    imprimir(consola, (
        f"[tenue]Escribe una frase y Enter para ver qué harían los filtros tal como están ahora (sin guardar). "
        f"«{EJEMPLO}» propone una frase de ejemplo; una línea vacía vuelve al menú.[/]"
    ))
    while True:
        frase = leer_linea(consola, "frase> ").strip()
        if not frase:
            return
        if frase == EJEMPLO:
            frase = random_sample(form.vocab, form.fixes_dict, form.ignore_list, keywords)
            imprimir(consola, f"  [tenue]{escape(frase)}[/]")
        pintar_veredicto(consola, test_phrase(form, frase, keywords))
