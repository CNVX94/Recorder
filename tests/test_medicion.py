"""«Medir mi equipo» (recorder/medicion.py) con motores falsos y un reloj de mentira: qué se prueba en cada
equipo, cuál es «la mejor», la poda y el tope de tiempo, la cancelación, que aplicar escriba solo las claves de la
prueba, el informe guardado y que la recomendación del equipo lo tenga en cuenta. Sin modelos, sin voz de Windows
y sin tocar la prioridad real del proceso."""
import dataclasses
import json
import pathlib
import tempfile
import unittest
import wave
from types import SimpleNamespace

import numpy as np

from recorder import medicion as m
from recorder import prioridad
from recorder.config.hardware import VENDOR_AMD, VENDOR_NVIDIA, GpuInfo
from recorder.config.schema import (
    PRIORITIES,
    AppConfig,
    apply_recommendation,
    choose_vulkan_device,
    recommend_config,
)
from tests.test_recommendation import IRIS, RX, i5_9500, i7_1255u

RATE = m.RATE


class Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class ModeloFalso:
    """Transcribe a `velocidad` veces el tiempo real: adelanta el reloj lo que tardaría y devuelve `texto`."""

    def __init__(self, reloj: Reloj, velocidad: float, texto: str = "uno", al_transcribir=None):
        self.reloj, self.velocidad, self.texto, self.al_transcribir = reloj, velocidad, texto, al_transcribir
        self.cerrado, self.llamadas = False, 0

    def transcribe(self, audio, **kw):
        self.llamadas += 1
        self.reloj.t += len(audio) / RATE / self.velocidad
        if self.al_transcribir:
            self.al_transcribir(self.llamadas)
        return [SimpleNamespace(text=self.texto)], {}

    def close(self):
        self.cerrado = True


def trozos(n: int = 3, segundos: float = 10.0):
    return [np.zeros(int(segundos * RATE), dtype=np.float32) for _ in range(n)]


def candidato(modelo="small", haz=5, hilos=4, dispositivo="cpu", **kw) -> m.Candidato:
    motor = "whisper.cpp" if dispositivo == "vulkan" else "faster-whisper"
    return m.Candidato(modelo, haz, motor, dispositivo, "int8" if dispositivo == "cpu" else "float16", hilos, **kw)


def lista(c: m.Candidato, velocidad: float, wer=0.0) -> m.Resultado:
    return m.Resultado(c, m.LISTA, velocidad, 40.0, wer)


