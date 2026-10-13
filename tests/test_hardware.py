"""Deteccion de hardware sin depender del equipo que ejecuta las pruebas.

Las piezas que interpretan lo que devuelve Windows son puras y se prueban con datos sinteticos:
una CPU hibrida 2P+8E, la lista de DXGI con la misma GPU repetida por monitores virtuales, la
enumeracion de Vulkan con un driver duplicado, el registro de whisper-server. `detect_hardware`
se prueba rompiendo ctypes a proposito: no puede lanzar.
"""

import ctypes
import struct
import unittest
from unittest import mock

from recorder.config import hardware as hw
from recorder.config.hardware import (
    VENDOR_AMD,
    VENDOR_INTEL,
    VENDOR_NVIDIA,
    DxgiAdapter,
    GpuInfo,
    classify_power,
    dedupe_dxgi_adapters,
    describe_hardware,
    detect_hardware,
    ggml_vulkan_order,
    merge_gpus,
    parse_core_topology,
    vulkan_gpus_from_raw,
)
from recorder.config.manager import ConfigManager
from recorder.engine.whispercpp import parse_vulkan_log, runs_on_cpu, server_command


def nucleo(clase: int, mascara: int) -> bytes:
    """Un SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX de RelationProcessorCore con un GROUP_AFFINITY."""
    cuerpo = struct.pack("<BB20sH", 0, clase, b"", 1)  # Flags, EfficiencyClass, Reserved, GroupCount
    cuerpo += struct.pack("<QH6x", mascara, 0)  # GROUP_AFFINITY: Mask, Group, Reserved
    return struct.pack("<II", 0, 8 + len(cuerpo)) + cuerpo


def cache() -> bytes:
    """Un registro de otra relacion (cache) que hay que saltarse."""
    return struct.pack("<II", 2, 32) + bytes(24)


class TestTopologia(unittest.TestCase):
    def test_hibrida_2p_8e_como_un_i7_1255u(self):
        # 2 nucleos P con HT (clase 1, dos procesadores logicos) y 8 E sin HT (clase 0).
        buf = nucleo(1, 0b11) + nucleo(1, 0b1100) + cache()
        buf += b"".join(nucleo(0, 1 << (4 + i)) for i in range(8))
        self.assertEqual(parse_core_topology(buf), (10, 12, 2, 8))

    def test_no_hibrida_todos_cuentan_como_p(self):
        buf = b"".join(nucleo(0, 1 << i) for i in range(6))  # i5-9500: 6 nucleos sin HT
        self.assertEqual(parse_core_topology(buf), (6, 6, 6, 0))

    def test_bufer_vacio_o_cortado_no_revienta(self):
        self.assertEqual(parse_core_topology(b""), (0, 0, 0, 0))
        self.assertEqual(parse_core_topology(nucleo(1, 0b11)[:20]), (0, 0, 0, 0))


def adaptador(nombre, vendor, device, subsys, mb, luid, flags=0):
    return DxgiAdapter(nombre, vendor, device, subsys, mb, 8163, luid, flags)


class TestDxgi(unittest.TestCase):
    def test_quita_duplicados_de_monitores_virtuales_y_el_adaptador_de_software(self):
        # Lo que dio DXGI en el sobremesa con Meta, SudoMaker y Amyuni: 4 veces la misma RX.
        lista = [adaptador("AMD Radeon RX 6700 XT", VENDOR_AMD, 0x73DF, 0x5C91043, 12243, luid) for luid in (1, 2, 3, 4)]
        lista.append(adaptador("Microsoft Basic Render Driver", 0x1414, 0x8C, 0, 0, 5, flags=2))
        lista.append(adaptador("Intel(R) UHD Graphics 630", VENDOR_INTEL, 0x3E92, 0x1, 128, 6))
        gpus = dedupe_dxgi_adapters(lista)
        self.assertEqual([g.name for g in gpus], ["AMD Radeon RX 6700 XT", "Intel(R) UHD Graphics 630"])
        rx, intel = gpus
        self.assertEqual((rx.vram_mb, rx.integrated, rx.luid), (12243, False, 1))
        self.assertTrue(intel.integrated, "128 MB dedicados: integrada")

    def test_un_adaptador_marcado_software_se_descarta_aunque_sea_de_otro_fabricante(self):
        self.assertEqual(dedupe_dxgi_adapters([adaptador("WARP", VENDOR_NVIDIA, 1, 1, 4096, 9, flags=2)]), [])


def vk(nombre, vendor, tipo, driver, uuid, mb=0, soportada=True, luid=0):
    return {
        "name": nombre, "vendor_id": vendor, "device_id": 1, "type": tipo, "api": 1 << 22 | 3 << 12,
        "driver_id": driver, "uuid": uuid, "luid": luid, "luid_valid": bool(luid),
        "device_local_mb": mb, "supported": soportada,
    }


