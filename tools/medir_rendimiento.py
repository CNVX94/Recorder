# -*- coding: utf-8 -*-
"""Mide cuánto tarda faster-whisper en transcribir en ESTE equipo, con la configuración de config.json.

    python tools/medir_rendimiento.py                    # barrido de hilos de CPU: 0 (por defecto), 4, 6, 8, 10, 12
    python tools/medir_rendimiento.py --hilos 4,8        # solo esos valores
    python tools/medir_rendimiento.py --hilos 8 --beam 1 # el mismo audio con beam 1 (compara velocidad y WER)
    python tools/medir_rendimiento.py --hilos 8 --sin-vocab
    python tools/medir_rendimiento.py --hilos 8 --fusion 30   # fragmentos pendientes fusionados hasta 30 s

Genera una muestra de 4 minutos en español con la voz de Windows (SAPI, es-MX) la primera vez,
la trocea igual que Recorder (pausa de 0,6 s tras 8 s, forzado a 20 s) y transcribe cada fragmento.
Imprime una tabla Markdown: velocidad en múltiplos del tiempo real (por debajo de 1,0x la cola
crece) y WER frente al guion, para ver si una configuración más rápida transcribe peor.

Mide con el equipo en reposo: cierra Recorder, Teams y el navegador. Si otros procesos consumen
CPU al empezar, avisa y no mide (salvo --forzar). Las cifras de docs/rendimiento.md salieron de aquí.
"""
import argparse
import ctypes
import html
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import unicodedata
import wave

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recorder.audio.capture import DEFAULT_MAX_SEC, DEFAULT_MIN_SEC, DEFAULT_PAUSE_SEC, DEFAULT_SILENCE_RMS, FRAMES_PER_BUFFER  # noqa: E402
from recorder.config.manager import ConfigManager  # noqa: E402

RATE = 16000
CARPETA = pathlib.Path(tempfile.gettempdir()) / "recorder-rendimiento"

# Daily ficticia con vocabulario técnico genérico. Entre turnos hay 0,8 s de silencio para que
# el segmentador tenga dónde cortar, como en una reunión de verdad.
GUION = [
    "Buenos días a todos, empezamos la daily de desarrollo. Hoy revisamos el despliegue del API Gateway y las incidencias del entorno de staging.",
    "Ayer terminé la migración del esquema en PostgreSQL. La réplica de lectura ya sincroniza bien y la latencia del endpoint de pedidos bajó a doscientos milisegundos.",
    "Perfecto. Ana, ¿qué pasó con el pipeline de integración continua? Anoche vi dos ejecuciones fallidas en Jenkins.",
    "Fue un problema del certificado TLS del registro de contenedores. Ya lo renové y el pipeline vuelve a publicar las imágenes en Kubernetes sin errores.",
    "Tengo un bloqueo con el microservicio de facturación. El webhook de pagos devuelve un token JWT caducado y el balanceador reintenta la petición tres veces.",
    "Eso lo vemos después de la daily. Mientras tanto, Luis, revisa la configuración de Redis en el servidor doce, puerto seis mil trescientos setenta y nueve.",
    "Sobre el frontend, la PWA ya funciona sin conexión. Guardamos las peticiones en IndexedDB y las reenviamos cuando vuelve la red.",
    "Marta, ¿cómo va la parte de observabilidad? Necesitamos los paneles de Grafana antes del despliegue canario del viernes.",
    "Ya están los dashboards de Prometheus con la latencia p noventa y cinco y la tasa de errores por endpoint. Falta la alerta de consumo de memoria en los pods.",
    "Pendiente: documentar el rollback del despliegue canario y actualizar el manifiesto de Helm con los nuevos límites de CPU.",
    "Otra cosa. El SDK de OAuth que usamos en el backend tiene una vulnerabilidad publicada. Hay que subir a la versión cuatro punto dos esta semana.",
    "De acuerdo, lo meto en el sprint. También hay que revisar la caché del catálogo, porque el TTL de cinco minutos está generando datos inconsistentes en el carrito.",
    "El equipo de QA reportó una incidencia en el formulario de recolección. Cuando el transportista escanea un código de barras duplicado, la aplicación se queda en blanco.",
    "Lo reproduje en el entorno de pruebas. Es una excepción no controlada en el servicio de embarques; el log muestra un error de clave duplicada en la tabla de bultos.",
    "Vale, asigno la corrección a Ana. Y Luis, prepara el script de SQL Server para limpiar los registros huérfanos antes de la migración a la nube.",
    "Una pregunta rápida: ¿el balanceador de carga sigue en modo round robin o ya activamos las sesiones persistentes para el portal de clientes?",
    "Sigue en round robin. Para activar la afinidad de sesión necesitamos que el token de sesión viva en Redis y no en memoria del proceso de IIS.",
    "Recordatorio: el viernes hay ventana de mantenimiento en el clúster de producción de las diez a las once de la noche. Avisen a soporte con anticipación.",
    "Por último, la retrospectiva del sprint queda para el jueves a las cuatro. Traigan métricas de tiempo de ciclo y de despliegues fallidos del mes.",
    "Ah, se me olvidaba: la integración con el servicio de mensajería por AMQP está lista. La cola de eventos ya procesa los pedidos en orden y con reintentos exponenciales.",
    "Y el contenedor de la API en el servidor veinte, puerto ocho mil ochenta, ya escala automáticamente hasta seis réplicas cuando la cola supera los mil mensajes.",
    "Genial. Entonces resumo: certificado renovado, migración terminada, bloqueo con el webhook de pagos y la alerta de memoria pendiente. Nos vemos mañana.",
]