class TestQueProbar(unittest.TestCase):
    def etiquetas(self, perfil, config=None, **kw):
        return [(c.preset, c.dispositivo, c.hilos) for c in m.candidatos(perfil, config or AppConfig(), **kw)]

    def test_portatil_hibrido_procesador_con_los_hilos_de_la_biblioteca_y_los_recomendados(self):
        # 2P+8E: recomendados 9 (fisicos - 1); la gama es media, así que se prueba hasta Alta
        self.assertEqual(self.etiquetas(i7_1255u()), [
            ("baja", "cpu", 9), ("media", "cpu", 4), ("media", "cpu", 9), ("alta", "cpu", 4), ("alta", "cpu", 9),
        ])

    def test_gama_alta_no_prueba_baja_y_gama_baja_no_prueba_alta(self):
        self.assertEqual({p for p, _d, _h in self.etiquetas(i5_9500(p_cores=8, physical_cores=8, logical_cores=8))}, {"media", "alta"})
        pequeno = i5_9500(physical_cores=2, logical_cores=4, p_cores=2)
        self.assertEqual({p for p, _d, _h in self.etiquetas(pequeno)}, {"baja", "media"})

    def test_hilos_nunca_pasan_de_los_del_equipo(self):
        self.assertEqual(m.hilos_a_probar(i5_9500(physical_cores=2, logical_cores=2, p_cores=2)), [2])

    def test_la_integrada_solo_con_permiso_y_con_whispercpp_listo(self):
        perfil = i7_1255u()
        sin_permiso = AppConfig()
        con_permiso = AppConfig(allow_igpu=True)
        self.assertFalse([c for c in m.candidatos(perfil, sin_permiso, True, False) if c.integrada])
        self.assertTrue(m.igpu_sin_permiso(perfil, sin_permiso, True), "se dice en los resultados")
        self.assertFalse(m.igpu_sin_permiso(perfil, sin_permiso, False), "sin whisper.cpp no hay nada que permitir")
        self.assertFalse([c for c in m.candidatos(perfil, con_permiso, False, False) if c.integrada])
        igpu = [c for c in m.candidatos(perfil, con_permiso, True, False) if c.integrada]
        self.assertEqual([(c.modelo, c.dispositivo, c.motor, c.gpu_nombre) for c in igpu],
                         [("large-v3-turbo", "vulkan", "whisper.cpp", IRIS.name)])
        self.assertFalse(m.igpu_sin_permiso(perfil, con_permiso, True))

    def test_la_integrada_nunca_prueba_large_v3(self):
        igpu = [c for c in m.candidatos(i7_1255u(), AppConfig(allow_igpu=True), True, True) if c.integrada]
        self.assertEqual({c.modelo for c in igpu}, {"large-v3-turbo"})

    def test_gpu_dedicada_de_vulkan_con_flash_attention(self):
        perfil = i5_9500(gpus=[RX], vulkan_devices=[RX])
        gpu = [c for c in m.candidatos(perfil, AppConfig(), True, True) if c.dispositivo == "vulkan"]
        self.assertEqual([(c.modelo, c.flash_attn, c.gpu_index, c.integrada) for c in gpu],
                         [("large-v3-turbo", True, 0, False), ("large-v3", True, 0, False)])
        self.assertFalse([c for c in m.candidatos(perfil, AppConfig(), False, False) if c.dispositivo == "vulkan"])

    def test_nvidia_con_cuda(self):
        rtx = GpuInfo("NVIDIA GeForce RTX 3060", VENDOR_NVIDIA, 0x2504, vram_mb=12288)
        cuda = [c for c in m.candidatos(i5_9500(gpus=[rtx], cuda_devices=1), AppConfig()) if c.dispositivo == "cuda"]
        self.assertEqual([(c.modelo, c.precision) for c in cuda], [("large-v3-turbo", "float16"), ("large-v3", "float16")])
        pequena = GpuInfo("NVIDIA GeForce GTX 1650", VENDOR_NVIDIA, 0x1F82, vram_mb=4096)
        cuda = [c for c in m.candidatos(i5_9500(gpus=[pequena], cuda_devices=1), AppConfig()) if c.dispositivo == "cuda"]
        self.assertEqual([c.modelo for c in cuda], ["large-v3-turbo"], "con menos de 6 GB, large-v3 no se prueba")

    def test_etiquetas_de_las_filas(self):
        self.assertEqual(candidato(hilos=9).etiqueta(), "Media · procesador, 9 hilos")
        self.assertEqual(candidato(hilos=9).etiqueta(corta=True), "Media · CPU, 9 hilos")
        self.assertEqual(candidato("large-v3-turbo", dispositivo="vulkan", integrada=True).etiqueta(), "Alta · tarjeta gráfica integrada")
        self.assertEqual(candidato("large-v3-turbo", dispositivo="vulkan", integrada=True).etiqueta(True), "Alta · GPU integrada")
        self.assertEqual(candidato("large-v3", dispositivo="vulkan").etiqueta(), "Extra · tarjeta gráfica")


class TestLaMejor(unittest.TestCase):
    def test_la_de_mas_calidad_entre_las_que_aguantan_dos_fuentes(self):
        baja, media, alta = (candidato("small", h, 9) for h in (1, 5)), None, None
        rapida = lista(candidato("small", 1, 9), 5.0)
        media = lista(candidato("small", 5, 9), 3.0)
        alta = lista(candidato("large-v3-turbo", 5, 9), 2.2)
        mejor, dos = m.elegir_mejor([rapida, media, alta])
        self.assertEqual((mejor, dos), (alta, True), "Alta cuenta aunque Media sea más rápida")

    def test_a_igual_calidad_la_mas_rapida(self):
        lenta, veloz = lista(candidato(hilos=4), 2.6), lista(candidato(hilos=9), 3.0)
        self.assertEqual(m.elegir_mejor([lenta, veloz]), (veloz, True))

    def test_si_ninguna_aguanta_dos_fuentes_la_mas_rapida(self):
        a, b = lista(candidato("small", 1), 1.6), lista(candidato("large-v3-turbo", 5), 0.9)
        self.assertEqual(m.elegir_mejor([b, a]), (a, False))

    def test_sin_medidas_no_hay_mejor(self):
        self.assertEqual(m.elegir_mejor([]), (None, False))
        self.assertEqual(m.elegir_mejor([m.Resultado(candidato(), m.OMITIDA), m.Resultado(candidato(), m.FALLO)]), (None, False))

    def test_una_prueba_que_transcribe_mal_no_gana_aunque_sea_rapida(self):
        mala = lista(candidato("large-v3-turbo", 5, 9), 4.0, wer=80.0)
        buena = lista(candidato("small", 5, 9), 2.1)
        self.assertEqual(mala.veredicto, "mal")
        self.assertEqual(m.elegir_mejor([mala, buena]), (buena, True))

    def test_veredictos(self):
        self.assertEqual([lista(candidato(), v).veredicto for v in (0.9, 1.0, 1.99, 2.0, 5.0)], ["atrasa", "justo", "justo", "si", "si"])
        self.assertEqual(m.VELOCIDAD_DOS_FUENTES, 2.0)


