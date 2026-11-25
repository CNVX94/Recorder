"""Capturas de las pantallas de terminal de Recorder en una consola real (conhost), para comparar antes y después.

Cada escenario abre `conhost cmd /k "... python recorder.py <args>"` con un config.json sintético,
se engancha a su consola, teclea con WriteConsoleInputW y en cada paso guarda el búfer como texto
y la ventana como PNG (PrintWindow, recorder.actions.screenshot.grab_window).

Abre ventanas de consola en el escritorio mientras corre (unos 3 min con todos los escenarios) y la grabación
carga el modelo de verdad; no toca el config.json del usuario ni sus notas (todo es sintético y temporal).
El Ctrl+C inyectado como tecla no equivale al del teclado: compruébalo a mano.

uso: python tools/capturar_terminal.py [--powershell | --cmd] [--lista] [carpeta_salida] [escenario ...]
(por defecto docs/capturas-terminal y cmd). --powershell lanza cada escenario en Windows PowerShell
(`powershell.exe -NoProfile -NoExit -Command ...`), la consola del día a día; en ambas se quita NO_COLOR y el
prompt enseña la raíz del repositorio, no la copia de trabajo desde la que se lance. --lista escribe los
escenarios y sale; -h o --help, esta ayuda.

Los escenarios «grabar-*» graban de verdad (carga el modelo y capta el audio que suene en el equipo): antes de lanzarlos
comprueba que no suena nada ni hay una llamada en curso. «ventana» abre la ventana gráfica y la cierra con WM_CLOSE.
"""
import ctypes
import ctypes.wintypes as wt
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from recorder.actions.screenshot import grab_window  # noqa: E402
from recorder.config.schema import AppConfig  # noqa: E402

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)
k32.GetConsoleWindow.restype = ctypes.c_void_p
k32.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
k32.CreateFileW.restype = ctypes.c_void_p


class KEY(ctypes.Structure):
    _fields_ = [("down", wt.BOOL), ("rep", wt.WORD), ("vk", wt.WORD), ("scan", wt.WORD), ("ch", wt.WCHAR), ("state", wt.DWORD)]


class REC(ctypes.Structure):
    _fields_ = [("tipo", wt.WORD), ("key", KEY)]


class PE32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("pid", wt.DWORD), ("heap", ctypes.c_void_p),
                ("mod", wt.DWORD), ("threads", wt.DWORD), ("ppid", wt.DWORD), ("prio", ctypes.c_long),
                ("flags", wt.DWORD), ("exe", wt.WCHAR * 260)]


class CSBI(ctypes.Structure):
    _fields_ = [("size", wt._COORD), ("cursor", wt._COORD), ("attr", wt.WORD), ("win", wt.SMALL_RECT), ("max", wt._COORD)]


def pythons():
    snap = k32.CreateToolhelp32Snapshot(2, 0)
    pe = PE32(); pe.dwSize = ctypes.sizeof(pe)
    out = set()
    ok = k32.Process32FirstW(ctypes.c_void_p(snap), ctypes.byref(pe))
    while ok:
        if pe.exe.lower() == "python.exe":
            out.add(pe.pid)
        ok = k32.Process32NextW(ctypes.c_void_p(snap), ctypes.byref(pe))
    k32.CloseHandle(ctypes.c_void_p(snap))
    return out


ESPECIALES = {"abajo": (0x28, 0x50, "\0", 0x100), "arriba": (0x26, 0x48, "\0", 0x100), "izquierda": (0x25, 0x4B, "\0", 0x100),
              "derecha": (0x27, 0x4D, "\0", 0x100), "fin": (0x23, 0x4F, "\0", 0x100), "enter": (0x0D, 0x1C, "\r", 0), "esc": (0x1B, 0x01, "\x1b", 0),
              "retroceso": (0x08, 0x0E, "\x08", 0), "ctrl+c": (0x43, 0x2E, "\x03", 0x0008),
              "repag": (0x21, 0x49, "\0", 0x100), "avpag": (0x22, 0x51, "\0", 0x100), "inicio": (0x24, 0x47, "\0", 0x100)}


def h(nombre):
    return k32.CreateFileW(nombre, 0xC0000000, 3, None, 3, 0, None)


