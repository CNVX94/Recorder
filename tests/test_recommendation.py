"""Recomendacion de configuracion segun el hardware, y eleccion de la GPU de Vulkan.

Todo con perfiles sinteticos (`HardwareProfile` es un dataclass): no hace falta ninguna GPU para
fijar que una NVIDIA de 12 GB va a Extra, que una RX sin whisper.cpp se queda en CPU diciendo
como instalarlo o que una iGPU nunca se elige sola. Al final, el worker: pasa `-dev` con la GPU
elegida y no acepta una integrada que whisper.cpp haya tomado por su cuenta.
"""

import pathlib
import queue
import sys
import tempfile
import threading
import types
import unittest

from recorder.actions.notes import NotesSession
from recorder.config.hardware import VENDOR_AMD, VENDOR_INTEL, VENDOR_NVIDIA, GpuInfo, HardwareProfile
from recorder.config.schema import (
    QUALITY_PRESETS,
    AppConfig,
    apply_preset,
    apply_recommendation,
    choose_vulkan_device,
    config_heavier_than,
    describe_recommendation,
    recommend_config,
    recommended_cpu_threads,
    resolve_runtime,
    startup_notices,
)
from recorder.engine import whisper_worker as ww
from recorder.engine.whispercpp import VulkanLogDevice

RX = GpuInfo("AMD Radeon RX 6700 XT", VENDOR_AMD, 0x73DF, vram_mb=12243, vulkan_index=0, luid=1)
RTX_12 = GpuInfo("NVIDIA GeForce RTX 3060", VENDOR_NVIDIA, 0x2504, vram_mb=12288, vulkan_index=0)
GTX_4 = GpuInfo("NVIDIA GeForce GTX 1650", VENDOR_NVIDIA, 0x1F82, vram_mb=4096, vulkan_index=0)
IRIS = GpuInfo("Intel(R) Iris(R) Xe Graphics", VENDOR_INTEL, 0x46A8, vram_mb=128, integrated=True, vulkan_index=0)


def i5_9500(**kw) -> HardwareProfile:
    """El sobremesa medido: i5-9500 de 6 nucleos sin HT, AVX2, 16 GB, enchufado."""
    base = dict(
        cpu_name="Intel(R) Core(TM) i5-9500 CPU @ 3.00GHz", physical_cores=6, logical_cores=6,
        p_cores=6, e_cores=0, avx2=True, ram_total_mb=16327, desktop=True,
    )
    base.update(kw)
    return HardwareProfile(**base)


def i7_1255u(**kw) -> HardwareProfile:
    """El portatil medido: 2P (con HT) + 8E, AVX2, 32 GB, Iris Xe."""
    base = dict(
        cpu_name="12th Gen Intel(R) Core(TM) i7-1255U", physical_cores=10, logical_cores=12,
        p_cores=2, e_cores=8, avx2=True, ram_total_mb=32480, desktop=False, has_battery=True,
        gpus=[IRIS], vulkan_devices=[IRIS],
    )
    base.update(kw)
    return HardwareProfile(**base)


def con_gpu(perfil: HardwareProfile, gpu: GpuInfo, cuda: int = 0) -> HardwareProfile:
    perfil.gpus = [gpu]
    perfil.vulkan_devices = [gpu]
    perfil.cuda_devices = cuda
    return perfil


