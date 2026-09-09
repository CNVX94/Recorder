import hashlib
import pathlib
import tempfile
import unittest

from recorder.digest import (
    DigestOptions,
    unique_digest_path,
    DerivedSourceError,
    apply_all,
    bucket_start,
    build_digest,
    digest_path,
    drop_short,
    group_by_interval,
    is_digest,
    list_originals,
    merge_consecutive,
    parse_text,
    write_digest,
)
from recorder.digest.parser import CAM, MIC, Entry

NOTA = f"""# Daily 2026-09-08 10:20

- **10:20:08** Primera frase larga sobre el despliegue del servicio.
  - {CAM} `aqui, aqui` → ![](capturas/2026-09-08_10-20-27_aqui.png)
- **10:20:23** A ver.
- **10:21:00** Segunda frase larga sobre la migracion pendiente.
- **10:21:09** {MIC} Yo estoy revisando el endpoint de pedidos ahora mismo.

> ⏸ Pausa 10:40:00

> ▶ Continúa 10:41:00

- **10:55:12** Frase de otro tramo distinto del reloj.
"""


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


class TestParser(unittest.TestCase):
    def test_parses_every_line_kind(self):
        n = parse_text(NOTA)
        self.assertEqual(n.title, "Daily 2026-09-08 10:20")
        kinds = [e.source for e in n.entries]
        self.assertEqual(kinds, ["out", "out", "out", "mic", "pausa", "pausa", "out"])

    def test_capture_attaches_to_previous_entry(self):
        n = parse_text(NOTA)
        first = n.entries[0]
        self.assertEqual(len(first.captures), 1)
        self.assertIn("aqui.png", first.captures[0])
        self.assertEqual(first.keywords, ["aqui", "aqui"])

    def test_seconds(self):
        self.assertEqual(Entry("01:02:03", "out", "x").seconds, 3723)

    def test_plain_text_is_not_derived(self):
        self.assertIsNone(parse_text(NOTA).derived_from)


class TestTransforms(unittest.TestCase):
    def test_bucket_start(self):
        self.assertEqual(bucket_start(10 * 3600 + 23 * 60, 30), 10 * 3600)
        self.assertEqual(bucket_start(10 * 3600 + 47 * 60, 30), 10 * 3600 + 1800)
        self.assertEqual(bucket_start(999, 0), 999)  # sin agrupar, se respeta

    def test_group_by_interval(self):
        n = parse_text(NOTA)
        grupos = group_by_interval(n.entries, 30)
        self.assertEqual([g[0] for g in grupos], ["10:00 - 10:30", "10:30 - 11:00"])

    def test_no_grouping_returns_single_block(self):
        n = parse_text(NOTA)
        grupos = group_by_interval(n.entries, 0)
        self.assertEqual(len(grupos), 1)
        self.assertEqual(grupos[0][0], "")

    def test_merge_consecutive_joins_same_source(self):
        e = [Entry("00:00:01", "out", "Uno."), Entry("00:00:05", "out", "Dos."), Entry("00:00:09", "mic", "Tres.")]
        m = merge_consecutive(e)
        self.assertEqual(len(m), 2)
        self.assertEqual(m[0].text, "Uno. Dos.")
        self.assertEqual(m[0].stamp, "00:00:01")  # conserva la marca de la primera
        self.assertEqual(m[1].source, "mic")

    def test_merge_does_not_mutate_input(self):
        e = [Entry("00:00:01", "out", "Uno."), Entry("00:00:05", "out", "Dos.")]
        merge_consecutive(e)
        self.assertEqual(e[0].text, "Uno.")  # el original sigue intacto

    def test_drop_short_keeps_entries_with_captures(self):
        e = [
            Entry("00:00:01", "out", "Si."),
            Entry("00:00:02", "out", "Ok.", captures=["a.png"]),
            Entry("00:00:03", "out", "Una frase suficientemente larga."),
        ]
        d = drop_short(e, 3)
        self.assertEqual(len(d), 2)
        self.assertIn("a.png", d[0].captures)

    def test_apply_all_filters_but_does_not_merge(self):
        e = [
            Entry("00:00:01", "out", "Si."),
            Entry("00:00:02", "out", "Frase larga de verdad aqui."),
            Entry("00:00:03", "out", "Otra frase igual de larga aqui."),
        ]
        out = apply_all(e, DigestOptions(merge=True, drop_short_words=3))
        self.assertEqual(len(out), 2)  # unir se hace por tramo, no aqui
        self.assertNotIn("Si.", [x.text for x in out])  # el relleno se fue

    def test_merge_respects_time_gap(self):
        lejos = [Entry("00:00:01", "out", "Primera."), Entry("00:05:00", "out", "Muy posterior.")]
        self.assertEqual(len(merge_consecutive(lejos)), 2)  # 5 min de hueco: turnos distintos
        cerca = [Entry("00:00:01", "out", "Primera."), Entry("00:00:20", "out", "Seguida.")]
        self.assertEqual(len(merge_consecutive(cerca)), 1)

    def test_merge_chains_gap_from_last_absorbed_line(self):
        # tres lineas separadas 20 s cada una: se encadenan aunque la primera y la ultima disten 40 s
        e = [
            Entry("00:00:00", "out", "Uno."),
            Entry("00:00:20", "out", "Dos."),
            Entry("00:00:40", "out", "Tres."),
        ]
        m = merge_consecutive(e, max_gap_sec=25)
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0].text, "Uno. Dos. Tres.")

    def test_merge_respects_max_chars(self):
        largo = "x" * 400
        e = [Entry("00:00:01", "out", largo), Entry("00:00:05", "out", largo)]
        self.assertEqual(len(merge_consecutive(e, max_chars=600)), 2)  # 800 > 600

    def test_entries_with_captures_are_not_merged(self):
        e = [
            Entry("00:00:01", "out", "Antes de la captura."),
            Entry("00:00:05", "out", "Con imagen.", captures=["a.png"]),
            Entry("00:00:09", "out", "Despues de la captura."),
        ]
        m = merge_consecutive(e)
        self.assertEqual(len(m), 3)  # la imagen queda pegada a su propio texto
        self.assertEqual(m[1].captures, ["a.png"])


