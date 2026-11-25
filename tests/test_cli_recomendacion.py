"""La pantalla «Recomendación del equipo» de `daily menu`, con perfiles de equipo fijos: la tarjeta
(filas «igual / cambia»), el porqué en viñetas, la confianza en palabras, «Aplicar» con su confirmación y el
caso «ya coincide». Aplicar guarda lo mismo que `daily recomendar --aplicar`."""
import io
import json
import unittest
from unittest import mock

from recorder import ayuda
from recorder.cli import recomendar
from recorder.cli.consola import make_console
from recorder.cli.pantallas.recomendacion import (
    Recomendacion, clave_fiabilidad, filas_comparacion, vinetas,
)
from recorder.cli.teclas import ABAJO, ENTER, ESC
from recorder.config import hardware
from recorder.config.schema import AppConfig, apply_recommendation, recommend_config
from tests.test_cli_pantallas import PERFIL, BaseTerminal, limpio
from tests.test_recommendation import i7_1255u

CAMBIOS = "Se guardará en config.json:"


def inicial(terminal):
    return Recomendacion(terminal)


class TestLogica(unittest.TestCase):
    def test_vinetas_parten_el_motivo_por_frases(self):
        self.assertEqual(vinetas("Una frase. Otra con 6,8 % y tools\\a.ps1 (docs/b.md). La última."), [
            "Una frase.", "Otra con 6,8 % y tools\\a.ps1 (docs/b.md).", "La última.",
        ])

    def test_las_vinetas_de_mas_se_juntan_en_la_ultima(self):
        self.assertEqual(vinetas("Uno. Dos. Tres. Cuatro.", 3), ["Uno.", "Dos.", "Tres. Cuatro."])

    def test_motivo_llano_sin_marcas_ni_jerga(self):
        for perfil in (PERFIL, i7_1255u()):
            motivo = recommend_config(perfil).reason
            for jerga in ("[", "int8", "haz ", "whispercpp_device", "float16"):
                self.assertNotIn(jerga, motivo)

    def test_filas_igual_y_cambia(self):
        rec = recommend_config(PERFIL)  # Media, procesador, 5 hilos
        filas = {r: (a, x, c) for r, a, x, c in filas_comparacion(AppConfig(), rec)}
        self.assertEqual(filas["Calidad"], ("Media", "Media", False))
        self.assertEqual(filas["Dónde se transcribe"], ("Procesador", "Procesador", False))
        self.assertEqual(filas["Hilos"], ("automático (4)", "5", True))
        alta = AppConfig()
        alta.model, alta.device, alta.cpu_threads = "large-v3-turbo", "cuda", 5
        filas = {r: (a, x, c) for r, a, x, c in filas_comparacion(alta, rec)}
        self.assertEqual(filas["Calidad"], ("Personalizado", "Media", True))
        self.assertEqual(filas["Dónde se transcribe"], ("Tarjeta gráfica", "Procesador", True))
        self.assertEqual(filas["Hilos"], ("5", "5", False))

    def test_la_confianza_en_palabras(self):
        medida = recommend_config(i7_1255u())
        self.assertEqual(medida.confidence, "medida")
        self.assertEqual(clave_fiabilidad(medida), "recomendacion_fiable_medido")
        estimada = recommend_config(PERFIL)
        self.assertEqual(clave_fiabilidad(estimada), "recomendacion_fiable_estimado")


