"""Diálogo «Medir mi equipo»: la misma prueba que la pantalla de la terminal (recorder/medicion.py).

Prueba unas cuantas configuraciones con una muestra de voz corta (2 o 3 minutos), con barra de progreso y botón
Cancelar, y enseña una tabla: velocidad (veces el habla), procesador usado y si aguanta dos fuentes a la vez
(>= 2,0x). «Aplicar el mejor» enseña qué cambia («antes → después»), pide confirmación y solo entonces escribe,
y solo las claves de esa prueba. Nada cambia sin esa confirmación; cancelar descarta lo medido.
"""
import copy
import threading
import tkinter as tk
from tkinter import messagebox
from typing import Callable, List, Optional, Tuple

from ... import ayuda
from ...config.hardware import HardwareProfile, cached_hardware, peek_hardware
from ...config.schema import AppConfig
from ...medicion import (
    EN_CURSO, EN_ESPERA, ERROR, FALLO, LISTA, MIDIENDO, OCUPADO, OMITIDA, PREPARANDO, TERMINADA,
    Instantanea, Prueba, Resultado, aplicar_candidato, candidato_actual, elegir_mejor, formato_fecha,
)
from ..animacion import cerrar
from ..theme import BTN_STYLE, HEADER_STYLE, LABEL_STYLE, P, fit_window
from ..tooltip import con_ayuda

SONDEO_MS = 300  # cada cuánto se repinta mientras mide
ANCHO_BARRA, ALTO_BARRA = 520, 14  # a 100 % de escala
REDONDEO_S = 5  # lo que queda se redondea a este paso para que no baile cada segundo
ANCHO_VENTANA, ALTO_VENTANA = 720, 520
PREFIJO = "medir_"