def pulsar(k, pausa=0.25):
    hin = h("CONIN$")
    if k in ESPECIALES:
        vk, scan, ch, st = ESPECIALES[k]
    else:
        vk = u32.VkKeyScanW(ord(k)) & 0xFF
        scan, ch, st = u32.MapVirtualKeyW(vk, 0), k, 0
    recs = (REC * 2)(REC(1, KEY(True, 1, vk, scan, ch, st)), REC(1, KEY(False, 1, vk, scan, ch, st)))
    n = wt.DWORD()
    k32.WriteConsoleInputW(ctypes.c_void_p(hin), recs, 2, ctypes.byref(n))
    k32.CloseHandle(ctypes.c_void_p(hin))
    time.sleep(pausa)


def pantalla():
    hout = h("CONOUT$")
    info = CSBI()
    k32.GetConsoleScreenBufferInfo(ctypes.c_void_p(hout), ctypes.byref(info))
    ancho = info.win.Right - info.win.Left + 1
    lineas = []
    for y in range(info.win.Top, info.win.Bottom + 1):
        buf = ctypes.create_unicode_buffer(ancho + 1)
        n = wt.DWORD()
        k32.ReadConsoleOutputCharacterW(ctypes.c_void_p(hout), buf, ancho, wt._COORD(info.win.Left, y), ctypes.byref(n))
        lineas.append(buf.value[:n.value].rstrip())
    k32.CloseHandle(ctypes.c_void_p(hout))
    return lineas


# ------------------------------------------------------------------ entorno sintético
NOTA = """# Daily 2026-11-24 09:30

- **09:30:05** Buenos días, empezamos con el estado del despliegue de la versión nueva.
- **09:30:41** 🎤 Ayer terminé la revisión de QA del módulo de notas y quedó todo en verde.
- **09:31:10** Sí.
- **09:32:02** Hay un bloqueo con el servidor de pruebas, lo vemos después de la daily.
  - 📸 `bloqueo` → ![](capturas/2026-11-24_09-32-02_bloqueo.png)
- **09:47:15** 🎤 Términos.
- **09:47:30** Para la demo del viernes falta la parte de capturas por palabra clave.
- **09:52:00** 🎤 Me encargo yo, lo dejo listo el jueves para revisarlo juntos.
"""


def preparar(claro: bool = False) -> pathlib.Path:
    raiz = pathlib.Path(tempfile.mkdtemp(prefix="evid"))
    notas = raiz / "notas"
    (notas / "capturas").mkdir(parents=True)
    (notas / "daily_2026-11-24_09-30.md").write_text(NOTA, encoding="utf-8")
    (notas / "daily_2026-11-21_09-30.md").write_text(NOTA.replace("2026-11-24", "2026-11-21"), encoding="utf-8")
    cfg = AppConfig()
    cfg.notes_dir, cfg.caps_dir = str(notas), str(notas / "capturas")
    cfg.vocab = "Recorder, Teams, QA, despliegue, demo"
    cfg.ignore = ["suscríbete", "gracias por ver"]
    cfg.fixes = {"cuba": "QA"}
    if claro:
        cfg.theme = "claro"
    (raiz / "config.json").write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return raiz


# ------------------------------------------------------------------ escenarios
# Cada paso: ("teclas", [...]) | ("texto", "linea") (teclea y Enter) | ("foto", nombre, espera) | ("ctrlc",)
E, ENT = "esc", "enter"
# Las filas del Inicio, de arriba abajo; las pantallas se abren con ↑/↓ y Enter (los números siguen siendo atajos, pero no son el camino).
FILAS = {"grabar": 0, "opciones": 1, "calibrar": 2, "reagrupar": 3, "recomendacion": 4, "ventana": 5, "rendimiento": 6, "ayuda": 7, "salir": 8}


def ir(destino, desde="grabar"):
    """Las teclas que llevan la fila elegida del Inicio de `desde` a `destino` y la abren."""
    d = FILAS[destino] - FILAS[desde]
    return ["abajo" if d > 0 else "arriba"] * abs(d) + [ENT]


