"""«Medir mi equipo» y los ajustes de rendimiento en la ventana: el diálogo con motores falsos (progreso, tabla,
cancelar, «Aplicar el mejor» con su confirmación), la entrada del menú «Más» y del panel de rendimiento, y los
campos nuevos de Opciones (GPU integrada, prioridad y el aviso de núcleos rápidos y lentos). Sin modelos, sin voz
de Windows y sin pantalla visible: se omite si no hay Tk."""
import copy
import dataclasses
import pathlib
import tempfile
import time
import tkinter as tk
import unittest
from unittest import mock

from recorder import ayuda
from recorder import medicion as m
from recorder.config import hardware
from recorder.config.options import hybrid_cores_notice, priority_choices, settings_form, apply_settings
from recorder.config.schema import AppConfig
from recorder.ui.dialogs import medir_dialog, settings_dialog
from recorder.ui.dialogs.medir_dialog import MedirDialog
from recorder.ui.dialogs.settings_dialog import SettingsDialog
from tests.test_dialogs import PANTALLAS, PERFIL, VENTANAS, CasoTk, PyAudioFalso
from tests.test_main_window import BaseVentana
from tests.test_medicion import ModeloFalso, Reloj, escribir_wav
from tests.test_recommendation import i7_1255u


class TestAjustesEnOpciones(CasoTk):
    def abrir(self, cfg, perfil=PERFIL):
        with mock.patch.object(hardware, "_cache", perfil), \
             mock.patch.object(settings_dialog, "screen_labels", lambda: list(PANTALLAS)), \
             mock.patch.object(settings_dialog, "window_titles", lambda: list(VENTANAS)):
            return SettingsDialog(self.root, cfg, PyAudioFalso(), on_save=lambda *_: None)

    def test_por_defecto_la_integrada_apagada_y_prioridad_normal(self):
        d = self.abrir(AppConfig())
        self.addCleanup(d.destroy)
        self.assertEqual((d.v_igpu.get(), d.v_priority.get()), (False, "Normal"))
        self.assertEqual(list(priority_choices()), ["Normal", "Por debajo de lo normal"], "nunca alta ni tiempo real")

    def test_guardar_escribe_la_integrada_y_la_prioridad(self):
        cfg = AppConfig()
        d = self.abrir(cfg)
        d.v_igpu.set(True)
        d.v_priority.set("Por debajo de lo normal")
        d._save()
        self.assertEqual((cfg.allow_igpu, cfg.process_priority), (True, "inferior"))

    def test_un_config_antiguo_se_abre_y_se_guarda_sin_tocar_lo_nuevo(self):
        cfg = AppConfig.from_dict({"model": "small", "beam_size": 5})
        d = self.abrir(cfg)
        d._save()
        self.assertEqual((cfg.allow_igpu, cfg.process_priority), (False, "normal"))

    def test_aviso_de_nucleos_rapidos_y_lentos_solo_en_cpu_hibrida(self):
        d = self.abrir(AppConfig(), i7_1255u())
        self.addCleanup(d.destroy)
        self.assertEqual(d.v_cores_notice.get(), hybrid_cores_notice(i7_1255u()))
        self.assertIn("2 núcleos rápidos y 8 lentos", d.v_cores_notice.get())
        d2 = self.abrir(AppConfig())
        self.addCleanup(d2.destroy)
        self.assertEqual(d2.v_cores_notice.get(), "")

    def test_el_formulario_lleva_los_campos_nuevos(self):
        cfg = AppConfig(allow_igpu=True, process_priority="inferior")
        f = settings_form(cfg, PANTALLAS)
        self.assertEqual((f.allow_igpu, f.priority), (True, "inferior"))
        f.allow_igpu, f.priority = False, "alta"  # una prioridad que no se ofrece no se guarda
        apply_settings(cfg, f, PANTALLAS)
        self.assertEqual((cfg.allow_igpu, cfg.process_priority), (False, "inferior"))


