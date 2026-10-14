"""`daily sintesis`: la ventana «Reagrupar nota» en la terminal, sobre la misma lógica (digest/).

Una copia reagrupada NO resume: ordena por hora, agrupa en tramos y limpia (líneas cortas, eco
del vocabulario, referencias de imagen); el texto es el de la transcripción y la cabecera de la
copia lo dice con cifras. Sin argumentos lista las notas originales (la más reciente primero, la
que se está escribiendo marcada), pregunta el agrupamiento y la limpieza con los mismos valores
por defecto que la ventana (`digest_options`), enseña las cifras y el principio de la vista previa
y escribe al confirmar. Con la nota y `--si` no pregunta nada: para scripts. El original no se
toca nunca: lo garantizan `preview_digest` y `write_digest`, que solo lo leen. No importa tkinter.
"""

import argparse
import datetime as dt
import pathlib
from typing import List, Optional

from rich.console import Console
from rich.markup import escape
from rich.text import Text

from ..config.manager import ConfigManager
from ..digest import (
    DEFAULT_INTERVAL,
    INTERVAL_LABELS,
    INTERVALS,
    MIN_WORDS,
    NOTE_HEADER,
    DerivedSourceError,
    DigestOptions,
    DigestPreview,
    digest_options,
    list_originals,
    note_row,
    preview_digest,
    unique_digest_path,
    write_digest,
)
from .preguntas import Cancelado, confirmar, elegir, imprimir, texto

NOMBRE = "sintesis"
AYUDA = "reagrupa una nota: copia ordenada por hora y agrupada por tramos (no resume); el original no se toca"

LINEAS_PREVIA = 10  # líneas del cuerpo que se enseñan antes de confirmar
# Sin sesión en este proceso no se sabe qué nota se está escribiendo: se toma por «en curso» la
# más reciente si se escribió en ella hace menos de este tiempo (cada línea renueva su fecha).
EN_CURSO_MIN = 30


