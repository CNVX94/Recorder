"""Lógica de la ventana de Opciones sin Tkinter (config/options.py y whispercpp_status).

Lo que la ventana ⚙ y el futuro `daily config` comparten: pasar de lo que el usuario escribe o
elige (etiquetas, textos) a la configuración, y saber qué cambió. Todo con valores planos: no
hace falta ninguna ventana, dispositivo de audio ni GPU.
"""

import pathlib
import tempfile
import unittest

from recorder.config.hardware import VENDOR_AMD, VENDOR_INTEL, GpuInfo, HardwareProfile
from recorder.config.options import (
    AUTO_GPU,
    DEFAULT_DEV,
    MAX_THREADS,
    WINDOW_PREFIX,
    SettingsForm,
    apply_settings,
    custom_runtime,
    device_choice,
    device_choices,
    device_from_choice,
    gpu_choice,
    gpu_choices,
    parse_keywords,
    parse_target,
    parse_threads,
    quality_description,
    quality_display,
    recommendation_text,
    settings_form,
    target_choice,
    target_choices,
    threads_hint,
    use_recommendation,
)
from recorder.config.schema import CUSTOM_PRESET, QUALITY_PRESETS, AppConfig, Recommendation, apply_preset
from recorder.engine.whispercpp import SERVER_EXE, whispercpp_status

PANTALLAS = ["(todas las pantallas)", "Pantalla 1: 1920×1080 en (0, 0)", "Pantalla 2: 1920×1080 en (1920, 0)"]
RX = GpuInfo("AMD Radeon RX 6700 XT", VENDOR_AMD, 0x73DF, vram_mb=12243, vulkan_index=0)
IRIS = GpuInfo("Intel(R) Iris(R) Xe Graphics", VENDOR_INTEL, 0x46A8, vram_mb=128, integrated=True, vulkan_index=1)


def rec_media(**kw) -> Recommendation:
    base = dict(
        preset="media", model="small", beam_size=5, device="cpu", compute_type="int8", cpu_threads=5,
        engine="faster-whisper", tier="cpu-media", reason="porque sí", confidence="estimada",
    )
    base.update(kw)
    return Recommendation(**base)


def rec_vulkan() -> Recommendation:
    return rec_media(
        preset=None, model="large-v3-turbo", device="vulkan", compute_type="float16", cpu_threads=5,
        engine="whisper.cpp", tier="gpu-vulkan", flash_attn=True,
    )


def formulario(cfg: AppConfig, **cambios) -> SettingsForm:
    f = settings_form(cfg, PANTALLAS)
    for k, v in cambios.items():
        setattr(f, k, v)
    return f


class TestFormularioDesdeConfig(unittest.TestCase):
    def test_valores_de_fabrica(self):
        cfg = AppConfig()
        f = settings_form(cfg, PANTALLAS)
        self.assertEqual(f.notes_dir, cfg.notes_dir)
        self.assertEqual(f.keywords, "pendiente, bloqueo, captura")
        self.assertEqual((f.out_dev, f.mic_dev), (DEFAULT_DEV, DEFAULT_DEV))  # "" = predeterminado
        self.assertEqual(f.target, PANTALLAS[0])
        self.assertEqual(f.quality, "media")  # small, haz 5, cpu, int8
        self.assertIsNone(f.custom_values)
        self.assertEqual(f.cpu_threads, "0")
        self.assertEqual(f.whispercpp_device, -1)

    def test_dispositivos_y_ventana_guardados(self):
        cfg = AppConfig(out_dev="Altavoces", mic_dev="Micro USB", window="Chat | Microsoft Teams", screen=2)
        f = settings_form(cfg, PANTALLAS)
        self.assertEqual((f.out_dev, f.mic_dev), ("Altavoces", "Micro USB"))
        self.assertEqual(f.target, WINDOW_PREFIX + "Chat | Microsoft Teams")  # la ventana manda sobre la pantalla

    def test_configuracion_personalizada(self):
        cfg = AppConfig(model="medium", beam_size=3)
        self.assertEqual(settings_form(cfg, PANTALLAS).quality, CUSTOM_PRESET)


