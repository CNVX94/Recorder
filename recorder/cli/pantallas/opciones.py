"""Opciones sobre la lógica de `daily config` (configurar.py y config/options.py): el mismo formulario, lo
mismo guardado y la misma tabla de cambios antes de guardar.

La lista de ajustes lleva rótulos de sección. Según el tipo de fila, Enter edita un texto (con cursor), abre la
lista de selección de un valor, alterna un sí o no o usa la recomendada; ←→ cambian el valor de una lista o un
interruptor y Espacio alterna este. «GPU de whisper.cpp» y «Flash attention» solo salen con carpeta de whisper.cpp.
"""
import dataclasses
import re
from typing import List, Optional, Sequence, Tuple

from ... import ayuda
from ...config.options import (
    MAX_THREADS,
    THEME_LABELS,
    capture_choices,
    device_choices,
    gpu_choices,
    quality_display,
    recommendation_text,
    settings_form,
    target_choices,
    use_recommendation,
)
from ...config.schema import CUSTOM_PRESET, PRESET_ORDER, QUALITY_PRESETS, recommend_config
from ...engine.whispercpp import vulkan_readiness, whispercpp_ready
from ...metricas import hilos_efectivos
from .. import configurar
from ..teclas import DERECHA, ENTER, ESC, ESPACIO, IZQUIERDA
from .base import Pantalla, pie
from .componentes import (
    CampoTexto, Confirmacion, Fila, Interruptor, ListaAjustes, ListaSeleccion, recortar_por_el_medio,
)

TEXTO, LISTA, INTERRUPTOR, ACCION = "texto", "lista", "interruptor", "accion"  # lo que hace Enter en cada fila
RECOMENDADA = "recomendada"  # la fila que no es un campo: aplica la recomendación
SIN_EMOJI = re.compile("\\s*[^\\x00-\\u1fff]+")


def etiqueta(clave: str) -> str:
    """El título de `clave` en recorder/ayuda.py sin los emoji de la ventana: las columnas miden lo mismo en los tres juegos."""
    return SIN_EMOJI.sub("", ayuda.entrada(clave)[0])


@dataclasses.dataclass
class Ajuste(Fila):
    """Una fila de Opciones: un campo de `SettingsForm`, su tipo y, para las de lista, (etiqueta, valor)."""

    campo: str = ""
    tipo: str = TEXTO
    opciones: Optional[List[Tuple[str, object]]] = None
    ruta: bool = False  # una carpeta: se recorta por el medio


