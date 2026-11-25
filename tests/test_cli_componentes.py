"""Los componentes comunes de las pantallas (cli/pantallas/componentes.py), el reparto del cuadro
(cli/pantallas/marco.py) y las pantallas que se apoyan en ellos: teclas guionizadas, sin terminal real.

Los componentes se prueban solos con sus teclas; el marco, con números; y las pantallas completas, a 100×30 y a
60×24 en los tres juegos de símbolos: cada línea del cuadro mide el ancho de la terminal, el cuadro la altura, y
en ASCII y en «consola» no queda ningún símbolo fuera de lo que esa consola dibuja.
"""
import threading
import unittest
from types import SimpleNamespace
from unittest import mock

from rich.cells import cell_len
from rich.text import Text

from recorder import ayuda
from recorder.cli import consola as modulo_consola
from recorder.cli.consola import JUEGO_ASCII, JUEGO_COMPLETO, JUEGO_CONSOLA, SEGUROS_CONSOLA
from recorder.cli.pantallas import Ayuda, Opciones, Rendimiento, Terminal, componentes, marco, registro
from recorder.cli.pantallas.componentes import (
    CampoTexto, Confirmacion, Fila, Interruptor, ListaAjustes, ListaSeleccion, Numerico, VistaPrevia, coma, estado_error,
    estado_vacio, recortar_por_el_medio,
)
from recorder.cli.teclas import (
    ABAJO, ARRIBA, AVPAG, DERECHA, ENTER, ESC, ESPACIO, FIN, INICIO, IZQUIERDA, REPAG, RETROCESO, SUPR,
)
from tests.test_cli_pantallas import ENTORNO, BaseTerminal, limpio


def teclear(componente, *teclas):
    """Las teclas una a una; devuelve lo que contestó cada una (si la atendió)."""
    return [componente.tecla(k) for k in teclas]


class TestCampoTexto(unittest.TestCase):
    def test_escribe_al_final_y_el_cursor_se_mueve_entre_letras(self):
        c = CampoTexto("hola")
        teclear(c, " ", "q", "?")
        self.assertEqual((c.texto, c.cursor), ("hola q?", 7), "q y ? son texto, como el resto de las letras")
        teclear(c, IZQUIERDA, IZQUIERDA, "X")
        self.assertEqual((c.texto, c.cursor), ("hola Xq?", 6))
        teclear(c, INICIO, "A")
        self.assertEqual((c.texto, c.cursor), ("Ahola Xq?", 1))
        teclear(c, FIN, DERECHA, "Z")
        self.assertEqual(c.texto, "Ahola Xq?Z")

    def test_retroceso_y_supr_borran_donde_esta_el_cursor(self):
        c = CampoTexto("abcd")
        teclear(c, IZQUIERDA, IZQUIERDA, RETROCESO)
        self.assertEqual((c.texto, c.cursor), ("acd", 1))
        teclear(c, SUPR)
        self.assertEqual((c.texto, c.cursor), ("ad", 1))
        teclear(c, INICIO, RETROCESO)
        self.assertEqual(c.texto, "ad", "al principio no hay nada que borrar")
        teclear(c, FIN, SUPR)
        self.assertEqual(c.texto, "ad", "al final no hay nada que suprimir")

    def test_enter_esc_y_flechas_verticales_no_son_suyas(self):
        c = CampoTexto("x")
        self.assertEqual(teclear(c, ENTER, ESC, ARRIBA, ABAJO, REPAG), [False] * 5)

    def test_el_cursor_se_pinta_entre_las_letras(self):
        c = CampoTexto("bloqueo, error, demo")
        c.cursor = len("bloqueo, error")
        antes = "".join(t for t, _e in c.partes(60))
        self.assertEqual(antes, "› bloqueo, error▌, demo")

    def test_ventana_deslizante_mantiene_el_cursor_a_la_vista(self):
        c = CampoTexto("0123456789" * 5)
        for posicion in (0, 7, 25, 50):
            c.cursor = posicion
            partes = c.partes(20)
            visible = "".join(t for t, _e in partes)
            self.assertLessEqual(len(visible), 20)
            self.assertIn("▌", visible, f"con el cursor en {posicion}")
        c.cursor = 25
        visible = "".join(t for t, _e in c.partes(20))
        self.assertTrue(visible[2] == "…" and visible.endswith("…"), "«…» en los dos lados cortados")
        c.cursor = 0
        visible = "".join(t for t, _e in c.partes(20))
        self.assertTrue("…" not in visible[:-1] and visible.endswith("…"), "al principio solo se corta por la derecha")


