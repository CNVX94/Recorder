"""La pantalla «Reagrupar nota» del menú (cli/pantallas/reagrupar.py) con teclas guionizadas, sobre una carpeta
temporal de notas. Misma base que las demás pantallas (tests/test_cli_pantallas.py)."""

import datetime as dt
import hashlib
import os
import re
import unittest

from rich.cells import cell_len

from recorder import ayuda
from recorder.cli import sintesis
from recorder.cli.pantallas import registro
from recorder.cli.pantallas.reagrupar import ReagruparNota, ReagruparOpciones
from recorder.cli.teclas import ABAJO, ARRIBA, AVPAG, DERECHA, ENTER, ESC, IZQUIERDA
from recorder.digest import digest_options, write_digest
from tests.apoyo_cli import argumentos, consola_de_prueba, solo_ascii
from tests.test_cli_pantallas import BaseTerminal

NOTA = (
    "# Daily 2026-09-08 10:20\n\n"
    "- **10:20:08** Primera frase larga sobre el despliegue del servicio.\n"
    "  - 📸 `captura` → ![](capturas/2026-09-08_10-20-27_captura.png)\n"
    "- **10:20:23** A ver.\n"
    "- **10:20:40** Términos.\n"
    "- **10:55:12** Otra frase larga de otro tramo del reloj.\n"
)
ANTIGUA = dt.datetime(2026, 9, 8, 11, 0).timestamp()
GENERADO = re.compile(r"^generado: .*$", re.M)
COPIA = "daily_2026-09-08_10-20_reagrupada-15min.md"


def abrir(t):
    return ReagruparNota(t)


class BaseReagrupar(BaseTerminal):
    def setUp(self):
        super().setUp()
        self.notas.mkdir()
        self.src = self.notas / "daily_2026-09-08_10-20.md"
        self.src.write_text(NOTA, encoding="utf-8")
        os.utime(self.src, (ANTIGUA, ANTIGUA))
        self.huella = hashlib.sha256(self.src.read_bytes()).hexdigest()

    def correr_aqui(self, *guion, **kw):
        return self.correr(*guion, inicial=abrir, **kw)

    def copias(self):
        return sorted(self.notas.glob("*_reagrupada*.md"))

    def assertOriginalIntacto(self):
        self.assertEqual(hashlib.sha256(self.src.read_bytes()).hexdigest(), self.huella)


class TestElegirNota(BaseReagrupar):
    def test_el_registro_la_abre_desde_el_menu(self):
        self.assertIs(registro.clase_de("sintesis"), ReagruparNota)

    def test_sin_notas_dice_que_hacer(self):
        self.src.unlink()
        _c, texto = self.correr_aqui(ESC)
        self.assertIn(ayuda.linea("reagrupar_vacio"), texto)

    def test_lista_con_fecha_hora_tamano_y_la_que_se_escribe(self):
        activa = self.notas / "daily_2026-09-09_09-00.md"
        activa.write_text(NOTA, encoding="utf-8")  # modificada ahora: se está escribiendo
        _c, texto = self.correr_aqui(ESC, ancho=100)
        self.assertIn("08/09/2026", texto)
        self.assertIn("● " + ayuda.entrada("reagrupar_en_curso")[0], texto)
        self.assertLess(texto.index(activa.name), texto.index(self.src.name), "la más reciente arriba")
        self.assertIn(ayuda.linea("reagrupar_en_curso")[:40], texto, "y su ayuda dice qué lleva la copia")

    def test_enter_y_numero_abren_las_opciones(self):
        _c, texto = self.correr_aqui(ENTER, ESC, ESC)
        self.assertIn(self.src.name, texto)
        self.assertIn("Cada 15 min", texto)
        _c, texto = self.correr_aqui("1", ESC, ESC)
        self.assertIn(ayuda.entrada("reagrupar_previa")[0], texto)

    def test_una_copia_no_se_lista(self):
        copia = write_digest(self.src, digest_options(15))
        _c, texto = self.correr_aqui(ESC)
        self.assertNotIn(copia.name, texto)