def _tiempo(segundos: float) -> str:
    s = int(round(segundos / REDONDEO_S) * REDONDEO_S)
    if s >= 60:
        return ayuda.entrada(PREFIJO + "tiempo")[0].format(m=s // 60, s=s % 60)
    return ayuda.entrada(PREFIJO + "tiempo_s")[0].format(s=s)


def _veces(velocidad: float) -> str:
    return f"{velocidad:.1f}×".replace(".", ",")


class MedirDialog(tk.Toplevel):
    """Mide el equipo y deja aplicar la mejor configuración. `al_aplicar(config)` guarda el config nuevo
    (la ventana principal lo pasa a la sesión); `config` es el de la sesión, que no se toca aquí."""

    def __init__(
        self, parent: tk.Widget, config: AppConfig, al_aplicar: Callable[[AppConfig], None],
        config_path=None, bloqueado: str = "", prueba: Optional[Callable[..., Prueba]] = None,
    ):
        super().__init__(parent)
        self.config, self.al_aplicar, self.config_path, self.bloqueado = config, al_aplicar, config_path, bloqueado
        self._crear_prueba = prueba or Prueba
        self.prueba: Optional[Prueba] = None
        self.perfil: Optional[HardwareProfile] = peek_hardware()
        self._firma: Tuple = ()
        self._sondeo = None

        self.title(ayuda.entrada("rendimiento_medir")[0])
        self.configure(bg=P.fondo)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        self.bind("<Escape>", lambda _e: self._cerrar())
        self._build_ui()
        self._pintar()
        fit_window(self, ANCHO_VENTANA, ALTO_VENTANA)
        if self.perfil is None:
            threading.Thread(target=cached_hardware, daemon=True, name="equipo").start()
        self._sondeo = self.after(SONDEO_MS, self._sondear)

    # ------------------------------------------------------------------ construcción
    def _build_ui(self):
        titulo, explicacion = ayuda.entrada("medir_intro")
        tk.Label(self, text="📏 " + ayuda.entrada("rendimiento_medir")[0], **HEADER_STYLE).pack(anchor="w", padx=16, pady=(14, 2))
        self.lbl_intro = tk.Label(self, text=explicacion, wraplength=int(ANCHO_VENTANA - 40), justify="left", anchor="w", **LABEL_STYLE)
        self.lbl_intro.pack(fill="x", padx=16, pady=(0, 8))

        self.v_estado = tk.StringVar()
        self.lbl_estado = tk.Label(self, textvariable=self.v_estado, bg=P.fondo, fg=P.texto, font=("Segoe UI Semibold", 10), anchor="w")
        self.lbl_estado.pack(fill="x", padx=16)
        self.barra = tk.Canvas(self, height=ALTO_BARRA, bg=P.superficie, highlightthickness=0)
        self.barra.pack(fill="x", padx=16, pady=(4, 4))
        self.v_queda = tk.StringVar()
        tk.Label(self, textvariable=self.v_queda, **LABEL_STYLE).pack(fill="x", padx=16)

        self.tabla = tk.Frame(self, bg=P.fondo)
        self.tabla.pack(fill="x", padx=16, pady=(10, 4))
        self.v_notas = tk.StringVar()
        self.lbl_notas = tk.Label(self, textvariable=self.v_notas, wraplength=int(ANCHO_VENTANA - 40), justify="left", anchor="w", **LABEL_STYLE)
        self.lbl_notas.pack(fill="x", padx=16, pady=(4, 0))

        self.botonera = tk.Frame(self, bg=P.fondo)
        self.botonera.pack(side="bottom", fill="x", padx=16, pady=12)
        self.botones: dict = {}
        for clave, clave_ayuda, comando in (
            ("cerrar", "medir_cerrar", self._cerrar),
            ("otra_vez", "medir_otra_vez", self._otra_vez),
            ("aplicar", "medir_aplicar", self._pedir_aplicar),
            ("igual", "medir_igual", lambda: self._empezar(forzar=True)),
            ("cancelar", "medir_cancelar", self._cancelar),
            ("empezar", "medir_empezar", self._empezar),
        ):
            self.botones[clave] = con_ayuda(tk.Button(self.botonera, text="", command=comando, **BTN_STYLE), clave_ayuda)

    # ------------------------------------------------------------------ estado
    def _fase(self) -> str:
        return self.prueba.fase if self.prueba else ""

    def _empezar(self, forzar: bool = False) -> None:
        if self.perfil is None:
            return
        if self.prueba is None:
            self.prueba = self._crear_prueba(self.perfil, self.config, self.config_path)
        self.prueba.iniciar(forzar=forzar)
        self._firma = ()
        self._pintar()

    def _otra_vez(self) -> None:
        self.prueba = None
        self._empezar()

    def _cancelar(self) -> None:
        """Para la medición y descarta lo medido; el diálogo vuelve al principio sin cambiar nada."""
        if self.prueba is not None:
            self.prueba.cancelar()
        self.prueba = None
        self.v_notas.set(ayuda.linea(PREFIJO + "cancelada"))
        self._firma = ()
        self._pintar()

    def _cerrar(self) -> None:
        if self.prueba is not None and self._fase() in (PREPARANDO, OCUPADO, EN_CURSO):
            self.prueba.cancelar()
        if self._sondeo is not None:
            self.after_cancel(self._sondeo)
            self._sondeo = None
        cerrar(self)

    # ------------------------------------------------------------------ pintar
    def _sondear(self) -> None:
        self._sondeo = None
        if not self.winfo_exists():
            return
        if self.perfil is None:
            self.perfil = peek_hardware()
            if self.perfil is not None:
                self._pintar()
        elif self.prueba is not None:
            self._pintar()
        self._sondeo = self.after(SONDEO_MS, self._sondear)

    def _mejor(self, inst: Instantanea) -> Tuple[Optional[Resultado], bool]:
        return elegir_mejor(inst.resultados)

    def _texto_fila(self, r: Resultado, corta: bool = False) -> Tuple[str, str, str, str, str]:
        """(marca, prueba, velocidad, procesador, dos fuentes) de una fila, y el color de la última sale de `veredicto`."""
        marca = {LISTA: "✔", MIDIENDO: "•", OMITIDA: "–", FALLO: "–"}.get(r.estado, " ")
        velocidad = _veces(r.velocidad) if r.estado == LISTA and r.velocidad is not None else ""
        if r.estado in (EN_ESPERA, MIDIENDO):
            velocidad = ayuda.entrada(PREFIJO + ("midiendo" if r.estado == MIDIENDO else "en_espera"))[0]
        cpu = f"{r.cpu_pct:.0f} %" if r.estado == LISTA and r.cpu_pct is not None else ""
        if r.estado == OMITIDA:
            dos = ayuda.entrada(PREFIJO + "omitida_" + r.motivo)[0]
        elif r.estado == FALLO:
            dos = ayuda.entrada(PREFIJO + "fallo")[0]
        elif r.estado == LISTA:
            dos = ayuda.entrada(PREFIJO + {"si": "si", "justo": "no_justo", "atrasa": "no_atrasa", "mal": "mal"}[r.veredicto])[0]
        else:
            dos = ""
        return marca, r.candidato.etiqueta(corta), velocidad, cpu, dos

    def _color(self, r: Resultado) -> str:
        if r.estado == FALLO:
            return P.error
        if r.estado != LISTA:
            return P.texto_tenue
        return {"si": P.ok, "justo": P.aviso, "atrasa": P.error, "mal": P.error}[r.veredicto]

    def _pintar(self) -> None:
        """Pone lo que corresponde a la fase de ahora: texto, barra, tabla y botones. Solo repinta si algo cambió."""
        inst = self.prueba.instantanea() if self.prueba else None
        fase = self._fase()
        mejor, dos = self._mejor(inst) if inst else (None, False)
        firma = (
            fase, self.perfil is not None, self.bloqueado,
            tuple((r.estado, r.velocidad, r.cpu_pct, r.motivo) for r in inst.resultados) if inst else (),
            inst.actual if inst else -1, round(inst.progreso, 2) if inst else 0,
            None if inst is None or inst.queda_s is None else round(inst.queda_s / REDONDEO_S),
        )
        if firma == self._firma:
            return
        self._firma = firma
        self._pintar_barra(inst.progreso if inst else 0.0)
        self._pintar_texto(inst, fase, mejor, dos)
        self._pintar_tabla(inst, mejor if fase == TERMINADA else None)
        self._pintar_botones(fase, mejor, dos)

    def _pintar_barra(self, progreso: float) -> None:
        self.barra.delete("all")
        ancho = self.barra.winfo_width() if self.barra.winfo_width() > 10 else int(ANCHO_BARRA)
        self.barra.configure(bg=P.superficie)
        if progreso > 0:
            self.barra.create_rectangle(0, 0, int(ancho * progreso), ALTO_BARRA * 4, fill=P.acento, width=0)

    def _pintar_texto(self, inst: Optional[Instantanea], fase: str, mejor: Optional[Resultado], dos: bool) -> None:
        notas, color = "", P.texto_tenue
        queda = ""
        if self.perfil is None and not fase:
            estado = ayuda.linea("terminal_detectando_equipo").rstrip(".") + "…"
        elif not fase:
            estado = ayuda.entrada(PREFIJO + "intro")[0]
            notas = self.v_notas.get() or self.bloqueado or ayuda.entrada(PREFIJO + "consejo")[1]
        elif fase == PREPARANDO:
            estado = ayuda.entrada(PREFIJO + "preparando")[0] + "…"
            notas = ayuda.linea(PREFIJO + "preparando")
        elif fase == OCUPADO:
            titulo, explicacion = ayuda.entrada(PREFIJO + "ocupado")
            estado, notas, color = titulo, explicacion.format(n=inst.reposo_pct), P.aviso
        elif fase == ERROR:
            estado, notas, color = ayuda.entrada(PREFIJO + "error")[0], self.prueba.error, P.error
        elif fase == EN_CURSO:
            n = len(inst.resultados)
            estado = ayuda.entrada(PREFIJO + "progreso")[0].format(i=max(1, inst.actual + 1), n=n)
            if inst.actual >= 0:
                estado += ": " + inst.resultados[inst.actual].candidato.etiqueta()
            if inst.queda_s is not None:
                queda = ayuda.entrada(PREFIJO + "queda")[0].format(tiempo=_tiempo(inst.queda_s))
            notas = ayuda.entrada(PREFIJO + "consejo")[1]
        else:  # TERMINADA
            estado = ayuda.entrada(PREFIJO + "mejor")[0].capitalize() + (f": {mejor.candidato.etiqueta()}" if mejor else "")
            titulo, explicacion = ayuda.entrada(PREFIJO + "col_dos")
            notas = f"{titulo} {explicacion}"
            if not dos:
                notas += f" {ayuda.entrada(PREFIJO + 'ninguna')[0]}. {ayuda.entrada(PREFIJO + 'ninguna')[1]}"
            if self.prueba.igpu_sin_permiso:
                notas += f" {ayuda.entrada(PREFIJO + 'igpu_apagada')[0]}. {ayuda.entrada(PREFIJO + 'igpu_apagada')[1]}"
            if self.prueba.informe is not None:
                notas += " " + ayuda.entrada(PREFIJO + "fecha")[0].format(fecha=formato_fecha(self.prueba.informe.fecha)) + "."
            if self.bloqueado:
                notas += " " + self.bloqueado
        self.v_estado.set(estado)
        self.v_queda.set(queda)
        self.v_notas.set(notas)
        self.lbl_notas.configure(fg=color)

    def _pintar_tabla(self, inst: Optional[Instantanea], mejor: Optional[Resultado]) -> None:
        for w in self.tabla.winfo_children():
            w.destroy()
        if inst is None or not inst.resultados:
            return
        cabeceras = ("", *(ayuda.entrada(PREFIJO + c)[0] for c in ("col_prueba", "col_velocidad", "col_cpu", "col_dos")))
        for j, texto in enumerate(cabeceras):
            tk.Label(self.tabla, text=texto, bg=P.fondo, fg=P.texto_tenue, font=("Segoe UI", 9), anchor="w").grid(row=0, column=j, sticky="w", padx=(0, 14))
        for i, r in enumerate(inst.resultados, start=1):
            marca, etiqueta, velocidad, cpu, dos = self._texto_fila(r)
            es_mejor = mejor is not None and r.candidato.clave == mejor.candidato.clave
            if es_mejor:
                marca, dos = "●", f"{dos}  {ayuda.entrada(PREFIJO + 'mejor')[0]}"
            color = self._color(r)
            for j, (texto, fg) in enumerate(((marca, P.acento if es_mejor else P.ok if marca == "✔" else P.texto_tenue),
                                             (etiqueta, P.texto if r.estado != EN_ESPERA else P.texto_tenue),
                                             (velocidad, color), (cpu, P.texto), (dos, color))):
                tk.Label(
                    self.tabla, text=texto, bg=P.fondo, fg=fg, anchor="w",
                    font=("Segoe UI Semibold", 10) if es_mejor and j in (1, 2) else ("Segoe UI", 10),
                ).grid(row=i, column=j, sticky="w", padx=(0, 14), pady=1)

    def _pintar_botones(self, fase: str, mejor: Optional[Resultado], dos: bool) -> None:
        for b in self.botones.values():
            b.pack_forget()
        visibles: List[str] = []
        if not fase:
            visibles = ["empezar"]
        elif fase in (PREPARANDO, EN_CURSO):
            visibles = ["cancelar"]
        elif fase == OCUPADO:
            visibles = ["igual", "otra_vez"]
        elif fase == ERROR:
            visibles = ["otra_vez"]
        elif fase == TERMINADA:
            visibles = ["otra_vez"]
            if mejor is not None and not candidato_actual(self.config, mejor.candidato):
                visibles.insert(0, "aplicar")
        visibles.append("cerrar")
        textos = {
            "empezar": ayuda.entrada(PREFIJO + "empezar")[0], "cancelar": ayuda.entrada(PREFIJO + "cancelar")[0],
            "igual": ayuda.entrada(PREFIJO + "igual")[0], "otra_vez": ayuda.entrada(PREFIJO + "otra_vez")[0],
            "aplicar": ayuda.entrada(PREFIJO + ("aplicar" if dos else "aplicar_rapida"))[0],
            "cerrar": ayuda.entrada(PREFIJO + "cerrar")[0],
        }
        for clave in visibles:
            b = self.botones[clave]
            b.configure(text=textos[clave], state="disabled" if clave == "aplicar" and self.bloqueado else "normal")
            b.pack(side="right", padx=(8, 0))
        if "empezar" in visibles and self.perfil is None:
            self.botones["empezar"].configure(state="disabled")

    # ------------------------------------------------------------------ aplicar
    def _pedir_aplicar(self) -> None:
        """Enseña qué cambia («antes → después») y, si se confirma, guarda solo lo de la mejor prueba."""
        from ...cli.configurar import diferencias  # la misma tabla de cambios que la terminal

        mejor, _dos = self._mejor(self.prueba.instantanea())
        if mejor is None or self.bloqueado:
            return
        nuevo = copy.deepcopy(self.config)
        aplicar_candidato(nuevo, mejor.candidato)
        cambios = diferencias(self.config, nuevo)
        if not cambios:
            messagebox.showinfo(ayuda.entrada(PREFIJO + "ya")[0], ayuda.linea(PREFIJO + "ya"), parent=self)
            return
        lineas = "\n".join(f"{etiqueta}: {antes}  →  {despues}" for etiqueta, antes, despues in cambios)
        if not messagebox.askyesno(ayuda.entrada(PREFIJO + "aplicar")[0], f"{mejor.candidato.etiqueta()}\n\n{lineas}", parent=self):
            return
        self.al_aplicar(nuevo)
        self.config = nuevo
        self._firma = ()
        self.v_notas.set(ayuda.linea(PREFIJO + "aplicado"))
        self._pintar()
        self.v_notas.set(ayuda.linea(PREFIJO + "aplicado"))