class TestGamasDeGpu(unittest.TestCase):
    def test_nvidia_12_gb_con_cuda_es_extra(self):
        rec = recommend_config(con_gpu(i5_9500(), RTX_12, cuda=1))
        self.assertEqual((rec.preset, rec.model, rec.device), ("extra", "large-v3", "gpu"))
        self.assertEqual((rec.engine, rec.tier), ("faster-whisper", "gpu-nvidia"))

    def test_nvidia_de_4_gb_va_a_turbo_en_cuda(self):
        rec = recommend_config(con_gpu(i5_9500(), GTX_4, cuda=1))
        self.assertIsNone(rec.preset)
        self.assertEqual((rec.model, rec.device, rec.compute_type), ("large-v3-turbo", "cuda", "float16"))

    def test_nvidia_vista_por_dxgi_sin_cuda_se_queda_en_cpu_y_dice_por_que(self):
        rec = recommend_config(con_gpu(i5_9500(), RTX_12, cuda=0))
        self.assertEqual(rec.device, "cpu")
        self.assertTrue(rec.tier.startswith("cpu-"))
        self.assertIn("CUDA", rec.reason)
        self.assertIn("RTX 3060", rec.reason)

    def test_i5_con_rx_6700_xt_y_whispercpp_va_a_turbo_en_vulkan(self):
        rec = recommend_config(con_gpu(i5_9500(), RX), vulkan_turbo_ready=True, vulkan_large_ready=True)
        self.assertEqual((rec.model, rec.beam_size, rec.device, rec.compute_type),
                         ("large-v3-turbo", 5, "vulkan", "float16"))
        self.assertEqual((rec.engine, rec.tier, rec.confidence), ("whisper.cpp", "gpu-vulkan", "medida"))
        self.assertTrue(rec.flash_attn)
        self.assertEqual(rec.cpu_threads, 5)

    def test_otra_gpu_dedicada_con_whispercpp_es_estimada(self):
        otra = GpuInfo("AMD Radeon RX 7600", VENDOR_AMD, 0x7480, vram_mb=8192, vulkan_index=0)
        rec = recommend_config(con_gpu(i5_9500(), otra), vulkan_turbo_ready=True)
        self.assertEqual((rec.device, rec.confidence), ("vulkan", "estimada"))

    def test_rx_sin_whispercpp_es_media_y_explica_como_instalarlo(self):
        rec = recommend_config(con_gpu(i5_9500(), RX))
        self.assertEqual((rec.preset, rec.device), ("media", "cpu"))
        self.assertIn("instalar_whispercpp.ps1", rec.reason)

    def test_solo_large_v3_descargado_es_extra_y_sugiere_turbo(self):
        rec = recommend_config(con_gpu(i5_9500(), RX), vulkan_turbo_ready=False, vulkan_large_ready=True)
        self.assertEqual((rec.preset, rec.engine), ("extra", "whisper.cpp"))
        self.assertIn("large-v3-turbo", rec.reason)

    def test_solo_igpu_se_trata_como_cpu_aunque_whispercpp_este_listo(self):
        rec = recommend_config(i7_1255u(), vulkan_turbo_ready=True, vulkan_large_ready=True)
        self.assertEqual(rec.device, "cpu")
        self.assertIn("integrada", rec.reason)


class TestGamasDeCpu(unittest.TestCase):
    def test_dos_nucleos_sin_avx2_es_baja(self):
        p = HardwareProfile(cpu_name="Intel(R) Celeron(R) N4020", physical_cores=2, logical_cores=2,
                            p_cores=2, avx2=False, ram_total_mb=4000)
        rec = recommend_config(p)
        self.assertEqual((rec.preset, rec.tier), ("baja", "cpu-baja"))
        self.assertIn("AVX2", rec.reason)
        self.assertEqual(rec.cpu_threads, 2, "nunca mas hilos que nucleos fisicos")

    def test_poca_ram_es_baja(self):
        self.assertEqual(recommend_config(i5_9500(ram_total_mb=3900)).preset, "baja")

    def test_ocho_nucleos_enchufado_es_alta_y_con_bateria_baja_una_gama(self):
        p = dict(cpu_name="AMD Ryzen 7 5800U with Radeon Graphics", physical_cores=8, logical_cores=16,
                 p_cores=8, avx2=True, ram_total_mb=16000, desktop=False, has_battery=True)
        self.assertEqual(recommend_config(HardwareProfile(**p)).preset, "alta")
        rec = recommend_config(HardwareProfile(**p, on_battery=True))
        self.assertEqual(rec.preset, "media")
        self.assertIn("batería", rec.reason)

    def test_media_con_bateria_baja_a_baja(self):
        self.assertEqual(recommend_config(i5_9500(on_battery=True, has_battery=True)).preset, "baja")

    def test_hibrida_con_pocos_nucleos_p_es_media_y_medida(self):
        # El i7-1255U tiene 10 nucleos, pero 8 son E: turbo iba a ~1,0x y la cola crecia.
        rec = recommend_config(i7_1255u())
        self.assertEqual((rec.preset, rec.confidence), ("media", "medida"))
        self.assertEqual(rec.cpu_threads, 9)

    def test_hibrida_con_seis_p_es_alta(self):
        p = HardwareProfile(cpu_name="12th Gen Intel(R) Core(TM) i7-12700H", physical_cores=14, logical_cores=20,
                            p_cores=6, e_cores=8, avx2=True, ram_total_mb=16000)
        rec = recommend_config(p)
        self.assertEqual(rec.preset, "alta")
        self.assertEqual(rec.cpu_threads, 6)

    def test_perfil_sin_datos_no_revienta(self):
        rec = recommend_config(HardwareProfile())
        self.assertEqual(rec.preset, "baja")  # sin AVX2 conocido: lo prudente
        self.assertTrue(describe_recommendation(rec))