BASE = [
    ("foto", "inicio", 5), ("teclas", ir("opciones")), ("foto", "opciones-cargando", 0.3), ("foto", "opciones", 3),
    ("teclas", ["abajo", "abajo", ENT, "e", "r", "r", "o", "r", "izquierda", "izquierda"]), ("foto", "texto-con-cursor", 1),
    ("teclas", [ENT]), ("foto", "con-cambios", 1),
    ("teclas", ["abajo", ENT]), ("foto", "lista-de-seleccion", 1.5),
    ("teclas", [E, "abajo", " "]), ("foto", "interruptor", 1),
    ("teclas", [E]), ("foto", "aviso-sin-guardar", 1),
    ("teclas", ["g"]), ("foto", "confirmar", 1),
    ("teclas", [ENT]), ("foto", "guardado", 1),
    ("teclas", [E] + ir("rendimiento", "opciones")), ("foto", "rendimiento", 8),
    ("teclas", [E] + ir("ayuda", "rendimiento")), ("foto", "ayuda", 1.5), ("teclas", ["abajo"] * 6), ("foto", "ayuda-bajando", 1),
]
# Del Inicio a cada pantalla y de vuelta, con flechas y Enter (nada debe quedar en el historial).
RECORRIDO = [
    ("foto", "inicio", 5),
    ("teclas", ir("calibrar")), ("foto", "calibrar", 3), ("teclas", [E]), ("foto", "de-vuelta-en-inicio", 1.5),
    ("teclas", ir("reagrupar", "calibrar")), ("foto", "reagrupar", 2), ("teclas", [E]),
    ("teclas", ir("recomendacion", "reagrupar")), ("foto", "recomendacion", 3), ("teclas", [E]),
    ("teclas", ir("opciones", "recomendacion")), ("foto", "opciones", 3), ("teclas", [E]),
    ("teclas", ir("rendimiento", "opciones")), ("foto", "rendimiento", 4), ("teclas", [E]),
    ("teclas", ir("ayuda", "rendimiento")), ("foto", "ayuda", 1.5), ("teclas", ["abajo"] * 3), ("foto", "ayuda-bajando", 1),
    ("teclas", ["fin"]), ("foto", "ayuda-al-final", 1), ("teclas", [E]), ("teclas", [E]), ("foto", "historial-limpio", 2),
]
# Comando suelto: abre su pantalla, baja, Esc sale a la terminal y el prompt queda limpio.
def suelto(nombre, espera=4):
    return [("foto", nombre, espera), ("teclas", ["abajo"]), ("foto", "bajando", 1), ("teclas", [E]), ("foto", "prompt", 2)]


