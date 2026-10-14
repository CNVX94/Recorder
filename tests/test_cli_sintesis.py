"""`daily sintesis` (cli/sintesis.py) con respuestas guionizadas, sobre una carpeta temporal de notas.

El camino interactivo (elegir nota, opciones, vista previa, confirmar) y el de scripts (nota más
`--si`, sin una sola pregunta). Los valores por defecto son los de la ventana «Reagrupar nota»
(texto puro, sin cortas, sin eco). El original no cambia nunca; una copia no sirve de origen.
"""

import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
import unittest

from recorder.cli import sintesis
from recorder.config.manager import ConfigManager
from recorder.config.schema import AppConfig
from recorder.digest import digest_options, write_digest
from tests.apoyo_cli import argumentos, consola_de_prueba, respuestas, solo_ascii

NOTA = (
    "# Daily 2026-09-08 10:20\n\n"
    "- **10:20:08** Primera frase larga sobre el despliegue del servicio.\n"
    "  - 📸 `captura` → ![](capturas/2026-09-08_10-20-27_captura.png)\n"
    "- **10:20:23** A ver.\n"
    "- **10:20:40** Términos.\n"
    "- **10:55:12** Otra frase larga de otro tramo del reloj.\n"
)
ANTIGUA = dt.datetime(2026, 9, 8, 11, 0).timestamp()


class CasoSintesis(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = pathlib.Path(self.tmp.name)
        self.notas = self.raiz / "notas"
        self.notas.mkdir()
        self.src = self.notas / "daily_2026-09-08_10-20.md"
        self.src.write_text(NOTA, encoding="utf-8")
        os.utime(self.src, (ANTIGUA, ANTIGUA))  # hace mucho: no está «en curso»
        self.huella = hashlib.sha256(self.src.read_bytes()).hexdigest()
        self.mgr = ConfigManager(self.raiz / "config.json")
        self.mgr.save(AppConfig(notes_dir=str(self.notas), caps_dir=str(self.raiz / "caps")))

    def tearDown(self):
        self.tmp.cleanup()

    def correr(self, *argv, ascii_mode=False, nota_activa=None):
        consola, buf = consola_de_prueba(ascii_mode)
        codigo = sintesis.ejecutar(argumentos(sintesis, *argv), consola, self.mgr, nota_activa=nota_activa)
        return codigo, buf.getvalue()

    def archivos(self):
        return sorted(p.name for p in self.notas.iterdir())

    def assertOriginalIntacto(self):
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(), self.huella)


class TestInteractivo(CasoSintesis):
    def test_lista_opciones_previa_y_confirma(self):
        with respuestas("1", "", "", "", "", "", "", "s"):
            # la nota 1; cada 15 min; unir; hora corta; texto puro; descartar cortas; quitar ecos; generar
            codigo, salida = self.correr()
        self.assertEqual(codigo, 0)
        self.assertEqual(self.archivos(), [self.src.name, "daily_2026-09-08_10-20_reagrupada-15min.md"])
        self.assertOriginalIntacto()
        # el listado: título, cabecera de columnas y la fila, con la fecha en la misma columna que su título
        lineas = salida.splitlines()
        cabecera = next(i for i, l in enumerate(lineas) if "archivo" in l and "fecha" in l)
        self.assertIn("Nota origen", lineas[cabecera - 1])
        self.assertIn(self.src.name, lineas[cabecera + 1])
        self.assertEqual(lineas[cabecera].index("fecha"), lineas[cabecera + 1].index("08/09/2026"))
        self.assertIn("Cada 15 min", salida)
        self.assertIn("2 bloques", salida)
        self.assertIn("## 10:15 - 10:30", salida)  # la vista previa enseña el cuerpo, no la cabecera
        self.assertNotIn("origen:", salida)
        self.assertIn("No es un resumen", salida)  # la cabecera honesta de la copia, en la vista previa
        self.assertIn("Se creará daily_2026-09-08_10-20_reagrupada-15min.md", salida)
        self.assertIn("✅ Creada", salida)
        self.assertIn("El original sigue intacto.", salida)
        # los valores por defecto son los de la ventana: texto puro, sin cortas, sin eco, hora corta
        contenido = (self.notas / "daily_2026-09-08_10-20_reagrupada-15min.md").read_text(encoding="utf-8")
        self.assertNotIn("![](", contenido)
        self.assertNotIn("A ver.", contenido)
        self.assertNotIn("Términos.", contenido)
        self.assertIn("- [10:20] Primera frase larga", contenido)

    def test_opciones_elegidas_a_mano(self):
        with respuestas("1", "1", "n", "n", "n", "n", "s"):
            # sin agrupar (no se pregunta por las horas); no unir; con imágenes; conservar cortas; conservar ecos; generar
            codigo, _ = self.correr()
        self.assertEqual(codigo, 0)
        destino = self.notas / "daily_2026-09-08_10-20_reagrupada.md"
        contenido = destino.read_text(encoding="utf-8")
        self.assertIn("sin agrupar", contenido)
        self.assertIn("A ver.", contenido)  # corta, conservada
        self.assertIn("Términos.", contenido)  # eco, conservado
        self.assertIn("![](", contenido)  # con imágenes
        self.assertIn("**10:20:08**", contenido)  # sin agrupar, la hora se conserva siempre

    def test_no_confirmar_no_crea_nada(self):
        with respuestas("1", "", "", "", "", "", "", "n"):
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("No se creó nada.", salida)
        self.assertEqual(self.archivos(), [self.src.name])

    def test_cancelar_en_la_lista(self):
        with respuestas():
            codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("Cancelado, no se creó nada.", salida)
        self.assertEqual(self.archivos(), [self.src.name])

    def test_marca_la_nota_en_curso(self):
        with respuestas("1", "", "", "", "", "", "", "n"):
            _, salida = self.correr()
        self.assertNotIn("en curso", salida)  # la nota es de hace mucho
        reciente = self.notas / "daily_2026-10-14_09-00.md"
        reciente.write_text(NOTA, encoding="utf-8")  # fecha de ahora: se está escribiendo
        with respuestas("2", "", "", "", "", "", "", "n"):
            _, salida = self.correr()
        fila = next(l for l in salida.splitlines() if "● en curso" in l)
        self.assertIn("  1  daily_2026-10-14_09-00.md", fila)  # la más reciente va primera y marcada
        with respuestas("1", "", "", "", "", "", "", "n"):
            _, salida = self.correr(nota_activa=self.src)  # quien sepa cuál es, la indica
        fila = next(l for l in salida.splitlines() if "● en curso" in l)
        self.assertIn(self.src.name, fila)

    def test_sin_notas(self):
        self.src.unlink()
        codigo, salida = self.correr()
        self.assertEqual(codigo, 1)
        self.assertIn("No hay notas originales", salida)


