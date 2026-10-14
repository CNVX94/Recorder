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
    drop_echo,
    drop_short,
    group_by_interval,
    is_digest,
    list_originals,
    merge_consecutive,
    parse_text,
    sort_by_time,
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
        # dice lo que hace (reagrupar), no lo que no hace (resumir)
        self.assertEqual(DigestOptions(0).slug(), "reagrupada")
        self.assertEqual(DigestOptions(5).slug(), "reagrupada-5min")
        self.assertEqual(DigestOptions(15).slug(), "reagrupada-15min")
        self.assertEqual(DigestOptions(60).slug(), "reagrupada-1h")

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


# Una nota con los defectos de la auditoría del 25-SEP, en sintético: frase escrita después de una
# pausa posterior (cola), dos pausas al cerrar que caen en un tramo nuevo, marcadores de atraso y
# de fuente, y eco del vocabulario.
NOTA_COLA = """# Daily 2026-09-25 16:05

- **17:52:40** Frase larga de antes de la pausa con suficiente texto.

> ⏸ Pausa 17:53:25

- **17:53:06** Frase larga transcrita tarde pero dicha antes de la pausa.

> ▶ Continúa 17:53:30

> ⏳ transcripción atrasada 54 min desde 18:08:44

- **18:08:44** Frase larga dicha durante el atraso de la transcripción.
  - 📸 `aqui` → ![](capturas/2026-09-25_18-08-50_aqui.jpg) · tardía, +54 min
- **18:16:03** Términos.
- **18:17:00** Términos crearon tres endpoints nuevos en el servicio.
- **18:59:58** Última frase larga de la reunión antes de cerrar.

> ⚠ audio de micrófono caído, reintentando: OSError('x') 19:00:10

> ⏸ Pausa 20:03:42

> ▶ Continúa 20:03:43
"""


class TestReagrupadaHonesta(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = pathlib.Path(self.tmp.name) / "daily_2026-09-25_16-05.md"
        self.src.write_text(NOTA_COLA, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_parsea_todos_los_marcadores(self):
        marcas = [e.text for e in parse_text(NOTA_COLA).entries if e.source == "pausa"]
        self.assertEqual(marcas[0], "⏸ Pausa")
        self.assertIn("⏳ transcripción atrasada 54 min desde", marcas)
        self.assertTrue(any(m.startswith("⚠ audio de micrófono caído") for m in marcas))

    def test_ordena_por_hora(self):
        horas = [e.stamp for e in sort_by_time(parse_text(NOTA_COLA).entries)]
        self.assertEqual(horas, sorted(horas))
        self.assertLess(horas.index("17:53:06"), horas.index("17:53:25"))

    def test_ordenar_respeta_la_medianoche(self):
        e = [Entry("23:59:50", "out", "a"), Entry("00:00:10", "out", "b"), Entry("23:59:55", "out", "c")]
        self.assertEqual([x.text for x in sort_by_time(e)], ["a", "c", "b"])

    def test_un_tramo_con_solo_marcadores_no_existe(self):
        md = build_digest(self.src, DigestOptions(60))
        self.assertNotIn("## 20:00 - 21:00", md)
        self.assertIn("Pausa 20:03:42", md)  # el marcador sigue, en el tramo anterior
        grupos = group_by_interval(sort_by_time(parse_text(NOTA_COLA).entries), 60)
        self.assertEqual([g[0] for g in grupos], ["17:00 - 18:00", "18:00 - 19:00"])

    def test_hora_por_parrafo_al_agrupar(self):
        md = build_digest(self.src, DigestOptions(60))
        self.assertIn("- [17:52] Frase larga de antes", md)
        self.assertIn("- [18:08] Frase larga dicha durante el atraso", md)

    def test_la_frase_tardia_queda_antes_de_la_pausa(self):
        md = build_digest(self.src, DigestOptions(60, merge=False))
        self.assertLess(md.index("transcrita tarde"), md.index("Pausa 17:53:25"))

    def test_marcador_de_atraso_y_captura_tardia_sobreviven(self):
        md = build_digest(self.src, DigestOptions(60))
        self.assertIn("⏳ transcripción atrasada 54 min desde 18:08:44", md)
        self.assertIn("2026-09-25_18-08-50_aqui.jpg", md)

    def test_quitar_eco_y_cortas(self):
        opts = DigestOptions(60, drop_short_words=4, drop_echo=True, vocab="Términos: API, QA.")
        md = build_digest(self.src, opts)
        self.assertNotIn("Términos.", md)
        self.assertIn("Crearon tres endpoints nuevos", md)

    def test_drop_echo_conserva_lineas_con_captura(self):
        e = [Entry("00:00:01", "out", "Términos.", captures=["a.png"]), Entry("00:00:02", "out", "Términos.")]
        d = drop_echo(e, "")
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0].captures, ["a.png"])

    def test_la_cabecera_dice_que_no_es_un_resumen(self):
        md = build_digest(self.src, DigestOptions(60))
        self.assertIn("No es un resumen", md)
        titulo = next(l for l in md.splitlines() if l.startswith("# "))
        self.assertIn("reagrupada", titulo)
        self.assertRegex(md, r"\d+ palabras en el original, \d+ aqui \(\d+ % menos\)")

    def test_texto_puro_sin_imagenes_ni_indicadores(self):
        nota = NOTA_COLA + (
            "- **19:10:00** Ok.\n  - 📸 `aqui` → ![](capturas/c.jpg)\n"
            "- **19:10:30** 📸 captura manual → ![](capturas/m.png)\n"
            "- **19:11:00** Términos.\n  - 📸 `ahi` → ![](capturas/d.jpg)\n"
        )
        self.src.write_text(nota, encoding="utf-8")
        md = build_digest(self.src, DigestOptions(60, keep_captures=False, drop_short_words=4, drop_echo=True))
        for rastro in ("📸", "![](", ".jpg", ".png", "tardía", "captura manual"):
            self.assertNotIn(rastro, md)
        # sin su imagen, lo corto y el eco ya no tienen por qué quedarse
        self.assertNotIn("Ok.", md)
        self.assertNotRegex(md, r"(?m)^- \[\d\d:\d\d\] *$", "ningún párrafo vacío")
        self.assertIn("Frase larga dicha durante el atraso", md)
        self.assertIn("texto puro", md.split("---")[1])

    def test_el_nombre_viejo_sigue_contando_como_derivado(self):
        viejo = self.src.with_name(self.src.stem + "_sintesis-1h.md")
        viejo.write_text("# sin cabecera\n", encoding="utf-8")
        self.assertEqual([p.name for p in list_originals(self.src.parent)], [self.src.name])


if __name__ == "__main__":
    unittest.main()