class Opciones(Pantalla):
    titulo = "Opciones"

    def __init__(self, terminal):
        super().__init__(terminal)
        self.config = terminal.mgr.load()
        self.error = terminal.mgr.last_error  # ilegible: se ve y se edita, pero no se guarda
        self.entorno: Optional[configurar.Entorno] = None
        self.form = None
        self.lista = ListaAjustes([])
        self.editando: Optional[CampoTexto] = None  # el campo de texto, mientras se edita
        self.avisado = False  # ya se dijo que hay cambios sin guardar: el siguiente Esc sale

    @property
    def escribiendo(self) -> bool:
        return self.editando is not None

    @property
    def ajuste(self) -> Ajuste:
        return self.lista.actual

    def _preparado(self) -> bool:
        if self.form is None:
            self.entorno = self.app.entorno()
            if self.entorno is None:
                return False
            self.form = settings_form(self.config, self.entorno.screens)
            self._componer()
        return True

    def _componer(self) -> None:
        e, f, hw = self.entorno, self.form, self.entorno.hardware
        anterior = self.ajuste.campo if self.lista.filas else None

        def lista(valores: Sequence[str], actual: str) -> List[Tuple[str, object]]:
            valores = list(valores)
            opciones = [(v, v) for v in valores]
            if actual not in valores:  # lo guardado que ya no se detecta sigue elegible
                opciones.insert(min(1, len(opciones)), (f"{actual}  {ayuda.entrada('opciones_no_detectado')[0]}", actual))
            return opciones

        extra = QUALITY_PRESETS["extra"]
        vulkan_listo = whispercpp_ready(f.whispercpp_dir.strip(), extra.model, extra.compute_type)

        def a(campo, clave, tipo=TEXTO, opciones=None, seccion="", ruta=False, nombre=None):
            return Ajuste(etiqueta=nombre or etiqueta(clave), clave=clave, seccion=seccion, campo=campo, tipo=tipo, opciones=opciones, ruta=ruta)

        carpetas, audio, capturas, calidad, apariencia = (ayuda.entrada(f"opciones_{s}")[0] for s in (
            "carpetas", "audio", "capturas", "calidad", "apariencia"))
        ajustes = [
            a("notes_dir", "carpeta_notas", seccion=carpetas, ruta=True),
            a("caps_dir", "carpeta_capturas", ruta=True),
            a("keywords", "palabras_clave"),
            a("out_dev", "salida_audio", LISTA, lista(device_choices(e.out_devs), f.out_dev), seccion=audio),
            a("mic", "transcribir_mic", INTERRUPTOR),
            a("mic_dev", "microfono", LISTA, lista(device_choices(e.mic_devs), f.mic_dev)),
            a("target", "que_capturar", LISTA, lista(target_choices(e.screens, e.windows, self.config.window), f.target), seccion=capturas),
            a("captures", "capturas_clave", LISTA, lista(capture_choices(), f.captures)),
            a("quality", "calidad", LISTA, [
                (quality_display(k, hw.cuda_devices, vulkan_listo), k) for k in PRESET_ORDER + [CUSTOM_PRESET]
            ], seccion=calidad, nombre=calidad),
            a("cpu_threads", "hilos"),
            a("whispercpp_dir", "whispercpp", ruta=True),
        ]
        if f.whispercpp_dir.strip():  # sin esa carpeta, la GPU y flash attention no hacen nada
            ajustes += [
                a("whispercpp_device", "gpu", LISTA, list(gpu_choices(hw.vulkan_devices, self.config.whispercpp_device).items())),
                a("whispercpp_flash_attn", "flash", INTERRUPTOR),
            ]
        ajustes += [
            a(RECOMENDADA, "opciones_recomendada", ACCION),
            a("theme", "tema", LISTA, [(v, k) for k, v in THEME_LABELS.items()], seccion=apariencia),
        ]
        self.lista = ListaAjustes(ajustes, next((i for i, x in enumerate(ajustes) if x.campo == anterior), 0))

    # ------------------------------------------------------------ valores
    def _etiqueta_de(self, a: Ajuste) -> str:
        valor = getattr(self.form, a.campo)
        return next((e for e, v in a.opciones if v == valor), str(valor))

    def valor_texto(self, a: Ajuste, ancho: int) -> str:
        valor = getattr(self.form, a.campo)
        if a.campo == "cpu_threads" and valor.strip() in ("", "0"):
            return ayuda.entrada("opciones_hilos_auto")[0].format(n=hilos_efectivos(0))
        if not valor:
            return ayuda.entrada("terminal_vacio")[0]
        return recortar_por_el_medio(valor, ancho, self.app.elidido) if a.ruta else valor

    def partes_valor(self, a: Ajuste, elegida: bool, ancho: int):
        if a.tipo == ACCION:
            return []
        if elegida and self.editando is not None:
            return self.editando.partes(ancho, self.app.elidido)
        if a.tipo == INTERRUPTOR:
            return Interruptor(getattr(self.form, a.campo)).partes(self.app.juego)
        if a.tipo == LISTA:
            if elegida:
                return [("‹ ", "acento"), (self._etiqueta_de(a), "texto"), (" ›", "acento")]
            return [(self._etiqueta_de(a), "tenue")]
        return [(self.valor_texto(a, ancho), "texto" if elegida else "tenue")]

    def cambios(self) -> List[Tuple[str, str, str]]:
        if self.form is None:
            return []
        return configurar.diferencias(self.config, configurar.aplicado(self.config, self.form, self.entorno.screens))

    # ------------------------------------------------------------ pintar
    def marca(self):
        if self.cambios():
            return f"● {ayuda.entrada('terminal_marca_cambios')[0]}", "acento"
        return "", "tenue"

    def cuerpo(self, ancho, sitio):
        if not self._preparado():
            if self.app.error_entorno:
                return [self.app.t((self.app.error_entorno, "error"))], 0
            return [self.app.spinner(ayuda.linea("terminal_cargando").rstrip(".") + "…")], 0
        return self.lista.lineas(self.app, self.partes_valor, ancho, sitio)

    def ayuda(self):
        if self.form is None:
            return "", "tenue"
        if self.editando is not None:
            return ayuda.linea("opciones_editar"), "tenue"
        return ayuda.linea(self.ajuste.clave), "tenue"

    def teclas(self):
        if self.form is None:
            return pie(("Esc", "volver"))
        if self.editando is not None:
            return pie(("←→", "cursor"), ("Enter", "aceptar"), ("Esc", "cancelar"))
        tipo = self.ajuste.tipo
        principal = {TEXTO: ("Enter", "editar"), LISTA: ("Enter", "elegir_de_la_lista"),
                     INTERRUPTOR: ("Espacio", "cambiar"), ACCION: ("Enter", "usar")}[tipo]
        cambiar = [("←→", "cambiar")] if tipo in (LISTA, INTERRUPTOR) else []
        return pie(principal, ("g", "guardar"), ("Esc", "volver"), *cambiar, ("↑↓", "mover"), ("?", "ayuda"), ("t", "tema"))

    # ------------------------------------------------------------ teclas
    def tecla(self, k):
        if self.form is None:
            return False  # mientras detecta, solo se puede volver
        if self.editando is not None:
            if k == ENTER:
                self._aceptar()
            elif k == ESC:
                self.editando = None
            else:
                self.editando.tecla(k)
            return True
        if k not in (ESC, "q"):
            self.avisado = False  # tras el aviso se siguió trabajando: el próximo Esc vuelve a avisar
        a = self.ajuste
        if self.lista.tecla(k):
            pass
        elif k in (IZQUIERDA, DERECHA) and a.tipo == LISTA:
            self._cambiar(a, -1 if k == IZQUIERDA else 1)
        elif a.tipo == INTERRUPTOR and k in (IZQUIERDA, DERECHA, ESPACIO, ENTER):
            setattr(self.form, a.campo, not getattr(self.form, a.campo))
        elif k == ENTER:
            if a.tipo == ACCION:
                self._recomendada()
            elif a.tipo == LISTA:
                self._abrir_lista(a)
            else:
                self.editando = CampoTexto(getattr(self.form, a.campo))
        elif k == "g":
            self._pedir_guardar()
        elif k == "t":
            tema = self.app.alternar_tema()
            if not self.app.mgr.last_error:  # ya está en config.json: no es un cambio pendiente
                self.config.theme = self.form.theme = tema
        elif k in (ESC, "q") and self.cambios() and not self.avisado:
            self.avisado = True
            self.app.avisar(f"⚠ {ayuda.linea('terminal_sin_guardar')}", "error")
        else:
            return False
        return True

    def _cambiar(self, a: Ajuste, paso: int) -> None:
        valores = [v for _e, v in a.opciones]
        actual = getattr(self.form, a.campo)
        i = valores.index(actual) if actual in valores else -1
        setattr(self.form, a.campo, valores[(i + paso) % len(valores)])

    def _abrir_lista(self, a: Ajuste) -> None:
        self.app.abrir(ListaSeleccion(
            self.app, a.etiqueta, a.opciones, getattr(self.form, a.campo),
            lambda valor: setattr(self.form, a.campo, valor), clave_ayuda=a.clave,
        ))

    def _aceptar(self) -> None:
        a, texto = self.ajuste, self.editando.texto.strip()
        if a.campo == "cpu_threads" and not (texto.isdigit() and int(texto) <= MAX_THREADS):
            titulo, explicacion = ayuda.entrada("opciones_hilos_error")
            self.app.avisar(f"⚠ {titulo}: {explicacion.format(max=MAX_THREADS)}", "error")
            return
        setattr(self.form, a.campo, texto)
        self.editando = None
        if a.campo == "whispercpp_dir":
            self._componer()  # de la carpeta dependen la GPU, flash attention y que Extra esté disponible

    def _recomendada(self) -> None:
        rec = recommend_config(self.entorno.hardware, *vulkan_readiness(self.form.whispercpp_dir.strip()))
        use_recommendation(self.form, rec)
        self.app.avisar(recommendation_text(rec), "ok")
        self._componer()  # la recomendada puede cambiar la carpeta de whisper.cpp

    def _pedir_guardar(self) -> None:
        if self.error:
            self.app.avisar(f"⚠ No se guarda: {self.error}", "error")
        elif not self.cambios():
            self.app.avisar(ayuda.linea("terminal_sin_cambios"), "tenue")
        else:
            self.app.abrir(Confirmacion(
                self.app, self.cambios(), self._guardar, marca=self.marca(),
                encabezado=ayuda.linea("terminal_se_guardara").format(archivo=self.app.mgr.path.name).rstrip(".") + ":",
            ))

    def _guardar(self) -> None:
        nuevo = configurar.aplicado(self.config, self.form, self.entorno.screens)
        self.app.mgr.save(nuevo)
        self.config, self.form = nuevo, settings_form(nuevo, self.entorno.screens)
        self._componer()
        self.avisado = False
        self.app.poner_tema(nuevo.theme)
        self.app.avisar(f"✔ Guardado en {self.app.mgr.path}. {configurar.AVISO_REINICIO}", "ok")
