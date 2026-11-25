"""Capturas de las pantallas de terminal de Recorder en una consola real (conhost), para comparar antes y después.

Cada escenario abre `conhost cmd /k "... python recorder.py <args>"` con un config.json sintético,
se engancha a su consola, teclea con WriteConsoleInputW y en cada paso guarda el búfer como texto
y la ventana como PNG (PrintWindow, recorder.actions.screenshot.grab_window).

Abre ventanas de consola en el escritorio mientras corre (unos 3 min con todos los escenarios) y la grabación
carga el modelo de verdad; no toca el config.json del usuario ni sus notas (todo es sintético y temporal).
El Ctrl+C inyectado como tecla no equivale al del teclado: compruébalo a mano.

uso: python tools/capturar_terminal.py [--powershell | --cmd] [carpeta_salida] [escenario ...]
(por defecto docs/capturas-terminal y cmd). --powershell lanza cada escenario en Windows PowerShell
(`powershell.exe -NoProfile -NoExit -Command ...`), la consola del día a día; en ambas se quita NO_COLOR.
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
              "derecha": (0x27, 0x4D, "\0", 0x100), "enter": (0x0D, 0x1C, "\r", 0), "esc": (0x1B, 0x01, "\x1b", 0),
              "retroceso": (0x08, 0x0E, "\x08", 0), "ctrl+c": (0x43, 0x2E, "\x03", 0x0008)}


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


def preparar() -> pathlib.Path:
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
    (raiz / "config.json").write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return raiz


# ------------------------------------------------------------------ escenarios
# Cada paso: ("teclas", [...]) | ("texto", "linea") (teclea y Enter) | ("foto", nombre, espera) | ("ctrlc",)
E, ENT = "esc", "enter"
BASE = [
    ("foto", "inicio", 5), ("teclas", ["2"]), ("foto", "opciones-cargando", 0.3), ("foto", "opciones", 3),
    ("teclas", ["abajo", "abajo", ENT, "e", "r", "r", "o", "r", "izquierda", "izquierda"]), ("foto", "texto-con-cursor", 1),
    ("teclas", [ENT]), ("foto", "con-cambios", 1),
    ("teclas", ["abajo", ENT]), ("foto", "lista-de-seleccion", 1.5),
    ("teclas", [E, "abajo", " "]), ("foto", "interruptor", 1),
    ("teclas", [E]), ("foto", "aviso-sin-guardar", 1),
    ("teclas", ["g"]), ("foto", "confirmar", 1),
    ("teclas", [ENT]), ("foto", "guardado", 1),
    ("teclas", [E, "7"]), ("foto", "rendimiento", 8),
    ("teclas", [E, "8"]), ("foto", "ayuda", 1.5), ("teclas", ["abajo"] * 6), ("foto", "ayuda-bajando", 1),
]
ESCENARIOS = {
    "menu": ("menu", 100, 30, [
        ("foto", "inicio", 5), ("teclas", ["3"]), ("foto", "calibrar-desde-el-menu", 3),
        ("texto", "8"), ("foto", "vuelta-pulsa-una-tecla", 2), ("teclas", ["x"]), ("foto", "de-vuelta-en-inicio", 2), ("ctrlc",),
    ]),
    "config": ("config", 100, 30, [
        ("foto", "secciones", 6), ("texto", "2"), ("foto", "audio-salida", 1.5), ("texto", ""), ("foto", "audio-transcribir-micro", 1),
        ("texto", ""), ("foto", "audio-micro", 1), ("texto", ""), ("foto", "audio-sin-cambios", 1.5),
        ("texto", "4"), ("foto", "calidad-carpeta-whispercpp", 1.5),
        ("texto", ""), ("foto", "calidad-recomendada", 1.5), ("texto", ""), ("foto", "calidad-lista", 1.5),
        ("texto", ""), ("foto", "calidad-hilos", 1.5), ("texto", ""), ("foto", "calidad-fin", 1.5),
        ("texto", "1"), ("texto", ""), ("texto", ""), ("texto", "bloqueo, demo"), ("foto", "tabla-de-cambios", 1.5),
        ("texto", "n"), ("foto", "no-guardado", 1), ("texto", "8"), ("foto", "salir-sin-guardar", 1.5),
    ]),
    "config-ver": ("config --ver", 100, 30, [("foto", "ver", 3)]),
    "calibrar": ("calibrar", 100, 30, [
        ("foto", "menu", 3), ("texto", "6"), ("foto", "sandbox", 1), ("texto", "?"), ("foto", "sandbox-ejemplo", 1.5),
        ("texto", "gracias por ver"), ("foto", "sandbox-descartada", 1.5), ("texto", ""), ("foto", "vuelta-al-menu", 1),
        ("texto", "4"), ("foto", "umbrales", 1), ("texto", ""), ("texto", ""), ("texto", ""), ("foto", "umbrales-fin", 1.5),
        ("texto", "8"), ("foto", "salir", 1.5),
    ]),
    "calibrar-60": ("calibrar", 60, 26, [("foto", "menu", 3), ("texto", "6"), ("texto", "?"), ("foto", "sandbox", 1.5), ("teclas", ["ctrl+c"]), ("foto", "ctrl-c", 5)]),
    "sintesis": ("sintesis", 100, 30, [
        ("foto", "lista-de-notas", 3), ("texto", ""), ("foto", "agrupamiento", 1.5), ("texto", ""), ("foto", "preguntas", 1.5),
        ("texto", ""), ("texto", ""), ("texto", ""), ("texto", ""), ("texto", ""), ("foto", "vista-previa", 2),
        ("texto", "n"), ("foto", "no-creada", 1.5),
    ]),
    "sintesis-60": ("sintesis", 60, 26, [("foto", "lista", 3), ("texto", ""), ("texto", ""), *[("texto", "")] * 5, ("foto", "vista-previa", 2), ("texto", "n")]),
    # Menú y Opciones a 100 y 60 columnas, y el menú con --ascii: la evidencia del color real y los símbolos seguros.
    "inicio-100": ("menu", 100, 30, [("foto", "inicio", 5), ("teclas", ["2"]), ("foto", "opciones", 3), ("teclas", [E, E])]),
    "inicio-60": ("menu", 60, 24, [("foto", "inicio", 5), ("teclas", ["2"]), ("foto", "opciones", 3), ("teclas", [E, E])]),
    "inicio-ascii": ("--ascii menu", 100, 30, [("foto", "inicio", 5), ("teclas", ["2"]), ("foto", "opciones", 3), ("teclas", [E, E])]),
    # La base común del paso 3: Opciones con sus componentes (texto con cursor, lista de selección, interruptor,
    # confirmación «antes → después»), el aviso, Rendimiento (tendencia) y Ayuda; en la consola de PowerShell y con --ascii.
    "base-100": ("menu", 100, 30, BASE),
    "base-60": ("menu", 60, 24, BASE),
    "base-ascii": ("--ascii menu", 100, 30, BASE),
    "recomendar": ("recomendar", 100, 30, [("foto", "salida", 5)]),
    "ayuda": ("-h", 100, 30, [("foto", "daily-h", 2)]),
    "grabar": ("", 100, 30, [
        ("foto", "arranque", 4), ("foto", "escuchando", 20), ("teclas", ["o"]), ("foto", "panel-opciones", 1.5),
        ("teclas", ["1"]), ("foto", "panel-salida", 2), ("teclas", [E]), ("teclas", [E]), ("teclas", ["p"]),
        ("foto", "pausa", 2), ("teclas", ["p"]), ("teclas", ["q"]), ("foto", "salida", 6),
    ]),
}


def lanzador(powershell, raiz, args, cols, lineas):
    """La línea que abre conhost: cmd o Windows PowerShell, con el config sintético y sin NO_COLOR."""
    config = raiz / "config.json"
    if powershell:
        orden = (f"mode con: cols={cols} lines={lineas}; $env:RECORDER_CONFIG='{config}'; "
                 f"Remove-Item Env:NO_COLOR -ErrorAction SilentlyContinue; & '{sys.executable}' recorder.py {args}")
        return ["conhost.exe", "powershell.exe", "-NoProfile", "-NoExit", "-Command", orden]
    orden = f"mode con: cols={cols} lines={lineas}& set RECORDER_CONFIG={config}& set NO_COLOR=& {sys.executable} recorder.py {args}"
    return ["conhost.exe", "cmd", "/k", orden]


def correr(nombre, raiz, salida, powershell=False):
    args, cols, lineas, pasos = ESCENARIOS[nombre]
    destino = salida / nombre
    destino.mkdir(parents=True, exist_ok=True)
    antes = pythons()
    proc = subprocess.Popen(lanzador(powershell, raiz, args, cols, lineas), cwd=REPO)
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
    argv = [a for a in sys.argv[1:] if a not in ("--powershell", "--cmd")]
    powershell = "--powershell" in sys.argv
    salida = pathlib.Path(argv[0]) if argv else REPO / "docs" / "capturas-terminal"
    elegidos = argv[1:] or list(ESCENARIOS)
    for nombre in elegidos:
        raiz = preparar()  # uno nuevo por escenario: lo que guarde uno no cambia lo que ve el siguiente
        try:
            correr(nombre, raiz, salida, powershell)
        finally:
            shutil.rmtree(raiz, ignore_errors=True)  # el config.json y las notas sintéticas


if __name__ == "__main__":
    main()