class TestOpciones(BaseReagrupar):
    def pantalla_tras(self, teclas, **kw):
        """Corre ENTER y `teclas`; devuelve (minutos, fila elegida) de las opciones tras cada tecla."""
        vistas = []

        def mirar():
            p = next(x for x in reversed(self.t.pila) if isinstance(x, ReagruparOpciones))
            vistas.append((p.minutos, p.lista.actual.dato))
            return True

        pasos = [ENTER]
        for k in teclas:
            pasos += [k, mirar]
        self.correr_aqui(*pasos, ESC, ESC, **kw)
        return vistas

    def test_cambiar_el_agrupamiento_cambia_la_vista_previa(self):
        _c, texto = self.correr_aqui(ENTER, IZQUIERDA, ESC, ESC, ancho=100)
        self.assertIn("## 10:15 - 10:30", texto, "con 15 minutos, tramos de 15")
        self.assertIn("Cada 5 min", texto)
        self.assertIn("## 10:20 - 10:25", texto, "al cambiar, la vista previa se recalcula")

    def test_sin_agrupar_apaga_la_hora_corta_y_las_flechas_la_saltan(self):
        vistas = self.pantalla_tras([IZQUIERDA, IZQUIERDA, ABAJO, ABAJO, ARRIBA, ARRIBA])
        self.assertEqual(vistas, [
            (5, "agrupar"), (0, "agrupar"), (0, "unir"), (0, "imagenes"), (0, "unir"), (0, "agrupar"),
        ])
        _c, texto = self.correr_aqui(ENTER, IZQUIERDA, IZQUIERDA, ESC, ESC, ancho=100)
        self.assertIn("Sin agrupar", texto)
        self.assertIn(ayuda.linea("reagrupar_hora_corta_no")[:30], texto, "y se dice por qué")
        t = self.terminal(ancho=100)
        pantalla = ReagruparOpciones(t, self.src)
        pantalla.cada = 0
        t.abrir(pantalla)
        self.assertNotIn("tramos ·", " ".join(l.plain for l in t.marco()), "sin agrupar no hay tramos")

    def test_el_agrupamiento_no_da_la_vuelta(self):
        vistas = self.pantalla_tras([DERECHA] * 5)
        self.assertEqual(vistas[-1][0], 60)

    def test_un_interruptor_cambia_la_copia(self):
        t = self.terminal(ancho=100)
        pantalla = ReagruparOpciones(t, self.src)
        t.abrir(pantalla)
        t.marco()
        self.assertNotIn("capturas/", pantalla._vista.markdown, "por defecto, texto puro")
        for k in (ABAJO, ABAJO, ABAJO, " "):  # hasta «Quitar imágenes» y apagarlo
            pantalla.tecla(k)
        t.marco()
        self.assertIn("capturas/2026-09-08_10-20-27_captura.png", pantalla._vista.markdown)

    def test_no_es_un_resumen_se_dice_una_vez(self):
        _c, texto = self.correr_aqui(ENTER, ESC, ESC, ancho=100)
        self.assertNotIn("No es un resumen", texto, "la vista previa no repite el aviso")
        _c, texto = self.correr_aqui(ENTER, "g", ESC, ESC, ESC, ancho=140)
        self.assertEqual(texto.count("no es un resumen"), 1)

    def test_la_vista_previa_se_desplaza(self):
        larga = "# Daily\n\n" + "".join(f"- **10:{m:02d}:00** Frase número {m} de la reunión larga.\n" for m in range(0, 59))
        self.src.write_text(larga, encoding="utf-8")
        os.utime(self.src, (ANTIGUA, ANTIGUA))
        _c, texto = self.correr_aqui(ENTER, *[AVPAG] * 6, ESC, ESC, ancho=100)
        self.assertIn("Frase número 58", texto)
        self.assertRegex(texto, r"\d+-\d+ de \d+")

    def test_crear_escribe_lo_mismo_que_el_modo_linea_y_no_toca_el_original(self):
        _c, texto = self.correr_aqui(ENTER, "g", ENTER, ESC, ESC, ancho=100)
        copias = self.copias()
        self.assertEqual([c.name for c in copias], [COPIA])
        self.assertIn(ayuda.linea("reagrupar_creada").format(nombre=COPIA), texto)
        # el modo línea, con las mismas opciones, escribe lo mismo (salvo la hora de generación)
        copia = copias[0].read_text(encoding="utf-8")
        copias[0].unlink()
        consola, _buf = consola_de_prueba()
        self.assertEqual(sintesis.ejecutar(argumentos(sintesis, "--si", str(self.src)), consola, self.mgr), 0)
        self.assertEqual(GENERADO.sub("", copia), GENERADO.sub("", copias[0].read_text(encoding="utf-8")))
        self.assertOriginalIntacto()

    def test_pide_confirmar_dice_el_nombre_y_esc_no_crea_nada(self):
        _c, texto = self.correr_aqui(ENTER, "g", ESC, ESC, ESC, ancho=100)
        self.assertIn("Se creará", texto)
        self.assertIn(COPIA, texto)
        self.assertIn(ayuda.linea("reagrupar_confirmar")[:40], texto)
        self.assertEqual(self.copias(), [])
        self.assertOriginalIntacto()

    def test_nunca_sobrescribe_una_copia_anterior(self):
        previa = self.notas / COPIA
        previa.write_text("la de antes", encoding="utf-8")
        self.correr_aqui(ENTER, "g", ENTER, ESC, ESC, ancho=100)
        self.assertEqual(previa.read_text(encoding="utf-8"), "la de antes")
        self.assertEqual(len(self.copias()), 2)

    def test_enter_en_la_fila_crear_tambien_crea(self):
        self.correr_aqui(ENTER, ARRIBA, ENTER, ENTER, ESC, ESC, ancho=100)  # ARRIBA da la vuelta hasta «Crear la copia»
        self.assertEqual(len(self.copias()), 1)

    def test_la_lista_de_agrupamiento_se_abre_con_enter(self):
        vistas = self.pantalla_tras([ENTER, "1"], ancho=100)
        self.assertEqual(vistas[-1][0], 0, "«Sin agrupar» elegido de la lista")

    def cuadro(self, ancho, alto=24, **kw):
        """El cuadro de las opciones, línea a línea (lo que pinta el bucle), sin pasar por teclas."""
        t = self.terminal(ancho=ancho, alto=alto, **kw)
        t.abrir(ReagruparOpciones(t, self.src))
        return [linea.plain for linea in t.marco()]

    def test_cabe_en_cada_ancho_y_en_ascii_no_deja_restos(self):
        for ancho, ascii_mode in ((60, True), (60, False), (80, True), (100, False), (140, False)):
            with self.subTest(ancho=ancho, ascii=ascii_mode):
                lineas = self.cuadro(ancho, ascii_mode=ascii_mode)
                self.assertEqual(len(lineas), 24)
                self.assertTrue(all(cell_len(l) <= ancho for l in lineas), [l for l in lineas if cell_len(l) > ancho])
                self.assertIn(ayuda.entrada("reagrupar_previa")[0], "".join(lineas))
                if ascii_mode:
                    self.assertTrue(solo_ascii("".join(lineas)))

    def test_el_cuadro_de_confirmar_cabe(self):
        t = self.terminal(ancho=60, alto=24, ascii_mode=True)
        pantalla = ReagruparOpciones(t, self.src)
        t.abrir(pantalla)
        t.marco()
        pantalla.confirmando = True
        lineas = [l.plain for l in t.marco()]
        self.assertTrue(any("Se creara" in l or "Se creará" in l for l in lineas))
        self.assertTrue(all(cell_len(l) <= 60 for l in lineas))

    def test_a_80_columnas_la_vista_previa_va_a_la_derecha(self):
        _c, texto = self.correr_aqui(ENTER, ESC, ESC, ancho=80)
        self.assertRegex(texto, r"Agrupar +‹ Cada 15 min › +│ Vista previa")

    def test_a_60_columnas_va_debajo(self):
        _c, texto = self.correr_aqui(ENTER, ESC, ESC, ancho=60)
        self.assertNotRegex(texto, r"Agrupar +‹ Cada 15 min › +│")
        self.assertIn(ayuda.entrada("reagrupar_previa")[0], texto)

    def test_el_original_no_cambia_nunca(self):
        self.correr_aqui(ENTER, DERECHA, "g", ENTER, ESC, ESC, ancho=100)
        self.assertOriginalIntacto()


if __name__ == "__main__":
    unittest.main()
