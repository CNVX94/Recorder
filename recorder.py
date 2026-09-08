"""Recorder: transcribe en vivo la salida de audio (Teams, etc.) y tu micrófono a un .md,
con capturas de pantalla automáticas al oír palabras clave.

Instalar:  pip install faster-whisper pyaudiowpatch pillow numpy
Usar:      escribe `daily` en PowerShell  (función en $PROFILE) o python recorder.py
Opciones:  botón ⚙ en la app -> rutas, palabras clave, dispositivos; se guardan en config.json
Tester:    los medidores 🔊/🎤 de la cabecera muestran el nivel en vivo de cada fuente
Pausa:     botón ⏸ deja de tomar nota sin cambiar de archivo; ▶ continúa en el mismo .md
Selftest:  python recorder.py --selftest
"""
import ctypes, ctypes.wintypes as wt, datetime as dt, json, os, pathlib, queue, re, shutil, sys, threading, time, unicodedata
import tkinter as tk
from tkinter import filedialog, scrolledtext
import numpy as np
import pyaudiowpatch as pa

try:  # píxeles físicos en todo el proceso: así los rectángulos de monitor coinciden con lo que captura Pillow
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

LANG = "es"
MODELS = ["small", "medium", "base", "tiny", "large-v3-turbo"]  # en i7-1255U: small 3x tiempo real, medium 1.2x
BEAM = 5                      # 1 = greedy (rápido); 5 = más preciso, ~1.5x más lento
MIN_SEC, MAX_SEC = 8, 20      # corta el chunk en una pausa tras MIN_SEC, o forzado a MAX_SEC (más contexto = mejor texto)
PAUSE_SEC = 0.6               # silencio que cuenta como pausa entre frases
SILENCE = 150                 # RMS int16 bajo el cual se considera silencio
CAP_COOLDOWN = 15             # segundos mínimos entre capturas por palabra clave
FRAMES = 1024
CONFIG = pathlib.Path(__file__).with_name("config.json")
DEFAULT_DEV = "(predeterminado de Windows)"
DEFAULTS = {
    "notes_dir": str(pathlib.Path.home() / "Documents" / "Dailies"),
    "caps_dir": str(pathlib.Path.home() / "Documents" / "Dailies" / "capturas"),
    "keywords": ["pendiente", "bloqueo", "captura"],
    "mic": True,
    "out_dev": "",   # nombre WASAPI de la salida a capturar; "" = predeterminada
    "mic_dev": "",   # nombre WASAPI del micrófono; "" = predeterminado
    "screen": 0,     # 0 = todas las pantallas; 1..n = monitor n
    "model": "small",  # aplica al reiniciar
    # contexto que se le da a Whisper para que escriba bien nombres y términos técnicos
    "vocab": "Daily de desarrollo de software. Términos: API Core, API Gateway, PWA, QA, IIS, SQL Server, Axon, TPR, "
             "manifiesto, flete, programa de embarques, transportista, operador, recolección, UPS, pedido, cajas, "
             "server 14, server 20, puerto 7100, 7200. Bruno, Chris, Richi.",
    # frases que Whisper inventa en silencios/ruido; se comparan sin acentos ni mayúsculas
    "ignore": ["suscríbete", "próximo vídeo", "gracias por ver", "hasta la próxima", "subtítulos", "amara.org",
               "gracias por estar aquí"],
    # correcciones personales tras transcribir (mal -> bien), palabra completa, sin distinguir mayúsculas
    "fixes": {"cuba": "QA", "ayayas": "IIS"},
}
cfg = {**DEFAULTS, **(json.loads(CONFIG.read_text("utf-8")) if CONFIG.exists() else {})}
state, lock = {"md": None, "pa": None, "cap": None, "paused": False, "last_cap": 0.0}, threading.Lock()
levels = {"out": 0.0, "mic": 0.0}  # RMS int16 del último frame de cada fuente (medidores)


def normalize(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def find_keywords(text, keywords):
    t = normalize(text)
    return [k for k in keywords if k and re.search(rf"\b{re.escape(normalize(k))}\b", t)]


def rms(pcm):
    return float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)))