class TestGuardar(unittest.TestCase):
    def test_sin_tocar_nada_no_cambia_nada(self):
        cfg = AppConfig()
        antes = cfg.to_dict()
        cambios = apply_settings(cfg, formulario(cfg), PANTALLAS)
        self.assertEqual((cambios.notes_changed, cambios.devices_changed), (False, False))
        self.assertEqual(cfg.to_dict(), antes)

    def test_carpeta_de_notas(self):
        cfg = AppConfig(notes_dir="C:/Dailies")
        cambios = apply_settings(cfg, formulario(cfg, notes_dir="  D:/Notas  ", caps_dir=" D:/Caps "), PANTALLAS)
        self.assertTrue(cambios.notes_changed)
        self.assertEqual((cfg.notes_dir, cfg.caps_dir), ("D:/Notas", "D:/Caps"))  # recortadas
        # solo espacios alrededor de la misma ruta: no cuenta como cambio
        self.assertFalse(apply_settings(cfg, formulario(cfg, notes_dir=" D:/Notas "), PANTALLAS).notes_changed)

    def test_dispositivos(self):
        cfg = AppConfig()
        self.assertTrue(apply_settings(cfg, formulario(cfg, out_dev="Altavoces"), PANTALLAS).devices_changed)
        self.assertEqual(cfg.out_dev, "Altavoces")
        self.assertTrue(apply_settings(cfg, formulario(cfg, mic_dev="Micro"), PANTALLAS).devices_changed)
        self.assertTrue(apply_settings(cfg, formulario(cfg, mic=False), PANTALLAS).devices_changed)
        self.assertFalse(cfg.mic)
        self.assertFalse(apply_settings(cfg, formulario(cfg), PANTALLAS).devices_changed)
        # volver al predeterminado guarda "" y cuenta como cambio
        self.assertTrue(apply_settings(cfg, formulario(cfg, out_dev=DEFAULT_DEV), PANTALLAS).devices_changed)
        self.assertEqual(cfg.out_dev, "")

    def test_palabras_clave(self):
        cfg = AppConfig()
        apply_settings(cfg, formulario(cfg, keywords=" bloqueo ,, pendiente,  "), PANTALLAS)
        self.assertEqual(cfg.keywords, ["bloqueo", "pendiente"])

    def test_capturar_ventana_conserva_la_pantalla_como_plan_b(self):
        cfg = AppConfig(screen=2)
        apply_settings(cfg, formulario(cfg, target=WINDOW_PREFIX + "Reunión | Microsoft Teams"), PANTALLAS)
        self.assertEqual(cfg.window, "Reunión | Microsoft Teams")
        self.assertEqual(cfg.screen, 2)

    def test_capturar_pantalla_borra_la_ventana(self):
        cfg = AppConfig(window="Chat | Microsoft Teams")
        apply_settings(cfg, formulario(cfg, target=PANTALLAS[1]), PANTALLAS)
        self.assertEqual((cfg.window, cfg.screen), ("", 1))
        apply_settings(cfg, formulario(cfg, target="Pantalla 9: ya no existe"), PANTALLAS)
        self.assertEqual(cfg.screen, 0)  # etiqueta desconocida: todas las pantallas

    def test_preset_aplica_sus_cuatro_valores(self):
        cfg = AppConfig()
        apply_settings(cfg, formulario(cfg, quality="alta"), PANTALLAS)
        alta = QUALITY_PRESETS["alta"]
        self.assertEqual(
            (cfg.model, cfg.beam_size, cfg.device, cfg.compute_type),
            (alta.model, alta.beam_size, alta.device, alta.compute_type),
        )

    def test_personalizado_con_recomendado_y_sin_el(self):
        cfg = AppConfig(model="medium", beam_size=3)
        apply_settings(cfg, formulario(cfg, quality=CUSTOM_PRESET), PANTALLAS)
        self.assertEqual((cfg.model, cfg.beam_size), ("medium", 3))  # sin «Usar recomendado»: intacto
        valores = ("large-v3-turbo", 5, "vulkan", "float16")
        apply_settings(cfg, formulario(cfg, quality=CUSTOM_PRESET, custom_values=valores), PANTALLAS)
        self.assertEqual((cfg.model, cfg.beam_size, cfg.device, cfg.compute_type), valores)

    def test_hilos_de_cpu(self):
        cfg = AppConfig(cpu_threads=4)
        apply_settings(cfg, formulario(cfg, cpu_threads="abc"), PANTALLAS)
        self.assertEqual(cfg.cpu_threads, 4)  # texto no numerico: se conserva
        apply_settings(cfg, formulario(cfg, cpu_threads=" 7 "), PANTALLAS)
        self.assertEqual(cfg.cpu_threads, 7)
        apply_settings(cfg, formulario(cfg, cpu_threads="9999"), PANTALLAS)
        self.assertEqual(cfg.cpu_threads, MAX_THREADS)
        apply_settings(cfg, formulario(cfg, cpu_threads="-3"), PANTALLAS)
        self.assertEqual(cfg.cpu_threads, 0)

    def test_whispercpp(self):
        cfg = AppConfig()
        f = formulario(cfg, whispercpp_dir=" C:/whispercpp ", whispercpp_flash_attn=True, whispercpp_device=1)
        apply_settings(cfg, f, PANTALLAS)
        self.assertEqual(cfg.whispercpp_dir, "C:/whispercpp")
        self.assertTrue(cfg.whispercpp_flash_attn)
        self.assertEqual(cfg.whispercpp_device, 1)