class TestNoInteractivo(CasoSintesis):
    def test_nota_cada_15_y_si_no_pregunta_nada(self):
        with respuestas():  # cualquier pregunta cerraría la entrada y cancelaría
            codigo, salida = self.correr(str(self.src), "--cada", "15", "--si")
        self.assertEqual(codigo, 0)
        destino = self.notas / "daily_2026-09-08_10-20_reagrupada-15min.md"
        self.assertTrue(destino.exists())
        self.assertIn(str(destino), salida)
        self.assertIn("2 bloques", salida)
        self.assertIn("→ 16 palabras", salida)  # las cifras: «A ver.» y «Términos.» fuera
        self.assertOriginalIntacto()

    def test_nombre_sin_extension_y_todas_las_banderas(self):
        with respuestas():
            codigo, _ = self.correr(
                "daily_2026-09-08_10-20", "--cada", "60", "--sin-unir", "--con-horas", "--con-imagenes",
                "--con-cortas", "--con-ecos", "--si",
            )
        self.assertEqual(codigo, 0)
        contenido = (self.notas / "daily_2026-09-08_10-20_reagrupada-1h.md").read_text(encoding="utf-8")
        self.assertIn("## 10:00 - 11:00", contenido)
        self.assertIn("**10:20:08**", contenido)  # --con-horas
        self.assertIn("A ver.", contenido)  # --con-cortas
        self.assertIn("Términos.", contenido)  # --con-ecos
        self.assertIn("![](", contenido)  # --con-imagenes
        self.assertNotIn("texto puro", contenido)
        self.assertNotIn("quitado el eco", contenido)

    def test_banderas_dan_el_valor_inicial_de_las_preguntas(self):
        with respuestas("", "", "", "", "", "", "s"):  # Enter en todo: quedan las banderas
            codigo, _ = self.correr(str(self.src), "--con-imagenes", "--con-cortas")
        self.assertEqual(codigo, 0)
        contenido = (self.notas / "daily_2026-09-08_10-20_reagrupada-15min.md").read_text(encoding="utf-8")
        self.assertIn("![](", contenido)
        self.assertIn("A ver.", contenido)
        self.assertNotIn("Términos.", contenido)  # el eco sigue fuera: no se pidió conservarlo

    def test_el_eco_se_reconoce_con_el_vocabulario_de_config(self):
        self.mgr.save(AppConfig(notes_dir=str(self.notas), caps_dir=str(self.raiz / "caps"), vocab="Daily con QA, IIS y Ana."))
        self.src.write_text(NOTA + "- **10:56:00** QA, IIS, Ana.\n", encoding="utf-8")
        self.assertEqual(self.correr(str(self.src), "--si")[0], 0)
        contenido = (self.notas / "daily_2026-09-08_10-20_reagrupada-15min.md").read_text(encoding="utf-8")
        self.assertNotIn("QA, IIS, Ana.", contenido)
        self.assertIn("quitado el eco del vocabulario", contenido)

    def test_con_nota_y_sin_si_solo_confirma(self):
        with respuestas("s"):
            codigo, salida = self.correr(str(self.src), "--cada", "30")
        self.assertEqual(codigo, 0)
        self.assertIn("## 10:00 - 10:30", salida)
        self.assertIn("No es un resumen", salida)
        self.assertTrue((self.notas / "daily_2026-09-08_10-20_reagrupada-30min.md").exists())

    def test_nunca_sobrescribe(self):
        for _ in range(2):
            self.assertEqual(self.correr(str(self.src), "--si")[0], 0)
        self.assertEqual(self.archivos(), [
            self.src.name, "daily_2026-09-08_10-20_reagrupada-15min (2).md", "daily_2026-09-08_10-20_reagrupada-15min.md",
        ])
        self.assertOriginalIntacto()

    def test_derivada_como_origen(self):
        derivada = write_digest(self.src, digest_options(60))
        codigo, salida = self.correr(str(derivada), "--si")
        self.assertEqual(codigo, 1)
        self.assertIn("ya es una sintesis de", salida)
        self.assertEqual(self.archivos(), [self.src.name, derivada.name])

    def test_una_sintesis_antigua_no_se_lista_ni_sirve_de_origen(self):
        vieja = self.notas / "daily_2026-09-08_10-20_sintesis-1h.md"
        vieja.write_text("---\norigen: x\n---\n# vieja\n", encoding="utf-8")
        with respuestas("1", "", "", "", "", "", "", "n"):
            _, salida = self.correr()
        self.assertNotIn("sintesis-1h", salida)
        self.assertEqual(self.correr(str(vieja), "--si")[0], 1)

    def test_nota_inexistente(self):
        codigo, salida = self.correr("no_existe.md", "--si")
        self.assertEqual(codigo, 1)
        self.assertIn("No existe la nota «no_existe.md»", salida)

    def test_en_ascii_no_trae_emoji(self):
        with respuestas("s"):
            codigo, salida = self.correr(str(self.src), "--cada", "15", ascii_mode=True)
        self.assertEqual(codigo, 0)
        self.assertTrue(solo_ascii(salida), salida)
        self.assertIn("OK Creada", salida)
        self.assertIn("! Las copias reagrupadas son derivadas", salida)

    def test_config_rota(self):
        self.mgr.path.write_text("{", encoding="utf-8")
        codigo, salida = self.correr(str(self.src), "--si")
        self.assertEqual(codigo, 1)
        self.assertIn("No se pudo leer", salida)
        self.assertEqual(self.archivos(), [self.src.name])


