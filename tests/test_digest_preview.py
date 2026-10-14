"""Lo que la ventana de Sintesis y el futuro `daily sintesis` comparten (digest/preview.py).

Traducir las casillas a DigestOptions, la vista previa con sus cifras y el listado de originales.
Siempre sobre una carpeta temporal: la nota original no se toca y nada sale de alli.
"""

import datetime as dt
import hashlib
import os
import pathlib
import tempfile
import unittest

from recorder.digest import (
    DEFAULT_INTERVAL,
    INTERVAL_LABELS,
    INTERVALS,
    MIN_WORDS,
    NOTE_HEADER,
    DerivedSourceError,
    build_digest,
    digest_options,
    note_row,
    preview_digest,
    write_digest,
)
from recorder.digest.parser import CAM

NOTA = f"""# Daily 2026-09-08 10:20

- **10:20:08** Primera frase larga sobre el despliegue del servicio.
  - {CAM} `aqui` → ![](capturas/2026-09-08_10-20-27_aqui.png)
- **10:20:23** A ver.
- **10:21:00** Segunda frase larga sobre la migracion pendiente.
- **10:55:12** Frase de otro tramo distinto del reloj.
"""


class TestOpcionesDesdeLaInterfaz(unittest.TestCase):
    def test_etiquetas_para_cada_intervalo(self):
        self.assertEqual(set(INTERVAL_LABELS), set(INTERVALS))
        self.assertEqual(INTERVAL_LABELS[0], "Sin agrupar")
        self.assertEqual(INTERVAL_LABELS[60], "Cada hora")

    def test_valores_por_defecto_de_la_ventana(self):
        # desde el 25-SEP-2026: texto puro y sin eco del vocabulario, por defecto; descartar cortas
        # no (se lleva respuestas como «Sí, va.» o «No.»)
        opts = digest_options(DEFAULT_INTERVAL)
        self.assertEqual((opts.interval_min, opts.merge, opts.keep_captures), (15, True, False))
        self.assertEqual(opts.drop_short_words, 0)
        self.assertTrue(opts.drop_echo)
        self.assertEqual(opts.vocab, "")
        self.assertFalse(opts.inline_stamps)  # agrupando, la hora corta por parrafo esta marcada por defecto

    def test_descartar_cortas_usa_el_minimo_de_palabras(self):
        self.assertEqual(digest_options(15, drop_short=True).drop_short_words, MIN_WORDS)
        self.assertEqual(digest_options(15, drop_short=False).drop_short_words, 0)

    def test_eco_y_vocabulario(self):
        opts = digest_options(15, drop_echo=False, vocab="QA, IIS")
        self.assertFalse(opts.drop_echo)
        self.assertEqual(opts.vocab, "QA, IIS")
        self.assertEqual(digest_options(15, vocab=None).vocab, "")

    def test_sin_agrupar_las_marcas_se_conservan_siempre(self):
        self.assertTrue(digest_options(0, strip_stamps=True).inline_stamps)
        self.assertTrue(digest_options(0, strip_stamps=False).inline_stamps)
        self.assertFalse(digest_options(30, strip_stamps=True).inline_stamps)
        self.assertTrue(digest_options(30, strip_stamps=False).inline_stamps)

    def test_el_resto_pasa_tal_cual(self):
        opts = digest_options(5, merge=False, keep_captures=False)
        self.assertEqual((opts.merge, opts.keep_captures), (False, False))


class TestVistaPrevia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = pathlib.Path(self.tmp.name) / "daily_2026-09-08_10-20.md"
        self.src.write_text(NOTA, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_misma_salida_que_build_digest_y_no_escribe(self):
        antes = hashlib.sha256(self.src.read_bytes()).hexdigest()
        opts = digest_options(30)
        ahora = dt.datetime(2026, 9, 8, 12, 0)
        vista = preview_digest(self.src, opts, now=ahora)
        self.assertEqual(vista.markdown, build_digest(self.src, opts, now=ahora))
        self.assertEqual(sorted(p.name for p in self.src.parent.iterdir()), [self.src.name])  # nada nuevo
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(), antes)

    def test_cifras(self):
        vista = preview_digest(self.src, digest_options(30))
        self.assertEqual(vista.source_lines, len(NOTA.splitlines()))
        self.assertEqual(vista.blocks, 2)  # 10:00 - 10:30 y 10:30 - 11:00
        self.assertEqual(vista.lines, len(vista.markdown.splitlines()))
        self.assertEqual(vista.kb, len(vista.markdown) // 1024)
        # 24 palabras habladas; por defecto se conservan todas («A ver.» se queda)
        self.assertEqual((vista.source_words, vista.words), (24, 24))
        self.assertEqual(
            vista.stats(), f"{vista.source_lines} líneas → 2 bloques · {vista.lines} líneas · ~0 KB · 24 → 24 palabras"
        )
        self.assertIn("24 palabras en el original, 24 aqui", vista.markdown)  # las mismas cifras que la cabecera
        descartando = preview_digest(self.src, digest_options(30, drop_short=True))
        self.assertEqual(descartando.words, 22)  # «A ver.» (2) fuera
        self.assertIn("24 palabras en el original, 22 aqui", descartando.markdown)

    def test_sin_agrupar_no_hay_bloques(self):
        self.assertEqual(preview_digest(self.src, digest_options(0)).blocks, 0)

    def test_se_niega_a_derivar_de_una_copia(self):
        copia = write_digest(self.src, digest_options(60))
        self.assertTrue(copia.name.endswith("_reagrupada-1h.md"))
        with self.assertRaises(DerivedSourceError):
            preview_digest(copia, digest_options(5))

    def test_archivo_inexistente(self):
        with self.assertRaises(OSError):
            preview_digest(self.src.with_name("no_existe.md"), digest_options(15))


class TestListadoDeOriginales(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = pathlib.Path(self.tmp.name) / "daily_2026-09-08_10-20.md"
        self.src.write_text(NOTA, encoding="utf-8")
        marca = dt.datetime(2026, 9, 8, 10, 20).timestamp()
        os.utime(self.src, (marca, marca))

    def tearDown(self):
        self.tmp.cleanup()

    def test_fila_alineada_con_la_cabecera(self):
        fila = note_row(self.src)
        self.assertTrue(fila.startswith(f"{self.src.name:<32}08/09/2026  10:20  "))
        self.assertTrue(fila.endswith(" KB"))
        # misma rejilla que la cabecera: fecha en la columna 32 y hora en la 44
        self.assertEqual((NOTE_HEADER.index("fecha"), fila.index("08/09/2026")), (32, 32))
        self.assertEqual((NOTE_HEADER.index("hora"), fila.index("10:20")), (44, 44))

    def test_marca_la_nota_en_curso(self):
        self.assertTrue(note_row(self.src, active_name=self.src.name).endswith(" ● en curso"))
        self.assertNotIn("en curso", note_row(self.src, active_name="otra.md"))
        self.assertNotIn("en curso", note_row(self.src))


if __name__ == "__main__":
    unittest.main()