class TestOrdenDeGgmlVulkan(unittest.TestCase):
    def test_igpu_enumerada_antes_que_la_dedicada_queda_como_dispositivo_0(self):
        devs = [
            vk("Intel(R) Iris(R) Xe Graphics", VENDOR_INTEL, hw.VK_TYPE_INTEGRATED, hw.VK_DRIVER_INTEL_PROPRIETARY_WINDOWS, "a", 8000),
            vk("NVIDIA GeForce RTX 3050 Laptop GPU", VENDOR_NVIDIA, hw.VK_TYPE_DISCRETE, hw.VK_DRIVER_NVIDIA_PROPRIETARY, "b", 4096),
        ]
        gpus = vulkan_gpus_from_raw(devs)
        self.assertEqual([(g.vulkan_index, g.integrated) for g in gpus], [(0, True), (1, False)])

    def test_la_misma_gpu_con_dos_drivers_se_queda_con_el_preferido_al_final(self):
        # Dozen (Vulkan sobre D3D12) y el driver de AMD ven la misma RX: ggml se queda con el de AMD
        # y lo mueve al final de su lista, detras de la iGPU.
        devs = [
            vk("Microsoft Direct3D12 (AMD Radeon RX 6700 XT)", VENDOR_AMD, hw.VK_TYPE_DISCRETE, hw.VK_DRIVER_MESA_DOZEN, "rx"),
            vk("AMD Radeon(TM) Graphics", VENDOR_AMD, hw.VK_TYPE_INTEGRATED, hw.VK_DRIVER_AMD_PROPRIETARY, "apu"),
            vk("AMD Radeon RX 6700 XT", VENDOR_AMD, hw.VK_TYPE_DISCRETE, hw.VK_DRIVER_AMD_PROPRIETARY, "rx", 12016),
            vk("llvmpipe", 0x10005, hw.VK_TYPE_CPU, 13, "cpu"),
        ]
        self.assertEqual(ggml_vulkan_order(devs), [1, 2])

    def test_sin_storage_16_bits_no_la_registra(self):
        devs = [vk("Vieja", VENDOR_AMD, hw.VK_TYPE_DISCRETE, 1, "x", soportada=False),
                vk("Nueva", VENDOR_AMD, hw.VK_TYPE_DISCRETE, 1, "y")]
        self.assertEqual(ggml_vulkan_order(devs), [1])

    def test_dxgi_y_vulkan_se_emparejan_por_luid(self):
        dxgi = dedupe_dxgi_adapters([
            adaptador("AMD Radeon RX 6700 XT", VENDOR_AMD, 2, 3, 12243, luid=77),
            adaptador("AMD Radeon(TM) Graphics", VENDOR_AMD, 9, 9, 2048, luid=88),  # APU con 2 GB de UMA
        ])
        vulkan = [
            GpuInfo("AMD Radeon(TM) Graphics", VENDOR_AMD, 9, 2048, integrated=True, vulkan_index=0, luid=88),
            GpuInfo("AMD Radeon RX 6700 XT", VENDOR_AMD, 2, 12016, vulkan_index=1, luid=77),
        ]
        rx, apu = merge_gpus(dxgi, vulkan)
        self.assertEqual((rx.vulkan_index, rx.integrated, rx.vram_mb), (1, False, 12243))
        self.assertEqual((apu.vulkan_index, apu.integrated), (0, True), "el tipo de Vulkan manda sobre la heuristica")


class TestEnergia(unittest.TestCase):
    def test_sobremesa_sin_bateria(self):
        self.assertEqual(classify_power(1, 128, 1), (True, False, False))

    def test_portatil_desenchufado(self):
        self.assertEqual(classify_power(0, 1, 2), (False, True, True))

    def test_portatil_enchufado(self):
        self.assertEqual(classify_power(1, 8, 2), (False, True, False))

    def test_sin_rol_se_deduce_de_la_bateria_y_desconocido_queda_en_none(self):
        self.assertEqual(classify_power(1, 128, 0)[0], True)
        self.assertEqual(classify_power(255, 255, None), (None, False, False))