class TestWriter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = pathlib.Path(self.tmp.name) / "daily_2026-09-08_10-20.md"
        self.src.write_text(NOTA, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_original_is_never_modified(self):
        antes = sha(self.src)
        for opts in (DigestOptions(30), DigestOptions(0), DigestOptions(60, merge=False, keep_captures=False)):
            write_digest(self.src, opts)
        self.assertEqual(sha(self.src), antes, "la nota original cambio")

    def test_slug_naming(self):
        self.assertEqual(DigestOptions(0).slug(), "sintesis")
        self.assertEqual(DigestOptions(5).slug(), "sintesis-5min")
        self.assertEqual(DigestOptions(15).slug(), "sintesis-15min")
        self.assertEqual(DigestOptions(60).slug(), "sintesis-1h")

    def test_never_overwrites_an_existing_digest(self):
        a = write_digest(self.src, DigestOptions(30))
        b = write_digest(self.src, DigestOptions(30))
        self.assertNotEqual(a, b)
        self.assertIn("(2)", b.name)
        self.assertTrue(a.exists() and b.exists())

    def test_unique_path_is_free_before_writing(self):
        self.assertFalse(unique_digest_path(self.src, DigestOptions(15)).exists())

    def test_digest_path_differs_from_source(self):
        for minutos in (0, 5, 30, 60):
            self.assertNotEqual(digest_path(self.src, DigestOptions(minutos)), self.src)

    def test_different_options_give_different_files(self):
        a = write_digest(self.src, DigestOptions(30))
        b = write_digest(self.src, DigestOptions(60))
        self.assertNotEqual(a, b)
        self.assertTrue(a.exists() and b.exists())

    def test_digest_records_its_origin(self):
        out = write_digest(self.src, DigestOptions(30))
        texto = out.read_text(encoding="utf-8")
        self.assertIn(f"origen: {self.src.name}", texto)
        self.assertIn("perdida", texto)  # el aviso de que es derivada

    def test_refuses_to_derive_from_a_digest(self):
        out = write_digest(self.src, DigestOptions(60))
        self.assertTrue(is_digest(out))
        with self.assertRaises(DerivedSourceError) as ctx:
            build_digest(out, DigestOptions(5))
        self.assertIn(self.src.name, str(ctx.exception))  # dice cual es el original

    def test_list_originals_excludes_digests(self):
        write_digest(self.src, DigestOptions(30))
        originales = list_originals(self.src.parent)
        self.assertEqual([p.name for p in originales], [self.src.name])

    def test_grouped_output_has_headers_and_ungrouped_has_stamps(self):
        agrupada = build_digest(self.src, DigestOptions(30))
        self.assertIn("## 10:00 - 10:30", agrupada)
        suelta = build_digest(self.src, DigestOptions(0))
        self.assertNotIn("## 10:00", suelta)
        self.assertIn("**10:20:08**", suelta)  # sin agrupar se conserva la marca

    def test_captures_survive_and_can_be_removed(self):
        con = build_digest(self.src, DigestOptions(30, keep_captures=True))
        self.assertIn("aqui.png", con)
        sin = build_digest(self.src, DigestOptions(30, keep_captures=False))
        self.assertNotIn("aqui.png", sin)

    def test_merge_never_spans_groups(self):
        # dos lineas a 20 s de distancia pero en tramos de 5 min distintos
        texto = (
            "# Daily 2026-09-08 10:00\n\n"
            "- **10:04:50** Frase justo antes de cambiar de tramo.\n"
            "- **10:05:10** Frase justo despues de cambiar de tramo.\n"
        )
        self.src.write_text(texto, encoding="utf-8")
        md = build_digest(self.src, DigestOptions(5, merge=True))
        self.assertIn("## 10:00 - 10:05", md)
        self.assertIn("## 10:05 - 10:10", md)
        self.assertNotIn("tramo. Frase justo despues", md)  # no se fundieron

    def test_pause_markers_survive(self):
        self.assertIn("Pausa", build_digest(self.src, DigestOptions(30)))


if __name__ == "__main__":
    unittest.main()