def clean(segs, ignore):
    """Une segmentos descartando los dudosos (sin voz / baja confianza) y las frases de la lista `ignore`."""
    keep = [s.text.strip() for s in segs if s.no_speech_prob < 0.6 and s.avg_logprob > -1.0]
    bad = [normalize(h) for h in ignore if h.strip()]
    return " ".join(t for t in keep if t and not any(h in normalize(t) for h in bad)).strip()


def fix(text, fixes):
    """Correcciones personales: reemplaza palabra completa, sin distinguir mayúsculas."""
    for wrong, right in fixes.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text, flags=re.I)
    return text


def parse_fixes(s):
    """'cuba=QA; ayayas=IIS' -> {'cuba': 'QA', 'ayayas': 'IIS'}"""
    pairs = (p.split("=", 1) for p in s.split(";") if "=" in p)
    return {k.strip().lower(): v.strip() for k, v in pairs if k.strip()}


def bars(v, n=8):
    """RMS int16 -> medidor de n bloques en escala log (-60 dB … 0 dB)."""
    k = 0 if v < 1 else int(np.clip((20 * np.log10(v / 32768) + 60) / 60 * n, 0, n))
    return "█" * k + "░" * (n - k)


def to_16k(pcm, rate, channels):
    """int16 intercalado -> float32 mono 16 kHz (lo que espera whisper)."""
    a = pcm.astype(np.float32).reshape(-1, channels).mean(1) / 32768
    n = int(len(a) * 16000 / rate)
    return np.interp(np.linspace(0, len(a), n, endpoint=False), np.arange(len(a)), a).astype(np.float32)


def md_ref(path, notes_dir):
    """Ruta para incrustar en markdown: relativa a la carpeta de notas, absoluta si es otra unidad."""
    try:
        rel = os.path.relpath(path, notes_dir)
    except ValueError:
        rel = str(path)
    return rel.replace("\\", "/")


def write_md(text):
    with lock, open(state["md"], "a", encoding="utf-8") as f:
        f.write(text + "\n")


def move_notes(new_dir):
    """Cambia la carpeta de notas en caliente: mueve el .md de esta sesión."""
    new_dir = pathlib.Path(new_dir)
    if new_dir == state["md"].parent:
        return
    new_dir.mkdir(parents=True, exist_ok=True)
    with lock:
        state["md"] = pathlib.Path(shutil.move(state["md"], new_dir / state["md"].name))


def monitors():
    """Rectángulos (l, t, r, b) de cada monitor en píxeles físicos, el principal primero."""
    rects = []
    proc = ctypes.WINFUNCTYPE(ctypes.c_int, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)
    cb = proc(lambda h, d, p, l: (rects.append((p.contents.left, p.contents.top, p.contents.right, p.contents.bottom)), 1)[1])
    ctypes.windll.user32.EnumDisplayMonitors(None, None, cb, 0)
    return rects


def screen_labels():
    return ["(todas las pantallas)"] + [f"Pantalla {i}: {r - l}×{b - t} en ({l}, {t})"
                                        for i, (l, t, r, b) in enumerate(monitors(), 1)]


def screenshot(tag):
    from PIL import ImageGrab
    d = pathlib.Path(cfg["caps_dir"])
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{dt.datetime.now():%Y-%m-%d_%H-%M-%S}_{normalize(tag).replace(' ', '-')}.png"
    rects = monitors()
    bbox = rects[cfg["screen"] - 1] if 0 < cfg["screen"] <= len(rects) else None  # fuera de rango = todas
    ImageGrab.grab(bbox=bbox, all_screens=True).save(f)
    return md_ref(f, state["md"].parent)


def wasapi_devices(p, kind):
    """Nombres WASAPI: 'out' = salidas (se capturan por loopback), 'mic' = entradas reales."""
    api = p.get_host_api_info_by_type(pa.paWASAPI)["index"]
    key = "maxOutputChannels" if kind == "out" else "maxInputChannels"
    return [d["name"] for d in p.get_device_info_generator()
            if d["hostApi"] == api and d[key] > 0 and not d.get("isLoopbackDevice")]


