"""Juegos de símbolos y modo VT de la consola (recorder/cli/consola.py y recorder/cli/vt.py)."""
import io
import unittest
from unittest import mock

from recorder.cli import app, consola, vt
from recorder.cli.consola import (
    ASCII, CONSOLA, JUEGO_ASCII, JUEGO_COMPLETO, JUEGO_CONSOLA, SEGUROS_CONSOLA, consolificar, elegir_juego, make_console,
    presentar,
)

MUESTRA = "✔ Guardado 🎯 Calibrar ▶ elegido █░ ⚠ 🔊 🎤 📸 ⏸ ● ‹ › ─ → ← ↑ ↓ … ▁▂▃▅▆▇ ✅ ⛔ ☕ ⏳ ‥ « » · á ñ"


class ElegirJuegoTest(unittest.TestCase):
    def juego(self, terminal=True, vt_activo=True, entorno=None, windows=True):
        return elegir_juego(terminal, vt_activo, entorno or {}, windows)

    def test_conhost_con_vt_es_consola(self):
        self.assertEqual(self.juego(), JUEGO_CONSOLA)

    def test_conhost_sin_vt_es_ascii(self):
        self.assertEqual(self.juego(vt_activo=False), JUEGO_ASCII)

    def test_salida_redirigida_es_ascii_aunque_haya_vt(self):
        self.assertEqual(self.juego(terminal=False), JUEGO_ASCII)
        self.assertEqual(self.juego(terminal=False, entorno={"WT_SESSION": "x"}), JUEGO_ASCII)

    def test_windows_terminal_y_vscode_son_completo(self):
        self.assertEqual(self.juego(entorno={"WT_SESSION": "abc"}), JUEGO_COMPLETO)
        self.assertEqual(self.juego(vt_activo=False, entorno={"TERM_PROGRAM": "vscode"}), JUEGO_COMPLETO)
        self.assertEqual(self.juego(entorno={"TERM_PROGRAM": "otro"}), JUEGO_CONSOLA)

    def test_fuera_de_windows_es_completo(self):
        self.assertEqual(self.juego(vt_activo=False, windows=False), JUEGO_COMPLETO)

    def test_make_console_decide_el_juego_y_ascii_lo_fuerza(self):
        with mock.patch.object(consola.vt, "hay_vt", return_value=True), \
                mock.patch.object(consola, "elegir_juego", return_value=JUEGO_CONSOLA) as elegir:
            c = make_console(file=io.StringIO(), force_terminal=True)
            self.assertEqual((c.juego, c.ascii_mode), (JUEGO_CONSOLA, False))
            self.assertEqual(elegir.call_args.args, (True, True))
        self.assertEqual(make_console(ascii_mode=True, file=io.StringIO()).juego, JUEGO_ASCII)
        self.assertTrue(make_console(ascii_mode=True, file=io.StringIO()).ascii_mode)
        self.assertEqual(make_console(ascii_mode=False, file=io.StringIO()).juego, JUEGO_COMPLETO)
        self.assertEqual(make_console(file=io.StringIO()).juego, JUEGO_ASCII, "un StringIO no es una terminal")


