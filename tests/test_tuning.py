"""Lógica de la ventana de Calibración sin Tkinter (filters/tuning.py).

Lo que la ventana 🎯 y el futuro `daily calibrar` comparten: leer los campos tal como se
escriben, probar una frase contra ellos (el sandbox) y guardarlos. Sin ventana ni modelo.
"""

import unittest

from recorder.config.schema import AppConfig
from recorder.filters.tuning import (
    COMMON_IGNORE,
    ECHO_VERDICT,
    THRESHOLD_RANGES,
    TuningForm,
    apply_tuning,
    format_ignore,
    parse_ignore,
    test_phrase,
    tuning_form,
    with_common_ignore,
)

KEYWORDS = ["pendiente", "bloqueo", "captura"]


def formulario(**cambios) -> TuningForm:
    f = TuningForm(
        vocab="Daily. Términos: QA, IIS.",
        ignore="suscríbete, gracias por ver",
        fixes="cuba=QA; ayayas=IIS",
        no_speech_threshold=0.6,
        logprob_threshold=-1.0,
        compression_ratio_threshold=2.4,
    )
    for k, v in cambios.items():
        setattr(f, k, v)
    return f


class TestCampos(unittest.TestCase):
    def test_formulario_desde_config(self):
        cfg = AppConfig(vocab="Términos: QA", ignore=["a", "b"], fixes={"cuba": "QA"}, no_speech_threshold=0.5)
        f = tuning_form(cfg)
        self.assertEqual((f.vocab, f.ignore, f.fixes), ("Términos: QA", "a, b", "cuba=QA"))
        self.assertEqual(f.no_speech_threshold, 0.5)
        self.assertEqual((f.logprob_threshold, f.compression_ratio_threshold), (-1.0, 2.4))

    def test_lista_negra_ida_y_vuelta(self):
        self.assertEqual(parse_ignore(" a ,, b,c "), ["a", "b", "c"])
        self.assertEqual(parse_ignore(""), [])
        self.assertEqual(format_ignore(["a", "b"]), "a, b")
        self.assertEqual(parse_ignore(format_ignore(["a", "b"])), ["a", "b"])

    def test_campos_interpretados(self):
        f = formulario()
        self.assertEqual(f.ignore_list, ["suscríbete", "gracias por ver"])
        self.assertEqual(f.fixes_dict, {"cuba": "QA", "ayayas": "IIS"})

    def test_anadir_comunes_no_repite(self):
        con = with_common_ignore(["gracias por ver", "mi frase"])
        self.assertEqual(con[:2], ["gracias por ver", "mi frase"])  # lo propio se conserva y va primero
        self.assertEqual(con.count("gracias por ver"), 1)
        for c in COMMON_IGNORE:
            self.assertIn(c, con)
        self.assertEqual(with_common_ignore([]), COMMON_IGNORE)
        self.assertEqual(with_common_ignore(COMMON_IGNORE), COMMON_IGNORE)  # ya estaban todas

    def test_rangos_de_los_umbrales_cubren_los_valores_de_fabrica(self):
        cfg = AppConfig()
        for campo, (lo, hi, paso) in THRESHOLD_RANGES.items():
            valor = getattr(cfg, campo)
            self.assertTrue(lo <= valor <= hi, f"{campo}={valor} fuera de [{lo}, {hi}]")
            self.assertGreater(paso, 0)


class TestSandbox(unittest.TestCase):
    def test_frase_prohibida_se_descarta(self):
        v = test_phrase(formulario(), "Hoy desplegamos. ¡Suscríbete!", KEYWORDS)
        self.assertFalse(v.accepted)
        self.assertEqual((v.processed, v.hits), ("", []))
        self.assertEqual(v.message, "⛔ DESCARTADA: Contiene una frase de la lista negra de alucinaciones.")

    def test_frase_aceptada_con_correcciones_y_claves(self):
        v = test_phrase(formulario(), "Hay un bloqueo en cuba y en el ayayas.", KEYWORDS)
        self.assertTrue(v.accepted)
        self.assertEqual(v.processed, "Hay un bloqueo en QA y en el IIS.")
        self.assertEqual(v.hits, ["bloqueo"])
        self.assertEqual(
            v.message,
            '✅ ACEPTADA: "Hay un bloqueo en QA y en el IIS."  (📸 Palabras clave detectadas: bloqueo)',
        )

    def test_frase_limpia_sin_claves(self):
        v = test_phrase(formulario(), "Revisamos el PR de autenticación.", KEYWORDS)
        self.assertTrue(v.accepted)
        self.assertEqual(v.message, '✅ ACEPTADA: "Revisamos el PR de autenticación."')

    def test_usa_lo_escrito_ahora_no_lo_guardado(self):
        # la frase solo se descarta si la lista negra del formulario la incluye
        self.assertTrue(test_phrase(formulario(ignore=""), "¡Suscríbete!", KEYWORDS).accepted)
        self.assertFalse(test_phrase(formulario(ignore="suscríbete"), "¡Suscríbete!", KEYWORDS).accepted)

    def test_sin_palabras_clave_no_hay_capturas(self):
        self.assertEqual(test_phrase(formulario(), "Hay un bloqueo.", []).hits, [])

    def test_el_eco_del_vocabulario_se_descarta_con_su_propio_veredicto(self):
        # el rótulo del vocabulario escrito AHORA en el formulario, y una lista de sus términos
        for eco in ("Términos.", "QA, IIS."):
            v = test_phrase(formulario(), eco, KEYWORDS)
            self.assertFalse(v.accepted, eco)
            self.assertTrue(v.echo, eco)
            self.assertEqual(v.message, ECHO_VERDICT)
            self.assertEqual((v.processed, v.hits), ("", []))
        legit = test_phrase(formulario(), "Términos de pago a treinta días.", KEYWORDS)
        self.assertTrue(legit.accepted)
        self.assertFalse(legit.echo)
        self.assertFalse(test_phrase(formulario(), "¡Suscríbete!", KEYWORDS).echo, "la lista negra manda antes")

    def test_las_comunes_traen_mas_informacion_www(self):
        self.assertIn("más información www", COMMON_IGNORE)


class TestGuardar(unittest.TestCase):
    def test_vuelca_los_campos_interpretados(self):
        cfg = AppConfig()
        apply_tuning(cfg, formulario(vocab="  Términos: QA  ", no_speech_threshold=0.45, logprob_threshold=-1.3))
        self.assertEqual(cfg.vocab, "Términos: QA")  # recortado
        self.assertEqual(cfg.ignore, ["suscríbete", "gracias por ver"])
        self.assertEqual(cfg.fixes, {"cuba": "QA", "ayayas": "IIS"})
        self.assertEqual((cfg.no_speech_threshold, cfg.logprob_threshold), (0.45, -1.3))
        self.assertIsInstance(cfg.compression_ratio_threshold, float)

    def test_no_toca_lo_que_no_es_suyo(self):
        cfg = AppConfig(notes_dir="C:/Dailies", keywords=["x"], model="medium")
        apply_tuning(cfg, formulario())
        self.assertEqual((cfg.notes_dir, cfg.keywords, cfg.model), ("C:/Dailies", ["x"], "medium"))

    def test_ida_y_vuelta(self):
        cfg = AppConfig(vocab="QA", ignore=["a"], fixes={"b": "c"})
        antes = cfg.to_dict()
        apply_tuning(cfg, tuning_form(cfg))
        self.assertEqual(cfg.to_dict(), antes)


if __name__ == "__main__":
    unittest.main()
