"""Calibrar como pantalla de `daily menu` (cli/pantallas/calibrar.py) con teclas guionizadas.

La base es la de tests/test_cli_pantallas.py: consola en memoria, reloj de mentira y un config.json temporal.
"""

import json
import unittest
from unittest import mock

from rich.cells import cell_len

from recorder.cli.pantallas.calibrar import Calibrar, decimales_de, veredicto
from recorder.cli.teclas import ABAJO, DERECHA, ENTER, ESC, IZQUIERDA, RETROCESO
from recorder.config.schema import AppConfig
from recorder.filters.tuning import THRESHOLD_RANGES, apply_tuning, tuning_form
from tests.test_cli_pantallas import BaseTerminal, comando_falso, limpio

# Posición de cada fila: la frase de prueba es la última.
VOCAB, CORRECCIONES, IGNORAR, COMUNES, ECO, SILENCIO, CONFIANZA, REPETICIONES, PROBAR = range(9)
SALIDA = 4  # cuántas veces Esc para salir pase lo que pase
FRASE = "En cuba ya probamos Teams y funcionó."


def abajo(n):
    return [ABAJO] * n


def escribir(texto):
    return list(texto)


class TestLogica(unittest.TestCase):
    def test_decimales_de_cada_paso(self):
        self.assertEqual([decimales_de(p) for _lo, _hi, p in THRESHOLD_RANGES.values()], [2, 1, 1])

    def test_veredicto_corregido_con_captura_y_descartes(self):
        cfg = AppConfig()
        cfg.vocab, cfg.ignore, cfg.fixes, cfg.keywords = "Acme, API Core, QA, IIS", ["gracias por ver"], {"cuba": "QA"}, ["demo"]
        form = tuning_form(cfg)
        v = veredicto(form, "En cuba hacemos la demo.", cfg.keywords)
        texto = "".join(s for s, _e in v.partes)
        self.assertTrue(v.se_queda)
        self.assertIn("Se queda: «En QA hacemos la demo.»", texto)
        self.assertIn("(corregido: cuba → QA)", texto)
        self.assertIn("y guardaría una captura (demo)", texto)
        v = veredicto(form, "Gracias por ver el vídeo.", cfg.keywords)
        self.assertFalse(v.se_queda)
        self.assertIn("Se descarta: contiene «gracias por ver» (Frases a ignorar)", v.partes[0][0])
        v = veredicto(form, "Acme, API Core, QA, IIS, QA, IIS.", cfg.keywords)
        self.assertIn("solo repite tu vocabulario", v.partes[0][0])
        self.assertIsNone(veredicto(form, "   ", cfg.keywords))