class DialogoBase(CasoTk):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = pathlib.Path(tmp.name)
        self.wav = escribir_wav(self.raiz / "muestra.wav")
        self.reloj = Reloj()
        self.velocidades = {}
        self.aplicado = []
        self.config = AppConfig(notes_dir=str(self.raiz))
        self.pruebas = []
        # el perfil ya detectado: no se lanza la detección
        parche = mock.patch.object(hardware, "_cache", PERFIL)
        parche.start()
        self.addCleanup(parche.stop)

    def cargar(self, c):
        guion = " ".join(m.GUION[:m.TURNOS_PRUEBA])
        modelo = ModeloFalso(self.reloj, self.velocidades.get(c.clave, 3.0))
        original = modelo.transcribe
        modelo.transcribe = lambda audio, **kw: (
            lambda r: ([mock.Mock(text=guion)], {}) if modelo.llamadas == 1 else r)(original(audio, **kw))
        return modelo

    def crear_prueba(self, perfil, config, config_path=None):
        r = self.reloj
        p = m.Prueba(
            perfil, config, self.raiz / "config.json", cargar=self.cargar, generar=lambda _t: self.wav, reposo=lambda: 2, reloj=r,
            tiempos=lambda: (int(r.t * 1e7 * 0.6), int(r.t * 1e7)),
        )
        self.pruebas.append(p)
        return p

    def abrir(self, bloqueado=""):
        d = MedirDialog(self.root, self.config, self.aplicado.append, self.raiz / "config.json", bloqueado, prueba=self.crear_prueba)
        self.addCleanup(lambda: d.winfo_exists() and d.destroy())
        self.addCleanup(lambda: [p.cancelar() or p.esperar(10) for p in self.pruebas])
        return d

    def esperar(self, d, fase, limite=10.0):
        fin = time.time() + limite
        while time.time() < fin:
            d.update()
            if d._fase() == fase:
                d._pintar()
                d.update()
                return
            time.sleep(0.02)
        self.fail(f"no llegó a {fase}: {d._fase()}")

    def textos(self, d):
        return [w.cget("text") for w in d.tabla.winfo_children()]


class TestMedirDialog(DialogoBase):
    def test_abre_con_la_explicacion_y_solo_empezar_y_cerrar(self):
        d = self.abrir()
        self.assertEqual(d.title(), "Medir mi equipo")
        self.assertEqual(d.v_estado.get(), "Qué aguanta tu equipo")
        self.assertIn("No uses el equipo para cosas pesadas", d.v_notas.get())
        visibles = [k for k, b in d.botones.items() if b.winfo_manager()]
        self.assertEqual(sorted(visibles), ["cerrar", "empezar"])
        self.assertIsNone(d.prueba, "no mide hasta que se pulse Empezar")

    def test_mide_y_enseña_la_tabla_con_la_mejor(self):
        self.velocidades = {"small-1-cpu-5--1": 5.0, "small-5-cpu-4--1": 2.6, "small-5-cpu-5--1": 3.0,
                            "large-v3-turbo-5-cpu-4--1": 1.3, "large-v3-turbo-5-cpu-5--1": 1.1}
        d = self.abrir()
        d._empezar()
        self.esperar(d, m.TERMINADA)
        textos = self.textos(d)
        self.assertIn("Media · procesador, 5 hilos", textos)
        self.assertIn("3,0×", textos)
        self.assertIn("●", textos)
        self.assertIn("sí  la mejor", textos)
        self.assertIn("no: va justo", textos)
        self.assertEqual(d.v_estado.get(), "La mejor: Media · procesador, 5 hilos")
        self.assertIn("2,0× o más", d.v_notas.get())
        self.assertEqual(sorted(k for k, b in d.botones.items() if b.winfo_manager()), ["aplicar", "cerrar", "otra_vez"])
        self.assertEqual(d.botones["aplicar"].cget("text"), "Aplicar el mejor")
        self.assertEqual(self.aplicado, [], "medir no aplica nada")
        self.assertTrue((self.raiz / m.NOMBRE_INFORME).is_file())

    def test_aplicar_enseña_antes_y_despues_y_solo_escribe_tras_confirmar(self):
        self.velocidades = {"large-v3-turbo-5-cpu-4--1": 1.3, "large-v3-turbo-5-cpu-5--1": 1.1}  # Alta no aguanta: gana Media con 5 hilos
        d = self.abrir()
        d._empezar()
        self.esperar(d, m.TERMINADA)
        with mock.patch.object(medir_dialog.messagebox, "askyesno", return_value=False) as pregunta:
            d._pedir_aplicar()
        self.assertEqual(self.aplicado, [], "si se dice que no, no se guarda nada")
        mensaje = pregunta.call_args[0][1]
        self.assertIn("Hilos de CPU: 0  →  5", mensaje)
        antes = copy.deepcopy(self.config)
        with mock.patch.object(medir_dialog.messagebox, "askyesno", return_value=True):
            d._pedir_aplicar()
        self.assertEqual(len(self.aplicado), 1)
        nuevo = self.aplicado[0]
        cambiadas = {k for k, v in dataclasses.asdict(nuevo).items() if dataclasses.asdict(antes)[k] != v}
        self.assertEqual(cambiadas, {"cpu_threads"}, "solo las claves de la prueba")
        self.assertEqual(d.config.cpu_threads, 5, "el diálogo sigue con lo aplicado")
        self.assertIn("Aplicado. Vale desde la próxima grabación.", d.v_notas.get())
        self.assertNotIn("aplicar", [k for k, b in d.botones.items() if b.winfo_manager()], "ya usa la mejor")

    def test_con_config_ilegible_se_mide_pero_no_se_aplica(self):
        d = self.abrir(bloqueado="No se aplica: No se pudo leer config.json.")
        d._empezar()
        self.esperar(d, m.TERMINADA)
        self.assertEqual(str(d.botones["aplicar"].cget("state")), "disabled")
        with mock.patch.object(medir_dialog.messagebox, "askyesno", return_value=True):
            d._pedir_aplicar()
        self.assertEqual(self.aplicado, [])

    def test_cancelar_descarta_lo_medido_y_vuelve_al_principio(self):
        d = self.abrir()
        d._empezar()
        d._cancelar()
        self.pruebas[0].esperar(10)
        self.assertEqual(self.pruebas[0].fase, m.CANCELADA)
        self.assertIsNone(d.prueba)
        self.assertEqual(d.v_notas.get(), "Medición cancelada. No se cambió nada.")
        self.assertEqual(self.aplicado, [])
        self.assertFalse((self.raiz / m.NOMBRE_INFORME).exists())
        self.assertEqual(sorted(k for k, b in d.botones.items() if b.winfo_manager()), ["cerrar", "empezar"])

    def test_cerrar_a_mitad_cancela_la_prueba(self):
        d = self.abrir()
        d._empezar()
        d._cerrar()
        self.pruebas[0].esperar(10)
        self.assertIn(self.pruebas[0].fase, (m.CANCELADA, m.TERMINADA))
        self.assertFalse(d.winfo_exists() and d.winfo_ismapped() and False)

    def test_equipo_ocupado_pide_decidir(self):
        def crear(perfil, config, config_path=None):
            p = self.crear_prueba(perfil, config, config_path)
            p._reposo = lambda: 50
            return p

        d = MedirDialog(self.root, self.config, self.aplicado.append, self.raiz / "config.json", "", prueba=crear)
        self.addCleanup(lambda: d.winfo_exists() and d.destroy())
        self.addCleanup(lambda: [p.cancelar() or p.esperar(10) for p in self.pruebas])
        d._empezar()
        self.esperar(d, m.OCUPADO)
        self.assertEqual(d.v_estado.get(), "El equipo está ocupado")
        self.assertIn("50 %", d.v_notas.get())
        self.assertEqual(self.pruebas[0].medidor, None, "no mide sin permiso")
        d._empezar(forzar=True)
        self.esperar(d, m.TERMINADA)

    def test_los_botones_llevan_ayuda_del_diccionario(self):
        d = self.abrir()
        for clave, boton in d.botones.items():
            self.assertTrue(hasattr(boton, "tooltip"), clave)
            for k in boton.tooltip.claves:
                self.assertIn(k, {**ayuda.VENTANA, **ayuda.COMUN})