class TestOpcionesDeLosSelectores(unittest.TestCase):
    def test_dispositivos(self):
        self.assertEqual(device_choices(["A", "B"]), [DEFAULT_DEV, "A", "B"])
        self.assertEqual(device_choice(""), DEFAULT_DEV)
        self.assertEqual(device_choice("A"), "A")
        self.assertEqual(device_from_choice(DEFAULT_DEV), "")
        self.assertEqual(device_from_choice("A"), "A")

    def test_objetivos_de_captura(self):
        abiertas = ["Bloc de notas", "Chat | Microsoft Teams"]
        self.assertEqual(
            target_choices(PANTALLAS, abiertas),
            PANTALLAS + [WINDOW_PREFIX + "Bloc de notas", WINDOW_PREFIX + "Chat | Microsoft Teams"],
        )
        # la guardada que ya no esta abierta va primera, para poder conservarla
        con_cerrada = target_choices(PANTALLAS, abiertas, "Excel")
        self.assertEqual(con_cerrada[len(PANTALLAS)], WINDOW_PREFIX + "Excel")
        # la guardada que si esta abierta no se duplica
        self.assertEqual(target_choices(PANTALLAS, abiertas, "Bloc de notas").count(WINDOW_PREFIX + "Bloc de notas"), 1)

    def test_etiqueta_del_objetivo_guardado(self):
        self.assertEqual(target_choice("", 1, PANTALLAS), PANTALLAS[1])
        self.assertEqual(target_choice("", 7, PANTALLAS), PANTALLAS[0])  # el monitor 7 ya no esta
        self.assertEqual(target_choice("Excel", 1, PANTALLAS), WINDOW_PREFIX + "Excel")

    def test_parse_target(self):
        self.assertEqual(parse_target(WINDOW_PREFIX + "Excel", PANTALLAS), ("Excel", None))
        self.assertEqual(parse_target(PANTALLAS[2], PANTALLAS), ("", 2))
        self.assertEqual(parse_target("otra cosa", PANTALLAS), ("", 0))

    def test_parse_keywords_y_threads(self):
        self.assertEqual(parse_keywords("a, b,,c "), ["a", "b", "c"])
        self.assertEqual(parse_keywords(""), [])
        self.assertEqual(parse_threads("12", 4), 12)
        self.assertEqual(parse_threads("", 4), 4)
        self.assertEqual(parse_threads("300", 4), MAX_THREADS)

    def test_gpus_de_vulkan(self):
        opciones = gpu_choices([RX, IRIS], current=-1)
        self.assertEqual(list(opciones.items())[0], (AUTO_GPU, -1))
        self.assertEqual(opciones["0: AMD Radeon RX 6700 XT (12 GB)"], 0)
        self.assertEqual(opciones["1: Intel(R) Iris(R) Xe Graphics (integrada)"], 1)
        self.assertEqual(gpu_choice(opciones, 1), "1: Intel(R) Iris(R) Xe Graphics (integrada)")
        self.assertEqual(gpu_choice(opciones, 5), AUTO_GPU)  # no esta: automatica

    def test_gpu_guardada_que_ya_no_se_detecta_sigue_en_la_lista(self):
        opciones = gpu_choices([RX], current=3)
        self.assertEqual(opciones["3: (no detectada ahora)"], 3)
        self.assertNotIn("0: (no detectada ahora)", gpu_choices([RX], current=0))  # detectada: no se repite