# Grabar de verdad desde el Inicio (carga el modelo; capta el audio que suene en el equipo, así que solo con el equipo callado).
GRABAR = [
    ("foto", "inicio", 5), ("teclas", ir("grabar")), ("foto", "arranque", 4), ("foto", "escuchando", 25),
    ("teclas", ["repag"]), ("foto", "revisando-repag", 1.5), ("teclas", ["fin"]),
    ("teclas", ["o"]), ("foto", "panel-opciones", 1.5), ("teclas", ["1"]), ("foto", "panel-salida", 2), ("teclas", [E, E]),
    ("teclas", ["m"]), ("foto", "rendimiento", 4), ("teclas", [E]),
    ("teclas", ["?"]), ("foto", "ayuda", 1.5), ("teclas", [E]),
    ("teclas", ["p"]), ("foto", "pausa", 2), ("teclas", ["p"]), ("teclas", ["q"]), ("foto", "tras-salir", 6),
    ("teclas", [E]), ("foto", "historial-limpio", 2),
]
ESCENARIOS = {
    "menu": ("menu", 100, 30, RECORRIDO),
    "config": ("config", 100, 30, [("foto", "opciones", 5), ("teclas", ["abajo", "abajo"]), ("foto", "bajando", 1), ("teclas", [E]), ("foto", "prompt", 2)]),
    "config-ver": ("config --ver", 100, 30, [("foto", "ver", 3)]),
    "calibrar": ("calibrar", 100, 30, suelto("calibrar")),
    "calibrar-60": ("calibrar", 60, 26, [("foto", "calibrar", 4), ("teclas", [E]), ("foto", "prompt", 2)]),
    "sintesis": ("sintesis", 100, 30, suelto("reagrupar")),
    "sintesis-60": ("sintesis", 60, 26, [("foto", "reagrupar", 4), ("teclas", [ENT]), ("foto", "vista-previa", 2), ("teclas", [E, E]), ("foto", "prompt", 2)]),
    # Reagrupar entre 80 y 96 columnas: la especificación pone el paso a dos columnas en 96, el código en 80.
    "sintesis-90": ("sintesis", 90, 30, [("foto", "reagrupar", 4), ("teclas", [ENT]), ("foto", "vista-previa", 2), ("teclas", [E, E]), ("foto", "prompt", 2)]),
    "sintesis-100": ("sintesis", 100, 30, [("foto", "reagrupar", 4), ("teclas", [ENT]), ("foto", "vista-previa", 2), ("teclas", [E, E]), ("foto", "prompt", 2)]),
    # Menú y Opciones a 100 y 60 columnas, y el menú con --ascii: la evidencia del color real y los símbolos seguros.
    "inicio-100": ("menu", 100, 30, [("foto", "inicio", 5), ("teclas", ir("opciones")), ("foto", "opciones", 3), ("teclas", [E, E])]),
    "inicio-60": ("menu", 60, 24, [("foto", "inicio", 5), ("teclas", ir("opciones")), ("foto", "opciones", 3), ("teclas", [E, E])]),
    "inicio-ascii": ("--ascii menu", 100, 30, [("foto", "inicio", 5), ("teclas", ir("opciones")), ("foto", "opciones", 3), ("teclas", [E, E])]),
    # El azul #012456 del acceso directo de PowerShell (con --powershell): con color real se pinta el fondo propio; con --ascii, no.
    "inicio-azul": ("menu", 100, 30, [("foto", "inicio", 5), ("teclas", ir("opciones")), ("foto", "opciones", 3), ("teclas", [E, E]), ("foto", "prompt", 2)]),
    "inicio-ascii-azul": ("--ascii menu", 100, 30, [("foto", "inicio", 5), ("teclas", ir("opciones")), ("foto", "opciones", 3), ("teclas", [E, E]), ("foto", "prompt", 2)]),
    # Tema claro: el config sintético lleva theme «claro» (escenarios con el sufijo -claro).
    "inicio-claro": ("menu", 100, 30, [("foto", "inicio", 5), ("teclas", ir("opciones")), ("foto", "opciones", 3), ("teclas", [E]),
                                       ("teclas", ir("calibrar", "opciones")), ("foto", "calibrar", 3), ("teclas", [E, E])]),
    # La base común del paso 3: Opciones con sus componentes (texto con cursor, lista de selección, interruptor,
    # confirmación «antes → después»), el aviso, Rendimiento (tendencia) y Ayuda; en la consola de PowerShell y con --ascii.
    "base-100": ("menu", 100, 30, BASE),
    "base-60": ("menu", 60, 24, BASE),
    "base-ascii": ("--ascii menu", 100, 30, BASE),
    # «Medir mi equipo» (paso 6 del plan de rendimiento): de verdad, con los modelos de la caché; dura ~2,5 min y carga la CPU.
    # Rendimiento → Enter abre la medición; al terminar, Enter pide la confirmación «antes → después» y Esc no guarda nada.
    # Tras preparar, un Enter: si el equipo estaba ocupado (hay más de un 15 % de procesador ajeno) es «Medir de todos
    # modos»; si no, la medición ya va y Enter no hace nada (mientras mide solo vale Esc).
    "medir-100": ("menu", 100, 30, [
        ("foto", "inicio", 4), ("teclas", ir("rendimiento")), ("foto", "rendimiento", 5), ("teclas", [ENT]),
        ("foto", "preparando", 0.5), ("foto", "tras-preparar", 12), ("teclas", [ENT]),
        ("foto", "progreso", 10), ("foto", "progreso-avanzado", 60),
        ("foto", "resultados", 90), ("teclas", [ENT]), ("foto", "confirmar", 1.5), ("teclas", [E]),
        ("teclas", ["abajo", ENT]), ("foto", "medir-otra-vez", 5), ("teclas", [E, E, E]),
    ]),
    "medir-60": ("menu", 60, 26, [
        ("teclas", ir("rendimiento")), ("foto", "rendimiento", 4), ("teclas", [ENT]), ("foto", "tras-preparar", 12), ("teclas", [ENT]),
        ("foto", "progreso", 15), ("foto", "resultados", 140), ("teclas", [ENT]), ("foto", "confirmar", 1.5), ("teclas", [E, E, E]),
    ]),
    "medir-ascii": ("--ascii menu", 100, 30, [
        ("teclas", ir("rendimiento")), ("foto", "rendimiento", 4), ("teclas", [ENT]), ("foto", "tras-preparar", 12), ("teclas", [ENT]),
        ("foto", "progreso", 15), ("foto", "resultados", 140), ("teclas", [E, E, E]),
    ]),
    # Los ajustes de rendimiento en Opciones: hilos (con el aviso de núcleos rápidos y lentos), prioridad y su lista.
    "ajustes-100": ("menu", 100, 30, [
        ("teclas", ir("opciones")), ("foto", "opciones", 4), ("teclas", ["abajo"] * 9), ("foto", "hilos-con-aviso", 1),
        ("teclas", ["abajo", "abajo"]), ("foto", "prioridad", 1), ("teclas", [ENT]), ("foto", "prioridad-lista", 1),
        ("teclas", ["2", "g"]), ("foto", "confirmar", 1.5), ("teclas", [E, E, E, E]),
    ]),
    "recomendar": ("recomendar", 100, 30, [("foto", "recomendacion", 5), ("teclas", [E]), ("foto", "prompt", 2)]),
    # Modo línea con un terminal real (argumento de script): pregunta en línea; Ctrl+C la corta sin traza.
    "recomendar-aplicar": ("recomendar --aplicar", 100, 30, [("foto", "en-linea", 5)]),
    # Ctrl+C en una pregunta de modo línea (la nota como argumento de script): sale sin traza y el prompt queda limpio.
    "sintesis-linea": ("sintesis {nota}", 100, 30, [("foto", "pregunta", 5), ("ctrlc",), ("foto", "tras-ctrl-c", 2)]),
    "ayuda": ("-h", 100, 30, [("foto", "daily-h", 2)]),
    "ayuda-menu": ("menu -h", 100, 30, [("foto", "menu-h", 2)]),
    "historial": ("--historial", 100, 30, [("foto", "arranque", 4), ("foto", "escuchando", 15), ("teclas", ["q"]), ("foto", "salida", 6)]),
    # Grabar de verdad: sin argumentos (pantalla completa) y desde el Inicio (vuelve al Inicio con el resumen).
    "grabar": ("", 100, 30, [
        ("foto", "arranque", 4), ("foto", "escuchando", 25), ("teclas", ["o"]), ("foto", "panel-opciones", 1.5),
        ("teclas", ["1"]), ("foto", "panel-salida", 2), ("teclas", [E, E]), ("teclas", ["p"]),
        ("foto", "pausa", 2), ("teclas", ["p"]), ("teclas", ["q"]), ("foto", "salida", 6),
    ]),
    "grabar-menu": ("menu", 100, 30, GRABAR),
    "grabar-60": ("", 60, 26, [("foto", "arranque", 4), ("foto", "escuchando", 20), ("teclas", ["q"]), ("foto", "salida", 6)]),
    # La ventana gráfica desde el Inicio: «La ventana está abierta» y, al cerrarla, vuelta al Inicio con su aviso.
    "ventana": ("menu", 100, 30, [
        ("foto", "inicio", 5), ("teclas", ir("ventana")), ("foto", "ventana-abierta", 8), ("cerrar",), ("foto", "tras-cerrar", 4),
        ("teclas", [E]), ("foto", "historial-limpio", 2),
    ]),
}
# Los que usan el tema claro.
CLAROS = {"inicio-claro"}
# Los que se lanzan sobre el azul de PowerShell (solo con --powershell): con 16 colores, sin fondo propio.
AZULES = {"inicio-azul", "inicio-ascii-azul"}


