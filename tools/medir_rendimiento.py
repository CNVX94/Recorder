# -*- coding: utf-8 -*-
"""Mide cuánto tarda faster-whisper en transcribir en ESTE equipo, con la configuración de config.json.

    python tools/medir_rendimiento.py                    # barrido de hilos de CPU: 0 (por defecto), 4, 6, 8, 10, 12
    python tools/medir_rendimiento.py --hilos 4,8        # solo esos valores
    python tools/medir_rendimiento.py --hilos 8 --beam 1 # el mismo audio con beam 1 (compara velocidad y WER)
    python tools/medir_rendimiento.py --hilos 8 --sin-vocab
    python tools/medir_rendimiento.py --turnos 4 --pasadas 1   # muestra corta (~45 s de voz) y una sola pasada
    python tools/medir_rendimiento.py --hilos 8 --fusion 30   # fragmentos pendientes fusionados hasta 30 s
    python tools/medir_rendimiento.py --motor whispercpp --modelo large-v3 --hilos 5   # GPU con Vulkan
    python tools/medir_rendimiento.py --motor whispercpp --modelo large-v3 --hilos 5 --flash-attn
    python tools/medir_rendimiento.py --motor whispercpp --modelo large-v3-turbo --hilos 4 --flash-attn --dev 0
                                                         # una GPU concreta (p. ej. la integrada) antes de elegirla

Genera una muestra de 4 minutos en español con la voz de Windows (SAPI, es-MX) la primera vez,
la trocea igual que Recorder (pausa de 0,6 s tras 8 s, forzado a 20 s) y transcribe cada fragmento.
Imprime una tabla Markdown: velocidad en múltiplos del tiempo real (por debajo de 1,0x la cola
crece) y WER frente al guion, para ver si una configuración más rápida transcribe peor.

Mide con el equipo en reposo: cierra Recorder, Teams y el navegador. Si otros procesos consumen
CPU al empezar, avisa y no mide (salvo --forzar). Las cifras de docs/rendimiento.md salieron de aquí.

La muestra, el troceado, el WER y la carga del sistema viven en recorder/medicion.py: son los mismos de
«Medir mi equipo» (la prueba corta de la ventana y de la terminal), que no necesita este script.
"""
import argparse
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from recorder.audio.capture import DEFAULT_MAX_SEC, DEFAULT_MIN_SEC  # noqa: E402
from recorder.config.manager import ConfigManager  # noqa: E402
from recorder.medicion import (  # noqa: E402
    CARPETA_MUESTRA as CARPETA, GUION, RATE, CargaAjena, SinVoz, cargar_wav, cpu_ocupada_pct, fusionar,
    generar_muestra, trocear, wer,
)


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
    ap.add_argument("--turnos", type=int, help="usar solo los N primeros turnos del guion (muestra corta; por defecto los 22)")
    ap.add_argument("--forzar", action="store_true", help="medir aunque la CPU ya esté ocupada")
    ap.add_argument("--motor", choices=["faster-whisper", "whispercpp"], default="faster-whisper",
                    help="whispercpp = GPU con Vulkan (whispercpp_dir de config.json); --hilos pasa a ser -t del servidor")
    ap.add_argument("--precision", default="float16", help="whispercpp: float16, q8_0, q5_0...")
    ap.add_argument("--flash-attn", action="store_true", help="whispercpp: activar flash attention")
    ap.add_argument("--dev", type=int, help="whispercpp: GPU de Vulkan (-dev N; por defecto whispercpp_device de config.json)")
    args = ap.parse_args()

    ocupada = cpu_ocupada_pct()
    if ocupada > 15 and not args.forzar:
        sys.exit(f"La CPU ya está al {ocupada} % antes de empezar: cierra Recorder, Teams y el navegador, "
                 f"o usa --forzar (los números saldrán peores y poco comparables).")

    cfg = ConfigManager().load()
    modelo_nombre = args.modelo or cfg.model
    beam = args.beam or cfg.beam_size
    vocab = None if args.sin_vocab else (cfg.vocab.strip() or None)

    try:
        wav = generar_muestra(args.turnos)
    except SinVoz:
        sys.exit("No hay ninguna voz de Windows en español instalada: instálala en Configuración, Hora e idioma, Voz.")
    trozos = trocear(cargar_wav(wav), args.min, args.max)
    if args.fusion:
        trozos = fusionar(trozos, args.fusion)
    referencia = "\n".join(GUION[:args.turnos])
    duraciones = [len(t) / RATE for t in trozos]
    print(f"muestra: {sum(duraciones):.0f} s de audio en {len(trozos)} fragmentos "
          f"(media {sum(duraciones) / len(duraciones):.1f} s, máx {max(duraciones):.1f} s); "
          f"modelo {modelo_nombre}, beam {beam}, vocab {'sí' if vocab else 'no'}, CPU ajena al empezar {ocupada} %\n")

    gpu_usada = set()
    if args.motor == "whispercpp":
        from recorder.engine.whispercpp import load_whispercpp_model, whispercpp_ready

        if not whispercpp_ready(cfg.whispercpp_dir, modelo_nombre, args.precision):
            sys.exit(f"No hay whisper-server ni ggml de {modelo_nombre} ({args.precision}) en whispercpp_dir "
                     f"'{cfg.whispercpp_dir}': ver tools/instalar_whispercpp.ps1.")

        dev = cfg.whispercpp_device if args.dev is None else args.dev

        def cargar(hilos):
            modelo = load_whispercpp_model(
                cfg.whispercpp_dir, modelo_nombre, args.precision, "es", hilos, args.flash_attn, device=dev
            )
            usada = modelo.vulkan_device  # se imprime al final para no partir la tabla
            gpu_usada.add(f"{usada.index} = {usada.name}{' (integrada)' if usada.uma else ''}" if usada else
                          "el registro de whisper-server no dice cuál (¿sin GPU de Vulkan?)")
            return modelo

        sufijo = f"_whispercpp_{args.precision}{'_fa' if args.flash_attn else ''}{f'_dev{dev}' if dev >= 0 else ''}"
        print(f"motor whisper.cpp (Vulkan), precisión {args.precision}, flash attention {'sí' if args.flash_attn else 'no'}\n")
    else:
        from faster_whisper import WhisperModel

        def cargar(hilos):
            return WhisperModel(modelo_nombre, device="cpu", compute_type="int8", cpu_threads=hilos)

        sufijo = ""

    print("| cpu_threads | Velocidad (x tiempo real) | WER vs guion | CPU de otros procesos |")
    print("| ---: | ---: | ---: | ---: |")
    for hilos in [int(h) for h in args.hilos.split(",")]:
        modelo = cargar(hilos)
        try:
            velocidad, texto, otros = medir(modelo, trozos, beam, vocab, args.pasadas)
        finally:
            getattr(modelo, "close", lambda: None)()  # whisper.cpp: parar el servidor
        etiqueta = f"{hilos} (por defecto = 4)" if hilos == 0 else str(hilos)
        print(f"| {etiqueta} | {velocidad:.2f}x | {wer(referencia, texto):.1f} % | {otros} % |", flush=True)
        (CARPETA / f"texto_{modelo_nombre}_hilos{hilos}_beam{beam}{sufijo}.txt").write_text(texto, encoding="utf-8")
        del modelo
    if gpu_usada:
        print(f"\nGPU de whisper.cpp: {'; '.join(sorted(gpu_usada))}")
    print(f"\nTextos transcritos en {CARPETA} para compararlos a ojo.")


if __name__ == "__main__":
    main()