class TestTextosDeCalidad(unittest.TestCase):
    def test_etiqueta_del_desplegable(self):
        self.assertEqual(quality_display(CUSTOM_PRESET, 0, False), "Personalizado")
        self.assertEqual(quality_display("media", 0, False), "Media")
        self.assertEqual(quality_display("extra", 0, False), "Extra (no disponible en este equipo)")
        self.assertEqual(quality_display("extra", 1, False), "Extra")
        self.assertEqual(quality_display("extra", 0, True), "Extra")

    def test_descripcion_de_un_preset(self):
        self.assertEqual(quality_description("media", ("x", 1, "cpu", "int8"), None, 0, False), QUALITY_PRESETS["media"].summary)
        sin_gpu = quality_description("extra", ("x", 1, "cpu", "int8"), None, 0, False)
        self.assertTrue(sin_gpu.startswith(QUALITY_PRESETS["extra"].summary))
        self.assertIn("cae a CPU solo", sin_gpu)
        self.assertEqual(quality_description("extra", ("x", 1, "cpu", "int8"), None, 1, False), QUALITY_PRESETS["extra"].summary)

    def test_descripcion_de_personalizado(self):
        valores = ("large-v3-turbo", 5, "vulkan", "float16")
        texto = quality_description(CUSTOM_PRESET, valores, None, 0, True)
        self.assertIn("Personalizado: large-v3-turbo, haz 5, GPU con whisper.cpp y Vulkan, float16.", texto)
        self.assertNotIn("recomendada", texto)
        self.assertIn("(la recomendada para este equipo)", quality_description(CUSTOM_PRESET, valores, rec_vulkan(), 0, True))

    def test_custom_runtime(self):
        cfg = AppConfig(model="medium", beam_size=3)
        self.assertEqual(custom_runtime(cfg, None), ("medium", 3, "cpu", "int8"))
        self.assertEqual(custom_runtime(cfg, ("tiny", 1, "cpu", "int8")), ("tiny", 1, "cpu", "int8"))