def raiz_mostrada() -> str:
    """La raíz del repositorio que enseña el prompt: si se lanza desde una copia de trabajo (git worktree), la del
    repositorio principal, que es donde vive el usuario."""
    try:
        comun = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
        return str(pathlib.Path(comun).parent)
    except (OSError, subprocess.CalledProcessError):
        return str(REPO)


RAIZ_MOSTRADA = raiz_mostrada()


# El acceso directo «Windows PowerShell» del menú Inicio pinta la consola de azul #012456 con texto #EEEDF0: redefine las
# casillas 5 (magenta, el fondo) y 3 (amarillo, el texto). Se imita con OSC 4 y `color 53` (fondo y texto por defecto de la consola, que es lo que ve también la pantalla alternativa).
AZUL_POWERSHELL = ("[Console]::Write([char]27+']4;5;#012456'+[char]27+'\\'+[char]27+']4;3;#EEEDF0'+[char]27+'\\'); "
                   "cmd /c color 53; Clear-Host; ")


def lanzador(powershell, raiz, args, cols, lineas, azul=False):
    """La línea que abre conhost: cmd o Windows PowerShell, con el config sintético y sin NO_COLOR."""
    config = raiz / "config.json"
    args = args.replace("{nota}", str(raiz / "notas" / "daily_2026-11-24_09-30.md"))  # la nota sintética (en %TEMP%, sin espacios)
    if powershell:
        orden = (f"mode con: cols={cols} lines={lineas}; $env:RECORDER_CONFIG='{config}'; {AZUL_POWERSHELL if azul else ''}"
                 f"Remove-Item Env:NO_COLOR -ErrorAction SilentlyContinue; function prompt {{ 'PS {RAIZ_MOSTRADA}> ' }}; "
                 f"& '{sys.executable}' recorder.py {args}")
        return ["conhost.exe", "powershell.exe", "-NoProfile", "-NoExit", "-Command", orden]
    orden = (f"mode con: cols={cols} lines={lineas}& set RECORDER_CONFIG={config}& set NO_COLOR=& prompt {RAIZ_MOSTRADA}$G& "
             f"{sys.executable} recorder.py {args}")
    return ["conhost.exe", "cmd", "/k", orden]


