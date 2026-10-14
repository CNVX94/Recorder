"""Las preguntas de la terminal (cli/preguntas.py) con respuestas guionizadas, sin terminal real.

Lo que importa: Enter conserva el valor actual, «-» vacía, lo inválido se vuelve a pedir, y
Ctrl+C o el fin de la entrada acaban en `Cancelado`. Además, ningún módulo de la terminal debe
cargar tkinter (se comprueba en un proceso aparte, porque en este ya lo cargan otras pruebas).
"""

import pathlib
import subprocess
import sys
import unittest

from recorder.cli import preguntas as p
from tests.apoyo_cli import consola_de_prueba, mock_input, respuestas, solo_ascii

RAIZ = pathlib.Path(__file__).resolve().parents[1]


class TestTexto(unittest.TestCase):
    def test_enter_conserva_el_actual(self):
        consola, buf = consola_de_prueba()
        with respuestas(""):
            self.assertEqual(p.preguntar_texto(consola, "Carpeta", "C:/x"), "C:/x")
        self.assertIn("Carpeta (C:/x): ", buf.getvalue())  # el actual se enseña

    def test_guion_vacia_y_lo_escrito_se_recorta(self):
        consola, _ = consola_de_prueba()
        with respuestas("-"):
            self.assertEqual(p.preguntar_texto(consola, "Carpeta", "C:/x"), "")
        with respuestas("  nuevo  "):
            self.assertEqual(p.preguntar_texto(consola, "Carpeta", "C:/x"), "nuevo")

    def test_sin_actual_no_se_ensena_parentesis_vacio(self):
        consola, buf = consola_de_prueba()
        with respuestas("algo"):
            p.preguntar_texto(consola, "Vocabulario", "", ayuda="una pista")
        self.assertIn("Vocabulario: ", buf.getvalue())
        self.assertNotIn("()", buf.getvalue())
        self.assertIn("una pista", buf.getvalue())


class TestElegir(unittest.TestCase):
    def test_lista_numerada_con_la_actual_marcada(self):
        consola, buf = consola_de_prueba()
        with respuestas("2"):
            self.assertEqual(
                p.elegir(consola, "¿Qué?", ["uno [raro]", "dos"], 0, detalles=["", "detalle"], cabecera="nombre"), 1
            )
        salida = buf.getvalue()
        self.assertIn(f"  {p.MARCA_ACTUAL}  1  uno [raro]", salida)  # los corchetes no se comen como marcado
        self.assertIn("     2  dos  detalle", salida)
        # la cabecera va entre el título y las filas, alineada con el texto de estas
        self.assertIn("¿Qué?\n        nombre\n  ", salida)
        self.assertEqual(salida.index("nombre"), salida.index("uno") - len("nombre\n  ▶  1  "))

    def test_enter_conserva_y_lo_invalido_se_repite(self):
        consola, buf = consola_de_prueba()
        with respuestas(""):
            self.assertEqual(p.elegir(consola, "¿Qué?", ["a", "b"], 1), 1)
        with respuestas("9", "x", "1"):
            self.assertEqual(p.elegir(consola, "¿Qué?", ["a", "b"]), 0)
        self.assertIn("Elige un número entre 1 y 2.", buf.getvalue())
        self.assertIn("Escribe un número entero.", buf.getvalue())