class TestInterruptor(unittest.TestCase):
    def test_espacio_enter_y_flechas_lo_alternan(self):
        i = Interruptor(True)
        teclear(i, ESPACIO, ENTER, DERECHA, IZQUIERDA, ESPACIO)
        self.assertFalse(i.valor)
        self.assertFalse(i.tecla("x"))

    def test_se_lee_sin_color_en_los_tres_juegos(self):
        i = Interruptor(True)
        self.assertEqual("".join(t for t, _e in i.partes(JUEGO_CONSOLA)), "● sí")
        self.assertEqual("".join(t for t, _e in i.partes(JUEGO_ASCII)), "[x] sí")
        i.alternar()
        self.assertEqual("".join(t for t, _e in i.partes(JUEGO_COMPLETO)), "○ no")
        self.assertEqual("".join(t for t, _e in i.partes(JUEGO_ASCII)), "[ ] no")


class TestNumerico(unittest.TestCase):
    def test_se_mueve_de_paso_en_paso_sin_dar_la_vuelta(self):
        n = Numerico(0.6, 0.0, 1.0, 0.05)
        teclear(n, IZQUIERDA, IZQUIERDA)
        self.assertEqual(n.valor, 0.5, "sin errores de coma flotante")
        for _ in range(30):
            n.tecla(DERECHA)
        self.assertEqual(n.valor, 1.0, "se queda en el máximo")
        for _ in range(30):
            n.tecla(IZQUIERDA)
        self.assertEqual(n.valor, 0.0, "y en el mínimo")

    def test_coma_decimal_al_mostrar_y_acepta_coma_o_punto_al_teclear(self):
        n = Numerico(0.6, 0.0, 1.0, 0.05)
        self.assertEqual(n.texto(), "0,60")
        self.assertEqual(coma(1.5, 1), "1,5")
        self.assertTrue(n.aceptar("0,35") and n.valor == 0.35)
        self.assertTrue(n.aceptar(" 0.9 ") and n.valor == 0.9)
        for malo in ("", "mucho", "1,5", "-0,1"):
            self.assertFalse(n.aceptar(malo), malo)
        self.assertEqual(n.valor, 0.9, "lo inválido no cambia nada")

    def test_flechas_solo_en_la_fila_elegida(self):
        n = Numerico(2, 0, 10, 1, decimales=0)
        self.assertEqual("".join(t for t, _e in n.partes(True)), "‹ 2 ›")
        self.assertEqual("".join(t for t, _e in n.partes(False)), "2")


class TestRecorteDeRutas(unittest.TestCase):
    def test_conserva_el_principio_y_lo_que_distingue(self):
        ruta = r"C:\Users\ana\Documents\Dailies\capturas"
        corta = recortar_por_el_medio(ruta, 28)
        self.assertEqual(cell_len(corta), 28)
        self.assertTrue(corta.startswith(r"C:\Users") and corta.endswith("Dailies" + chr(92) + "capturas") and "…" in corta, corta)
        self.assertEqual(recortar_por_el_medio(ruta, 100), ruta, "si cabe, tal cual")


