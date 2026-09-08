import unittest
from types import SimpleNamespace as S

from recorder.filters.normalizer import normalize
from recorder.filters.quality import calculate_compression_ratio, is_segment_valid
from recorder.filters.blacklist import contains_blacklisted_phrase, filter_blacklisted_segments
from recorder.filters.lexicon import fix, parse_fixes, format_fixes
from recorder.filters.keywords import find_keywords
from recorder.filters.pipeline import clean_segments, TextPipeline


class TestFiltersAndLexicon(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize("Hola Cómo Estás"), "hola como estas")
        self.assertEqual(normalize("ÁÉÍÓÚ ñ"), "aeiou n")
        self.assertEqual(normalize(""), "")

    def test_quality_filter(self):
        valid = S(text="Voz clara", no_speech_prob=0.1, avg_logprob=-0.4, compression_ratio=1.2)
        self.assertTrue(is_segment_valid(valid))

        no_speech = S(text="Ruido", no_speech_prob=0.8, avg_logprob=-0.2, compression_ratio=1.2)
        self.assertFalse(is_segment_valid(no_speech))

        low_conf = S(text="asdfgh", no_speech_prob=0.1, avg_logprob=-1.5, compression_ratio=1.2)
        self.assertFalse(is_segment_valid(low_conf))

        # Repetición alta
        rep = S(text="de de de de de de de de de de de de de de de de", no_speech_prob=0.1, avg_logprob=-0.3, compression_ratio=3.5)
        self.assertFalse(is_segment_valid(rep))

    def test_compression_ratio_calculation(self):
        ratio_normal = calculate_compression_ratio("Este es un texto normal variado en una conversación de desarrollo.")
        ratio_repetitive = calculate_compression_ratio("palabra palabra palabra palabra palabra palabra palabra palabra palabra palabra palabra palabra")
        self.assertGreater(ratio_repetitive, ratio_normal)

    def test_blacklist(self):
        blacklist = ["suscríbete", "próximo vídeo", "amara.org"]
        self.assertTrue(contains_blacklisted_phrase("¡Por favor suscríbete al canal!", blacklist))
        self.assertTrue(contains_blacklisted_phrase("subtítulos en Amara.org gracias", blacklist))
        self.assertFalse(contains_blacklisted_phrase("Revisamos el PR de autenticación", blacklist))

        segs = ["Hola a todos", "suscríbete", "Vamos a comenzar"]
        self.assertEqual(filter_blacklisted_segments(segs, blacklist), ["Hola a todos", "Vamos a comenzar"])

    def test_lexicon_fixes(self):
        fixes = {"cuba": "QA", "ayayas": "IIS", "yenkins": "Jenkins"}
        text = "Subimos a cuba y reiniciamos el ayayas para revisar yenkins."
        result = fix(text, fixes)
        self.assertEqual(result, "Subimos a QA y reiniciamos el IIS para revisar Jenkins.")

        # Palabra completa respetada
        self.assertEqual(fix("incubadora", {"cuba": "QA"}), "incubadora")

    def test_parse_and_format_fixes(self):
        raw = " cuba = QA ; ayayas = IIS ;  test = 123 "
        parsed = parse_fixes(raw)
        self.assertEqual(parsed, {"cuba": "QA", "ayayas": "IIS", "test": "123"})
        formatted = format_fixes(parsed)
        self.assertIn("cuba=QA", formatted)
        self.assertIn("ayayas=IIS", formatted)

    def test_keywords(self):
        kws = ["bloqueo", "pendiente", "captura"]
        hits = find_keywords("Tenemos un BLOQUEO con el servidor", kws)
        self.assertEqual(hits, ["bloqueo"])

        # No coincidir subpalabras
        self.assertEqual(find_keywords("desbloqueo realizado", kws), [])

        # Insensible a acentos
        self.assertEqual(find_keywords("Atención al código ahí", ["ahi"]), ["ahi"])

    def test_text_pipeline(self):
        pipeline = TextPipeline(
            keywords=["bloqueo"],
            ignore=["suscríbete"],
            fixes={"cuba": "QA"},
        )
        segs = [
            S(text="Estamos probando en cuba.", no_speech_prob=0.1, avg_logprob=-0.2),
            S(text="¡Suscríbete al canal!", no_speech_prob=0.1, avg_logprob=-0.2),
            S(text="Hay un bloqueo en la base.", no_speech_prob=0.1, avg_logprob=-0.2),
        ]
        text, hits = pipeline.process_segments(segs)
        self.assertEqual(text, "Estamos probando en QA. Hay un bloqueo en la base.")
        self.assertEqual(hits, ["bloqueo"])

    def test_pipeline_sandbox(self):
        pipeline = TextPipeline(
            keywords=["captura"],
            ignore=["amara.org"],
            fixes={"cuba": "QA"},
        )
        test_ignored = pipeline.test_sample("visita amara.org para mas")
        self.assertTrue(test_ignored["is_ignored"])
        self.assertEqual(test_ignored["processed"], "")

        test_accepted = pipeline.test_sample("Revisando cuba para la captura")
        self.assertFalse(test_accepted["is_ignored"])
        self.assertEqual(test_accepted["processed"], "Revisando QA para la captura")
        self.assertEqual(test_accepted["hits"], ["captura"])


if __name__ == "__main__":
    unittest.main()