class TestDeteccionNoLanza(unittest.TestCase):
    def test_si_ctypes_y_todo_lo_demas_fallan_devuelve_un_perfil_neutro(self):
        with mock.patch.object(ctypes, "WinDLL", side_effect=OSError("kernel32 no carga")), \
                mock.patch.object(hw, "_cpu_name", side_effect=OSError("sin registro")), \
                mock.patch.object(hw, "_numpy_cpu_features", side_effect=ImportError("sin numpy")), \
                mock.patch.object(hw, "_run_vulkan_probe", side_effect=TimeoutError("Vulkan colgado")), \
                mock.patch("recorder.config.schema.detect_cuda_device_count", side_effect=RuntimeError("cuda")):
            p = detect_hardware()
        self.assertEqual((p.physical_cores, p.ram_total_mb, p.gpus, p.cuda_devices), (0, 0, [], 0))
        self.assertFalse(p.avx2)
        self.assertIsNone(p.desktop)
        self.assertGreaterEqual(len(p.detection_errors), 6, p.detection_errors)
        self.assertTrue(describe_hardware(p))  # y se puede describir sin datos

    def test_un_bloque_que_falla_no_se_lleva_a_los_demas(self):
        with mock.patch.object(hw, "_dxgi_adapters", side_effect=OSError("DXGI")):
            p = detect_hardware(vulkan=False, cuda=False)
        self.assertTrue(any("DXGI" in e for e in p.detection_errors))
        self.assertGreater(p.logical_cores, 0)
        self.assertGreater(p.ram_total_mb, 0, "la RAM se detecta aunque DXGI falle")

    def test_en_este_equipo_detecta_algo_coherente(self):
        p = detect_hardware(vulkan=False, cuda=False)
        self.assertGreater(p.physical_cores, 0, p.detection_errors)
        self.assertLessEqual(p.physical_cores, p.logical_cores)
        self.assertEqual(p.p_cores + p.e_cores, p.physical_cores)


class TestRegistroDelServidor(unittest.TestCase):
    REAL = (
        "ggml_vulkan: Found 1 Vulkan devices:\n"
        "ggml_vulkan: 0 = AMD Radeon RX 6700 XT (AMD proprietary driver) | uma: 0 | fp16: 1 | bf16: 0\n"
        "whisper_backend_init_gpu: device 0: Vulkan0 (type: 1)\n"
        "whisper_backend_init_gpu: using Vulkan0 backend\n"
    )

    def test_lee_la_gpu_usada_del_registro_real(self):
        devices, usada = parse_vulkan_log(self.REAL)
        self.assertEqual(len(devices), 1)
        self.assertEqual((usada.index, usada.name, usada.uma), (0, "AMD Radeon RX 6700 XT", False))

    def test_igpu_con_parentesis_en_el_nombre(self):
        texto = (
            "ggml_vulkan: 0 = Intel(R) Iris(R) Xe Graphics (Intel Corporation) | uma: 1 | fp16: 1\n"
            "ggml_vulkan: 1 = NVIDIA GeForce RTX 3050 Laptop GPU (NVIDIA) | uma: 0 | fp16: 1\n"
            "whisper_backend_init_gpu: using Vulkan0 backend\n"
        )
        devices, usada = parse_vulkan_log(texto)
        self.assertEqual([d.uma for d in devices], [True, False])
        self.assertEqual((usada.name, usada.uma), ("Intel(R) Iris(R) Xe Graphics", True))

    def test_sin_gpu_no_hay_usada(self):
        self.assertEqual(parse_vulkan_log("whisper_backend_init_gpu: no GPU found\n"), ([], None))

    def test_detecta_que_whispercpp_se_quedo_en_cpu(self):
        self.assertTrue(runs_on_cpu("ggml_vulkan: No devices found.\nwhisper_backend_init_gpu: no GPU found\n"))
        self.assertFalse(runs_on_cpu(self.REAL))
        # El VAD escribe "no GPU found" despues, en una ejecucion que si usa la GPU.
        self.assertFalse(runs_on_cpu(self.REAL + "whisper_backend_init_gpu: no GPU found\n"))
        self.assertFalse(runs_on_cpu(""), "sin registro no se concluye nada")


class TestComandoConDispositivo(unittest.TestCase):
    def test_dev_solo_si_se_elige_una_gpu(self):
        cmd = server_command("E:/w", "large-v3-turbo", "float16", "es", threads=5, flash_attn=True, device=1)
        self.assertEqual(cmd[cmd.index("-dev") + 1], "1")
        self.assertIn("-dev", server_command("E:/w", "large-v3-turbo", "float16", "es", 5, True, device=0))
        self.assertNotIn("-dev", server_command("E:/w", "large-v3-turbo", "float16", "es", 5, True))


class TestPrimerArranque(unittest.TestCase):
    def test_config_manager_dice_si_no_habia_archivo(self):
        import pathlib
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            mgr = ConfigManager(pathlib.Path(d) / "config.json")
            cfg = mgr.load()
            self.assertTrue(mgr.first_run)
            self.assertFalse(mgr.path.exists(), "cargar no crea el archivo: lo crea quien guarda la recomendacion")
            mgr.save(cfg)
            mgr.load()
            self.assertFalse(mgr.first_run)


if __name__ == "__main__":
    unittest.main()