class TestListaAjustes(unittest.TestCase):
    def lista(self, n=5):
        return ListaAjustes([Fila(f"fila {i}") for i in range(n)])

    def test_mueve_dando_la_vuelta_y_va_a_los_extremos(self):
        lista = self.lista()
        teclear(lista, ARRIBA)
        self.assertEqual(lista.sel, 4)
        teclear(lista, ABAJO, "j")
        self.assertEqual(lista.sel, 1)
        teclear(lista, FIN)
        self.assertEqual(lista.sel, 4)
        teclear(lista, INICIO, "k")
        self.assertEqual(lista.sel, 4)
        self.assertFalse(lista.tecla("x"))

    def test_paginas_de_su_alto_menos_uno(self):
        lista = self.lista(30)
        lista.sitio = 10
        teclear(lista, AVPAG)
        self.assertEqual(lista.sel, 9)
        teclear(lista, AVPAG, AVPAG, AVPAG)
        self.assertEqual(lista.sel, 29, "no pasa del final")
        teclear(lista, REPAG)
        self.assertEqual(lista.sel, 20)


class TestVistaPrevia(unittest.TestCase):
    def test_pagina_y_dice_donde_esta(self):
        v = VistaPrevia([Text(f"línea {i}") for i in range(24)])
        visibles, posicion = v.ventana(10)
        self.assertEqual((len(visibles), posicion), (10, "1-10 de 24"))
        v.tecla(AVPAG, 10)
        self.assertEqual(v.ventana(10)[1], "10-19 de 24", "la página es el alto menos una línea")
        v.tecla(FIN, 10)
        self.assertEqual(v.ventana(10)[1], "15-24 de 24")
        v.tecla(REPAG, 10)
        v.tecla(INICIO, 10)
        self.assertEqual(v.ventana(10)[1], "1-10 de 24")
        self.assertFalse(v.tecla(ABAJO, 10), "↑↓ mueven las filas, no la vista previa")

    def test_cabe_entera_o_esta_vacia(self):
        self.assertEqual(VistaPrevia([Text("a")]).ventana(10)[1], "1-1 de 1")
        self.assertEqual(VistaPrevia([]).ventana(10), ([], ""))


class TestMarco(unittest.TestCase):
    def test_alto_de_la_ayuda_fijo_para_cada_ancho(self):
        self.assertEqual([marco.alto_ayuda(a) for a in (120, 92, 91, 74, 73, 60)], [2, 2, 3, 3, 4, 4])

    def test_respiros_segun_el_espacio_libre(self):
        self.assertEqual(marco.respiros(23), (1, 1), "100×30")
        self.assertEqual(marco.respiros(15), (0, 1), "60×24: solo el de abajo")
        self.assertEqual(marco.respiros(11), (0, 0))

    def test_demasiado_pequena(self):
        self.assertFalse(marco.demasiado_pequena(60, 24))
        self.assertTrue(marco.demasiado_pequena(59, 24))
        self.assertTrue(marco.demasiado_pequena(100, 23))

    def test_ventana_de_una_lista_con_sus_marcadores(self):
        self.assertEqual(marco.ventana(5, 0, 10), (range(5), 0, 0))
        filas, arriba, abajo = marco.ventana(30, 0, 10)
        self.assertEqual((filas, arriba, abajo), (range(0, 9), 0, 21), "al principio solo hay «más abajo»")
        filas, arriba, abajo = marco.ventana(30, 15, 10)
        self.assertEqual((len(filas) + 2, arriba, abajo), (10, filas.start, 30 - filas.stop), "en medio, los dos")
        self.assertIn(15, filas)
        filas, arriba, abajo = marco.ventana(30, 29, 10)
        self.assertEqual((filas, abajo), (range(21, 30), 0), "al final solo hay «más arriba»")

    def test_el_pie_deja_las_teclas_principales_y_mas(self):
        teclas = [("Enter", "Editar"), ("g", "Guardar"), ("Esc", "Volver"), ("?", "Ayuda"), ("t", "Tema")]

        def cabe(n):
            return lambda ts: sum(len(f"[{t}] {a}") + 3 for t, a in ts) <= n

        mas = ("?", "Más")
        self.assertEqual(marco.pie_que_cabe(teclas, cabe(200), mas), teclas)
        self.assertEqual(marco.pie_que_cabe(teclas, cabe(50), mas), [("Enter", "Editar"), ("g", "Guardar"), ("?", "Más")])
        sin_ayuda = [("Enter", "Aceptar"), ("Esc", "Cancelar")]
        self.assertEqual(marco.pie_que_cabe(sin_ayuda, cabe(20), mas), [("Enter", "Aceptar")], "sin «?» no se inventa «Más»")