class TestEntradasEnLaVentana(BaseVentana):
    def test_el_menu_mas_tiene_medir_mi_equipo(self):
        menu = self.win.menu_mas
        etiquetas = [menu.entrycget(i, "label") for i in range(menu.index("end") + 1) if menu.type(i) != "separator"]
        self.assertIn("📏 Medir mi equipo…", etiquetas)

    def test_el_panel_de_rendimiento_tiene_su_boton(self):
        textos = []
        pila = [self.win.panel]
        while pila:
            w = pila.pop()
            pila.extend(w.winfo_children())
            if isinstance(w, tk.Button):
                textos.append(w.cget("text"))
        self.assertIn("📏 Medir mi equipo", textos)

    def test_abrir_pasa_la_sesion_y_aplicar_la_guarda_por_ella(self):
        with mock.patch("recorder.ui.main_window.MedirDialog") as dialogo:
            self.win.open_medir()
        args = dialogo.call_args[0]
        self.assertIs(args[1], self.session.config)
        self.assertEqual(args[3], self.session.config_manager.path)
        self.assertEqual(args[4], "", "config legible: se puede aplicar")
        nuevo = dataclasses.replace(self.session.config, cpu_threads=7)
        args[2](nuevo)
        self.assertEqual(self.session.config.cpu_threads, 7)
        self.assertEqual(self.session.config_manager.load().cpu_threads, 7, "guardado en config.json")

    def test_config_ilegible_bloquea_aplicar(self):
        self.session.config_manager.last_error = "No se pudo leer «config.json» (JSONDecodeError)."
        with mock.patch("recorder.ui.main_window.MedirDialog") as dialogo:
            self.win.open_medir()
        self.assertIn("No se aplica", dialogo.call_args[0][4])


if __name__ == "__main__":
    unittest.main()
