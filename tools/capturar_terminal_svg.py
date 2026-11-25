"""Las pantallas de terminal como las pinta una terminal moderna (truecolor, tema oscuro), en SVG.

Cada comando corre en este proceso con una consola que graba, con un config.json sintético y las
respuestas guionizadas (se escriben tras su pregunta, como si se tecleasen).

uso: python tools/capturar_terminal_svg.py [carpeta_salida]   (por defecto docs/capturas-terminal/svg)
"""
import builtins
import io
import os
import pathlib
import shutil
import sys
from types import SimpleNamespace

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(REPO))
os.environ.pop("NO_COLOR", None)
from capturar_terminal import preparar  # noqa: E402

RAIZ = preparar()
os.environ["RECORDER_CONFIG"] = str(RAIZ / "config.json")

from rich.console import Group  # noqa: E402
from rich.text import Text  # noqa: E402

from recorder.cli import app, configurar, pantallas  # noqa: E402
from recorder.cli.consola import make_console  # noqa: E402
from recorder.config.manager import ConfigManager  # noqa: E402

VENTANAS = ["Daily | Microsoft Teams", "Presentación - PowerPoint"]  # sintéticas: nada de lo abierto de verdad
configurar.window_titles = lambda: list(VENTANAS)
pantallas.configurar.window_titles = configurar.window_titles

SALIDA = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "capturas-terminal" / "svg"
SALIDA.mkdir(parents=True, exist_ok=True)


def consola(ancho=100, alto=30):
    return make_console(ascii_mode=False, record=True, file=io.StringIO(), width=ancho, height=alto,
                        force_terminal=True, color_system="truecolor", legacy_windows=False, no_color=False)


def guardar(c, nombre, titulo):
    c.save_svg(str(SALIDA / f"{nombre}.svg"), title=titulo, clear=False)
    (SALIDA / f"{nombre}.txt").write_text(c.export_text(), encoding="utf-8")
    print(nombre)


def comando(nombre, respuestas, argv=(), ancho=100):
    c = consola(ancho)
    pendientes = iter(respuestas)

    def teclear(_prompt=""):
        try:
            r = next(pendientes)
        except StopIteration:
            raise EOFError
        c.print(Text(r))  # lo tecleado, tras la pregunta
        return r

    original = builtins.input
    builtins.input = teclear
    try:
        c.print(Text(f"> daily {nombre} {' '.join(argv)}".rstrip(), style="tenue"))
        app.ejecutar_comando(nombre, argv, c, app.cargar_comandos())
    finally:
        builtins.input = original
    guardar(c, f"{nombre}{'-' + str(ancho) if ancho != 100 else ''}", f"daily {nombre}")


comando("config", ["2", "", "", "", "4", "", "", "", "", "1", "", "", "bloqueo, demo", "n", "8"])
comando("calibrar", ["6", "?", "gracias por ver", "", "4", "", "", "", "8"])
comando("calibrar", ["6", "?", "", "8"], ancho=60)
comando("sintesis", ["", "", "", "", "", "", "", "n"])
comando("recomendar", [])

# Las pantallas del menú nuevo, como referencia del estilo
mgr = ConfigManager(RAIZ / "config.json")
c = consola()
t = pantallas.Terminal(c, app.cargar_comandos(), mgr, leer_tecla=lambda: None)
t._refrescar_cabecera()
c.print(Group(*t.marco()))
guardar(c, "menu-inicio", "daily menu")
c = consola()
t.consola = c
entorno = configurar.Entorno(["(todas las pantallas)", "Pantalla 1: 1920×1080 en (0, 0)"], VENTANAS,
                             ["Altavoces", "Auriculares USB"], ["Micrófono del portátil"], pantallas.cached_hardware())
t._detectar = lambda: entorno
t.entorno()
t._hilo_entorno.join()
t.abrir(pantallas.Opciones(t))
c.print(Group(*t.marco()))
guardar(c, "menu-opciones", "daily menu · Opciones")

# La grabación (`daily`): líneas, pie y panel de opciones, con una sesión de mentira
from recorder.cli.live import TECLAS, Panel, PantallaEnVivo  # noqa: E402
from recorder.metricas import Metricas, MotorEfectivo  # noqa: E402
from recorder.session import StatusSnapshot  # noqa: E402

cfg = mgr.load()
nota = pathlib.Path(cfg.notes_dir) / "daily_2026-11-24_09-30.md"
c = consola()
p = PantallaEnVivo(SimpleNamespace(pa=None, file_path=nota, config=cfg), consola=c, leer_tecla=lambda: None, entorno=SimpleNamespace())
c.print(Text("> daily", style="tenue"))
p._cabecera()
p._hecho("09:30:01", "Fuentes: 🔊 Altavoces · 🎤 Micrófono del portátil")
p._linea("09:30:05", "out", "Buenos días, empezamos con el estado del despliegue de la versión nueva.", [])
p._linea("09:30:41", "mic", "Ayer terminé la revisión de QA del módulo de notas y quedó todo en verde.", [])
p._linea("09:32:02", "out", "Hay un bloqueo con el servidor de pruebas, lo vemos después de la daily.", ["bloqueo"])
p._hecho("09:33:10", "⏸ pausa: no se captura audio nuevo")
st = StatusSnapshot(
    base_status="● Escuchando", status_highlight=True, pending=1, pending_summary="1 fragmento (~6 s de audio)",
    busy=True, paused=False, draining=False, finished=False, awake=True, errors=0, mic=True,
    levels={"out": 0.55, "mic": 0.12}, attempts={}, muted=None, file_path=nota,
    metricas=Metricas(MotorEfectivo("faster-whisper", "cpu", "small", 5, 4), 2.6, 1.9, 14.0, 31.0, 912.0, None, None, 1, 6.0),
)
c.print(p._pie(st, TECLAS))
c.print(Text("── con [o] ──", style="tenue"))
p._panel = Panel()
c.print(p._pie(st, TECLAS))
p._panel = Panel(seccion="out", opciones=["(predeterminado de Windows)", "Altavoces", "Auriculares USB"], actual=1)
c.print(p._pie(st, TECLAS))
guardar(c, "grabar", "daily")
shutil.rmtree(RAIZ, ignore_errors=True)  # el config.json y las notas sintéticas
