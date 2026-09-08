import random
import unittest

from recorder.filters.pipeline import TextPipeline
from recorder.filters.samples import FALLBACK_TERMS, extract_terms, random_sample, sample_kinds

VOCAB = "Daily de desarrollo de software. Términos: API Core, QA, IIS, Bruno."
FIXES = {"cuba": "QA", "ayayas": "IIS"}
IGNORE = ["suscríbete", "gracias por ver"]
KEYWORDS = ["pendiente", "bloqueo"]


def build_pipeline():
    return TextPipeline(
        keywords=KEYWORDS,
        ignore=IGNORE,
        fixes=FIXES,
        no_speech_thresh=0.6,
        logprob_thresh=-1.0,
        compression_ratio_thresh=2.4,
    )


class TestSamples(unittest.TestCase):
    def test_extract_terms_drops_prose(self):
        terms = extract_terms(VOCAB)
        self.assertEqual(terms, ["API Core", "QA", "IIS", "Bruno"])
        self.assertNotIn("Daily de desarrollo de software", terms)  # prosa, no termino
        self.assertNotIn("Términos", terms)  # etiqueta del prompt

    def test_extract_terms_empty(self):
        self.assertEqual(extract_terms(""), [])
        self.assertEqual(extract_terms("   "), [])

    def test_sample_kinds_only_offers_what_is_configured(self):
        self.assertEqual(sample_kinds({}, [], []), ["limpia"])
        self.assertEqual(
            sorted(sample_kinds(FIXES, IGNORE, KEYWORDS)),
            ["alucinacion", "clave", "correccion", "limpia"],
        )

    def test_hallucination_sample_is_discarded(self):
        pipe = build_pipeline()
        for seed in range(20):
            s = random_sample(VOCAB, FIXES, IGNORE, KEYWORDS, rng=random.Random(seed), kind="alucinacion")
            self.assertTrue(pipe.test_sample(s)["is_ignored"], f"deberia descartarse: {s}")

    def test_correction_sample_gets_fixed(self):
        pipe = build_pipeline()
        for seed in range(20):
            s = random_sample(VOCAB, FIXES, IGNORE, KEYWORDS, rng=random.Random(seed), kind="correccion")
            res = pipe.test_sample(s)
            self.assertFalse(res["is_ignored"])
            self.assertNotEqual(res["processed"], s)  # el lexico cambio algo
            self.assertTrue(any(v in res["processed"] for v in FIXES.values()))

    def test_keyword_sample_is_detected(self):
        pipe = build_pipeline()
        for seed in range(20):
            s = random_sample(VOCAB, FIXES, IGNORE, KEYWORDS, rng=random.Random(seed), kind="clave")
            self.assertTrue(pipe.test_sample(s)["hits"], f"deberia disparar captura: {s}")

    def test_clean_sample_passes_untouched(self):
        pipe = build_pipeline()
        for seed in range(20):
            s = random_sample(VOCAB, FIXES, IGNORE, KEYWORDS, rng=random.Random(seed), kind="limpia")
            res = pipe.test_sample(s)
            self.assertFalse(res["is_ignored"])
            self.assertEqual(res["hits"], [])

    def test_empty_glossary_does_not_crash(self):
        s = random_sample("", {}, [], [], rng=random.Random(0))
        self.assertTrue(s.strip())
        self.assertTrue(any(t in s for t in FALLBACK_TERMS))

    def test_samples_vary(self):
        seen = {random_sample(VOCAB, FIXES, IGNORE, KEYWORDS, rng=random.Random(s)) for s in range(30)}
        self.assertGreater(len(seen), 5)  # no repite siempre la misma frase


if __name__ == "__main__":
    unittest.main()
