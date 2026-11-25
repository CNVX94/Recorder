"""El lector de teclas (cli/teclas.py): secuencias de Windows y POSIX guionizadas y la terminal
restaurada aunque salte una excepción. Sin consola real: lo de cada plataforma se inyecta."""

import os
import unittest
from types import SimpleNamespace

from recorder.cli import teclas
from recorder.cli.teclas import (
    ABAJO, ARRIBA, AVPAG, DERECHA, ENTER, ESC, ESPACIO, ESPERA_ESC, FIN, INICIO, IZQUIERDA, REPAG, RETROCESO, SUPR, TAB,
    LectorPosix, decodificar_posix, decodificar_windows, modo_cbreak,
)


class TestWindows(unittest.TestCase):
    def tecla(self, *caracteres):
        resto = iter(caracteres[1:])
        return decodificar_windows(caracteres[0], lambda: next(resto))

    def test_flechas_con_los_dos_prefijos(self):
        for prefijo in ("\xe0", "\x00"):
            self.assertEqual(
                [self.tecla(prefijo, c) for c in "HPKM"], [ARRIBA, ABAJO, IZQUIERDA, DERECHA], repr(prefijo)
            )

    def test_inicio_fin_supr_y_paginas(self):
        for prefijo in ("\xe0", "\x00"):
            self.assertEqual(
                [self.tecla(prefijo, c) for c in "GOSIQ"], [INICIO, FIN, SUPR, REPAG, AVPAG], repr(prefijo)
            )

    def test_otras_especiales_se_consumen_y_se_ignoran(self):
        self.assertIsNone(self.tecla("\x00", ";"))  # F1
        self.assertIsNone(self.tecla("\xe0", "R"))  # Insert

    def test_teclas_con_nombre_y_caracteres(self):
        self.assertEqual(
            [self.tecla(c) for c in ("\r", "\x1b", "\t", "\x08", "q", "Ñ", "?", " ")],
            [ENTER, ESC, TAB, RETROCESO, "q", "Ñ", "?", ESPACIO],
        )


class TestPosix(unittest.TestCase):
    def test_flechas_csi_y_ss3(self):
        for secuencia, tecla in (("\x1b[A", ARRIBA), ("\x1b[B", ABAJO), ("\x1b[C", DERECHA), ("\x1b[D", IZQUIERDA), ("\x1bOA", ARRIBA)):
            self.assertEqual(decodificar_posix(secuencia), (tecla, ""), repr(secuencia))

    def test_inicio_fin_supr_y_paginas(self):
        casos = (
            ("\x1b[H", INICIO), ("\x1b[F", FIN), ("\x1bOH", INICIO), ("\x1bOF", FIN), ("\x1b[1~", INICIO),
            ("\x1b[4~", FIN), ("\x1b[7~", INICIO), ("\x1b[8~", FIN), ("\x1b[3~", SUPR), ("\x1b[5~", REPAG), ("\x1b[6~", AVPAG),
        )
        for secuencia, tecla in casos:
            self.assertEqual(decodificar_posix(secuencia), (tecla, ""), repr(secuencia))
        self.assertEqual(decodificar_posix("\x1b[6~j"), (AVPAG, "j"))
        self.assertEqual(decodificar_posix(" "), (ESPACIO, ""))

    def test_secuencias_que_no_son_flechas_se_consumen_enteras(self):
        self.assertEqual(decodificar_posix("\x1b[1;5Aj"), (None, "j"))  # Ctrl+↑ y una j
        self.assertEqual(decodificar_posix("\x1b[15~"), (None, ""))  # F5
        self.assertEqual(decodificar_posix("\x1b["), (None, ""))  # cortada

    def test_esc_suelto_o_seguido_de_otra_tecla(self):
        self.assertEqual(decodificar_posix("\x1b"), (ESC, ""))
        self.assertEqual(decodificar_posix("\x1bq"), (ESC, "q"))

    def test_teclas_con_nombre_y_varias_de_golpe(self):
        self.assertEqual(decodificar_posix("\n"), (ENTER, ""))
        self.assertEqual(decodificar_posix("\r"), (ENTER, ""))
        self.assertEqual(decodificar_posix("\x7f"), (RETROCESO, ""))
        self.assertEqual(decodificar_posix("\x1b[Bk"), (ABAJO, "k"))
        self.assertEqual(decodificar_posix(""), (None, ""))


class Fd:
    """Un descriptor de mentira: entrega los trozos en orden, uno por lectura, y anota las esperas."""

    def __init__(self, *trozos: bytes):
        self.trozos = list(trozos)
        self.esperas = []

    def leer(self, _fd, _n):
        return self.trozos.pop(0)

    def listo(self, espera):
        self.esperas.append(espera)
        return bool(self.trozos)


def leer_todo(fd: Fd, veces: int):
    lector = LectorPosix(0, leer=fd.leer, listo=fd.listo)
    return [lector() for _ in range(veces)]


class TestLectorPosix(unittest.TestCase):
    def test_varias_teclas_en_una_lectura(self):
        self.assertEqual(leer_todo(Fd(b"j\x1b[Bk"), 4), ["j", ABAJO, "k", None])

    def test_esc_suelto_espera_un_poco_por_el_resto(self):
        fd = Fd(b"\x1b")
        self.assertEqual(leer_todo(fd, 2), [ESC, None])
        self.assertIn(ESPERA_ESC, fd.esperas)

    def test_una_flecha_partida_en_dos_lecturas(self):
        self.assertEqual(leer_todo(Fd(b"\x1b", b"[A"), 2), [ARRIBA, None])

    def test_una_letra_partida_entre_lecturas(self):
        self.assertEqual(leer_todo(Fd("ñ".encode()[:1], "ñ".encode()[1:]), 2), [None, "ñ"])


class TestRestauracion(unittest.TestCase):
    def termios_falso(self):
        llamadas = []
        termios = SimpleNamespace(
            TCSADRAIN=1,
            tcgetattr=lambda fd: ["como estaba", fd],
            tcsetattr=lambda fd, cuando, modo: llamadas.append(("restaurada", fd, cuando, modo)),
        )
        tty = SimpleNamespace(setcbreak=lambda fd: llamadas.append(("cbreak", fd)))
        return termios, tty, llamadas

    def test_se_restaura_tras_una_excepcion_y_con_ctrl_c(self):
        for error in (RuntimeError, KeyboardInterrupt):
            with self.subTest(error=error.__name__):
                termios, tty, llamadas = self.termios_falso()
                with self.assertRaises(error):
                    with modo_cbreak(7, termios, tty):
                        self.assertEqual(llamadas, [("cbreak", 7)])
                        raise error()
                self.assertEqual(llamadas[-1], ("restaurada", 7, 1, ["como estaba", 7]))

    def test_tambien_si_falla_al_entrar_en_cbreak(self):
        termios, _tty, llamadas = self.termios_falso()

        def falla(_fd):
            raise OSError("no es una terminal")

        with self.assertRaises(OSError):
            with modo_cbreak(3, termios, SimpleNamespace(setcbreak=falla)):
                pass
        self.assertEqual(llamadas, [("restaurada", 3, 1, ["como estaba", 3])])

    @unittest.skipIf(os.name == "nt", "en Windows se lee la consola con msvcrt")
    def test_sin_terminal_no_hay_teclas(self):
        import io
        from unittest import mock

        with mock.patch.object(teclas.sys, "stdin", io.StringIO("")):
            with teclas.teclado() as leer:
                self.assertIsNone(leer())


if __name__ == "__main__":
    unittest.main()