class SimbolosTest(unittest.TestCase):
    def test_juego_consola_solo_deja_simbolos_seguros(self):
        salida = consolificar(MUESTRA)
        fuera = {c for c in salida if ord(c) >= 0x2000 and c not in SEGUROS_CONSOLA and c not in "–—"}
        self.assertEqual(fuera, set(), f"fuera de la lista segura: {fuera} en {salida!r}")
        for simbolo in list(ASCII) + ["▶"]:
            for c in consolificar(f"a {simbolo} b"):
                self.assertTrue(ord(c) < 0x2000 or c in SEGUROS_CONSOLA, f"{simbolo!r} deja {c!r}")

    def test_consola_conserva_lo_seguro_y_cambia_lo_demas(self):
        seguros = "█░ ● ‹ › ─ · « » ► ↑ ↓ ← → … ▲ ○ ■ ▌ ▄ │ √ ‖ • ∙"
        self.assertEqual(consolificar(seguros), seguros)
        self.assertEqual(consolificar("▶ Opciones"), "► Opciones", "la marca de fila propia del juego")
        self.assertEqual(consolificar("🎯 Calibrar"), "Calibrar", "el emoji se lleva su espacio")
        self.assertEqual(consolificar("✔ ok ⚠ ⛔ ⏸ ⏳ 📸 🎤"), "√ ok ▲ × ‖ … ■ MIC")
        self.assertEqual(consolificar("‥"), "", "«‥» no está en Consolas: solo se veía porque Windows la toma de otra fuente")
        self.assertNotIn("‥", SEGUROS_CONSOLA)
        self.assertEqual(CONSOLA["▶"], "►")

    def test_cada_simbolo_propio_tiene_reserva_si_sale_de_la_lista_segura(self):
        for propio in consola.PROPIOS_CONSOLA.values():
            self.assertTrue(propio in SEGUROS_CONSOLA or ord(propio) < consola.LATIN1 or propio in consola.RESERVA_CONSOLA, propio)
        for reserva in consola.RESERVA_CONSOLA.values():
            self.assertTrue(all(ord(c) < 0x2000 or c in SEGUROS_CONSOLA for c in reserva), f"la reserva {reserva!r} no es segura")

    def test_un_simbolo_que_se_ve_mal_pasa_a_su_reserva_quitandolo_de_la_lista(self):
        sin = "".join(c for c in SEGUROS_CONSOLA if c not in "►‖")
        with mock.patch.object(consola, "SEGUROS_CONSOLA", sin):
            tabla = consola.construir_consola()
        self.assertEqual((tabla["▶"], tabla["⏸"], tabla["►"]), ("›", "=", "›"))

    def test_presentar_segun_el_juego(self):
        def con(juego):
            return mock.Mock(juego=juego, ascii_mode=juego == JUEGO_ASCII)

        self.assertEqual(presentar("▶ █ ⚠", con(JUEGO_ASCII)), "> # !")
        self.assertEqual(presentar("▶ █ ⚠", con(JUEGO_CONSOLA)), "► █ ▲")
        self.assertEqual(presentar("▶ █ ✔", con(JUEGO_COMPLETO)), "▶ █ ✅")

    def test_los_pares_de_flechas_del_pie_son_un_par_en_ascii(self):
        self.assertEqual(presentar("[↑↓] Mover · [←→] Cambiar", mock.Mock(juego=JUEGO_ASCII)), "[^v] Mover · [<>] Cambiar")
        self.assertEqual(presentar("[↑↓] [←→]", mock.Mock(juego=JUEGO_CONSOLA)), "[↑↓] [←→]")

    def test_consola_sin_juego_se_guia_por_ascii_mode(self):
        class Vieja:
            ascii_mode = True

        self.assertEqual(presentar("▶", Vieja()), ">")