class TestRecomendacion(unittest.TestCase):
    def test_texto(self):
        self.assertEqual(recommendation_text(None), "Recomendado para este equipo: detectando el equipo…")
        texto = recommendation_text(rec_media())
        self.assertTrue(texto.startswith("Recomendado para este equipo: Media (small, haz 5, CPU, int8, 5 hilos)"))
        self.assertIn("— porque sí [estimada]", texto)

    def test_usar_recomendado_con_preset(self):
        cfg = AppConfig(model="medium", beam_size=3, cpu_threads=0)
        f = formulario(cfg, custom_values=("tiny", 1, "cpu", "int8"), whispercpp_flash_attn=False)
        use_recommendation(f, rec_media(cpu_threads=5))
        self.assertEqual((f.quality, f.custom_values, f.cpu_threads), ("media", None, "5"))
        self.assertFalse(f.whispercpp_flash_attn)  # faster-whisper no toca flash attention
        self.assertEqual(f.notes_dir, cfg.notes_dir)  # las rutas no se tocan

    def test_usar_recomendado_sin_preset_va_como_personalizado(self):
        cfg = AppConfig()
        f = formulario(cfg)
        use_recommendation(f, rec_vulkan())
        self.assertEqual(f.quality, CUSTOM_PRESET)
        self.assertEqual(f.custom_values, ("large-v3-turbo", 5, "vulkan", "float16"))
        self.assertTrue(f.whispercpp_flash_attn)
        apply_settings(cfg, f, PANTALLAS)
        self.assertEqual((cfg.model, cfg.device, cfg.cpu_threads, cfg.whispercpp_flash_attn), ("large-v3-turbo", "vulkan", 5, True))

    def test_pista_de_hilos(self):
        self.assertEqual(threads_hint(None), "0 = 4 de la biblioteca")
        p = HardwareProfile(cpu_name="x", physical_cores=6, logical_cores=6, p_cores=6)
        self.assertEqual(threads_hint(p), "0 = 4 de la biblioteca · recomendado: 5 (6 núcleos)")
        solo_logicos = HardwareProfile(cpu_name="x", logical_cores=8)
        self.assertEqual(threads_hint(solo_logicos), "0 = 4 de la biblioteca · recomendado: 0 (8 hilos)")


class TestEstadoDeWhisperCpp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_vacia_sin_perfil_es_informativa(self):
        estado = whispercpp_status("  ")
        self.assertEqual(estado.level, "info")
        self.assertTrue(estado.text.startswith("Vacía: sin motor Vulkan."))

    def test_vacia_con_gpu_dedicada_sin_cuda_avisa(self):
        perfil = HardwareProfile(gpus=[RX], vulkan_devices=[RX])
        estado = whispercpp_status("", perfil)
        self.assertEqual(estado.level, "warning")
        self.assertIn("la GPU AMD Radeon RX 6700 XT (12 GB) no se usa", estado.text)
        self.assertIn("instalar_whispercpp.ps1", estado.text)

    def test_vacia_con_cuda_o_solo_igpu_no_avisa(self):
        con_cuda = HardwareProfile(gpus=[RX], vulkan_devices=[RX], cuda_devices=1)
        self.assertEqual(whispercpp_status("", con_cuda).level, "info")
        solo_igpu = HardwareProfile(gpus=[IRIS], vulkan_devices=[IRIS])
        self.assertEqual(whispercpp_status("", solo_igpu).level, "info")

    def test_sin_servidor(self):
        estado = whispercpp_status(str(self.root))
        self.assertEqual(estado.level, "warning")
        self.assertEqual(estado.text, f"⚠ No hay bin\\whisper-server.exe en «{self.root}».")

    def test_servidor_sin_modelos(self):
        (self.root / "bin").mkdir()
        (self.root / "bin" / SERVER_EXE).write_bytes(b"")
        estado = whispercpp_status(str(self.root))
        self.assertEqual(estado.level, "warning")
        self.assertIn("no hay modelos ggml", estado.text)

    def test_servidor_y_modelos(self):
        (self.root / "bin").mkdir()
        (self.root / "bin" / SERVER_EXE).write_bytes(b"")
        (self.root / "models").mkdir()
        for nombre in ("ggml-large-v3-turbo.bin", "ggml-large-v3-q8_0.bin", "ggml-silero-v6.2.0.bin"):
            (self.root / "models" / nombre).write_bytes(b"")
        estado = whispercpp_status(f" {self.root} ")  # los espacios alrededor no estorban
        self.assertEqual(estado.level, "ok")
        self.assertEqual(estado.text, "✔ whisper-server y modelos: large-v3-q8_0, large-v3-turbo.")  # sin el VAD


if __name__ == "__main__":
    unittest.main()