class TestEstados(BaseTerminal):
    def test_vacio_y_error_son_una_linea_que_dice_que_hacer(self):
        t = self.terminal()
        [vacio] = estado_vacio(t, "terminal_sin_opciones")
        [error] = estado_error(t, "No se pudo leer.")
        self.assertEqual(vacio.plain, ayuda.linea("terminal_sin_opciones"))
        self.assertEqual(error.plain, "⚠ No se pudo leer.")


class TestSubpantallas(BaseTerminal):
    def test_lista_de_seleccion_elige_con_enter_con_numero_y_esc_no_cambia(self):
        elegido = []
        opciones = [("uno", 1), ("dos", 2), ("tres", 3)]

        def abrir(*guion):
            t = self.terminal(*guion)
            t.abrir(ListaSeleccion(t, "Lista", opciones, 2, elegido.append))
            return t

        _c, texto = abrir(ABAJO, ENTER, "q").run(), limpio(self.salida.getvalue())
        self.assertEqual(elegido, [3])
        self.assertIn("Inicio › Lista", texto)
        self.assertRegex(texto, r"2  dos  \(actual\)")
        self.assertRegex(texto, r"▶ 2  dos", "abre con la fila en lo actual")
        elegido.clear()
        abrir("1", "q").run()
        self.assertEqual(elegido, [1], "los números eligen directamente")
        elegido.clear()
        abrir(ABAJO, ESC, "q").run()
        self.assertEqual(elegido, [], "Esc vuelve sin cambiar")

    def test_confirmacion_en_una_linea_o_en_dos_si_no_cabe(self):
        filas = [("Palabras clave", "bloqueo, error", "bloqueo, error, demo"), ("Calidad", "Alta", "Media")]
        guardado = []
        t = self.terminal(ancho=100, alto=30)
        t.abrir(Confirmacion(t, filas, lambda: guardado.append(1), encabezado="Se guardará en config.json:"))
        t._refrescar_cabecera()
        ancha = [l.plain for l in t.marco()]
        self.assertTrue(any(l.startswith("    Calidad") and "Alta" in l and "→" in l for l in ancha), ancha[:12])
        angosta = self.terminal(ancho=60, alto=24)
        largas = [("Carpeta de notas", r"C:\Users\ana\Documents\Dailies", r"D:\Reuniones\Dailies"), *filas]
        angosta.abrir(Confirmacion(angosta, largas, lambda: None))
        angosta._refrescar_cabecera()
        lineas = [l.plain.strip() for l in angosta.marco()]
        self.assertIn("Calidad", lineas)
        self.assertIn("Alta → Media", lineas, "todas las filas pasan a dos líneas")

    def test_confirmacion_enter_confirma_y_esc_sigue_editando(self):
        guardado = []
        t = self.terminal(ENTER, "q")
        t.abrir(Confirmacion(t, [("A", "1", "2")], lambda: guardado.append("sí")))
        t.run()
        self.assertEqual(guardado, ["sí"])
        guardado.clear()
        t = self.terminal(ESC, "q")
        t.abrir(Confirmacion(t, [("A", "1", "2")], lambda: guardado.append("sí")))
        t.run()
        self.assertEqual(guardado, [])


