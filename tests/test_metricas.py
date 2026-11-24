"""Métricas: motor efectivo, velocidad del transcriptor y coste para el equipo (recorder/metricas.py).

La velocidad y los % de CPU se prueban con reloj y contadores falsos; el motor efectivo, cargando
el transcriptor con faster-whisper y whisper.cpp de mentira (como test_whispercpp.py), para que
lo que se describe sea lo que de verdad decide `_load_model`. Las lecturas reales de Windows solo
se prueban de humo: que no revienten y devuelvan algo con forma.
"""
import os
import queue
import sys
import tempfile
import threading
import time
import types
import unittest
from types import SimpleNamespace as S
from unittest import mock

from recorder import metricas as met
from recorder.actions.notes import NotesSession
from recorder.config.hardware import GpuInfo
from recorder.config.schema import CPU_FALLBACK_PRESET, QUALITY_PRESETS, AppConfig, apply_preset
from recorder.engine import whisper_worker as ww
from recorder.engine.whispercpp import EngineUnavailable, VulkanLogDevice
from recorder.metricas import Metricas, MotorEfectivo, Muestreador, Velocidad, gpu_pct

RX = GpuInfo("AMD Radeon RX 6700 XT", 0x1002, 0x73DF, 12272, vulkan_index=0)
IRIS = GpuInfo("Intel(R) Iris(R) Xe Graphics", 0x8086, 0x46A8, 128, integrated=True, vulkan_index=0)
ALTA = QUALITY_PRESETS[CPU_FALLBACK_PRESET]


class TestVelocidad(unittest.TestCase):
    def test_media_movil_ponderada_por_audio_y_ultimo_fragmento(self):
        v = Velocidad(ventana=2)
        self.assertIsNone(v.media)
        self.assertIsNone(v.ultimo_s)
        v.registrar(10, 5)
        v.registrar(20, 5)
        self.assertAlmostEqual(v.media, 3.0, msg="30 s de audio en 10 s, no la media de 2× y 4×")
        v.registrar(10, 10)
        self.assertAlmostEqual(v.media, 30 / 15, msg="solo los dos últimos")
        self.assertEqual(v.ultimo_s, 10)

    def test_resumen_media_de_la_sesion_y_p95_por_el_lado_lento(self):
        v = Velocidad(ventana=1)
        for audio, proceso in ((10, 5), (20, 5), (10, 10)):  # 2×, 4×, 1×
            v.registrar(audio, proceso)
        media, p95, n = v.resumen()
        self.assertAlmostEqual(media, 40 / 20)
        self.assertAlmostEqual(p95, 1.1, msg="el 95 % fue al menos así de rápido")
        self.assertEqual(n, 3)

    def test_ignora_fragmentos_sin_duracion(self):
        v = Velocidad()
        v.registrar(0, 1)
        v.registrar(1, 0)
        self.assertEqual(v.resumen(), (None, None, 0))


class Contadores:
    """Reloj, CPU del sistema y de los procesos y GPU de mentira, que la prueba va moviendo."""

    def __init__(self):
        self.t = 0.0
        self.sis = (1000, 2000)  # (reposo, total) en 100 ns
        self.cpu_s, self.ram = 10.0, 300 * 2**20
        self.gpu = None
        self.pedidos = []  # pids que se leyeron en cada muestra

    def procesos(self, pids):
        self.pedidos.append(tuple(pids))
        return self.cpu_s, self.ram

    def avanzar(self, dt, cpu_s, reposo, total):
        self.t += dt
        self.cpu_s += cpu_s
        self.sis = (self.sis[0] + reposo, self.sis[1] + total)