def open_stream(p, kind):
    """kind: 'out' = loopback de la salida (los demás), 'mic' = tu micrófono."""
    api = p.get_host_api_info_by_type(pa.paWASAPI)
    want = cfg["out_dev" if kind == "out" else "mic_dev"]
    if kind == "out":
        name = want or p.get_device_info_by_index(api["defaultOutputDevice"])["name"]
        dev = next((d for d in p.get_loopback_device_info_generator() if name in d["name"]), None)
    elif want:  # ponytail: con bocinas (sin audífonos) el mic también oye a los demás y se duplica
        dev = next((d for d in p.get_device_info_generator() if d["hostApi"] == api["index"] and d["name"] == want), None)
    else:
        dev = p.get_device_info_by_index(api["defaultInputDevice"])
    if dev is None:
        raise ValueError(f"no encontré el dispositivo '{want}'")
    rate, ch = int(dev["defaultSampleRate"]), dev["maxInputChannels"]
    s = p.open(format=pa.paInt16, channels=ch, rate=rate, input=True,
               input_device_index=dev["index"], frames_per_buffer=FRAMES)
    return s, rate, ch


def capture_thread(kind, s, rate, ch, chunks, ui, stop):
    try:
        tail = max(1, int(PAUSE_SEC * rate / FRAMES))  # frames que deben estar en silencio para cortar
        buf = []
        while not stop.is_set():
            raw = np.frombuffer(s.read(FRAMES, exception_on_overflow=False), np.int16)
            lvl = levels[kind] = rms(raw)
            if state["paused"] or (kind == "mic" and not cfg["mic"]):
                buf = []  # los medidores siguen vivos, pero no se transcribe
                continue
            if not buf:
                t0 = None
            if t0 is None and lvl > SILENCE:
                t0 = time.time()  # la hora de la nota es la del primer frame con voz, no del silencio previo
            buf.append(raw)
            secs = len(buf) * FRAMES / rate
            if (secs >= MIN_SEC and rms(np.concatenate(buf[-tail:])) < SILENCE) or secs >= MAX_SEC:
                pcm, buf = np.concatenate(buf), []
                if t0 is not None and rms(pcm) > SILENCE:  # no mandar silencio a whisper (alucina)
                    chunks.put((t0, kind, to_16k(pcm, rate, ch)))
    except Exception as e:
        ui.put(("status", f"Error audio ({kind}): {e!r}"))
    finally:
        levels[kind] = 0.0
        s.close()


def start_capture(chunks, ui):
    """Abre los streams en el hilo principal (PortAudio no aguanta inits concurrentes) y lanza los lectores.
    Devuelve el Event que los detiene; llamar de nuevo tras cambiar dispositivos."""
    stop = threading.Event()
    for kind in ("out", "mic"):
        try:
            args = (kind, *open_stream(state["pa"], kind), chunks, ui, stop)
            threading.Thread(target=capture_thread, args=args, daemon=True).start()
        except Exception as e:
            ui.put(("status", f"Sin audio ({kind}): {e!r}"))
    return stop


def transcribe_thread(chunks, ui, stop):
    try:
        ui.put(("status", f"Cargando modelo {cfg['model']}…"))
        from faster_whisper import WhisperModel
        model = WhisperModel(cfg["model"], device="cpu", compute_type="int8")
        ui.put(("status", "● Escuchando"))
        while not stop.is_set():
            try:
                t0, kind, audio = chunks.get(timeout=0.5)
            except queue.Empty:
                continue
            segs, _ = model.transcribe(audio, language=LANG, beam_size=BEAM, vad_filter=True,
                                       condition_on_previous_text=False, initial_prompt=cfg["vocab"] or None)
            text = fix(clean(segs, cfg["ignore"]), cfg["fixes"])
            if not text:
                continue
            stamp = dt.datetime.fromtimestamp(t0).strftime("%H:%M:%S")
            hits = find_keywords(text, cfg["keywords"])
            line = f"- **{stamp}** {'🎤 ' if kind == 'mic' else ''}{text}"
            if hits and time.time() - state["last_cap"] > CAP_COOLDOWN:
                state["last_cap"] = time.time()  # ponytail: la captura llega ~chunk+inferencia tarde; ring buffer si molesta
                line += f"\n  - 📸 `{', '.join(hits)}` → ![]({screenshot(hits[0])})"
            else:
                hits = []
            write_md(line)
            ui.put(("line", stamp, kind, text, hits))
    except Exception as e:
        ui.put(("status", f"Error transcripción: {e!r}"))