class TestTerminalComoBase(BaseTerminal):
    def test_demasiado_pequena_solo_pinta_el_aviso_y_vuelve_sola_al_agrandar(self):
        t = self.terminal(ancho=50, alto=20)
        t._refrescar_cabecera()
        texto = " ".join(l.plain for l in t.marco())
        self.assertIn(ayuda.entrada("terminal_pequena")[0], texto)
        self.assertIn("60 columnas y 24 líneas", texto)
        self.assertNotIn("Grabar", texto)
        self.consola.size = (80, 24)
        self.assertIn("Grabar", " ".join(l.plain for l in t.marco()))

    def test_una_pantalla_se_abre_directa_y_esc_sale_a_la_terminal(self):
        t = self.terminal(ESC, inicial=Ayuda)
        self.assertEqual(t.run(), 0)
        self.assertEqual([p.titulo for p in t.pila], [], "sin Inicio debajo")
        texto = limpio(self.salida.getvalue())
        self.assertIn("Teclas de las pantallas", texto)
        self.assertNotIn("Grabar", texto)

    def test_una_pantalla_cierra_dejando_un_aviso_a_la_anterior(self):
        class Cierra(Ayuda):
            def tecla(self, k):
                if k == ENTER:
                    self.app.volver(("Hecho: de vuelta en el inicio.", "ok"))
                    return True
                return False

        t = self.terminal(ENTER, None, "q")
        t.abrir(Cierra(t))
        t.run()
        self.assertIn("Hecho: de vuelta en el inicio.", limpio(self.salida.getvalue()))
        self.assertEqual(t.aviso[0], "", "y dura hasta la siguiente tecla")

    def test_el_registro_abre_cada_pantalla_por_su_modulo(self):
        self.assertLessEqual({"ayuda", "config", "rendimiento"}, set(registro.PANTALLAS))  # y las que se vayan añadiendo
        t = self.terminal()
        for accion, clase in (("config", Opciones), ("rendimiento", Rendimiento), ("ayuda", Ayuda)):
            self.assertIs(registro.clase_de(accion), clase)
        self.assertEqual(registro.clase_de("recomendar").__name__, "Recomendacion")
        self.assertIsNone(registro.clase_de("grabar"), "lo que no es una pantalla se ejecuta fuera")
        self.assertIsNotNone(t)

    def test_la_cabecera_es_de_una_linea_fuera_de_inicio_y_hay_margen(self):
        t = self.terminal(ancho=100, alto=30)
        t._refrescar_cabecera()
        inicio = [l.plain for l in t.marco()]
        self.assertTrue(inicio[0].startswith(" Recorder · nota de hoy:") and inicio[2].startswith(" Equipo:"), inicio[:3])
        t.abrir(Ayuda(t))
        ayuda_ = [l.plain for l in t.marco()]
        self.assertTrue(ayuda_[0].startswith(" Recorder · aún no hay"), ayuda_[0])
        self.assertEqual(ayuda_[1], " " + "─" * 98 + " ", "regla a todo el ancho útil, con margen")
        self.assertEqual(ayuda_[2].strip(), "Inicio › Ayuda")

    def test_el_aviso_dura_hasta_la_siguiente_tecla_y_su_region_siempre_esta(self):
        t = self.terminal(ancho=100, alto=30)
        t._refrescar_cabecera()
        con = len(t.marco())
        t.avisar("✔ Algo salió bien.", "ok")
        self.assertEqual(len(t.marco()), con, "el aviso no cambia la altura del cuadro")
        self.assertTrue(any("Algo salió bien" in l.plain for l in t.marco()))


JUEGOS = (JUEGO_COMPLETO, JUEGO_CONSOLA, JUEGO_ASCII)