class TestMuestreador(unittest.TestCase):
    def setUp(self):
        self.c = Contadores()
        self.cola = (0, 0.0)
        self.trans = S(motor=None, velocidad=Velocidad(), modelo=None)
        self.m = Muestreador(
            self.trans, lambda: self.cola, reloj=lambda: self.c.t, sistema=lambda: self.c.sis,
            procesos=self.c.procesos, gpu=lambda: self.c.gpu, n_cpus=4, pid=100,
        )

    def test_cpu_del_proceso_y_del_sistema_entre_dos_muestras(self):
        self.m.muestrear()
        f = self.m.foto()
        self.assertIsNone(f.cpu_proceso, "sin muestra previa no hay %: n/d")
        self.assertIsNone(f.cpu_sistema)
        self.c.avanzar(2.0, cpu_s=2.0, reposo=600, total=1000)
        self.m.muestrear()
        f = self.m.foto()
        self.assertAlmostEqual(f.cpu_proceso, 25.0, msg="2 s de CPU en 2 s con 4 CPUs")
        self.assertAlmostEqual(f.cpu_sistema, 40.0)
        self.assertAlmostEqual(f.ram_mb, 300.0)

    def test_suma_whisper_server_y_no_mezcla_tramos_si_cambia(self):
        self.m.muestrear()
        self.trans.modelo = S(pid=999)  # arrancó whisper-server
        self.c.avanzar(2.0, cpu_s=50.0, reposo=0, total=1000)  # su tiempo acumulado no es de este tramo
        self.m.muestrear()
        self.assertEqual(self.c.pedidos, [(100,), (100, 999)])
        self.assertIsNone(self.m.cpu_proceso)
        self.c.avanzar(2.0, cpu_s=4.0, reposo=0, total=1000)
        self.m.muestrear()
        self.assertAlmostEqual(self.m.cpu_proceso, 50.0)
        self.assertEqual(self.m.muestras_cpu, 1, "la media solo cuenta tramos limpios")

    def test_gpu_que_no_se_puede_leer_es_nd(self):
        self.m.muestrear()
        self.assertIsNone(self.m.foto().gpu_sistema)
        self.assertIsNone(self.m.foto().gpu_proceso)

    def test_gpu_del_sistema_y_de_recorder(self):
        self.trans.modelo = S(pid=999)
        self.c.gpu = [
            ("pid_555_luid_0x00000000_0x0000D3B4_phys_0_eng_0_engtype_3D", 70.0),  # otro proceso
            ("pid_100_luid_0x00000000_0x0000D3B4_phys_0_eng_0_engtype_3D", 5.0),
            ("pid_999_luid_0x00000000_0x0000D3B4_phys_0_eng_1_engtype_Compute", 50.0),
        ]
        self.m.muestrear()
        self.assertEqual((self.m.gpu_sistema, self.m.gpu_proceso), (75.0, 50.0))

    def test_gpu_pct_ignora_instancias_raras_y_no_pasa_de_100(self):
        self.assertEqual(gpu_pct([("_Total", 99.0)]), (0.0, 0.0))
        self.assertEqual(gpu_pct([(f"pid_{p}_luid_0x0_0x1_phys_0_eng_0_engtype_3D", 60.0) for p in (1, 2)], (1,)), (100.0, 60.0))

    def test_resumen_para_el_registro(self):
        self.trans.motor = MotorEfectivo("faster-whisper", "cpu", "small", 5, 4)
        for audio, proceso in ((10, 5), (20, 5), (10, 10)):
            self.trans.velocidad.registrar(audio, proceso)
        self.m.muestrear()
        for cola in ((3, 45.0), (1, 10.0)):
            self.cola = cola
            self.c.avanzar(2.0, cpu_s=2.0, reposo=600, total=1000)
            self.m.muestrear()
        r = self.m.resumen()
        self.assertIn("faster-whisper · CPU, 4 hilos · small · haz 5", r)
        self.assertIn("velocidad media 2,0× tiempo real, p95 1,1× (3 fragmentos)", r)
        self.assertIn("CPU media 25 % (sistema 40 %)", r)
        self.assertIn("pico de cola 3 fragmentos (~45 s de audio)", r)
        self.assertEqual((self.m.foto().cola, self.m.foto().atraso_s), (1, 10.0))

    def test_resumen_sin_modelo_ni_muestras(self):
        r = self.m.resumen()
        self.assertIn("modelo sin cargar · sin fragmentos transcritos · CPU media n/d (sistema n/d)", r)

    def test_parar_solo_cuenta_la_primera_vez(self):
        self.m.iniciar()
        self.assertTrue(self.m.parar())
        self.assertFalse(self.m.parar())

    def test_linea_del_pie(self):
        f = Metricas(None, None, None, None, None, None, None, None, 0, 0.0)
        self.assertEqual(f.linea, "", "mientras carga el modelo no hay línea")
        motor = MotorEfectivo("faster-whisper", "cpu", "small", 5, 4)
        self.assertEqual(Metricas(motor, None, None, None, None, None, None, None, 0, 0.0).linea, motor.texto)
        self.assertEqual(
            Metricas(motor, 2.14, 3.0, None, None, None, None, None, 0, 0.0).linea,
            "faster-whisper · CPU, 4 hilos · small · haz 5 · 2,1× tiempo real",
        )