def cerrar_ventanas(pid):
    """Cierra (WM_CLOSE) las ventanas visibles del proceso `pid` que no son la consola."""
    cerradas = []
    enum = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cada(hwnd, _):
        propietario = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(propietario))
        if propietario.value == pid and u32.IsWindowVisible(hwnd) and hwnd != k32.GetConsoleWindow():
            u32.PostMessageW(hwnd, 0x0010, 0, 0)
            cerradas.append(hwnd)
        return True

    u32.EnumWindows(enum(cada), 0)
    return cerradas


def correr(nombre, raiz, salida, powershell=False):
    args, cols, lineas, pasos = ESCENARIOS[nombre]
    destino = salida / nombre
    destino.mkdir(parents=True, exist_ok=True)
    antes = pythons()
    proc = subprocess.Popen(lanzador(powershell, raiz, args, cols, lineas, nombre in AZULES), cwd=REPO)
    pid = None
    for _ in range(150):
        nuevos = pythons() - antes
        if nuevos:
            pid = max(nuevos)
            break
        time.sleep(0.1)
    assert pid, f"{nombre}: no arrancó python"
    time.sleep(0.5)
    k32.FreeConsole()
    assert k32.AttachConsole(pid), ctypes.get_last_error()
    k32.SetConsoleCtrlHandler(None, True)
    hwnd = k32.GetConsoleWindow()
    n = 0
    for paso in pasos:
        if paso[0] == "teclas":
            for k in paso[1]:
                pulsar(k)
        elif paso[0] == "texto":
            for c in paso[1]:
                pulsar(c, 0.05)
            pulsar(ENT, 0.4)
        elif paso[0] == "cerrar":
            print(f"{nombre}: ventanas cerradas: {len(cerrar_ventanas(pid))}")
            time.sleep(1.5)
        elif paso[0] == "ctrlc":
            k32.GenerateConsoleCtrlEvent(0, 0)
            time.sleep(1)
        else:
            _f, foto, espera = paso
            time.sleep(espera)
            n += 1
            base = destino / f"{n:02d}_{foto}"
            base.with_suffix(".txt").write_text("\n".join(pantalla()).rstrip() + "\n", encoding="utf-8")
            img = grab_window(hwnd)
            if img is not None:
                img.save(base.with_suffix(".png"))
    k32.FreeConsole()
    proc.kill()
    print(f"{nombre}: {n} capturas")


def main():
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        print(__doc__)
        return
    if "--lista" in sys.argv[1:]:
        print("\n".join(ESCENARIOS))
        return
    argv = [a for a in sys.argv[1:] if a not in ("--powershell", "--cmd")]
    powershell = "--powershell" in sys.argv
    salida = pathlib.Path(argv[0]) if argv else REPO / "docs" / "capturas-terminal"
    elegidos = argv[1:] or list(ESCENARIOS)
    for nombre in elegidos:
        raiz = preparar(nombre in CLAROS)  # uno nuevo por escenario: lo que guarde uno no cambia lo que ve el siguiente
        try:
            correr(nombre, raiz, salida, powershell)
        finally:
            shutil.rmtree(raiz, ignore_errors=True)  # el config.json y las notas sintéticas


if __name__ == "__main__":
    main()