class TestRecomendacion(BaseTerminal):
    def correr_recomendacion(self, *guion, **kwargs):
        return self.correr(*guion, inicial=inicial, **kwargs)

    def test_tarjeta_con_ahora_recomendado_y_porque(self):
        _codigo, texto = self.correr_recomendacion("q", alto=40)
        self.assertIn("Recomendación del equipo", texto)
        self.assertRegex(texto, r"Ahora +Recomendado")
        self.assertRegex(texto, r"Calidad +Media +Media +○ igual")
        self.assertRegex(texto, r"Dónde se transcribe +Procesador +Procesador +○ igual")
        self.assertRegex(texto, r"Hilos +automático \(4\) +5 +● cambia")
        self.assertIn("Tu equipo", texto)
        self.assertIn("Por qué", texto)
        self.assertIn("· Intel", texto)
        self.assertIn("Fiabilidad: estimado a partir de equipos parecidos al tuyo.", texto)
        self.assertIn("▶ Aplicar lo recomendado", texto)
        self.assertIn("[Enter] Aplicar lo recomendado", texto)
        for jerga in ("[estimada]", "int8", "whispercpp_device"):
            self.assertNotIn(jerga, texto)

    def test_sin_equipo_detectado_gira_el_spinner(self):
        with mock.patch.object(hardware, "_cache", None), \
                mock.patch("recorder.cli.pantallas.recomendacion.cached_hardware", side_effect=lambda: None):
            _codigo, texto = self.correr_recomendacion(ESC)
        self.assertIn("Detectando el equipo…", texto)

    def test_aplicar_ensena_antes_y_despues_y_guarda_lo_mismo_que_aplicar(self):
        codigo, texto = self.correr_recomendacion(ENTER, ENTER, "q")
        self.assertEqual(codigo, 0)
        self.assertIn(CAMBIOS, texto)
        self.assertRegex(texto, r"Hilos de CPU +0 +→ +5")
        self.assertIn("Aplicado. Vale desde la próxima grabación.", texto)
        self.assertIn("Ya usas lo recomendado", texto, "tras aplicar, ya coincide")
        guardado = self.guardado()
        # lo que guarda `daily recomendar --aplicar` sobre el mismo config.json
        otra = self.ruta.with_name("otra.json")
        otra.write_text(json.dumps(AppConfig().to_dict()), encoding="utf-8")
        from recorder.config.manager import ConfigManager

        mgr = ConfigManager(otra)
        self.assertEqual(recomendar.recomendar(True, make_console(file=io.StringIO()), mgr), 0)
        campos = ("model", "beam_size", "device", "compute_type", "cpu_threads", "whispercpp_flash_attn")
        igual = json.loads(otra.read_text(encoding="utf-8"))
        self.assertEqual({c: guardado[c] for c in campos}, {c: igual[c] for c in campos})

    def test_esc_en_la_confirmacion_no_guarda(self):
        antes = self.ruta.read_bytes()
        _codigo, texto = self.correr_recomendacion(ENTER, ESC, "q")
        self.assertIn(CAMBIOS, texto)
        self.assertEqual(self.ruta.read_bytes(), antes)

    def test_si_ya_coincide_no_hay_accion(self):
        cfg = AppConfig()
        cfg.notes_dir = str(self.notas)
        apply_recommendation(cfg, recommend_config(PERFIL))
        self.ruta.write_text(json.dumps(cfg.to_dict()), encoding="utf-8")
        antes = self.ruta.read_bytes()
        _codigo, texto = self.correr_recomendacion(ENTER, "q")
        self.assertIn("Ya usas lo recomendado", texto)
        self.assertNotIn("Aplicar lo recomendado", texto)
        self.assertNotRegex(texto, "● cambia")
        self.assertNotIn(CAMBIOS, texto)
        self.assertEqual(self.ruta.read_bytes(), antes)

    def test_con_config_ilegible_no_se_aplica_y_dice_por_que(self):
        self.ruta.write_bytes(b"{ roto")
        _codigo, texto = self.correr_recomendacion(ENTER, "q")
        self.assertIn("No se aplica: No se pudo leer", texto)
        self.assertNotIn(CAMBIOS, texto)
        self.assertEqual(self.ruta.read_bytes(), b"{ roto")

    def test_fiabilidad_medida_de_un_equipo_medido(self):
        with mock.patch.object(hardware, "_cache", i7_1255u()):
            _codigo, texto = self.correr_recomendacion("q", alto=40)
        self.assertIn("Fiabilidad: medido en un equipo como el tuyo.", texto)

    def test_60_columnas_la_accion_siempre_se_ve_aunque_no_quepa_todo(self):
        with mock.patch.object(hardware, "_cache", i7_1255u()):
            _codigo, texto = self.correr_recomendacion("q", ancho=60, alto=24)
        self.assertIn("▶ Aplicar lo recomendado", texto)
        self.assertRegex(texto, r"↓ \d+ más abajo")

    def test_60_columnas_ascii_y_juego_consola_sin_restos(self):
        for ascii_mode in (False, True):
            _codigo, texto = self.correr_recomendacion("q", ancho=60, alto=24, ascii_mode=ascii_mode)
            self.assertNotIn("Tu equipo", texto, "a 60 columnas la ficha se quita")
            self.assertRegex(texto, r"Hilos +automático \(4\) +5 [●*] cambia")
            self.assertIn("Aplicar lo recomendado", texto)
            if ascii_mode:
                for simbolo in "●○✔✅▶►⚠":
                    self.assertNotIn(simbolo, texto, "en ASCII no queda ningún símbolo propio")

    def test_se_abre_desde_el_menu_con_el_5(self):
        _codigo, texto = self.correr("5", ABAJO, ESC, "q")
        self.assertIn("Inicio › Recomendación del equipo", texto)


if __name__ == "__main__":
    unittest.main()