class TestMedidor(unittest.TestCase):
    def setUp(self):
        self.reloj = Reloj()
        self.modelos = {}
        self.cargados = []

    def medidor(self, candidatos, velocidades, **kw):
        def cargar(c):
            self.cargados.append(c)
            velocidad = velocidades[c.clave]
            if isinstance(velocidad, Exception):
                raise velocidad
            self.modelos[c.clave] = ModeloFalso(self.reloj, velocidad)
            return self.modelos[c.clave]

        reloj = self.reloj
        return m.Medidor(
            candidatos, trozos(), "uno uno uno", cargar, reloj=reloj,
            tiempos=lambda: (int(reloj.t * 1e7 * 0.6), int(reloj.t * 1e7)), **kw,
        )

    def test_mide_velocidad_cpu_y_calidad_sobre_los_fragmentos_tras_el_calentamiento(self):
        c = candidato(hilos=4)
        medidor = self.medidor([c], {c.clave: 2.5})
        medidor.ejecutar()
        r = medidor.resultados[0]
        self.assertEqual(r.estado, m.LISTA)
        self.assertAlmostEqual(r.velocidad, 2.5, places=3)  # 20 s de audio cronometrados (el primero fue calentamiento)
        self.assertEqual(r.cpu_pct, 40)
        self.assertEqual(r.wer, 0.0)
        self.assertTrue(r.dos_fuentes)
        self.assertTrue(self.modelos[c.clave].cerrado, "el modelo se suelta al acabar cada prueba")
        self.assertTrue(medidor.terminado)

    def test_pasa_el_vocabulario_y_el_haz_como_el_transcriptor(self):
        llamadas = []
        c = candidato(haz=3)

        def cargar(_c):
            modelo = ModeloFalso(self.reloj, 2.0)
            original = modelo.transcribe
            modelo.transcribe = lambda audio, **kw: llamadas.append(kw) or original(audio, **kw)
            return modelo

        m.Medidor([c], trozos(), "uno uno uno", cargar, vocab="API Core", reloj=self.reloj).ejecutar()
        self.assertEqual({(k["beam_size"], k["initial_prompt"], k["language"], k["vad_filter"]) for k in llamadas},
                         {(3, "API Core", "es", True)})
        self.assertFalse(llamadas[0]["condition_on_previous_text"])

    def test_cancelar_corta_entre_fragmentos_y_deja_en_espera_lo_que_falta(self):
        a, b, c = candidato(hilos=4), candidato(hilos=9), candidato("large-v3-turbo", hilos=9)
        medidor = self.medidor([a, b, c], {a.clave: 3.0, b.clave: 3.0, c.clave: 3.0})
        original = medidor._cargar

        def cargar(cand):
            modelo = original(cand)
            if cand is b:  # se cancela durante la segunda prueba, tras el calentamiento
                modelo.al_transcribir = lambda n: medidor.cancelar() if n == 2 else None
            return modelo

        medidor._cargar = cargar
        medidor.ejecutar()
        estados = [r.estado for r in medidor.resultados]
        self.assertEqual(estados, [m.LISTA, m.OMITIDA, m.EN_ESPERA])
        self.assertEqual(medidor.resultados[1].motivo, m.MOTIVO_CANCELADA)
        self.assertTrue(self.modelos[b.clave].cerrado, "también se suelta el modelo de la prueba cancelada")
        self.assertNotIn(c, self.cargados, "no se carga nada tras cancelar")
        self.assertTrue(medidor.cancelado and medidor.terminado)

    def test_poda_lo_mas_pesado_si_lo_ligero_ya_iba_mas_lento_que_el_habla(self):
        media9, alta9, alta4 = candidato("small", 5, 9), candidato("large-v3-turbo", 5, 9), candidato("large-v3-turbo", 5, 4)
        medidor = self.medidor([media9, alta4, alta9], {media9.clave: 0.8, alta4.clave: 9.0, alta9.clave: 9.0})
        medidor.ejecutar()
        self.assertEqual([(r.estado, r.motivo) for r in medidor.resultados], [
            (m.LISTA, ""), (m.OMITIDA, m.MOTIVO_PODA), (m.OMITIDA, m.MOTIVO_PODA),
        ], "con 9 hilos Media ya se atrasa: Alta, con los mismos o menos hilos, iría peor")
        self.assertEqual(self.cargados, [media9], "lo omitido ni se carga")

    def test_no_poda_si_la_pesada_tiene_mas_hilos_que_la_ligera_lenta(self):
        media4, alta9 = candidato("small", 5, 4), candidato("large-v3-turbo", 5, 9)
        medidor = self.medidor([media4, alta9], {media4.clave: 0.8, alta9.clave: 1.1})
        medidor.ejecutar()
        self.assertEqual([r.estado for r in medidor.resultados], [m.LISTA, m.LISTA], "con más hilos podría ir mejor: se mide")

    def test_no_poda_entre_dispositivos_distintos(self):
        cpu = candidato("small", 5, 9)
        gpu = candidato("large-v3-turbo", 5, 4, dispositivo="vulkan", gpu_index=0)
        medidor = self.medidor([cpu, gpu], {cpu.clave: 0.5, gpu.clave: 4.0})
        medidor.ejecutar()
        self.assertEqual([r.estado for r in medidor.resultados], [m.LISTA, m.LISTA])

    def test_el_presupuesto_de_tiempo_omite_lo_que_no_cabe(self):
        a, b = candidato("small", 1, 4), candidato("large-v3-turbo", 5, 9)
        medidor = self.medidor([a, b], {a.clave: 0.5, b.clave: 5.0}, presupuesto_s=60.0)  # a tarda ~30 s; quedan 30 = el margen
        medidor.ejecutar()
        self.assertEqual((medidor.resultados[0].estado, medidor.resultados[1].estado), (m.LISTA, m.OMITIDA))
        self.assertEqual(medidor.resultados[1].motivo, m.MOTIVO_TIEMPO)

    def test_el_tope_por_prueba_corta_la_cronometrada_y_deja_la_velocidad(self):
        c = candidato("large-v3-turbo", 5, 9)
        medidor = self.medidor([c], {c.clave: 0.4}, tope_candidato_s=20.0)  # cada fragmento de 10 s tarda 25 s
        medidor.trozos = trozos(4)
        medidor.referencia = "uno uno uno uno"
        medidor.ejecutar()
        r = medidor.resultados[0]
        self.assertEqual(self.modelos[c.clave].llamadas, 2, "calentamiento y un fragmento cronometrado")
        self.assertAlmostEqual(r.velocidad, 0.4, places=3)
        self.assertIsNone(r.wer, "sin la muestra entera el WER no vale")

    def test_modelo_sin_descargar_se_omite_y_un_error_no_tira_las_demas(self):
        a, b, c = candidato("small", 1, 4), candidato("small", 5, 4), candidato("small", 5, 9)
        medidor = self.medidor([a, b, c], {a.clave: m.ModeloNoDisponible("small"), b.clave: RuntimeError("sin memoria"), c.clave: 3.0})
        medidor.ejecutar()
        self.assertEqual([r.estado for r in medidor.resultados], [m.OMITIDA, m.FALLO, m.LISTA])
        self.assertEqual(medidor.resultados[0].motivo, m.MOTIVO_MODELO)
        self.assertIn("sin memoria", medidor.resultados[1].motivo)

    def test_progreso_y_lo_que_queda(self):
        a, b = candidato("small", 5, 4), candidato("small", 5, 9)
        medidor = self.medidor([a, b], {a.clave: 2.0, b.clave: 2.0})
        self.assertEqual(medidor.instantanea()[2], 0.0)
        medidor._inicio = self.reloj()
        medidor._medir(0, medidor.resultados[0])
        _filas, actual, progreso, queda = medidor.instantanea()
        self.assertEqual(progreso, 0.5)
        self.assertGreater(queda, 0)
        medidor.ejecutar()
        self.assertEqual(medidor.instantanea()[2], 1.0)
        self.assertIsNone(medidor.instantanea()[3])