class TestSiNoYNumeros(unittest.TestCase):
    def test_si_no_en_espanol(self):
        consola, buf = consola_de_prueba()
        with respuestas(""):
            self.assertFalse(p.confirmar(consola, "¿Seguro?", False))
        self.assertIn("¿Seguro? [s/n] (n): ", buf.getvalue())
        for texto in ("s", "SI", "sí", "y"):
            with respuestas(texto):
                self.assertTrue(p.confirmar(consola, "¿Seguro?", False))
        with respuestas("quizá", "no"):
            self.assertFalse(p.confirmar(consola, "¿Seguro?", True))
        self.assertIn("Responde s o n.", buf.getvalue())

    def test_entero_en_rango(self):
        consola, buf = consola_de_prueba()
        with respuestas("999", "-1", "7"):
            self.assertEqual(p.preguntar_entero(consola, "Hilos", 4, 0, 256, ayuda="0 = 4"), 7)
        self.assertEqual(buf.getvalue().count("Debe estar entre 0 y 256."), 2)
        with respuestas(""):
            self.assertEqual(p.preguntar_entero(consola, "Hilos", 4, 0, 256), 4)

    def test_decimal_en_rango_con_coma_y_redondeo_al_paso(self):
        consola, buf = consola_de_prueba()
        with respuestas("0,45"):
            self.assertEqual(p.preguntar_decimal(consola, "Umbral", 0.6, 0.1, 0.95, 0.05), 0.45)
        with respuestas("0.4567"):
            self.assertEqual(p.preguntar_decimal(consola, "Umbral", 0.6, 0.1, 0.95, 0.05), 0.46)
        with respuestas("5", "abc", ""):
            self.assertEqual(p.preguntar_decimal(consola, "Umbral", -1.0, -2.5, -0.2, 0.1), -1.0)
        self.assertIn("Debe estar entre -2.5 y -0.2.", buf.getvalue())
        self.assertIn("Escribe un número", buf.getvalue())


class TestCancelar(unittest.TestCase):
    def test_fin_de_la_entrada(self):
        consola, _ = consola_de_prueba()
        with respuestas():
            for pregunta in (
                lambda: p.preguntar_texto(consola, "x", "y"),
                lambda: p.elegir(consola, "x", ["a"]),
                lambda: p.confirmar(consola, "x"),
                lambda: p.preguntar_entero(consola, "x", 1, 0, 9),
                lambda: p.preguntar_decimal(consola, "x", 1.0, 0.0, 9.0, 0.1),
                lambda: p.leer_linea(consola, "frase> "),
            ):
                with self.assertRaises(p.Cancelado):
                    pregunta()

    def test_ctrl_c(self):
        consola, _ = consola_de_prueba()

        def interrumpir(_prompt=""):
            raise KeyboardInterrupt

        with mock_input(interrumpir):
            with self.assertRaises(p.Cancelado):
                p.confirmar(consola, "¿Seguro?")


class TestTextoParaLaConsola(unittest.TestCase):
    def test_modo_ascii_quita_emoji_y_marca(self):
        consola, buf = consola_de_prueba(ascii_mode=True)
        with respuestas(""):
            p.elegir(consola, "⚙ Salida 🔊", ["a ● b", "c"], 1)
        self.assertTrue(solo_ascii(buf.getvalue()), buf.getvalue())
        self.assertIn("Salida OUT", buf.getvalue())
        self.assertIn("  >  2  c", buf.getvalue())
        self.assertIn("a * b", buf.getvalue())
        self.assertEqual(p.texto(consola, "✅ ok"), "OK ok")

    def test_sin_modo_ascii_se_deja_tal_cual(self):
        consola, _ = consola_de_prueba()
        self.assertEqual(p.texto(consola, "✅ ok"), "✅ ok")

    def test_contar(self):
        self.assertEqual(p.contar(1, "frase", "frases"), "1 frase")
        self.assertEqual(p.contar(3, "frase", "frases"), "3 frases")


class TestSinTkinter(unittest.TestCase):
    def test_importar_los_comandos_no_carga_tkinter(self):
        codigo = (
            "import sys, recorder.cli.preguntas, recorder.cli.configurar, recorder.cli.calibrar, "
            "recorder.cli.sintesis; print('tkinter' in sys.modules)"
        )
        salida = subprocess.run(
            [sys.executable, "-c", codigo], cwd=str(RAIZ), capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(salida.returncode, 0, salida.stderr)
        self.assertEqual(salida.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