class TestLecturasReales(unittest.TestCase):
    """De humo: las firmas de ctypes no revientan en este Windows."""

    def test_sistema_y_proceso(self):
        sis = met.tiempos_sistema()
        self.assertIsNotNone(sis)
        self.assertGreater(sis[1], sis[0])
        cpu_s, ram = met.leer_procesos([os.getpid()])
        self.assertGreater(cpu_s, 0)
        self.assertGreater(ram, 0)
        self.assertEqual(met.leer_procesos([0x7FFFFFF0]), (0.0, 0), "un proceso que no existe suma 0")

    def test_gpu_n_d_o_instancias(self):
        lector = met.LectorGpu()
        for _ in range(2):  # la primera lectura de un contador de tasa no tiene valor
            items = lector()
        self.assertTrue(items is None or all(isinstance(n, str) and v >= 0 for n, v in items), items)


class TestMotorEfectivo(unittest.TestCase):
    """Lo que `_load_model` deja en `worker.motor` en cada camino: CPU, CUDA, Vulkan dedicada,
    Vulkan integrada pedida a mano y las caídas a CPU."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        self.cfg = AppConfig(notes_dir=tmp.name, caps_dir=os.path.join(tmp.name, "caps"), keywords=[])
        self.cfg.whispercpp_dir = ""  # sin whisper.cpp salvo en las pruebas de Vulkan
        self.cuda, self.vulkan, self.usada, self.vulkan_falla = 0, [], None, None
        falso = types.ModuleType("faster_whisper")
        falso.WhisperModel = lambda nombre, **kw: S(transcribe=lambda audio, **k: ([], None))
        for parche in (
            mock.patch.dict(sys.modules, {"faster_whisper": falso}),
            mock.patch.object(ww, "detect_cuda_device_count", lambda: self.cuda),
            mock.patch.object(ww, "whispercpp_ready", lambda d, *a: bool(d)),  # listo si hay carpeta
            mock.patch.object(ww, "cached_vulkan_devices", lambda: self.vulkan),
            mock.patch.object(ww, "load_whispercpp_model", self.cargar_vulkan),
        ):
            parche.start()
            self.addCleanup(parche.stop)

    def cargar_vulkan(self, *a, **kw):
        if self.vulkan_falla:
            raise self.vulkan_falla
        return S(close=lambda: None, vulkan_device=self.usada, transcribe=self.vulkan_transcribe)

    vulkan_transcribe = None

    def motor(self) -> MotorEfectivo:
        stop = threading.Event()
        stop.set()  # solo interesa la carga del modelo
        worker = ww.TranscriberWorker(self.cfg, queue.Queue(), queue.Queue(), NotesSession(self.tmp), stop)
        worker.run()
        return worker.motor

    def test_cpu_con_los_hilos_por_defecto_de_ctranslate2(self):
        apply_preset(self.cfg, "media")
        self.cfg.cpu_threads = 0
        m = self.motor()
        self.assertEqual(m.texto, f"faster-whisper · CPU, 4 hilos · {self.cfg.model} · haz {self.cfg.beam_size}")
        self.assertEqual(m.caida, "")
        self.cfg.cpu_threads = 6
        self.assertEqual(self.motor().hilos, 6)

    def test_cuda(self):
        apply_preset(self.cfg, "extra")
        self.cuda = 1
        self.assertEqual(self.motor().texto, "faster-whisper · GPU NVIDIA (dedicada, CUDA) · large-v3 · haz 5")

    def test_vulkan_dedicada_segun_el_registro(self):
        apply_preset(self.cfg, "extra")
        self.cfg.whispercpp_dir = "E:/whispercpp"
        self.vulkan = [RX]
        self.usada = VulkanLogDevice(0, "AMD Radeon RX 6700 XT", "AMD proprietary driver", False)
        m = self.motor()
        self.assertEqual(m.texto, "whisper.cpp · GPU AMD Radeon RX 6700 XT (dedicada, Vulkan) · large-v3 · haz 5")
        self.assertEqual((m.dispositivo, m.integrada, m.hilos), ("vulkan", False, 0))

    def test_vulkan_integrada_pedida_a_mano(self):
        apply_preset(self.cfg, "extra")
        self.cfg.whispercpp_dir = "E:/whispercpp"
        self.cfg.whispercpp_device = 0
        self.vulkan = [IRIS]
        self.usada = VulkanLogDevice(0, "Intel(R) Iris(R) Xe Graphics", "Intel Corporation", True)
        m = self.motor()
        self.assertEqual(m.texto, "whisper.cpp · GPU Intel(R) Iris(R) Xe Graphics (integrada, Vulkan) · large-v3-turbo · haz 5")
        self.assertEqual(m.caida, "")

    def test_caida_a_cpu_sin_gpu(self):
        apply_preset(self.cfg, "extra")
        self.cfg.cpu_threads = 0
        m = self.motor()
        self.assertEqual(m.texto, f"faster-whisper · CPU, 4 hilos · {ALTA.model} · haz {ALTA.beam_size} · ⚠ caída a CPU")
        self.assertIn("no tiene", m.caida)
        self.assertFalse(m.caida.startswith("⚠"))

    def test_caida_a_cpu_si_vulkan_no_arranca(self):
        apply_preset(self.cfg, "extra")
        self.cfg.whispercpp_dir = "E:/whispercpp"
        self.vulkan = [RX]
        self.vulkan_falla = RuntimeError("vk::DeviceLostError")
        m = self.motor()
        self.assertEqual((m.motor, m.dispositivo, m.modelo), ("faster-whisper", "cpu", ALTA.model))
        self.assertIn("DeviceLostError", m.caida)

    def test_caida_a_cpu_si_whispercpp_toma_la_integrada_sin_pedirla(self):
        apply_preset(self.cfg, "extra")
        self.cfg.whispercpp_dir = "E:/whispercpp"
        self.usada = VulkanLogDevice(0, "Intel(R) Iris(R) Xe Graphics", "Intel Corporation", True)
        m = self.motor()
        self.assertEqual(m.dispositivo, "cpu")
        self.assertIn("integrada", m.caida)

    def test_caida_a_cpu_en_plena_reunion_y_velocidad(self):
        apply_preset(self.cfg, "extra")
        self.cfg.whispercpp_dir = "E:/whispercpp"
        self.vulkan = [RX]

        def revienta(audio, **k):
            raise EngineUnavailable("whisper-server se cayo y no volvio a arrancar")

        self.vulkan_transcribe = revienta
        chunks, stop = queue.Queue(), threading.Event()
        worker = ww.TranscriberWorker(self.cfg, chunks, queue.Queue(), NotesSession(self.tmp), stop)
        hilo = threading.Thread(target=worker.run, daemon=True)
        hilo.start()
        chunks.put((time.time(), "out", [0.0] * 32000))  # 2 s de audio
        fin = time.time() + 4
        while not worker.velocidad.fragmentos and time.time() < fin:
            time.sleep(0.05)
        stop.set()
        hilo.join(timeout=3)
        self.assertEqual(worker.motor.dispositivo, "cpu")
        self.assertIn("se cayo", worker.motor.caida)
        self.assertEqual(len(worker.velocidad.fragmentos), 1, "el fragmento rehecho en CPU cuenta para la velocidad")
        self.assertEqual(worker.velocidad.fragmentos[0][0], 2.0)


if __name__ == "__main__":
    unittest.main()