def escribir_wav(ruta: pathlib.Path, turnos: int = 3, segundos: float = 10.0) -> pathlib.Path:
    """Turnos de «voz» (un tono fuerte) separados por 0,8 s de silencio, a 16 kHz mono: lo que parte `trocear`."""
    tono = (np.sin(np.linspace(0, 2000 * np.pi, int(segundos * RATE))) * 6000).astype("<i2")
    silencio = np.zeros(int(0.8 * RATE), dtype="<i2")
    pcm = np.concatenate([np.concatenate([tono, silencio]) for _ in range(turnos)])
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.tobytes())
    return ruta


class BasePrueba(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = pathlib.Path(tmp.name)
        self.ruta_config = self.raiz / "config.json"
        self.wav = escribir_wav(self.raiz / "muestra.wav")
        self.reloj = Reloj()
        self.cargados = []
        self.velocidades = {}

    def cargar(self, c):
        self.cargados.append(c)
        modelo = ModeloFalso(self.reloj, self.velocidades.get(c.clave, 3.0), texto="")
        original = modelo.transcribe
        guion = " ".join(m.GUION[:m.TURNOS_PRUEBA])
        # dice el guion entero en la primera llamada (el calentamiento) y calla después: así el WER sale 0
        modelo.transcribe = lambda audio, **kw: (
            lambda r: ([SimpleNamespace(text=guion)], {}) if modelo.llamadas == 1 else r)(original(audio, **kw))
        return modelo

    def prueba(self, perfil=None, config=None, reposo=lambda: 2, generar=None, **kw):
        return m.Prueba(
            perfil or i7_1255u(), config or AppConfig(), self.ruta_config, cargar=self.cargar,
            generar=generar or (lambda turnos: self.wav), reposo=reposo, reloj=self.reloj, **kw,
        )

    def correr(self, prueba: m.Prueba, **kw):
        prueba.iniciar(**kw)
        prueba.esperar(30)
        return prueba


class TestPrueba(BasePrueba):
    def test_de_principio_a_fin_deja_el_informe_junto_al_config(self):
        self.velocidades = {c.clave: v for c, v in zip(m.candidatos(i7_1255u(), AppConfig()), (5.0, 2.6, 3.0, 1.3, 1.1))}
        p = self.correr(self.prueba())
        self.assertEqual(p.fase, m.TERMINADA, p.error)
        self.assertEqual(p.informe.mejor, candidato("small", 5, 9).clave, "Media con 9 hilos: la de más calidad que aguanta dos fuentes")
        self.assertTrue(p.informe.dos_fuentes)
        guardado = self.raiz / m.NOMBRE_INFORME
        self.assertTrue(guardado.is_file(), "medicion.json junto al config.json")
        leido = m.cargar_informe(guardado)
        self.assertEqual(leido.mejor, p.informe.mejor)
        self.assertEqual([(r.estado, r.candidato) for r in leido.resultados], [(r.estado, r.candidato) for r in p.informe.resultados])
        self.assertFalse(self.ruta_config.exists(), "medir no escribe config.json")
        self.assertEqual(p.instantanea().progreso, 1.0)

    def test_equipo_ocupado_no_mide_hasta_que_se_diga(self):
        p = self.correr(self.prueba(reposo=lambda: 40))
        self.assertEqual((p.fase, p.instantanea().reposo_pct), (m.OCUPADO, 40))
        self.assertEqual(self.cargados, [], "no se carga ningún modelo")
        self.correr(p, forzar=True)
        self.assertEqual(p.fase, m.TERMINADA)
        self.assertTrue(p.informe.forzada)
        self.assertTrue(self.cargados)

    def test_cancelar_no_guarda_nada(self):
        p = self.prueba()
        original = p._cargar

        def cargar(c):
            p.cancelar()  # el usuario pulsa Esc al cargar la primera prueba
            return original(c)

        p._cargar = cargar
        self.correr(p)
        self.assertEqual(p.fase, m.CANCELADA)
        self.assertIsNone(p.informe)
        self.assertFalse((self.raiz / m.NOMBRE_INFORME).exists())

    def test_sin_voz_de_windows_dice_que_hacer(self):
        def sin_voz(_turnos):
            raise m.SinVoz()

        p = self.correr(self.prueba(generar=sin_voz))
        self.assertEqual(p.fase, m.ERROR)
        self.assertIn("voz en español", p.error)

    def test_una_medicion_sin_ninguna_medida_no_pisa_la_anterior(self):
        previo = m.Informe("2026-11-01T10:00:00", m.huella(i7_1255u()), [lista(candidato(hilos=9), 3.0)], candidato(hilos=9).clave, True)
        m.guardar_informe(previo, self.raiz / m.NOMBRE_INFORME)
        self.cargar = lambda c: (_ for _ in ()).throw(m.ModeloNoDisponible(c.modelo))
        p = self.correr(self.prueba())
        self.assertEqual(p.fase, m.TERMINADA)
        self.assertIsNone(p.informe.mejor)
        self.assertEqual(m.cargar_informe(self.raiz / m.NOMBRE_INFORME).fecha, previo.fecha)

    def test_la_integrada_sin_permiso_se_dice(self):
        p = self.prueba(config=AppConfig(whispercpp_dir=str(self.raiz)))  # sin whisper-server: no hay motor
        self.assertFalse(p.igpu_sin_permiso)


class TestAplicar(unittest.TestCase):
    def cambios(self, antes: AppConfig, c: m.Candidato):
        despues = dataclasses.replace(antes)
        tocadas = m.aplicar_candidato(despues, c)
        distintas = {k for k, v in dataclasses.asdict(antes).items() if dataclasses.asdict(despues)[k] != v}
        return tocadas, distintas

    def test_en_cpu_escribe_calidad_dispositivo_y_hilos_y_nada_mas(self):
        antes = AppConfig(model="large-v3", beam_size=3, device="gpu", compute_type="float16", cpu_threads=0, whispercpp_device=3, vocab="API")
        tocadas, distintas = self.cambios(antes, candidato("small", 5, 9))
        self.assertEqual(set(tocadas), {"model", "beam_size", "device", "compute_type", "cpu_threads"})
        self.assertLessEqual(distintas, set(tocadas))
        self.assertEqual(distintas, set(tocadas), "y todas cambian en este caso")

    def test_en_la_gpu_no_toca_los_hilos_pero_si_el_motor_vulkan(self):
        antes = AppConfig(cpu_threads=7, whispercpp_dir="E:/w", whispercpp_device=-1, whispercpp_flash_attn=False)
        c = candidato("large-v3-turbo", 5, 4, dispositivo="vulkan", gpu_index=1, flash_attn=True)
        despues = dataclasses.replace(antes)
        tocadas = m.aplicar_candidato(despues, c)
        self.assertEqual(set(tocadas), {"model", "beam_size", "device", "compute_type", "whispercpp_flash_attn", "whispercpp_device"})
        self.assertEqual((despues.cpu_threads, despues.whispercpp_dir, despues.vocab, despues.allow_igpu), (7, "E:/w", antes.vocab, False))
        self.assertEqual((despues.device, despues.whispercpp_device, despues.whispercpp_flash_attn), ("vulkan", 1, True))

    def test_candidato_actual(self):
        c = candidato("small", 5, 9)
        config = AppConfig(model="small", beam_size=5, device="cpu", compute_type="int8", cpu_threads=9)
        self.assertTrue(m.candidato_actual(config, c))
        self.assertFalse(m.candidato_actual(dataclasses.replace(config, cpu_threads=4), c))


class TestRecomendacionConLaMedicion(BasePrueba):
    def informe(self, c, velocidad, dos=True, huella=None):
        return m.Informe("2026-11-25T10:30:00", huella or m.huella(i7_1255u()), [lista(c, velocidad)], c.clave, dos)

    def test_la_recomendacion_usa_la_mejor_medida_de_este_equipo(self):
        base = recommend_config(i7_1255u())
        self.assertEqual((base.preset, base.cpu_threads), ("media", 9), "sin medición, lo de siempre")
        c = candidato("large-v3-turbo", 5, 4)
        m.guardar_informe(self.informe(c, 2.4), self.raiz / m.NOMBRE_INFORME)
        rec = m.recomendar(i7_1255u(), AppConfig(), self.ruta_config)
        self.assertEqual((rec.preset, rec.model, rec.cpu_threads, rec.confidence, rec.tier), ("alta", "large-v3-turbo", 4, "medida", m.TIER_MEDIDO))
        self.assertIn("25/11/2026", rec.reason)
        self.assertIn("2,4 veces", rec.reason)
        self.assertIn("Alta · procesador, 4 hilos", rec.reason)
        config = AppConfig()
        apply_recommendation(config, rec)
        self.assertEqual((config.model, config.cpu_threads), ("large-v3-turbo", 4))

    def test_si_ninguna_aguanta_lo_dice(self):
        m.guardar_informe(self.informe(candidato("small", 1, 9), 1.5, dos=False), self.raiz / m.NOMBRE_INFORME)
        rec = m.recomendar(i7_1255u(), AppConfig(), self.ruta_config)
        self.assertIn("ninguna aguanta dos fuentes", rec.reason)

    def test_la_medicion_de_otro_equipo_no_vale(self):
        m.guardar_informe(self.informe(candidato("small", 1, 9), 4.0, huella="otro|4|8|"), self.raiz / m.NOMBRE_INFORME)
        self.assertEqual(m.recomendar(i7_1255u(), AppConfig(), self.ruta_config), recommend_config(i7_1255u()))

    def test_sin_whispercpp_o_sin_permiso_no_se_recomienda_la_gpu_medida(self):
        igpu = candidato("large-v3-turbo", 5, 4, dispositivo="vulkan", gpu_index=0, gpu_nombre=IRIS.name, integrada=True, flash_attn=False)
        m.guardar_informe(self.informe(igpu, 2.5), self.raiz / m.NOMBRE_INFORME)
        base = recommend_config(i7_1255u())
        self.assertEqual(m.recomendar(i7_1255u(), AppConfig(allow_igpu=True), self.ruta_config), base, "whisper.cpp ya no está")
        wcpp = self.raiz / "w"
        (wcpp / "bin").mkdir(parents=True)
        (wcpp / "models").mkdir()
        (wcpp / "bin" / "whisper-server.exe").write_bytes(b"")
        (wcpp / "models" / "ggml-large-v3-turbo.bin").write_bytes(b"")
        con_motor = AppConfig(whispercpp_dir=str(wcpp))
        self.assertNotEqual(m.recomendar(i7_1255u(), dataclasses.replace(con_motor, allow_igpu=True), self.ruta_config).tier, base.tier)
        self.assertEqual(m.recomendar(i7_1255u(), con_motor, self.ruta_config).tier, base.tier, "sin permiso de la integrada")

    def test_aplicada_en_la_gpu_pone_el_numero_de_gpu(self):
        wcpp = self.raiz / "w"
        (wcpp / "bin").mkdir(parents=True)
        (wcpp / "models").mkdir()
        (wcpp / "bin" / "whisper-server.exe").write_bytes(b"")
        (wcpp / "models" / "ggml-large-v3-turbo.bin").write_bytes(b"")
        rx = dataclasses.replace(RX, vulkan_index=2)
        perfil = i5_9500(gpus=[rx], vulkan_devices=[rx])
        c = candidato("large-v3-turbo", 5, 4, dispositivo="vulkan", gpu_index=2, gpu_nombre=rx.name, flash_attn=True)
        m.guardar_informe(m.Informe("2026-11-25T10:30:00", m.huella(perfil), [lista(c, 8.0)], c.clave, True), self.raiz / m.NOMBRE_INFORME)
        config = AppConfig(whispercpp_dir=str(wcpp))
        rec = m.recomendar(perfil, config, self.ruta_config)
        apply_recommendation(config, rec)
        self.assertEqual((config.device, config.whispercpp_device, config.whispercpp_flash_attn), ("vulkan", 2, True))

    def test_informe_ilegible_o_de_otra_version_se_ignora(self):
        ruta = self.raiz / m.NOMBRE_INFORME
        for contenido in ("{ roto", "[]", json.dumps({"version": 99}), json.dumps({"version": 1, "fecha": "x"})):
            ruta.write_text(contenido, encoding="utf-8")
            self.assertIsNone(m.cargar_informe(ruta), contenido)
        self.assertIsNone(m.cargar_informe(self.raiz / "no_existe.json"))
        self.assertEqual(m.recomendar(i7_1255u(), AppConfig(), self.ruta_config), recommend_config(i7_1255u()))


class TestConfiguracionNueva(unittest.TestCase):
    def test_un_config_antiguo_sin_los_campos_nuevos_carga_con_lo_de_siempre(self):
        antiguo = {"model": "small", "beam_size": 5, "cpu_threads": 4, "whispercpp_device": 0}
        config = AppConfig.from_dict(antiguo)
        self.assertEqual((config.allow_igpu, config.process_priority), (False, "normal"))

    def test_prioridad_desconocida_o_peligrosa_cae_a_normal(self):
        for valor in ("alta", "tiempo_real", "", "HIGH"):
            self.assertEqual(AppConfig(process_priority=valor).process_priority, "normal", valor)
        self.assertEqual(AppConfig(process_priority="inferior").process_priority, "inferior")
        self.assertEqual(PRIORITIES, ("normal", "inferior"), "nunca alta ni tiempo real")

    def test_la_integrada_en_automatico_solo_con_permiso_y_si_no_hay_dedicada(self):
        self.assertFalse(choose_vulkan_device(-1, [IRIS]).usable)
        c = choose_vulkan_device(-1, [IRIS], allow_integrated=True)
        self.assertEqual((c.index, c.integrated, c.usable), (0, True, True))
        rx1 = GpuInfo("AMD Radeon RX 6700 XT", VENDOR_AMD, 1, vram_mb=12016, vulkan_index=1)
        c = choose_vulkan_device(-1, [IRIS, rx1], allow_integrated=True)
        self.assertEqual((c.index, c.integrated), (1, False), "la dedicada manda aunque la integrada esté permitida")


class TestPrioridad(unittest.TestCase):
    def test_solo_normal_e_inferior(self):
        self.assertEqual(prioridad.clase_de("normal"), prioridad.NORMAL_PRIORITY_CLASS)
        self.assertEqual(prioridad.clase_de("inferior"), prioridad.BELOW_NORMAL_PRIORITY_CLASS)
        for desconocida in ("alta", "tiempo_real", "algo"):
            self.assertEqual(prioridad.clase_de(desconocida), prioridad.NORMAL_PRIORITY_CLASS, "una desconocida nunca sube")

    def test_aplicar_pasa_la_clase_a_windows(self):
        puestas = []
        self.assertTrue(prioridad.aplicar("inferior", lambda clase: puestas.append(clase) or 1))
        self.assertEqual(puestas, [prioridad.BELOW_NORMAL_PRIORITY_CLASS])
        self.assertFalse(prioridad.aplicar("inferior", lambda clase: 0), "si Windows no deja, False y se sigue")

    def test_ajustar_no_toca_un_proceso_normal_que_pide_normal(self):
        original = prioridad.actual
        self.addCleanup(setattr, prioridad, "actual", original)
        puestas = []
        original_aplicar = prioridad.aplicar
        self.addCleanup(setattr, prioridad, "aplicar", original_aplicar)
        prioridad.aplicar = lambda nombre, establecer=None: puestas.append(nombre) or True
        prioridad.actual = lambda: "normal"
        prioridad.ajustar("normal")
        self.assertEqual(puestas, [], "ya estaba normal: nada que hacer")
        prioridad.ajustar("inferior")
        prioridad.actual = lambda: "inferior"
        prioridad.ajustar("normal")
        self.assertEqual(puestas, ["inferior", "normal"], "volver a normal deshace una inferior anterior")

    def test_prioridad_real_del_proceso_es_una_conocida(self):
        self.assertIn(prioridad.actual(), ("normal", "inferior", None))


class TestMuestra(unittest.TestCase):
    def test_trocear_parte_la_muestra_en_los_turnos(self):
        with tempfile.TemporaryDirectory() as d:
            pcm = m.cargar_wav(escribir_wav(pathlib.Path(d) / "x.wav", turnos=3, segundos=10.0))
        partes = m.trocear(pcm)
        self.assertEqual(len(partes), 3)
        self.assertTrue(all(9.5 < len(p) / RATE < 11.5 for p in partes), [len(p) / RATE for p in partes])

    def test_fusionar_une_hasta_el_tope(self):
        self.assertEqual([len(t) // RATE for t in m.fusionar(trozos(5, 10.0), 30.0)], [30, 20])

    def test_wer(self):
        self.assertEqual(m.wer("uno dos tres", "uno dos tres"), 0.0)
        self.assertAlmostEqual(m.wer("uno dos tres cuatro", "uno tres cuatro"), 25.0)
        self.assertEqual(m.wer("Qué pasó", "que paso"), 0.0, "sin tildes ni mayúsculas")

    def test_la_muestra_corta_es_un_trozo_del_guion(self):
        self.assertEqual(m.TURNOS_PRUEBA, 3)
        self.assertLessEqual(len(" ".join(m.GUION[:m.TURNOS_PRUEBA])), 500)


if __name__ == "__main__":
    unittest.main()
