"""Eco del vocabulario, reemplazos con espacios, muletillas y la hora de la palabra clave.

Fixtures sintéticos: los renglones imitan la forma de los de una daily real (docs/auditoria-
daily-2026-09-25.md), no su contenido.
"""
import unittest
from types import SimpleNamespace as S

from recorder.filters.echo import labels_in, strip_prompt_echo
from recorder.filters.keywords import MULETILLAS, find_keywords, first_keyword_pos
from recorder.filters.lexicon import fix
from recorder.filters.pipeline import TextPipeline, hit_offset

VOCAB_CON_ROTULOS = "Daily de desarrollo de software. Términos: API Core, QA, IIS. Nombres del equipo: Ana, Luis, Marta."
VOCAB_SIN_ROTULOS = "Daily de desarrollo de software con Acme. API Core, QA, IIS, programa de embarques, puerto 7100 y 7200. Ana, Luis y Marta."


def seg(text, start=0.0, end=0.0):
    return S(text=text, start=start, end=end, no_speech_prob=0.1, avg_logprob=-0.3)


class TestEcoDelVocabulario(unittest.TestCase):
    def test_renglones_que_son_solo_eco_se_descartan(self):
        # los casos reales de la auditoría (sección 2 del documento), con el vocabulario con rótulos
        for eco in [
            "Términos.",
            "Términos, ¿sabes? Términos, ¿sabes? Términos, ¿sabes?",
            "Términos del equipo. Términos del equipo. Ok.",
            "Nombres del equipo.",
            "¿Términos?",
            "Luis, Marta.",
            "Luis. Luis.",
            "Ana, Luis, Marta.",
        ]:
            self.assertEqual(strip_prompt_echo(eco, VOCAB_CON_ROTULOS), "", eco)

    def test_lista_del_vocabulario_sin_rotulos_tambien_es_eco(self):
        # Whisper small recitó así la lista del prompt sobre ruido de tecleo (medido, ver docs)
        self.assertEqual(strip_prompt_echo("Acme, API Core, QA, IIS, QA, IIS.", VOCAB_SIN_ROTULOS), "")
        self.assertEqual(strip_prompt_echo("Daily de desarrollo de software con Acme.", VOCAB_SIN_ROTULOS), "")

    def test_lo_que_una_persona_diria_se_conserva(self):
        # respuestas reales con términos del vocabulario: con "y"/"e", o con algo que no está en el vocab
        for frase in ["Ana y Luis.", "QA e IIS.", "Puerto 7100 y 7200.", "Ana, Luis, Marta y Pedro.", "Ana, Luis y Marta."]:
            self.assertEqual(strip_prompt_echo(frase, VOCAB_SIN_ROTULOS), frase)
            self.assertEqual(strip_prompt_echo(frase, VOCAB_CON_ROTULOS), frase)

    def test_el_rotulo_pegado_a_una_frase_real_se_quita(self):
        self.assertEqual(strip_prompt_echo("Términos crearon tres endpoints nuevos.", VOCAB_CON_ROTULOS),
                         "Crearon tres endpoints nuevos.")
        self.assertEqual(strip_prompt_echo("Términos, ya me deja iniciar sesión.", VOCAB_CON_ROTULOS), "Ya me deja iniciar sesión.")
        self.assertEqual(strip_prompt_echo("¿Sí? Términos, ya se puede checar.", VOCAB_CON_ROTULOS), "¿Sí? ya se puede checar.")

    def test_el_rotulo_solo_se_quita_si_esta_en_el_vocabulario(self):
        self.assertEqual(strip_prompt_echo("Términos crearon tres endpoints nuevos.", VOCAB_SIN_ROTULOS),
                         "Términos crearon tres endpoints nuevos.")
        self.assertEqual(strip_prompt_echo("Nombres del equipo.", VOCAB_SIN_ROTULOS), "Nombres del equipo.")
        # el más largo primero, para que "términos del equipo" gane a "términos"
        self.assertEqual(labels_in(VOCAB_CON_ROTULOS), ("términos del equipo", "nombres del equipo", "términos"))
        self.assertEqual(labels_in(VOCAB_SIN_ROTULOS), ())
        self.assertEqual(labels_in("Daily. Términos: QA."), ("términos",))

    def test_sin_vocabulario_no_se_toca_nada(self):
        for frase in ["Términos.", "Luis, Marta.", "Términos, ya me deja iniciar sesión."]:
            self.assertEqual(strip_prompt_echo(frase, ""), frase)
            self.assertEqual(strip_prompt_echo(frase, "   "), frase)

    def test_frases_legitimas_con_terminos_no_se_tocan(self):
        for legit in [
            "Términos de pago a treinta días.",
            "Términos del contrato firmados ayer.",
            "Términos y condiciones del contrato.",
            "Términos en los que quedamos.",
            "En términos de rendimiento mejoró bastante.",
            "Revisa los términos del acuerdo con el cliente.",
            "Ya quedaron los términos.",
            "Nombres del equipo de software es la misma herramienta.",
        ]:
            self.assertEqual(strip_prompt_echo(legit, VOCAB_CON_ROTULOS), legit)

    def test_un_termino_suelto_del_vocabulario_se_conserva(self):
        # puede ser una respuesta real ("¿en qué puerto?" "Puerto 7100.")
        for suelto in ["API Core.", "Programa de embarques.", "QA.", "Puerto 7100."]:
            self.assertEqual(strip_prompt_echo(suelto, VOCAB_SIN_ROTULOS), suelto)

    def test_frase_normal_que_menciona_terminos_del_vocab(self):
        frase = "Desplegamos el API Core en QA y falta el IIS."
        self.assertEqual(strip_prompt_echo(frase, VOCAB_SIN_ROTULOS), frase)

    def test_el_pipeline_descarta_el_eco_por_segmento(self):
        p = TextPipeline(keywords=[], ignore=[], fixes={}, vocab=VOCAB_CON_ROTULOS)
        text, _ = p.process_segments([seg("Términos."), seg("Términos crearon el endpoint."), seg("Luis, Marta.")])
        self.assertEqual(text, "Crearon el endpoint.")

    def test_el_filtro_se_puede_apagar(self):
        p = TextPipeline(keywords=[], ignore=[], fixes={}, vocab=VOCAB_CON_ROTULOS, echo_filter=False)
        text, _ = p.process_segments([seg("Términos."), seg("Términos crearon el endpoint."), seg("Luis, Marta.")])
        self.assertEqual(text, "Términos. Términos crearon el endpoint. Luis, Marta.")
        res = p.test_sample("Términos.")
        self.assertFalse(res["is_echo"])
        self.assertEqual(res["processed"], "Términos.")

    def test_el_probador_marca_el_eco(self):
        p = TextPipeline(keywords=[], ignore=[], fixes={}, vocab=VOCAB_CON_ROTULOS)
        res = p.test_sample("Términos.")
        self.assertTrue(res["is_echo"])
        self.assertFalse(res["is_ignored"])
        self.assertFalse(p.test_sample("Términos de pago.")["is_echo"])

    def test_mas_informacion_www_esta_en_la_lista_negra_por_defecto(self):
        from recorder.config.schema import AppConfig

        p = TextPipeline(keywords=[], ignore=AppConfig().ignore, fixes={})
        self.assertTrue(p.test_sample("Más información www.ejemplo-alucinado.com")["is_ignored"])