def main():
    now = dt.datetime.now()
    pathlib.Path(cfg["notes_dir"]).mkdir(parents=True, exist_ok=True)
    state["md"] = pathlib.Path(cfg["notes_dir"]) / f"daily_{now:%Y-%m-%d_%H-%M}.md"
    write_md(f"# Daily {now:%Y-%m-%d %H:%M}\n")
    state["pa"] = pa.PyAudio()
    chunks, ui, stop = queue.Queue(), queue.Queue(), threading.Event()
    state["cap"] = start_capture(chunks, ui)
    threading.Thread(target=transcribe_thread, args=(chunks, ui, stop), daemon=True).start()

    BG, PANEL, FG, DIM, ACC, MIC = "#1e1e2e", "#313244", "#cdd6f4", "#7f849c", "#f9e2af", "#89b4fa"
    BTN = dict(bg=PANEL, fg=FG, relief="flat", activebackground=ACC, padx=10, font=("Segoe UI", 10))
    root = tk.Tk()
    root.title("Recorder · Daily")
    root.configure(bg=BG)
    root.geometry("820x540")
    top = tk.Frame(root, bg=BG)  # cabecera: estado + medidores + botones, empacada primero para que nunca se recorte
    top.pack(fill="x", padx=14, pady=(12, 0))
    status = tk.Label(top, text="Iniciando…", bg=BG, fg=DIM, anchor="w", font=("Segoe UI Semibold", 11))
    status.pack(side="left")
    meter = tk.Label(top, text="", bg=BG, fg=DIM, font=("Consolas", 10))
    meter.pack(side="left", padx=16)
    path_lbl = tk.Label(root, text=str(state["md"]), bg=BG, fg=DIM, anchor="w", font=("Segoe UI", 8))
    path_lbl.pack(fill="x", padx=14)
    txt = scrolledtext.ScrolledText(root, bg=BG, fg=FG, insertbackground=FG, wrap="word", relief="flat",
                                    font=("Segoe UI", 11), padx=10, pady=8, spacing3=6, height=10)
    txt.pack(fill="both", expand=True, padx=14, pady=(10, 14))
    txt.tag_config("t", foreground=DIM, font=("Consolas", 10))
    txt.tag_config("kw", foreground=ACC)
    txt.tag_config("mic", foreground=MIC)

    def add_line(stamp, kind, text, hits):
        txt.insert("end", f"{stamp}  ", "t")
        if kind == "mic":
            txt.insert("end", "🎤 ", "mic")
        txt.insert("end", text + "\n", "kw" if hits else "")
        if hits:
            txt.insert("end", f"          📸 captura: {', '.join(hits)}\n", "t")
        txt.see("end")

    def manual_shot():
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        write_md(f"- **{stamp}** 📸 captura manual → ![]({screenshot('manual')})")
        add_line(stamp, "out", "(captura manual)", ["manual"])

    def options():
        win = tk.Toplevel(root)
        win.title("Opciones")
        win.configure(bg=BG)
        win.resizable(False, False)
        win.transient(root)
        win.grab_set()
        screens = screen_labels()
        v = {"notes_dir": tk.StringVar(value=cfg["notes_dir"]), "caps_dir": tk.StringVar(value=cfg["caps_dir"]),
             "keywords": tk.StringVar(value=", ".join(cfg["keywords"])), "mic": tk.BooleanVar(value=cfg["mic"]),
             "vocab": tk.StringVar(value=cfg["vocab"]), "model": tk.StringVar(value=cfg["model"]),
             "ignore": tk.StringVar(value=", ".join(cfg["ignore"])),
             "fixes": tk.StringVar(value="; ".join(f"{k}={r}" for k, r in cfg["fixes"].items())),
             "out_dev": tk.StringVar(value=cfg["out_dev"] or DEFAULT_DEV),
             "mic_dev": tk.StringVar(value=cfg["mic_dev"] or DEFAULT_DEV),
             "screen": tk.StringVar(value=screens[cfg["screen"] if cfg["screen"] < len(screens) else 0])}

        def label(r, text):
            tk.Label(win, text=text, bg=BG, fg=DIM, font=("Segoe UI", 9)).grid(row=r, column=0, sticky="w", padx=12, pady=6)

        def row(r, text, var, browse=False):
            label(r, text)
            tk.Entry(win, textvariable=var, width=52, bg=PANEL, fg=FG, insertbackground=FG, relief="flat",
                     font=("Segoe UI", 10)).grid(row=r, column=1, ipady=4, sticky="ew")
            if browse:
                tk.Button(win, text="📁", command=lambda: var.set(filedialog.askdirectory(initialdir=var.get()) or var.get()),
                          **BTN).grid(row=r, column=2, padx=(6, 12))

        def choice(r, text, var, names, first=DEFAULT_DEV):
            label(r, text)
            om = tk.OptionMenu(win, var, first, *names)
            om.config(bg=PANEL, fg=FG, activebackground=ACC, relief="flat", highlightthickness=0,
                      font=("Segoe UI", 10), anchor="w")
            om["menu"].config(bg=PANEL, fg=FG, activebackground=ACC)
            om.grid(row=r, column=1, sticky="ew")

        row(0, "Carpeta de notas (.md)", v["notes_dir"], True)
        row(1, "Carpeta de capturas", v["caps_dir"], True)
        row(2, "Palabras clave (coma)", v["keywords"])
        row(3, "Vocabulario / contexto", v["vocab"])
        row(4, "Frases a ignorar (coma)", v["ignore"])
        row(5, "Correcciones (mal=bien; …)", v["fixes"])
        choice(6, "Salida a capturar  🔊", v["out_dev"], wasapi_devices(state["pa"], "out"))
        choice(7, "Micrófono  🎤", v["mic_dev"], wasapi_devices(state["pa"], "mic"))
        choice(8, "Pantalla a capturar  📸", v["screen"], screens[1:], first=screens[0])
        choice(9, "Modelo Whisper (al reiniciar)", v["model"], MODELS[1:], first=MODELS[0])
        tk.Checkbutton(win, text="Transcribir también mi micrófono  🎤", variable=v["mic"], bg=BG, fg=FG,
                       selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                       font=("Segoe UI", 10)).grid(row=10, column=0, columnspan=2, sticky="w", padx=12, pady=6)

        def save():
            move_notes(v["notes_dir"].get().strip())
            devs = {k: "" if v[k].get() == DEFAULT_DEV else v[k].get() for k in ("out_dev", "mic_dev")}
            changed = devs != {k: cfg[k] for k in devs}
            cfg.update(notes_dir=v["notes_dir"].get().strip(), caps_dir=v["caps_dir"].get().strip(), mic=v["mic"].get(),
                       keywords=[k.strip() for k in v["keywords"].get().split(",") if k.strip()],
                       vocab=v["vocab"].get().strip(), screen=screens.index(v["screen"].get()),
                       model=v["model"].get(), fixes=parse_fixes(v["fixes"].get()),
                       ignore=[k.strip() for k in v["ignore"].get().split(",") if k.strip()], **devs)
            CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), "utf-8")
            if changed:  # reabre los streams con los dispositivos nuevos, sin reiniciar la app
                state["cap"].set()
                ui.put(("status", "● Escuchando"))
                state["cap"] = start_capture(chunks, ui)
            path_lbl.config(text=str(state["md"]))
            win.destroy()

        tk.Button(win, text="Guardar", command=save, **BTN).grid(row=11, column=1, sticky="e", pady=(6, 12))

    def toggle_pause():
        state["paused"] = not state["paused"]
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        write_md(f"\n> {'⏸ Pausa' if state['paused'] else '▶ Continúa'} {stamp}\n")
        pause_btn.config(text="▶ Continuar" if state["paused"] else "⏸ Pausar")
        add_line(stamp, "out", "⏸ pausa, no se toma nota" if state["paused"] else "▶ continúa", [])

    tk.Button(top, text="📸 Captura", command=manual_shot, **BTN).pack(side="right")
    tk.Button(top, text="⚙ Opciones", command=options, **BTN).pack(side="right", padx=(0, 8))
    pause_btn = tk.Button(top, text="⏸ Pausar", command=toggle_pause, **BTN)
    pause_btn.pack(side="right", padx=(0, 8))

    def poll():
        while not ui.empty():
            m = ui.get()
            if m[0] == "status":
                status.config(text=m[1], fg=FG if m[1].startswith("●") else DIM)
            else:
                add_line(*m[1:])
        if status.cget("text")[0] in "●⏸":
            status.config(text="⏸ En pausa" if state["paused"] else
                          f"● Escuchando{' + 🎤' if cfg['mic'] else ''} · pendientes: {chunks.qsize()}")
        meter.config(text=f"🔊 {bars(levels['out'])}   🎤 {bars(levels['mic'])}")
        root.after(200, poll)

    poll()
    root.protocol("WM_DELETE_WINDOW", lambda: (state["cap"].set(), stop.set(), root.destroy()))
    root.mainloop()