class TestPiezas(unittest.TestCase):
    def test_resolver_nota(self):
        with tempfile.TemporaryDirectory() as tmp:
            nota = pathlib.Path(tmp) / "a.md"
            nota.write_text("x", encoding="utf-8")
            self.assertEqual(sintesis.resolver_nota(str(nota), "C:/otra"), nota)
            self.assertEqual(sintesis.resolver_nota("a.md", tmp), nota)
            self.assertEqual(sintesis.resolver_nota("a", tmp), nota)
            self.assertIsNone(sintesis.resolver_nota("b", tmp))

    def test_en_curso(self):
        with tempfile.TemporaryDirectory() as tmp:
            nota = pathlib.Path(tmp) / "a.md"
            nota.write_text("x", encoding="utf-8")
            marca = dt.datetime(2026, 9, 8, 10, 20)
            os.utime(nota, (marca.timestamp(), marca.timestamp()))
            self.assertEqual(sintesis.en_curso([nota], ahora=marca + dt.timedelta(minutes=5)), "a.md")
            self.assertIsNone(sintesis.en_curso([nota], ahora=marca + dt.timedelta(hours=2)))
            self.assertIsNone(sintesis.en_curso([]))

    def test_cuerpo_quita_la_cabecera(self):
        md = "---\norigen: a.md\ngenerado: hoy\n---\n\n# Título\n\n- línea\n"
        self.assertEqual(sintesis.cuerpo(md), ["# Título", "", "- línea"])
        self.assertEqual(sintesis.cuerpo("# Sin cabecera\n"), ["# Sin cabecera"])

    def test_opciones_desde_args(self):
        # sin banderas, exactamente lo que propone la ventana (digest_options)
        self.assertEqual(sintesis.opciones_desde_args(argumentos(sintesis), "QA"), digest_options(15, vocab="QA"))
        opts = sintesis.opciones_desde_args(argumentos(sintesis))
        self.assertEqual((opts.interval_min, opts.merge, opts.keep_captures, opts.drop_short_words, opts.inline_stamps, opts.drop_echo), (15, True, False, 4, False, True))
        opts = sintesis.opciones_desde_args(argumentos(sintesis, "--cada", "0", "--sin-unir", "--con-imagenes", "--con-cortas", "--con-ecos"))
        self.assertEqual((opts.interval_min, opts.merge, opts.keep_captures, opts.drop_short_words, opts.inline_stamps, opts.drop_echo), (0, False, True, 0, True, False))
        self.assertTrue(sintesis.opciones_desde_args(argumentos(sintesis, "--con-horas")).inline_stamps)


if __name__ == "__main__":
    unittest.main()