class TestCalibrar(BaseTerminal):
    def setUp(self):
        super().setUp()
        cfg = AppConfig.from_dict(self.guardado())
        cfg.vocab, cfg.ignore, cfg.fixes = "Recorder, Teams, QA", ["suscríbete"], {"cuba": "QA"}
        self.ruta.write_text(json.dumps(cfg.to_dict()), encoding="utf-8")

    def calibrar(self, *guion, **kwargs):
        kwargs.setdefault("ancho", 100)
        kwargs.setdefault("alto", 30)
        # Esc de sobra: cierra un campo abierto, avisa de los cambios y sale; si ya había salido, no se lee
        codigo = self.terminal(*guion, *[ESC] * SALIDA, inicial=lambda t: Calibrar(t), **kwargs).run()
        return codigo, limpio(self.salida.getvalue().replace("\x1b[H", "\n"))  # cada cuadro empieza arriba del todo

    def test_se_abre_desde_inicio_y_enseña_las_filas(self):
        self.comandos["calibrar"] = comando_falso("calibrar", self.ejecutados)
        codigo, texto = self.correr("3", ESC, "q", ancho=100, alto=30)
        self.assertEqual(codigo, 0)
        self.assertIn("Inicio › Calibrar", texto)
        for etiqueta in ("Vocabulario", "Correcciones", "Frases a ignorar", "Añadir las comunes",
                         "Quitar eco del vocabulario", "Filtro de silencio", "Confianza mínima",
                         "Filtro de repeticiones", "Probar una frase"):
            self.assertIn(etiqueta, texto)
        self.assertIn("Enter para escribir una frase · e para probar con un ejemplo", texto)
        self.assertEqual(self.ejecutados, [], "es una pantalla, no el modo línea")

    def test_editar_un_campo_con_cursor_y_guardar(self):
        # «Recorder, Teams, QA»: tres a la izquierda del final, se borra la «s» y se escribe en medio
        guion = [ENTER, *([IZQUIERDA] * 4), RETROCESO, *escribir("XY"), ENTER, "g", ENTER]
        _codigo, texto = self.calibrar(*guion)
        self.assertIn("Recorder, TeamXY▌, QA", texto, "el cursor queda donde se editó")
        self.assertRegex(texto, r"Vocabulario +Recorder, Teams, QA +→ +Recorder, TeamXY, QA")
        self.assertEqual(self.guardado()["vocab"], "Recorder, TeamXY, QA")

    def test_guarda_lo_mismo_que_el_modo_linea(self):
        guion = [*abajo(SILENCIO), DERECHA, DERECHA, ABAJO, IZQUIERDA, ABAJO, "j", "k", " ", "g", ENTER, ESC]
        _codigo, texto = self.calibrar(*guion)
        self.assertEqual(texto.count("Vale desde la próxima grabación"), 1, "el aviso se dice una sola vez")
        esperado = AppConfig.from_dict(json.loads(self.ruta.read_text(encoding="utf-8")))
        original = AppConfig.from_dict(json.loads(self.ruta.read_text(encoding="utf-8")))
        form = tuning_form(original)
        form.no_speech_threshold, form.logprob_threshold = 0.7, -1.1
        apply_tuning(original, form)
        self.assertEqual(esperado.to_dict(), original.to_dict())

    def test_umbral_con_flechas_se_queda_en_su_rango(self):
        minimo, maximo, _paso = THRESHOLD_RANGES["no_speech_threshold"]
        self.calibrar(*abajo(SILENCIO), *([IZQUIERDA] * 40), "g", ENTER, ESC)
        self.assertEqual(self.guardado()["no_speech_threshold"], minimo)
        self.calibrar(*abajo(SILENCIO), *([DERECHA] * 40), "g", ENTER, ESC)
        self.assertEqual(self.guardado()["no_speech_threshold"], maximo)

    def test_teclear_un_umbral_y_fuera_de_rango(self):
        _c, texto = self.calibrar(*abajo(SILENCIO), ENTER, *([RETROCESO] * 6), *escribir("9,5"), ENTER, ESC)
        self.assertIn("⚠ Fuera de rango: Escribe un número entre 0,10 y 0,95.", texto)
        self.calibrar(*abajo(SILENCIO), ENTER, *([RETROCESO] * 6), *escribir("0,3"), ENTER, "g", ENTER, ESC)
        self.assertAlmostEqual(self.guardado()["no_speech_threshold"], 0.3)

    def test_la_pista_acompana_a_la_fila_elegida(self):
        _c, texto = self.calibrar(*abajo(SILENCIO), ABAJO)
        self.assertIn("‹ 0,60 ›   ← descarta más · descarta menos →", texto)
        self.assertIn("‹ -1,0 ›   ← descarta menos · descarta más →", texto, "la confianza descarta más hacia la derecha")

    def test_el_veredicto_cambia_al_cambiar_la_lista_negra(self):
        frase = [*abajo(PROBAR), ENTER, *escribir("Gracias por ver el vídeo."), ENTER]
        _c, texto = self.calibrar(*frase)
        self.assertIn("Se queda: «Gracias por ver el vídeo.»", texto)
        # Editar «Frases a ignorar» desde la frase de prueba: Inicio sube a la lista, y se vuelve a la frase.
        guion = [*frase, "j", *["k"] * (PROBAR - IGNORAR + 1), ENTER, *escribir(", gracias por ver"), ENTER]
        _c, texto = self.calibrar(*guion)
        self.assertIn("Se descarta: contiene «gracias por ver» (Frases a ignorar)", texto)

    def test_el_veredicto_se_recalcula_al_escribir(self):
        _c, texto = self.calibrar(*abajo(PROBAR), ENTER, *escribir("En cuba ya"))
        self.assertIn("En cuba ya▌", texto)
        self.assertIn("Se queda: «En QA ya»", texto, "sin aceptar la frase: se prueba según se teclea")
        self.assertIn("(corregido: cuba → QA)", texto)

    def test_e_propone_una_frase_y_la_prueba(self):
        with mock.patch("recorder.cli.pantallas.calibrar.random_sample", return_value=FRASE):
            _c, texto = self.calibrar("e")
        self.assertIn("› " + FRASE, texto)
        self.assertIn("Se queda: «En QA ya probamos Teams y funcionó.»", texto)

    def test_anadir_las_comunes_una_sola_vez(self):
        _c, texto = self.calibrar(*abajo(COMUNES), ENTER, ENTER, "g", ENTER, ESC)
        self.assertIn("Añadidas 6 frases comunes; ahora hay 7.", texto)
        self.assertIn("Ya estaban todas.", texto)
        self.assertEqual(len(self.guardado()["ignore"]), 7)

    def test_interruptor_del_eco(self):
        self.calibrar(*abajo(ECO), " ", "g", ENTER, ESC)
        self.assertIs(self.guardado()["echo_filter"], False)

    def test_avisa_al_salir_con_cambios_y_el_segundo_esc_sale_sin_guardar(self):
        guardado = self.ruta.read_bytes()
        codigo, texto = self.calibrar(*abajo(ECO), " ", ESC, ESC)
        self.assertEqual(codigo, 0)
        self.assertIn("⚠ Hay cambios sin guardar", texto)
        self.assertIn("● cambios sin guardar", texto)
        self.assertEqual(self.ruta.read_bytes(), guardado)

    def test_esc_desde_la_frase_de_prueba_tambien_avisa(self):
        _c, texto = self.calibrar(*abajo(ECO), " ", *abajo(PROBAR - ECO), ESC)
        self.assertIn("⚠ Hay cambios sin guardar", texto)

    def test_sin_cambios_no_hay_nada_que_guardar(self):
        _c, texto = self.calibrar("g")
        self.assertIn("No hay nada que guardar.", texto)

    def test_con_config_ilegible_se_prueba_pero_no_se_guarda(self):
        self.ruta.write_bytes(b"{ roto")
        _c, texto = self.calibrar(*abajo(ECO), " ", "g")
        self.assertIn("config.json no se puede leer", texto)
        self.assertEqual(self.ruta.read_bytes(), b"{ roto")

    def test_el_tema_no_se_pisa_al_guardar(self):
        self.calibrar("t", *abajo(ECO), " ", "g", ENTER, ESC)
        datos = self.guardado()
        self.assertEqual(datos["theme"], "claro")
        self.assertIs(datos["echo_filter"], False)

    def test_a_60_columnas_la_frase_queda_a_la_vista_y_nada_se_pasa_de_ancho(self):
        for ascii_mode in (False, True):
            with self.subTest(ascii=ascii_mode), mock.patch("recorder.cli.pantallas.calibrar.random_sample", return_value=FRASE):
                _c, texto = self.calibrar("e", *abajo(SILENCIO), ancho=60, alto=24, ascii_mode=ascii_mode)
                final = texto[texto.rindex("Probar una frase"):]
                self.assertIn("En QA ya probamos Teams y funcionó.", final)
                self.assertIn("corregido", final)
                self.assertFalse([l for l in texto.splitlines() if cell_len(l) > 60])

    def test_en_ascii_no_hay_simbolos_fuera_de_ascii(self):
        with mock.patch("recorder.cli.pantallas.calibrar.random_sample", return_value="Gracias suscríbete"):
            _c, texto = self.calibrar("e", *abajo(SILENCIO), ascii_mode=True)
        final = texto[texto.rindex("Recorder"):]
        self.assertIn("x Se descarta: contiene «suscríbete»", final)
        self.assertEqual([c for c in final if ord(c) > 0x2000 and c not in "–—"], [])


if __name__ == "__main__":
    unittest.main()