def selftest():
    import tempfile
    from types import SimpleNamespace as S
    segs = [S(text=" Hola equipo. ", no_speech_prob=0.1, avg_logprob=-0.3),
            S(text="¡Suscríbete!", no_speech_prob=0.1, avg_logprob=-0.3),          # alucinación conocida
            S(text="mitalaka mitalaka", no_speech_prob=0.1, avg_logprob=-1.4),      # baja confianza
            S(text="ruido", no_speech_prob=0.9, avg_logprob=-0.2),                  # sin voz
            S(text="Falta probar el flujo.", no_speech_prob=0.2, avg_logprob=-0.5)]
    assert clean(segs, DEFAULTS["ignore"]) == "Hola equipo. Falta probar el flujo."
    assert fix("Desplegamos en Cuba y en el ayayas.", {"cuba": "QA", "ayayas": "IIS"}) == "Desplegamos en QA y en el IIS."
    assert fix("incubadora", {"cuba": "QA"}) == "incubadora"                  # solo palabra completa
    assert parse_fixes(" cuba = QA ; ayayas=IIS; basura ; =x") == {"cuba": "QA", "ayayas": "IIS"}
    assert find_keywords("Hay un BLOQUEO con la base", ["bloqueo"]) == ["bloqueo"]
    assert find_keywords("bloqueos varios", ["bloqueo"]) == []            # palabra completa
    assert find_keywords("acción tomada", ["accion"]) == ["accion"]       # ignora acentos
    assert find_keywords("sin nada", ["", "x"]) == []
    a = to_16k(np.zeros(48000 * 2, np.int16), 48000, 2)
    assert a.shape == (16000,) and a.dtype == np.float32
    assert bars(0) == "░" * 8 and bars(32768) == "█" * 8 and bars(327.68) == "██░░░░░░"  # -40 dB
    assert md_ref(r"C:\n\caps\x.png", r"C:\n") == "caps/x.png"
    assert md_ref(r"C:\otro\x.png", r"C:\n") == "../otro/x.png"
    assert md_ref(r"D:\x.png", r"C:\n") == "D:/x.png"
    with tempfile.TemporaryDirectory() as tmp:
        state["md"] = pathlib.Path(tmp, "a", "d.md")
        state["md"].parent.mkdir()
        write_md("hola")
        move_notes(pathlib.Path(tmp, "b"))
        assert state["md"] == pathlib.Path(tmp, "b", "d.md") and state["md"].read_text() == "hola\n"
        write_md("otra")
        assert state["md"].read_text() == "hola\notra\n"
    p = pa.PyAudio()
    assert wasapi_devices(p, "out") and wasapi_devices(p, "mic") and not any("Loopback" in n for n in wasapi_devices(p, "mic"))
    m = monitors()
    assert m and all(r > l and b > t for l, t, r, b in m) and len(screen_labels()) == len(m) + 1
    print("selftest ok")


if __name__ == "__main__":
    selftest() if "--selftest" in sys.argv else main()