class TestReemplazosNuevos(unittest.TestCase):
    # Misma forma que las correcciones añadidas a config.json (nombres propios y siglas mal oídos),
    # con nombres inventados.
    FIXES = {
        "zinlat": "ZNLT",
        "sinlats": "ZNLT",
        "la gamel": "Lagamel",
        "nipple": "NIP",
        "iajs": "IIS",
        "botoken": "bot token",
        "programa de mark": "programa de embarques",
    }

    def test_variantes_de_una_sigla(self):
        self.assertEqual(fix("Zinlat y SINLATS mandaron el archivo.", self.FIXES), "ZNLT y ZNLT mandaron el archivo.")

    def test_claves_con_espacio(self):
        self.assertEqual(fix("Eso lo pidió la GAMEL ayer.", self.FIXES), "Eso lo pidió Lagamel ayer.")
        self.assertEqual(fix("Abre el programa de mark.", self.FIXES), "Abre el programa de embarques.")

    def test_clave_con_espacio_respeta_la_palabra_completa(self):
        self.assertEqual(fix("el programa de marketing", self.FIXES), "el programa de marketing")
        self.assertEqual(fix("la gameleira", self.FIXES), "la gameleira")

    def test_siglas_y_palabras_pegadas(self):
        self.assertEqual(fix("Reinicia el IAJs y pon el botoken del nipple.", self.FIXES),
                         "Reinicia el IIS y pon el bot token del NIP.")
        self.assertEqual(fix("nipples", self.FIXES), "nipples")


class TestPalabrasClave(unittest.TestCase):
    def test_este_es_muletilla_y_no_dispara(self):
        self.assertIn("este", MULETILLAS)
        texto = "Este, o sea, este ya está aquí."
        self.assertEqual(find_keywords(texto, ["este", "aquí"]), ["aquí"])

    def test_los_valores_por_defecto_no_traen_muletillas(self):
        from recorder.config.schema import AppConfig

        self.assertFalse({k.lower() for k in AppConfig().keywords} & MULETILLAS)

    def test_guardo_casa_tambien_guardo_con_acento(self):
        # sin acentos a propósito: "se guardó" también dispara; en 2 h 39 min fueron 3 veces
        self.assertEqual(find_keywords("Esto ya se guardó.", ["guardo"]), ["guardo"])

    def test_first_keyword_pos(self):
        self.assertEqual(first_keyword_pos("hola, esto va aquí", ["aqui"]), len("hola, esto va "))
        self.assertIsNone(first_keyword_pos("nada", ["aqui"]))


class TestHoraDeLaPalabra(unittest.TestCase):
    def test_interpola_dentro_del_segmento(self):
        texto = "a" * 50 + " aqui " + "b" * 44  # la palabra empieza en el carácter 51 de 100
        kept = [(seg("Primera frase.", 0.0, 4.0), "Primera frase."), (seg(texto, 10.0, 20.0), texto)]
        self.assertAlmostEqual(hit_offset(kept, {}, ["aqui"]), 10.0 + 51 / 100 * 10.0)

    def test_usa_el_primer_segmento_con_palabra(self):
        kept = [(seg("aquí al inicio", 2.0, 6.0), "aquí al inicio"), (seg("y aquí", 7.0, 9.0), "y aquí")]
        self.assertAlmostEqual(hit_offset(kept, {}, ["aqui"]), 2.0)

    def test_la_palabra_puede_salir_de_un_reemplazo(self):
        kept = [(seg("dile a cuba", 0.0, 10.0), "dile a cuba")]
        self.assertIsNotNone(hit_offset(kept, {"cuba": "QA"}, ["QA"]))

    def test_process_devuelve_la_hora(self):
        p = TextPipeline(keywords=["captura"], ignore=[], fixes={})
        text, hits, offset = p.process([seg("Hola."), seg("Toma captura de esto.", 5.0, 7.0)])
        self.assertEqual(hits, ["captura"])
        self.assertGreater(offset, 5.0)
        self.assertLess(offset, 7.0)
        self.assertEqual(p.process([seg("Sin nada.")])[2], None)


if __name__ == "__main__":
    unittest.main()