def agregar_argumentos(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("nota", nargs="?", help="ruta o nombre de la nota original; sin ella se elige de la lista")
    parser.add_argument(
        "--cada", type=int, choices=INTERVALS, metavar="MIN",
        help=f"agrupa en tramos de {', '.join(str(m) for m in INTERVALS)} minutos (0 = sin agrupar; "
        f"por defecto {DEFAULT_INTERVAL})",
    )
    # Las banderas invierten lo que la ventana trae marcado por defecto (digest_options).
    parser.add_argument("--sin-unir", action="store_true", help="no une las líneas seguidas del mismo hablante")
    parser.add_argument("--con-horas", action="store_true", help="HH:MM:SS en cada línea en vez de la hora corta [HH:MM] por párrafo")
    parser.add_argument("--con-imagenes", action="store_true", help="conserva las referencias de imagen (por defecto texto puro)")
    parser.add_argument("--con-cortas", action="store_true", help=f"conserva las líneas de menos de {MIN_WORDS} palabras")
    parser.add_argument("--con-ecos", action="store_true", help="conserva el eco del vocabulario («Términos.», listas del vocab)")
    parser.add_argument("--si", action="store_true", help="no pide confirmación (con la nota, no pregunta nada)")


def ejecutar(
    args: argparse.Namespace,
    consola: Console,
    mgr: Optional[ConfigManager] = None,
    nota_activa: Optional[pathlib.Path] = None,
) -> int:
    """Punto de entrada. `mgr` se inyecta en las pruebas; `nota_activa` la puede pasar quien sepa cuál se escribe."""
    mgr = mgr or ConfigManager()
    config = mgr.load()
    if mgr.last_error:
        imprimir(consola, f"[error]{escape(mgr.last_error)}[/]")
        return 1  # la carpeta de notas sería la de fábrica, no la del usuario
    try:
        return sintetizar(args, config.notes_dir, consola, nota_activa, vocab=config.vocab)
    except Cancelado:
        imprimir(consola, "\n[tenue]Cancelado, no se creó nada.[/]")
        return 1


def sintetizar(
    args: argparse.Namespace,
    notes_dir: str,
    consola: Console,
    nota_activa: Optional[pathlib.Path],
    vocab: str = "",
) -> int:
    """`vocab` es el vocabulario con que se grabó: con él se reconoce su eco al limpiar."""
    if args.nota:
        origen = resolver_nota(args.nota, notes_dir)
        if origen is None:
            imprimir(consola, f"[error]No existe la nota «{escape(args.nota)}» (ni en {escape(notes_dir)}).[/]")
            return 1
    else:
        origen = elegir_nota(consola, notes_dir, nota_activa)
        if origen is None:
            return 1

    # Las opciones se preguntan solo si no se fijaron por argumentos; las banderas dan los valores iniciales.
    if args.si or args.cada is not None:
        opts = opciones_desde_args(args, vocab)
    else:
        opts = preguntar_opciones(consola, args, vocab)
    try:
        vista = preview_digest(origen, opts)
    except DerivedSourceError as e:
        imprimir(consola, f"[error]⚠ {escape(str(e))}[/]")
        return 1
    except OSError as e:
        imprimir(consola, f"[error]No se pudo leer {escape(str(origen))}: {escape(str(e))}[/]")
        return 1

    imprimir(consola, f"[tenue]{escape(vista.stats())}[/]")
    if not args.si:
        mostrar_previa(consola, vista)
        destino = unique_digest_path(origen, opts)
        imprimir(consola, (
            f"Se creará [acento]{escape(destino.name)}[/] en la misma carpeta "
            f"[tenue](si ya existe se numera; nunca se sobrescribe)[/]."
        ))
        imprimir(consola, (
            "[tenue]⚠ Las copias reagrupadas son derivadas y con pérdida: para otro agrupamiento, regenera "
            "desde la nota original, nunca desde otra copia. No es un resumen: es el mismo texto.[/]"
        ))
        if not confirmar(consola, "¿Generar la copia reagrupada?", True):
            imprimir(consola, "[tenue]No se creó nada.[/]")
            return 1
    try:
        destino = write_digest(origen, opts)
    except (DerivedSourceError, OSError) as e:
        imprimir(consola, f"[error]No se generó: {escape(str(e))}[/]")
        return 1
    imprimir(consola, f"[ok]✅ Creada {escape(str(destino))}[/]  [tenue]El original sigue intacto.[/]")
    return 0


# ------------------------------------------------------------------ qué nota
def resolver_nota(nombre: str, notes_dir: str) -> Optional[pathlib.Path]:
    """La ruta que significa `nombre`: tal cual, dentro de la carpeta de notas, o con .md añadido."""
    candidatos = [pathlib.Path(nombre), pathlib.Path(notes_dir) / nombre, pathlib.Path(notes_dir) / f"{nombre}.md"]
    return next((c for c in candidatos if c.is_file()), None)


def en_curso(notas: List[pathlib.Path], ahora: Optional[dt.datetime] = None) -> Optional[str]:
    """Nombre de la nota que se está escribiendo, si la más reciente cambió hace menos de EN_CURSO_MIN."""
    if not notas:
        return None
    ahora = ahora or dt.datetime.now()
    ultima = dt.datetime.fromtimestamp(notas[0].stat().st_mtime)
    return notas[0].name if ahora - ultima < dt.timedelta(minutes=EN_CURSO_MIN) else None


def elegir_nota(consola: Console, notes_dir: str, nota_activa: Optional[pathlib.Path]) -> Optional[pathlib.Path]:
    notas = list_originals(notes_dir)
    if not notas:
        imprimir(consola, f"[error]No hay notas originales en {escape(notes_dir)}.[/]")
        return None
    activa = pathlib.Path(nota_activa).name if nota_activa else en_curso(notas)
    filas = [note_row(p, activa) for p in notas]
    i = elegir(
        consola, "Nota origen (solo se lee; las copias reagrupadas no se listan)", filas, 0, cabecera=NOTE_HEADER
    )
    return notas[i]


# ------------------------------------------------------------------ qué opciones
def opciones_desde_args(args: argparse.Namespace, vocab: str = "") -> DigestOptions:
    """Las banderas sobre los valores por defecto de la ventana (`digest_options`)."""
    cada = DEFAULT_INTERVAL if args.cada is None else args.cada
    return digest_options(
        cada,
        merge=not args.sin_unir,
        strip_stamps=not args.con_horas,
        keep_captures=args.con_imagenes,
        drop_short=not args.con_cortas,
        drop_echo=not args.con_ecos,
        vocab=vocab,
    )


def preguntar_opciones(consola: Console, args: argparse.Namespace, vocab: str = "") -> DigestOptions:
    """Agrupamiento y limpieza como en la ventana; Enter deja lo que dicen las banderas (o lo de siempre)."""
    imprimir(consola)
    imprimir(consola, (
        "[tenue]Cada bloque pasa a ser un encabezado como ## 09:30 - 09:45 con sus líneas debajo. "
        "«Sin agrupar» solo aplica la limpieza.[/]"
    ))
    etiquetas = [INTERVAL_LABELS[m] for m in INTERVALS]
    cada = INTERVALS[elegir(consola, "Agrupamiento temporal", etiquetas, INTERVALS.index(DEFAULT_INTERVAL))]
    merge = confirmar(consola, "¿Unir líneas seguidas del mismo hablante?", not args.sin_unir)
    # sin agrupar, la hora completa es lo único que ordena y se conserva siempre: no se pregunta
    strip_stamps = confirmar(consola, "¿Hora corta [HH:MM] por párrafo, en vez de HH:MM:SS por línea?", not args.con_horas) if cada else True
    sin_imagenes = confirmar(consola, "¿Quitar las referencias de imagen (texto puro)?", not args.con_imagenes)
    drop_short = confirmar(consola, f"¿Descartar las líneas de menos de {MIN_WORDS} palabras?", not args.con_cortas)
    drop_echo = confirmar(consola, "¿Quitar el eco del vocabulario («Términos.», listas del vocab)?", not args.con_ecos)
    return digest_options(
        cada, merge=merge, strip_stamps=strip_stamps, keep_captures=not sin_imagenes,
        drop_short=drop_short, drop_echo=drop_echo, vocab=vocab,
    )


# ------------------------------------------------------------------ vista previa
def cuerpo(markdown: str) -> List[str]:
    """Las líneas de la copia sin la cabecera (origen, generado…): lo que interesa ver antes de confirmar."""
    lineas = markdown.splitlines()
    if lineas and lineas[0] == "---":
        try:
            lineas = lineas[lineas.index("---", 1) + 1:]
        except ValueError:
            pass
    while lineas and not lineas[0].strip():
        lineas.pop(0)
    return lineas


def mostrar_previa(consola: Console, vista: DigestPreview) -> None:
    imprimir(consola)
    lineas = cuerpo(vista.markdown)
    for linea in lineas[:LINEAS_PREVIA]:
        if linea.startswith("#"):
            estilo = "acento"
        elif linea.startswith(">"):
            estilo = "tenue"
        elif "![](" in linea:
            estilo = "mic"
        else:
            estilo = "texto"
        consola.print(Text(texto(consola, linea), style=estilo))
    if len(lineas) > LINEAS_PREVIA:
        imprimir(consola, f"[tenue]… ({len(lineas) - LINEAS_PREVIA} líneas más)[/]")
    imprimir(consola)
