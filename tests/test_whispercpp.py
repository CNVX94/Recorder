"""Motor whisper.cpp (Vulkan) a traves de whisper-server.

No hace falta GPU ni whisper.cpp compilado: `SERVIDOR_FALSO` es un whisper-server de mentira
en Python que habla el mismo HTTP (/health y /inference con verbose_json), tarda un poco en
"cargar el modelo" y puede morirse a proposito. Asi se prueba el contrato con el worker, el
reinicio tras una caida y la caida a CPU cuando no vuelve a arrancar.
"""

import io
import json
import pathlib
import queue
import sys
import tempfile
import textwrap
import threading
import time
import types
import unittest
import wave

import numpy as np

from recorder.actions.notes import NotesSession
from recorder.config.schema import AppConfig, apply_preset
from recorder.engine import whisper_worker as ww
from recorder.engine.whispercpp import (
    EngineUnavailable,
    WhisperCppModel,
    WhisperCppServer,
    model_filename,
    parse_segments,
    request_fields,
    server_command,
    wav_bytes,
    whispercpp_ready,
)
from recorder.filters.pipeline import TextPipeline

SERVIDOR_FALSO = textwrap.dedent(
    r'''
    import email.parser, json, os, pathlib, sys, time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    args = sys.argv[1:]
    opt = lambda name: args[args.index(name) + 1] if name in args else None
    marca = pathlib.Path(opt("--marca")) if opt("--marca") else None
    if "--no-arranca-con-marca" in args and marca and marca.exists():
        sys.exit(3)
    time.sleep(0.3)  # "cargando el modelo": aun no escucha

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, code, obj):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            self._json(200 if self.path == "/health" else 404, {"status": "ok"})

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            msg = email.parser.BytesParser().parsebytes(
                b"Content-Type: " + self.headers["Content-Type"].encode() + b"\r\n\r\n" + body)
            campos = {p.get_param("name", header="content-disposition"): p.get_payload(decode=True)
                      for p in msg.get_payload()}
            if "--muere-una-vez" in args and marca and not marca.exists():
                marca.write_text("x")
                os._exit(1)  # como un cierre del driver: sin responder
            recibido = {k: v.decode("utf-8") for k, v in campos.items() if k != "file"}
            recibido["wav_bytes"] = len(campos["file"])
            self._json(200, {"segments": [
                {"text": " Hola desde la GPU.", "avg_logprob": -0.2, "no_speech_prob": 0.05},
                {"text": " silencio inventado", "avg_logprob": -0.3, "no_speech_prob": 0.9},
            ], "recibido": recibido})

    HTTPServer(("127.0.0.1", int(opt("--port"))), H).serve_forever()
    '''
)