class SpinnerYTemaTest(unittest.TestCase):
    def test_cada_juego_tiene_su_spinner_y_el_de_consola_solo_usa_simbolos_seguros(self):
        self.assertTrue(all(c in SEGUROS_CONSOLA for c in consola.FOTOGRAMAS[JUEGO_CONSOLA]))
        self.assertEqual(consola.fotograma(JUEGO_CONSOLA, 0.0), "∙")
        self.assertEqual(consola.fotograma(JUEGO_CONSOLA, consola.TIC_ANIMACION * 1.5), "•")
        self.assertEqual(consola.fotograma(JUEGO_CONSOLA, consola.TIC_ANIMACION * 4), "∙", "da la vuelta")
        self.assertEqual(consola.fotograma(JUEGO_ASCII, consola.TIC_ANIMACION * 2), "|")

    def test_en_ascii_el_tema_es_el_de_16_colores_y_sin_fondo(self):
        c = make_console(ascii_mode=True, file=io.StringIO(), force_terminal=True, color_system="standard")
        for estilo, color in (("texto", "bright_white"), ("acento", "bright_yellow"), ("mic", "bright_cyan")):
            self.assertEqual(c.get_style(estilo).color.name, color)
        self.assertIsNone(c.get_style("fondo").bgcolor)
        nombres = {str(c.get_style(e).color.name) for e in consola.ESTILOS_16 if c.get_style(e).color}
        self.assertFalse({"magenta", "yellow"} & nombres, "el acceso directo de PowerShell redefine esas dos casillas")

    def test_con_color_real_el_tema_trae_aviso_fondo_y_fila(self):
        c = make_console(ascii_mode=False, file=io.StringIO(), force_terminal=True, color_system="truecolor")
        self.assertEqual(c.get_style("aviso").color.get_truecolor().hex, "#fab387")
        self.assertEqual(c.get_style("fondo").bgcolor.get_truecolor().hex, "#1e1e2e")
        self.assertEqual(c.get_style("fila").bgcolor.get_truecolor().hex, "#313244")


class FalsoKernel32:
    """Un kernel32 de mentira: dos salidas con su modo, para probar el activar y el restaurar."""

    def __init__(self, modos):
        self.modos = dict(modos)  # manejador -> modo

    def GetStdHandle(self, codigo):
        return codigo if codigo in self.modos else 0

    def GetConsoleMode(self, manejador, destino):
        if manejador not in self.modos:
            return 0
        destino._obj.value = self.modos[manejador]
        return 1

    def SetConsoleMode(self, manejador, modo):
        self.modos[manejador] = modo
        return 1


class ModoVtTest(unittest.TestCase):
    def setUp(self):
        vt._originales.clear()
        self.addCleanup(vt._originales.clear)
        self.k32 = FalsoKernel32({-11: 0x0003, -12: 0x0003})
        parches = [mock.patch.object(vt, "_kernel32", return_value=self.k32), mock.patch.object(vt.sys, "platform", "win32"),
                   mock.patch.object(vt.atexit, "register")]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)

    def test_activa_vt_en_las_dos_salidas_y_restaura_el_modo_original(self):
        self.assertTrue(vt.activar())
        self.assertEqual(self.k32.modos, {-11: 0x0007, -12: 0x0007})
        vt.restaurar()
        self.assertEqual(self.k32.modos, {-11: 0x0003, -12: 0x0003})

    def test_restaura_tras_una_excepcion_y_limpia_colores_y_cursor(self):
        salida = mock.Mock()
        salida.isatty.return_value = True
        with mock.patch.object(app, "main", side_effect=RuntimeError("falla")), \
                mock.patch.object(app.sys, "stdout", salida), mock.patch.object(vt.sys, "stdout", salida):
            with self.assertRaises(RuntimeError):
                app.arrancar([])
        self.assertEqual(self.k32.modos, {-11: 0x0003, -12: 0x0003})
        salida.write.assert_called_with(vt.LIMPIAR)

    def test_si_ya_tenia_vt_no_toca_nada(self):
        self.k32.modos = {-11: 0x0007}
        self.assertTrue(vt.activar())
        self.assertEqual(vt._originales, {})
        vt.restaurar()
        self.assertEqual(self.k32.modos, {-11: 0x0007})

    def test_salida_redirigida_no_cambia_nada(self):
        self.k32.modos = {}
        self.assertFalse(vt.activar())
        self.assertEqual(vt._originales, {})

    def test_si_falla_todo_sigue_como_antes(self):
        with mock.patch.object(vt, "_kernel32", side_effect=OSError):
            self.assertFalse(vt.activar())
            self.assertFalse(vt.hay_vt())

    def test_fuera_de_windows_no_hace_nada(self):
        with mock.patch.object(vt.sys, "platform", "linux"):
            self.assertFalse(vt.activar())
            self.assertFalse(vt.hay_vt())


if __name__ == "__main__":
    unittest.main()