class TestSinRestos(BaseTerminal):
    """A 100×30 y a 60×24, en los tres juegos: nada se sale, el cuadro mide lo que la terminal y no deja restos."""

    def montar(self, juego, ancho, alto):
        with mock.patch.object(modulo_consola, "elegir_juego", return_value=juego):
            t = self.terminal(ancho=ancho, alto=alto, ascii_mode=None)
        self.assertEqual(t.juego, juego)
        t._refrescar_cabecera()
        t._entorno, t._hilo_entorno = ENTORNO, threading.Thread()  # sin detectar nada de verdad
        return t

    def comprobar(self, t, que):
        ancho, alto = t.consola.size
        lineas = t.marco()
        texto = "\n".join(l.plain for l in lineas)
        self.assertEqual(len(lineas), alto, f"{que}: la altura del cuadro")
        largas = [l.plain for l in lineas if cell_len(l.plain) != ancho]
        self.assertFalse(largas, f"{que}: {largas[:2]}")
        if t.juego == JUEGO_ASCII:
            fuera = {c for c in texto if ord(c) >= 0x2000 and c not in "–—"}
            self.assertEqual(fuera, set(), f"{que}: fuera de ASCII")
        if t.juego == JUEGO_CONSOLA:
            fuera = {c for c in texto if ord(c) >= 0x2000 and c not in SEGUROS_CONSOLA and c not in "–—"}
            self.assertEqual(fuera, set(), f"{que}: fuera de lo que dibuja Consolas")
        return texto

    def test_inicio_opciones_ayuda_y_rendimiento(self):
        for juego in JUEGOS:
            for ancho, alto in ((100, 30), (60, 24)):
                with self.subTest(juego=juego, ancho=ancho, alto=alto):
                    t = self.montar(juego, ancho, alto)
                    self.comprobar(t, "Inicio")
                    for clase in (Opciones, Ayuda, Rendimiento):
                        t.pila = t.pila[:1]
                        t.abrir(clase(t))
                        self.comprobar(t, clase.__name__)

    def test_opciones_editando_confirmando_y_con_lista_abierta(self):
        for juego in JUEGOS:
            for ancho, alto in ((100, 30), (60, 24)):
                with self.subTest(juego=juego, ancho=ancho, alto=alto):
                    t = self.montar(juego, ancho, alto)
                    t.abrir(Opciones(t))
                    t.marco()  # prepara el formulario
                    for k in (ABAJO, ABAJO, ENTER):  # a «Palabras clave» y a editarlas
                        t._tecla(k)
                    texto = self.comprobar(t, "editando")
                    self.assertIn(modulo_consola.presentar("▌", t.consola), texto)
                    for k in "x" * 90:  # un texto que no cabe: la ventana deslizante lo recorta
                        t._tecla(k)
                    self.comprobar(t, "texto largo")
                    t._tecla(ENTER)
                    for k in (ABAJO, ABAJO, ENTER):  # a «Salida a capturar» y su lista
                        t._tecla(k)
                    self.comprobar(t, "lista de selección")
                    t._tecla(ESC)
                    t._tecla("g")
                    texto = self.comprobar(t, "confirmación")
                    self.assertIn("Guardar", texto)

    def test_con_mas_filas_que_sitio_salen_los_marcadores_de_mas_arriba_y_mas_abajo(self):
        t = self.montar(JUEGO_CONSOLA, 60, 24)
        t.abrir(Opciones(t))
        texto = self.comprobar(t, "arriba del todo")
        self.assertIn("↓", texto)
        self.assertRegex(texto, r"↓ \d+ más abajo")
        self.assertNotIn("más arriba", texto)
        for _ in range(6):
            t._tecla(ABAJO)
        texto = self.comprobar(t, "en medio")
        self.assertRegex(texto, r"↑ \d+ más arriba")
        self.assertRegex(texto, r"↓ \d+ más abajo")
        t._tecla(FIN)
        texto = self.comprobar(t, "al final")
        self.assertRegex(texto, r"↑ \d+ más arriba")
        self.assertNotIn("más abajo", texto)

    def test_en_ascii_la_cabecera_corta_con_tres_puntos(self):
        t = self.montar(JUEGO_ASCII, 60, 24)
        t.abrir(Ayuda(t))
        primera = t.marco()[0].plain
        self.assertTrue(primera.rstrip().endswith("..."), primera)
        self.assertEqual(cell_len(primera), 60)