class TestPiezasPuras(unittest.TestCase):
    def test_wav_de_16_khz_mono_16_bits(self):
        audio = np.array([0.0, 0.5, -1.0, 2.0], dtype=np.float32)  # 2.0 se recorta
        with wave.open(io.BytesIO(wav_bytes(audio))) as w:
            self.assertEqual((w.getframerate(), w.getnchannels(), w.getsampwidth()), (16000, 1, 2))
            pcm = np.frombuffer(w.readframes(4), dtype="<i2")
        self.assertEqual(pcm.tolist(), [0, 16383, -32767, 32767])

    def test_campos_equivalentes_a_process(self):
        f = request_fields("es", 5, "vocabulario", vad=True)
        self.assertEqual(f["response_format"], "verbose_json")
        self.assertEqual((f["language"], f["beam_size"], f["prompt"], f["vad"]), ("es", "5", "vocabulario", "true"))
        self.assertEqual(f["no_language_probabilities"], "true")
        self.assertNotIn("prompt", request_fields("es", 1, None, vad=False))

    def test_nombre_del_modelo_segun_precision(self):
        self.assertEqual(model_filename("large-v3", "float16"), "ggml-large-v3.bin")
        self.assertEqual(model_filename("large-v3-turbo", "q8_0"), "ggml-large-v3-turbo-q8_0.bin")

    def test_listo_solo_con_servidor_y_modelo(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            self.assertFalse(whispercpp_ready("", "large-v3", "float16"))
            (root / "bin").mkdir()
            (root / "bin" / "whisper-server.exe").write_bytes(b"")
            self.assertFalse(whispercpp_ready(d, "large-v3", "float16"), "falta el modelo")
            (root / "models").mkdir()
            (root / "models" / "ggml-large-v3.bin").write_bytes(b"")
            self.assertTrue(whispercpp_ready(d, "large-v3", "float16"))

    def test_comando_con_flash_attention_apagada_y_vad_si_existe(self):
        with tempfile.TemporaryDirectory() as d:
            cmd = server_command(d, "large-v3", "float16", "es", threads=5, flash_attn=False)
            self.assertIn("-nfa", cmd)
            self.assertNotIn("--vad", cmd)
            self.assertEqual(cmd[cmd.index("-t") + 1], "5")
            (pathlib.Path(d) / "models").mkdir()
            (pathlib.Path(d) / "models" / "ggml-silero-v6.2.0.bin").write_bytes(b"")
            cmd = server_command(d, "large-v3", "float16", "es", threads=0, flash_attn=True)
            self.assertIn("-fa", cmd)
            self.assertIn("--vad", cmd)
            self.assertNotIn("-t", cmd)

    def test_los_segmentos_pasan_por_los_filtros_de_siempre(self):
        payload = {"segments": [
            {"text": " Frase buena.", "avg_logprob": -0.2, "no_speech_prob": 0.1},
            {"text": " Gracias por ver", "avg_logprob": -0.1, "no_speech_prob": 0.9},
            {"text": " sí sí sí sí sí sí sí sí sí sí sí sí sí sí sí sí sí sí", "avg_logprob": -0.2, "no_speech_prob": 0.1},
        ]}
        texto, _ = TextPipeline(keywords=[], ignore=[], fixes={}).process_segments(parse_segments(payload))
        self.assertEqual(texto, "Frase buena.")  # sin voz y bucle (compression_ratio local) fuera


class ServidorFalso(unittest.TestCase):
    def setUp(self):
        # Windows puede tardar unas decimas en soltar el log de un proceso recien terminado
        # (antivirus, indexador): que eso no cuente como fallo de la prueba.
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.dir = pathlib.Path(tmp.name)
        self.script = self.dir / "servidor_falso.py"
        self.script.write_text(SERVIDOR_FALSO, encoding="utf-8")
        self.marca = self.dir / "murio"

    def servidor(self, *extra, timeout=10.0):
        # El python.exe de un venv es un lanzador que crea otro proceso: se usa el interprete real.
        python = getattr(sys, "_base_executable", sys.executable)
        cmd = [python, str(self.script), "--marca", str(self.marca), *extra]
        srv = WhisperCppServer(cmd, self.dir / "logs" / "server.log", load_timeout=timeout)
        self.addCleanup(srv.stop)
        return srv


class TestServidor(ServidorFalso):
    def test_transcribe_con_la_forma_de_faster_whisper(self):
        srv = self.servidor()
        srv.start()
        segs, payload = WhisperCppModel(srv, has_vad=True).transcribe(
            np.zeros(16000, dtype=np.float32), language="es", beam_size=5, vad_filter=True,
            condition_on_previous_text=False, initial_prompt="Jenkins, Redis", repetition_penalty=1.1,
        )
        self.assertEqual([s.text for s in segs], [" Hola desde la GPU.", " silencio inventado"])
        self.assertEqual(segs[1].no_speech_prob, 0.9)
        recibido = payload["recibido"]
        self.assertEqual((recibido["language"], recibido["beam_size"], recibido["prompt"]), ("es", "5", "Jenkins, Redis"))
        self.assertEqual(recibido["vad"], "true")
        self.assertEqual(recibido["wav_bytes"], 44 + 2 * 16000)

    def test_sin_modelo_de_vad_no_pide_vad(self):
        srv = self.servidor()
        srv.start()
        _, payload = WhisperCppModel(srv, has_vad=False).transcribe(np.zeros(1600, dtype=np.float32))
        self.assertEqual(payload["recibido"]["vad"], "false")

    def test_si_muere_al_arrancar_lo_dice_con_su_codigo(self):
        self.marca.write_text("x")
        srv = self.servidor("--no-arranca-con-marca")
        with self.assertRaisesRegex(RuntimeError, "codigo 3"):
            srv.start()
        self.assertFalse(srv.alive())

    def test_si_se_cae_en_un_fragmento_se_reinicia_y_lo_reintenta(self):
        srv = self.servidor("--muere-una-vez")
        srv.start()
        primer_proceso = srv.proc.pid
        segs, _ = WhisperCppModel(srv, has_vad=True).transcribe(np.zeros(1600, dtype=np.float32))
        self.assertEqual(segs[0].text, " Hola desde la GPU.")
        self.assertNotEqual(srv.proc.pid, primer_proceso, "debio arrancar un proceso nuevo")

    def test_si_no_vuelve_a_arrancar_avisa_para_cambiar_de_motor(self):
        srv = self.servidor("--muere-una-vez", "--no-arranca-con-marca")
        srv.start()
        with self.assertRaises(EngineUnavailable):
            WhisperCppModel(srv, has_vad=True).transcribe(np.zeros(1600, dtype=np.float32))

    def test_cerrar_termina_el_proceso(self):
        srv = self.servidor()
        srv.start()
        proc = srv.proc
        WhisperCppModel(srv, has_vad=True).close()
        self.assertIsNotNone(proc.poll())
        self.assertFalse(srv.alive())


class TestWorkerConVulkan(unittest.TestCase):
    """Con el preset Extra, sin CUDA y con whisper.cpp instalado, el worker usa Vulkan."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = AppConfig(notes_dir=tmp.name, caps_dir=str(pathlib.Path(tmp.name) / "caps"), keywords=[])
        apply_preset(self.cfg, "extra")
        self.cfg.whispercpp_dir = "E:/whispercpp"
        self.session = NotesSession(tmp.name)
        self.chunks, self.ui, self.stop = queue.Queue(), queue.Queue(), threading.Event()
        self.addCleanup(self.stop.set)
        # Sin lista de Vulkan (como si no se pudiera consultar): no depende de las GPUs del equipo
        # que ejecuta la prueba (con solo una iGPU, "auto" caeria a CPU).
        for nombre, valor in (
            ("detect_cuda_device_count", lambda: 0),
            ("whispercpp_ready", lambda *a: True),
            ("cached_vulkan_devices", lambda: []),
        ):
            original = getattr(ww, nombre)
            setattr(ww, nombre, valor)
            self.addCleanup(setattr, ww, nombre, original)
        self.cpu_pedidos = []
        falso = types.ModuleType("faster_whisper")
        cpu_seg = types.SimpleNamespace(text="Texto desde la CPU.", no_speech_prob=0.1, avg_logprob=-0.2)

        def WhisperModel(nombre, **kw):
            self.cpu_pedidos.append((nombre, kw["device"]))
            return types.SimpleNamespace(transcribe=lambda audio, **k: ([cpu_seg], None))

        falso.WhisperModel = WhisperModel
        previo = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = falso
        self.addCleanup(lambda: sys.modules.__setitem__("faster_whisper", previo)
                        if previo else sys.modules.pop("faster_whisper", None))

    def arrancar(self, modelo_gpu):
        self.cargas = []

        def cargar(*args):
            self.cargas.append(args)
            if isinstance(modelo_gpu, Exception):
                raise modelo_gpu
            return modelo_gpu

        original = ww.load_whispercpp_model
        ww.load_whispercpp_model = cargar
        self.addCleanup(setattr, ww, "load_whispercpp_model", original)
        worker = ww.TranscriberWorker(self.cfg, self.chunks, self.ui, self.session, self.stop)
        hilo = threading.Thread(target=worker.run, daemon=True)
        hilo.start()
        return worker, hilo

    def esperar(self, cond, limite=4.0):
        fin = time.time() + limite
        while time.time() < fin and not cond():
            time.sleep(0.05)
        return cond()

    def estados(self):
        out = []
        while not self.ui.empty():
            m = self.ui.get()
            if m[0] == "status":
                out.append(m[1])
        return out

    def test_carga_large_v3_en_whispercpp_con_la_configuracion(self):
        gpu_seg = types.SimpleNamespace(text="Texto desde la GPU.", no_speech_prob=0.1, avg_logprob=-0.2)
        modelo = types.SimpleNamespace(transcribe=lambda audio, **k: ([gpu_seg], None), close=lambda: None)
        self.cfg.cpu_threads = 5
        _worker, hilo = self.arrancar(modelo)
        self.chunks.put((time.time(), "out", np.zeros(10)))
        nota = lambda: self.session.file_path.read_text(encoding="utf-8")  # noqa: E731
        self.assertTrue(self.esperar(lambda: "desde la GPU" in nota()))
        self.assertEqual(self.cargas[0], ("E:/whispercpp", "large-v3", "float16", "es", 5, False))
        self.assertEqual(self.cpu_pedidos, [], "con Vulkan no debe cargar faster-whisper")

    def test_si_vulkan_no_arranca_cae_al_preset_de_cpu_entero(self):
        worker, _hilo = self.arrancar(RuntimeError("vk::DeviceLostError"))
        self.assertTrue(self.esperar(lambda: self.cpu_pedidos))
        self.assertEqual(self.cpu_pedidos, [("large-v3-turbo", "cpu")])
        self.assertTrue(any("Vulkan" in e for e in self.estados()))

    def test_si_el_servidor_muere_sin_remedio_el_fragmento_se_hace_en_cpu(self):
        cerrado = []

        def revienta(audio, **k):
            raise EngineUnavailable("whisper-server se cayo y no volvio a arrancar")

        modelo = types.SimpleNamespace(transcribe=revienta, close=lambda: cerrado.append(True))
        worker, hilo = self.arrancar(modelo)
        self.chunks.put((time.time(), "out", np.zeros(10)))
        nota = lambda: self.session.file_path.read_text(encoding="utf-8")  # noqa: E731
        self.assertTrue(self.esperar(lambda: "desde la CPU" in nota()), "el fragmento se perdio")
        self.assertEqual(worker.errors, 0)
        self.assertEqual(self.cpu_pedidos, [("large-v3-turbo", "cpu")])
        self.assertEqual(cerrado, [True], "el motor caido debe cerrarse al cambiar a CPU")
        self.assertTrue(any("se sigue en CPU" in e for e in self.estados()))
        self.stop.set()
        hilo.join(timeout=3)
        self.assertFalse(hilo.is_alive())


if __name__ == "__main__":
    unittest.main()