class TestHilos(unittest.TestCase):
    def caso(self, fisicos, p=None, e=0):
        return recommended_cpu_threads(HardwareProfile(physical_cores=fisicos, p_cores=fisicos if p is None else p, e_cores=e))

    def test_homogenea_deja_un_nucleo_y_nunca_menos_de_cuatro(self):
        self.assertEqual(self.caso(6), 5)
        self.assertEqual(self.caso(4), 4)
        self.assertEqual(self.caso(16), 15)

    def test_hibrida(self):
        self.assertEqual(self.caso(14, p=6, e=8), 6)  # >= 4 P: los P
        self.assertEqual(self.caso(10, p=2, e=8), 9)  # pocos P: fisicos - 1

    def test_nunca_mas_que_fisicos_y_cero_si_no_se_sabe(self):
        self.assertEqual(self.caso(2), 2)
        self.assertEqual(self.caso(0), 0)


class TestComparaciones(unittest.TestCase):
    def setUp(self):
        self.media = recommend_config(i5_9500())
        self.vulkan = recommend_config(con_gpu(i5_9500(), RX), vulkan_turbo_ready=True)

    def config(self, preset):
        c = AppConfig()
        apply_preset(c, preset)
        return c

    def test_alta_es_mas_pesada_que_media(self):
        self.assertTrue(config_heavier_than(self.config("alta"), self.media))
        self.assertFalse(config_heavier_than(self.config("baja"), self.media))
        self.assertFalse(config_heavier_than(self.config("media"), self.media))

    def test_mismo_modelo_con_mas_haz_es_mas_pesado(self):
        baja = recommend_config(i5_9500(ram_total_mb=4000))
        self.assertTrue(config_heavier_than(self.config("media"), baja))

    def test_gpu_frente_a_cpu_no_cuenta_porque_resolve_runtime_ya_cae(self):
        self.assertFalse(config_heavier_than(self.config("extra"), self.media))

    def test_large_v3_en_cpu_es_mas_pesado_aunque_se_recomiende_gpu(self):
        c = AppConfig(model="large-v3", beam_size=5, device="cpu", compute_type="int8")
        self.assertTrue(config_heavier_than(c, self.vulkan))
        self.assertFalse(config_heavier_than(self.config("alta"), self.vulkan))

    def test_extra_en_vulkan_es_mas_pesado_que_turbo(self):
        self.assertTrue(config_heavier_than(self.config("extra"), self.vulkan))


class TestAvisosAlArrancar(unittest.TestCase):
    def test_gpu_dedicada_con_whispercpp_dir_vacio(self):
        perfil = con_gpu(i5_9500(), RX)
        avisos = startup_notices(AppConfig(), perfil, recommend_config(perfil))
        self.assertTrue(any("whispercpp_dir" in a and a.startswith("⚠") for a in avisos), avisos)

    def test_configuracion_mas_pesada_que_la_recomendada(self):
        perfil = i5_9500()
        cfg = AppConfig()
        apply_preset(cfg, "alta")
        avisos = startup_notices(cfg, perfil, recommend_config(perfil))
        self.assertEqual(len(avisos), 1)
        self.assertIn("más pesada", avisos[0])

    def test_en_cpu_pudiendo_usar_la_gpu_lo_sugiere_sin_alarma(self):
        perfil = con_gpu(i5_9500(), RX)
        cfg = AppConfig(whispercpp_dir="E:/whispercpp")
        avisos = startup_notices(cfg, perfil, recommend_config(perfil, vulkan_turbo_ready=True))
        self.assertEqual(len(avisos), 1)
        self.assertTrue(avisos[0].startswith("💡"))

    def test_la_recomendada_no_avisa_de_nada(self):
        perfil = con_gpu(i5_9500(), RX)
        rec = recommend_config(perfil, vulkan_turbo_ready=True)
        cfg = AppConfig(whispercpp_dir="E:/whispercpp")
        apply_recommendation(cfg, rec)
        self.assertEqual(startup_notices(cfg, perfil, rec), [])