class TestOpcionesConComponentes(BaseTerminal):
    def entrar(self, *guion, **kwargs):
        return self.correr("2", self.opciones_listas, *guion, **kwargs)

    def test_enter_en_un_ajuste_de_lista_abre_la_lista_y_elige(self):
        antes = self.guardado()["mic_dev"]
        _c, texto = self.entrar(*["j"] * 5, ENTER, "2", "g", ENTER, "q", "q")
        self.assertIn("Inicio › Opciones › Micrófono", texto)
        self.assertIn(ayuda.linea("microfono")[:40], texto, "la lista explica lo que se elige")
        self.assertNotEqual(self.guardado()["mic_dev"], antes)
        self.assertEqual(self.guardado()["mic_dev"], "Micrófono")

    def test_esc_en_la_lista_vuelve_sin_cambiar(self):
        guardado = self.ruta.read_bytes()
        _c, _t = self.entrar(*["j"] * 5, ENTER, ABAJO, ESC, "g", "q", "q")
        self.assertEqual(self.ruta.read_bytes(), guardado)

    def test_el_cursor_se_mueve_en_un_texto_y_supr_borra(self):
        carpeta = str(self.notas)
        guion = [ENTER, INICIO, SUPR, DERECHA, "_", ENTER, "g", ENTER, "q", "q"]
        self.entrar(*guion, ancho=160)
        self.assertEqual(self.guardado()["notes_dir"], carpeta[1:2] + "_" + carpeta[2:], "borra la primera letra y pone «_» tras la segunda")

    def test_esc_en_un_texto_lo_deja_como_estaba(self):
        guardado = self.ruta.read_bytes()
        self.entrar(ENTER, "z", "z", ESC, "g", "q", "q")
        self.assertEqual(self.ruta.read_bytes(), guardado)

    def test_gpu_y_flash_attention_solo_con_carpeta_de_whispercpp(self):
        _c, sin = self.entrar("q", "q")
        self.assertNotIn("GPU de whisper.cpp", sin)
        self.assertNotIn("Flash attention", sin)
        guion = [*["j"] * 10, ENTER, *"C:/wcpp", ENTER, FIN]
        _c, con = self.entrar(*guion, "q", ESC, "q", ancho=100, alto=40)
        self.assertIn("Carpeta de whisper.cpp", con)
        self.assertIn("GPU de whisper.cpp", con)
        self.assertIn("Flash attention", con)

    def test_interruptor_con_espacio_y_hilos_automatico(self):
        _c, texto = self.entrar(*["j"] * 4, ESPACIO, "g", ENTER, "q", "q")
        self.assertIn("○ no", texto)
        _c, texto = self.entrar("q", "q", alto=40)
        self.assertIn("Hilos de CPU", texto)
        self.assertRegex(texto, r"Hilos de CPU +automático \(4\)")

    def test_el_pie_cambia_segun_el_tipo_de_fila(self):
        t = self.terminal(ancho=120)
        t._entorno, t._hilo_entorno = ENTORNO, threading.Thread()
        t.abrir(Opciones(t))
        t.marco()  # prepara el formulario
        opciones = t.pila[-1]
        esperado = {
            "texto": (0, ("Enter", "Editar")), "interruptor": (4, ("Espacio", "Cambiar")),
            "lista": (3, ("Enter", "Elegir de la lista")), "accion": (12, ("Enter", "Usar")),
        }
        for tipo, (fila, principal) in esperado.items():
            opciones.lista.sel = fila
            pie = opciones.teclas()
            self.assertEqual(pie[0], principal, tipo)
            self.assertEqual(("←→", "Cambiar") in pie, tipo in ("lista", "interruptor"), tipo)
            self.assertIn(("g", "Guardar"), pie)
        opciones.editando = CampoTexto("x")
        self.assertEqual(opciones.teclas(), [("←→", "Cursor"), ("Enter", "Aceptar"), ("Esc", "Cancelar")])

    def test_numero_de_filas_y_secciones(self):
        t = self.terminal(ancho=100, alto=40)
        t._refrescar_cabecera()
        t._entorno, t._hilo_entorno = ENTORNO, threading.Thread()
        t.abrir(Opciones(t))
        texto = "\n".join(l.plain for l in t.marco())
        for seccion in ("Carpetas", "Audio", "Capturas", "Calidad", "Apariencia"):
            self.assertIn(f"  {seccion}", texto)
        self.assertNotIn("🔊", texto)
        self.assertNotIn("🎤", texto)


if __name__ == "__main__":
    unittest.main()