# ------------------------------------------------------------------ muestra de audio
def generar_muestra() -> pathlib.Path:
    """Sintetiza el guion con la voz de Windows en español a 16 kHz mono (solo la primera vez)."""
    CARPETA.mkdir(parents=True, exist_ok=True)
    wav, ssml = CARPETA / "muestra.wav", CARPETA / "muestra.ssml"
    if wav.exists():
        return wav
    cuerpo = "".join(f"<s>{html.escape(t)}</s><break time=\"800ms\"/>" for t in GUION)
    ssml.write_text(
        '<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="es-MX">' + cuerpo + "</speak>",
        encoding="utf-8",
    )
    ps = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1; "
        "if (-not $v) { throw 'No hay ninguna voz de Windows en español instalada' }; "
        "$s.SelectVoice($v.VoiceInfo.Name); "
        "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); "
        f'$s.SetOutputToWaveFile("{wav}", $fmt); '
        f'$s.SpeakSsml((Get-Content "{ssml}" -Raw -Encoding UTF8)); $s.Dispose(); '
        "Write-Output ('voz: ' + $v.VoiceInfo.Name)"
    )
    print(subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True, text=True).stdout.strip())
    return wav


def cargar_wav(path: pathlib.Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        assert w.getframerate() == RATE and w.getnchannels() == 1, "la muestra debe ser mono a 16 kHz"
        return np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


def trocear(pcm: np.ndarray, min_sec: float, max_sec: float) -> list:
    """Misma política que _read_loop en capture.py: corta en pausa tras min_sec o forzado a max_sec."""
    cola = max(1, int(DEFAULT_PAUSE_SEC * RATE / FRAMES_PER_BUFFER))
    trozos, buf, hablando = [], [], False
    for i in range(0, len(pcm) - FRAMES_PER_BUFFER + 1, FRAMES_PER_BUFFER):
        raw = pcm[i : i + FRAMES_PER_BUFFER]
        hablando = hablando or rms(raw) > DEFAULT_SILENCE_RMS
        buf.append(raw)
        secs = len(buf) * FRAMES_PER_BUFFER / RATE
        if (secs >= min_sec and rms(np.concatenate(buf[-cola:])) < DEFAULT_SILENCE_RMS) or secs >= max_sec:
            if hablando:
                trozos.append(np.concatenate(buf))
            buf, hablando = [], False
    if buf and hablando and len(buf) * FRAMES_PER_BUFFER / RATE >= 1.0:
        trozos.append(np.concatenate(buf))
    return [t / 32768.0 for t in trozos]  # float32 en [-1, 1], como to_16k()


def fusionar(trozos: list, tope_sec: float) -> list:
    """Une fragmentos consecutivos mientras no pasen de tope_sec (lo que haría un worker con cola pendiente)."""
    out, actual = [], []
    for t in trozos:
        if actual and (sum(len(a) for a in actual) + len(t)) / RATE > tope_sec:
            out.append(np.concatenate(actual))
            actual = []
        actual.append(t)
    if actual:
        out.append(np.concatenate(actual))
    return out


# ------------------------------------------------------------------ calidad
def palabras(texto: str) -> list:
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return "".join(c if c.isalnum() or c.isspace() else " " for c in t).split()


def wer(referencia: str, hipotesis: str) -> float:
    """Word Error Rate clásico (Levenshtein sobre palabras normalizadas), en %."""
    r, h = palabras(referencia), palabras(hipotesis)
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        previo, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            actual = d[j]
            d[j] = min(d[j] + 1, d[j - 1] + 1, previo + (r[i - 1] != h[j - 1]))
            previo = actual
    return 100.0 * d[len(h)] / max(1, len(r))


# ------------------------------------------------------------------ carga del sistema
class _FT(ctypes.Structure):
    _fields_ = [("lo", ctypes.c_uint32), ("hi", ctypes.c_uint32)]


def _tiempos():
    idle, kern, user = _FT(), _FT(), _FT()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
    v = lambda f: (f.hi << 32) | f.lo  # noqa: E731
    return v(idle), v(kern) + v(user)


class CargaAjena:
    """% de CPU del sistema que consumen OTROS procesos durante un tramo (para saber si la medida es limpia)."""

    def __enter__(self):
        self.i0, self.t0 = _tiempos()
        self.p0, self.w0 = time.process_time(), time.perf_counter()
        return self

    def __exit__(self, *_):
        i1, t1 = _tiempos()
        ocupado = 1.0 - (i1 - self.i0) / max(1, t1 - self.t0)
        nuestro = (time.process_time() - self.p0) / max(1e-9, (time.perf_counter() - self.w0) * (ctypes.windll.kernel32.GetActiveProcessorCount(0xFFFF)))
        self.otros_pct = round(100 * max(0.0, ocupado - nuestro))


def cpu_ocupada_pct(segundos: float = 2.0) -> int:
    i0, t0 = _tiempos()
    time.sleep(segundos)
    i1, t1 = _tiempos()
    return round(100 * (1.0 - (i1 - i0) / max(1, t1 - t0)))


# ------------------------------------------------------------------ medición
def medir(modelo, trozos, beam: int, vocab, pasadas: int):
    kw = dict(language="es", beam_size=beam, vad_filter=True, condition_on_previous_text=False,
              initial_prompt=vocab, repetition_penalty=1.1)  # como _process() en whisper_worker.py

    def transcribir(audio):
        segs, _ = modelo.transcribe(audio, **kw)
        return " ".join(s.text.strip() for s in segs)  # el generador es perezoso: hay que consumirlo

    transcribir(trozos[0])  # calentamiento: se descarta
    audio_sec = sum(len(t) for t in trozos) / RATE
    velocidades, texto, otros = [], "", []
    for _ in range(pasadas):
        with CargaAjena() as carga:
            t0 = time.perf_counter()
            texto = " ".join(transcribir(t) for t in trozos)
            velocidades.append(audio_sec / (time.perf_counter() - t0))
        otros.append(carga.otros_pct)
    velocidades.sort()
    return velocidades[len(velocidades) // 2], texto, max(otros)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hilos", default="0,4,6,8,10,12", help="valores de cpu_threads a probar (0 = por defecto)")
    ap.add_argument("--beam", type=int, help="beam_size (por defecto el de config.json)")
    ap.add_argument("--modelo", help="modelo (por defecto el de config.json)")
    ap.add_argument("--sin-vocab", action="store_true", help="no pasar el vocab como initial_prompt")
    ap.add_argument("--fusion", type=float, help="fusionar fragmentos consecutivos hasta N segundos")
    ap.add_argument("--min", type=float, default=DEFAULT_MIN_SEC, help="min_sec del segmentador")
    ap.add_argument("--max", type=float, default=DEFAULT_MAX_SEC, help="max_sec del segmentador")
    ap.add_argument("--pasadas", type=int, default=2, help="pasadas cronometradas (se toma la mediana)")
    ap.add_argument("--forzar", action="store_true", help="medir aunque la CPU ya esté ocupada")
    args = ap.parse_args()

    ocupada = cpu_ocupada_pct()
    if ocupada > 15 and not args.forzar:
        sys.exit(f"La CPU ya está al {ocupada} % antes de empezar: cierra Recorder, Teams y el navegador, "
                 f"o usa --forzar (los números saldrán peores y poco comparables).")

    cfg = ConfigManager().load()
    modelo_nombre = args.modelo or cfg.model
    beam = args.beam or cfg.beam_size
    vocab = None if args.sin_vocab else (cfg.vocab.strip() or None)

    wav = generar_muestra()
    trozos = trocear(cargar_wav(wav), args.min, args.max)
    if args.fusion:
        trozos = fusionar(trozos, args.fusion)
    referencia = "\n".join(GUION)
    duraciones = [len(t) / RATE for t in trozos]
    print(f"muestra: {sum(duraciones):.0f} s de audio en {len(trozos)} fragmentos "
          f"(media {sum(duraciones) / len(duraciones):.1f} s, máx {max(duraciones):.1f} s); "
          f"modelo {modelo_nombre}, beam {beam}, vocab {'sí' if vocab else 'no'}, CPU ajena al empezar {ocupada} %\n")

    from faster_whisper import WhisperModel

    print("| cpu_threads | Velocidad (x tiempo real) | WER vs guion | CPU de otros procesos |")
    print("| ---: | ---: | ---: | ---: |")
    for hilos in [int(h) for h in args.hilos.split(",")]:
        modelo = WhisperModel(modelo_nombre, device="cpu", compute_type="int8", cpu_threads=hilos)
        velocidad, texto, otros = medir(modelo, trozos, beam, vocab, args.pasadas)
        etiqueta = f"{hilos} (por defecto = 4)" if hilos == 0 else str(hilos)
        print(f"| {etiqueta} | {velocidad:.2f}x | {wer(referencia, texto):.1f} % | {otros} % |", flush=True)
        (CARPETA / f"texto_hilos{hilos}_beam{beam}.txt").write_text(texto, encoding="utf-8")
        del modelo
    print(f"\nTextos transcritos en {CARPETA} para compararlos a ojo.")


if __name__ == "__main__":
    main()