class TestAplicarRecomendacion(unittest.TestCase):
    def test_aplica_modelo_hilos_y_flash_attention_sin_tocar_lo_demas(self):
        rec = recommend_config(con_gpu(i5_9500(), RX), vulkan_turbo_ready=True)
        cfg = AppConfig(vocab="mi vocabulario", whispercpp_dir="E:/whispercpp")
        apply_recommendation(cfg, rec)
        self.assertEqual((cfg.model, cfg.device, cfg.cpu_threads, cfg.whispercpp_flash_attn),
                         ("large-v3-turbo", "vulkan", 5, True))
        self.assertEqual((cfg.vocab, cfg.whispercpp_dir), ("mi vocabulario", "E:/whispercpp"))

    def test_una_de_cpu_no_toca_flash_attention(self):
        cfg = AppConfig(whispercpp_flash_attn=True)
        apply_recommendation(cfg, recommend_config(i5_9500()))
        self.assertTrue(cfg.whispercpp_flash_attn)
        self.assertEqual(cfg.cpu_threads, 5)


class TestEleccionDeGpuVulkan(unittest.TestCase):
    RX_1 = GpuInfo("AMD Radeon RX 6700 XT", VENDOR_AMD, 1, vram_mb=12016, vulkan_index=1)
    RX_PEQ = GpuInfo("AMD Radeon RX 6400", VENDOR_AMD, 2, vram_mb=4096, vulkan_index=2)

    def test_auto_elige_la_dedicada_con_mas_vram_aunque_la_igpu_sea_la_0(self):
        c = choose_vulkan_device(-1, [IRIS, self.RX_1, self.RX_PEQ])
        self.assertEqual((c.index, c.integrated, c.usable), (1, False, True))

    def test_auto_nunca_elige_una_integrada(self):
        c = choose_vulkan_device(-1, [IRIS])
        self.assertFalse(c.usable)
        self.assertIn("integrada", c.reason)

    def test_pedida_a_mano_la_integrada_vale(self):
        c = choose_vulkan_device(0, [IRIS, self.RX_1])
        self.assertEqual((c.index, c.integrated, c.usable), (0, True, True))

    def test_un_numero_que_no_existe_no_es_utilizable(self):
        self.assertFalse(choose_vulkan_device(5, [IRIS, self.RX_1]).usable)

    def test_sin_lista_no_se_pasa_dev(self):
        self.assertEqual(choose_vulkan_device(-1, []).index, -1)
        self.assertTrue(choose_vulkan_device(-1, []).usable)

    def test_en_la_integrada_large_v3_pasa_a_turbo(self):
        cfg = AppConfig(whispercpp_dir="E:/w")
        apply_preset(cfg, "extra")
        model, device, _ct, _beam, aviso = resolve_runtime(cfg, 0, True, choose_vulkan_device(0, [IRIS]))
        self.assertEqual((model, device), ("large-v3-turbo", "vulkan"))
        self.assertIn("integrada", aviso)

    def test_solo_igpu_en_automatico_cae_a_cpu_explicando_por_que(self):
        cfg = AppConfig(whispercpp_dir="E:/w")
        apply_preset(cfg, "extra")
        model, device, _ct, _beam, aviso = resolve_runtime(cfg, 0, True, choose_vulkan_device(-1, [IRIS]))
        self.assertEqual(device, "cpu")
        self.assertNotEqual(model, "large-v3")
        self.assertIn("integrada", aviso)


class TestWorkerEligeLaGpu(unittest.TestCase):
    """Igual que TestWorkerConVulkan (test_whispercpp.py), con la lista de Vulkan como dato."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.cfg = AppConfig(notes_dir=tmp.name, caps_dir=str(pathlib.Path(tmp.name) / "caps"), keywords=[])
        apply_preset(self.cfg, "extra")
        self.cfg.whispercpp_dir = "E:/whispercpp"
        self.session = NotesSession(tmp.name)
        self.ui, self.stop = queue.Queue(), threading.Event()
        self.stop.set()  # solo interesa la carga del modelo
        self.vulkan = []
        self.listos = []
        for nombre, valor in (
            ("detect_cuda_device_count", lambda: 0),
            ("whispercpp_ready", lambda d, m, ct: self.listos.append(m) or True),
            ("cached_vulkan_devices", lambda: self.vulkan),
        ):
            original = getattr(ww, nombre)
            setattr(ww, nombre, valor)
            self.addCleanup(setattr, ww, nombre, original)
        self.cpu_pedidos = []
        falso = types.ModuleType("faster_whisper")
        falso.WhisperModel = lambda nombre, **kw: self.cpu_pedidos.append((nombre, kw["device"])) or object()
        previo = sys.modules.get("faster_whisper")
        sys.modules["faster_whisper"] = falso
        self.addCleanup(lambda: sys.modules.__setitem__("faster_whisper", previo)
                        if previo else sys.modules.pop("faster_whisper", None))

    def cargar(self, usada=None):
        self.cargas = []

        def load(*args, **kw):
            self.cargas.append((args, kw))
            return types.SimpleNamespace(close=lambda: None, vulkan_device=usada)

        original = ww.load_whispercpp_model
        ww.load_whispercpp_model = load
        self.addCleanup(setattr, ww, "load_whispercpp_model", original)
        worker = ww.TranscriberWorker(self.cfg, queue.Queue(), self.ui, self.session, self.stop)
        worker.run()
        estados = []
        while not self.ui.empty():
            m = self.ui.get()
            if m[0] == "status":
                estados.append(m[1])
        return estados

    def test_pasa_dev_con_la_dedicada_aunque_la_igpu_sea_la_0(self):
        self.vulkan = [IRIS, GpuInfo("NVIDIA GeForce RTX 3050 Laptop GPU", VENDOR_NVIDIA, 1, 4096, vulkan_index=1)]
        estados = self.cargar()
        self.assertEqual(self.cargas[0][1], {"device": 1})
        self.assertEqual(self.cargas[0][0][1], "large-v3")
        self.assertTrue(any("RTX 3050" in e for e in estados), estados)

    def test_integrada_pedida_a_mano_carga_turbo_y_nunca_large_v3(self):
        self.vulkan = [IRIS]
        self.cfg.whispercpp_device = 0
        self.cargar()
        self.assertEqual(self.cargas[0][0][1], "large-v3-turbo")
        self.assertEqual(self.cargas[0][1], {"device": 0})
        self.assertEqual(self.listos, ["large-v3-turbo"], "se comprueba el modelo que se va a cargar")

    def test_solo_igpu_en_automatico_no_arranca_whispercpp(self):
        self.vulkan = [IRIS]
        estados = self.cargar()
        self.assertEqual(self.cargas, [])
        self.assertEqual(self.cpu_pedidos, [(QUALITY_PRESETS["alta"].model, "cpu")])
        self.assertTrue(any("integrada" in e for e in estados), estados)

    def test_si_el_registro_dice_que_tomo_la_integrada_cae_a_cpu(self):
        # Vulkan no se pudo consultar antes (lista vacia): whisper.cpp toma su dispositivo 0.
        estados = self.cargar(usada=VulkanLogDevice(0, "Intel(R) Iris(R) Xe Graphics", "Intel Corporation", True))
        self.assertEqual(self.cargas[0][1], {}, "sin lista no se pasa -dev")
        self.assertEqual(self.cpu_pedidos, [(QUALITY_PRESETS["alta"].model, "cpu")])
        self.assertTrue(any("integrada" in e for e in estados), estados)

    def test_dedicada_segun_el_registro_se_queda_en_gpu(self):
        self.cargar(usada=VulkanLogDevice(0, "AMD Radeon RX 6700 XT", "AMD proprietary driver", False))
        self.assertEqual(self.cpu_pedidos, [])


if __name__ == "__main__":
    unittest.main()
