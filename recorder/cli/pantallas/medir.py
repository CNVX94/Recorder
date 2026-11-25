"""Medir mi equipo: una prueba corta (2 o 3 minutos) de qué configuración aguanta este equipo, con su progreso
cancelable, la tabla de resultados y «Aplicar el mejor» con su confirmación «antes → después»
(docs/terminal-especificacion.md, sección 7.7). La lógica de la medición está en `recorder/medicion.py` y es la
misma que usa la ventana; aquí solo se pinta y se atienden las teclas.

Mientras prepara y mide solo vale Esc (cancela y no cambia nada). Con el equipo ocupado, la prueba no empieza
sin que se diga («Medir de todos modos»). Al terminar, la mejor queda marcada y Enter abre la confirmación; solo
tras ella se escribe config.json, y solo las claves de esa prueba (`medicion.aplicar_candidato`).
"""
import copy
import threading
from typing import List, Optional, Tuple

from rich.cells import cell_len
from rich.text import Text

from ... import ayuda
from ...config.hardware import cached_hardware, peek_hardware
from ...medicion import (
    EN_CURSO, EN_ESPERA, ERROR, FALLO, LISTA, MIDIENDO, OCUPADO, OMITIDA, PREPARANDO, TERMINADA,
    Instantanea, Prueba, Resultado, aplicar_candidato, candidato_actual, elegir_mejor, formato_fecha,
)
from .. import configurar
from ..consola import fotograma
from ..teclas import ABAJO, ARRIBA, ENTER, ESC
from .base import Pantalla, barra, pie
from .componentes import Confirmacion, estado_error

SANGRIA = 2  # columnas antes de cada línea del cuerpo
MARCA = 3  # columnas de la marca de cada prueba («✔», «●», «•»)
HUECO = 2  # entre las columnas de la tabla
CELDAS_BARRA = 40  # ancho máximo de la barra de progreso
CELDAS_BARRA_MIN = 10
REDONDEO_S = 5  # el «queda… aprox.» se redondea a este paso para que no baile cada segundo
ANCHO_COMPLETO = 76  # de ancho útil; por debajo, cabeceras y rótulos cortos y «la mejor» solo como ●
APLICAR, OTRA_VEZ, DE_TODOS_MODOS = "aplicar", "otra_vez", "de_todos_modos"  # lo que puede hacer Enter
PREFIJO = "medir_"


# ------------------------------------------------------------------ lógica pura
def tiempo(segundos: float) -> str:
    """90 → «1 min 30 s»; 45 → «45 s». Redondeado a REDONDEO_S."""
    s = int(round(segundos / REDONDEO_S) * REDONDEO_S)
    if s >= 60:
        return ayuda.entrada(PREFIJO + "tiempo")[0].format(m=s // 60, s=s % 60)
    return ayuda.entrada(PREFIJO + "tiempo_s")[0].format(s=s)


def veces(velocidad: float) -> str:
    """2.6 → «2,6×»."""
    return f"{velocidad:.1f}×".replace(".", ",")


def columna_dos_fuentes(r: Resultado) -> Tuple[str, str]:
    """(texto, estilo) de «¿Dos fuentes?» de una fila: sí, no con su porqué, o lo que le pasó a la prueba."""
    if r.estado in (EN_ESPERA, MIDIENDO):
        return "", "tenue"  # «en espera» y «midiendo…» van en la columna de velocidad
    if r.estado == OMITIDA:
        return ayuda.entrada(PREFIJO + "omitida_" + r.motivo)[0], "tenue"
    if r.estado == FALLO:
        return ayuda.entrada(PREFIJO + "fallo")[0], "error"
    return {
        "si": (ayuda.entrada(PREFIJO + "si")[0], "ok"),
        "justo": (ayuda.entrada(PREFIJO + "no_justo")[0], "aviso"),
        "atrasa": (ayuda.entrada(PREFIJO + "no_atrasa")[0], "error"),
        "mal": (ayuda.entrada(PREFIJO + "mal")[0], "error"),
    }[r.veredicto]


# ------------------------------------------------------------------ la pantalla
class Medir(Pantalla):
    titulo = ayuda.entrada("rendimiento_medir")[0]

    def __init__(self, terminal):
        super().__init__(terminal)
        self.prueba: Optional[Prueba] = None
        self.perfil = None
        self.sel = 0  # la fila de acción elegida (resultados, equipo ocupado o error)
        if peek_hardware() is None:  # el cerrojo de cached_hardware evita detectar dos veces
            threading.Thread(target=cached_hardware, daemon=True, name="equipo").start()

    # ------------------------------------------------------------ estado
    def _nueva_prueba(self) -> Prueba:
        return Prueba(self.perfil, self.app.config, self.app.mgr.path)

    def _preparar(self) -> bool:
        """True cuando el equipo está detectado y la prueba en marcha (la crea una sola vez)."""
        if self.prueba is None:
            self.perfil = peek_hardware()
            if self.perfil is None:
                return False
            self._empezar()
        return True

    def _empezar(self) -> None:
        self.prueba = self._nueva_prueba()
        self.prueba.iniciar()
        self.sel = 0

    def _fase(self) -> str:
        return self.prueba.fase if self.prueba else PREPARANDO

    @property
    def midiendo(self) -> bool:
        """Mientras prepara y mide solo vale Esc."""
        return self.prueba is None or self._fase() in (PREPARANDO, EN_CURSO)

    def _mejor(self) -> Tuple[Optional[Resultado], bool]:
        return elegir_mejor(self.prueba.instantanea().resultados)

    def _acciones(self) -> List[Tuple[str, str]]:
        """Las filas de acción de ahora: [(clave, texto)]. Vacías mientras mide."""
        fase = self._fase()
        if fase == OCUPADO:
            return [(DE_TODOS_MODOS, ayuda.entrada(PREFIJO + "igual")[0]), (OTRA_VEZ, ayuda.entrada(PREFIJO + "otra_vez")[0])]
        if fase == ERROR:
            return [(OTRA_VEZ, ayuda.entrada(PREFIJO + "otra_vez")[0])]
        if fase != TERMINADA:
            return []
        mejor, dos = self._mejor()
        acciones = []
        if mejor is not None and not candidato_actual(self.app.config, mejor.candidato):
            titulo = ayuda.entrada(PREFIJO + ("aplicar" if dos else "aplicar_rapida"))[0]
            acciones.append((APLICAR, f"{titulo}: {mejor.candidato.etiqueta()}"))
        acciones.append((OTRA_VEZ, ayuda.entrada(PREFIJO + "otra_vez")[0]))
        return acciones

    def _accion(self) -> Optional[str]:
        acciones = self._acciones()
        return acciones[min(self.sel, len(acciones) - 1)][0] if acciones else None

    # ------------------------------------------------------------ pintar
    def ayuda(self):
        if not self._preparar():
            return "", "tenue"
        if self.midiendo:
            return ayuda.linea(PREFIJO + "cancelar"), "tenue"
        accion = self._accion()
        clave = {APLICAR: "aplicar", OTRA_VEZ: "otra_vez", DE_TODOS_MODOS: "igual"}.get(accion)
        if accion == APLICAR and not self._mejor()[1]:
            clave = "aplicar_rapida"
        return (ayuda.linea(PREFIJO + clave) if clave else ""), "tenue"

    def teclas(self):
        if self.midiendo:
            return pie(("Esc", "cancelar"))
        accion = self._accion()
        nombre = {
            APLICAR: ayuda.entrada(PREFIJO + "aplicar")[0], OTRA_VEZ: ayuda.entrada(PREFIJO + "otra_vez")[0],
            DE_TODOS_MODOS: ayuda.entrada(PREFIJO + "igual")[0],
        }.get(accion)
        return ([("Enter", nombre)] if nombre else []) + pie(("↑↓", "mover"), ("Esc", "volver"), ("?", "ayuda"), ("t", "tema"))

    def _barra(self, inst: Instantanea, ancho: int) -> List[Text]:
        """«Midiendo 2 de 4: Media · procesador, 9 hilos», la barra con su % y lo que queda."""
        t = self.app.t
        n = len(inst.resultados)
        corta = ancho < ANCHO_COMPLETO
        if inst.actual >= 0:
            texto = ayuda.entrada(PREFIJO + "progreso")[0].format(i=inst.actual + 1, n=n)
            texto += ": " + inst.resultados[inst.actual].candidato.etiqueta(corta)
        else:
            texto = ayuda.entrada(PREFIJO + "preparando")[0]
        queda = f"  ·  {ayuda.entrada(PREFIJO + 'queda')[0].format(tiempo=tiempo(inst.queda_s))}" if inst.queda_s is not None else ""
        pct = f"{round(100 * inst.progreso)} %"
        celdas = max(CELDAS_BARRA_MIN, min(CELDAS_BARRA, ancho - SANGRIA - cell_len(pct) - cell_len(queda) - 4))
        lleno, vacio = barra(100 * inst.progreso, celdas)
        lineas = [
            t((" " * SANGRIA + fotograma(self.app.juego, self.app.reloj()) + " ", "acento"), (texto, "texto")),
            t((" " * SANGRIA, "texto"), (lleno, "acento"), (vacio, "borde"), (f"  {pct}", "texto"), (queda, "tenue")),
        ]
        self.app.spinner("")  # pide repintar en cada vuelta: gira el spinner y avanza la barra
        return lineas

    def _tabla(self, inst: Instantanea, ancho: int, mejor: Optional[Resultado]) -> List[Text]:
        t, pr = self.app.t, self.app.presentar
        corta = ancho < ANCHO_COMPLETO
        sufijo = "_corta" if corta else ""
        cabeceras = (
            ayuda.entrada(PREFIJO + "col_prueba")[0], ayuda.entrada(PREFIJO + "col_velocidad" + sufijo)[0],
            ayuda.entrada(PREFIJO + "col_cpu" + sufijo)[0], ayuda.entrada(PREFIJO + "col_dos")[0],
        )
        filas = []
        for i, r in enumerate(inst.resultados):
            es_mejor = mejor is not None and r.candidato.clave == mejor.candidato.clave and inst.progreso >= 1.0
            if r.estado == LISTA:
                marca, estilo_marca = ("●", "acento") if es_mejor else ("✔", "ok")
            elif r.estado == MIDIENDO:
                marca, estilo_marca = fotograma(self.app.juego, self.app.reloj()), "acento"
            else:
                marca, estilo_marca = ("–" if r.estado in (OMITIDA, FALLO) else " "), "tenue"
            velocidad = veces(r.velocidad) if r.estado == LISTA and r.velocidad is not None else ""
            cpu = f"{r.cpu_pct:.0f} %" if r.estado == LISTA and r.cpu_pct is not None else ""
            if r.estado in (EN_ESPERA, MIDIENDO):
                velocidad = ayuda.entrada(PREFIJO + ("midiendo" if r.estado == MIDIENDO else "en_espera"))[0]
            dos, estilo_dos = columna_dos_fuentes(r)
            if es_mejor and not corta:
                dos += "  " + ayuda.entrada(PREFIJO + "mejor")[0]
            filas.append((marca, estilo_marca, r.candidato.etiqueta(corta), velocidad, cpu, dos, estilo_dos, r.estado, r))
        ancho_prueba = max(cell_len(pr(c)) for c in [cabeceras[0]] + [f[2] for f in filas])
        ancho_vel = max(cell_len(pr(c)) for c in [cabeceras[1]] + [f[3] for f in filas])
        ancho_cpu = max(cell_len(pr(c)) for c in [cabeceras[2]] + [f[4] for f in filas])
        lineas = [t((" " * (SANGRIA + MARCA), "texto"), (cabeceras[0].ljust(ancho_prueba) + " " * HUECO, "tenue"),
                    (cabeceras[1].ljust(ancho_vel) + " " * HUECO, "tenue"), (cabeceras[2].ljust(ancho_cpu) + " " * HUECO, "tenue"),
                    (cabeceras[3], "tenue"))]
        for marca, estilo_marca, etiqueta, velocidad, cpu, dos, estilo_dos, estado, r in filas:
            relleno = " " * max(0, MARCA - 1 - cell_len(pr(marca)))
            estilo_vel = {"si": "ok", "justo": "aviso", "atrasa": "error", "mal": "error"}[r.veredicto] if estado == LISTA else "tenue"
            lineas.append(t(
                (" " * SANGRIA + marca + relleno + " ", estilo_marca),
                (etiqueta.ljust(ancho_prueba) + " " * HUECO, "texto" if estado != EN_ESPERA else "tenue"),
                (velocidad.ljust(ancho_vel) + " " * HUECO, estilo_vel), (cpu.ljust(ancho_cpu) + " " * HUECO, "texto"),
                (dos, estilo_dos),
            ))
        return lineas

    def _notas(self, inst: Instantanea, ancho: int, dos: bool) -> List[Text]:
        """Lo que explica la tabla: «¿Dos fuentes?…», si ninguna aguanta, la gráfica integrada sin probar y cuándo se midió."""
        t, parrafo = self.app.t, self.app.parrafo
        titulo, explicacion = ayuda.entrada(PREFIJO + "col_dos")
        lineas = parrafo([(" " * SANGRIA + f"{titulo} {explicacion}", "tenue")], ancho, sangria=SANGRIA)
        if not dos:
            titulo, explicacion = ayuda.entrada(PREFIJO + "ninguna")
            lineas += parrafo([(" " * SANGRIA + f"{titulo}. {explicacion}", "aviso")], ancho, sangria=SANGRIA)
        if self.prueba.igpu_sin_permiso:
            titulo, explicacion = ayuda.entrada(PREFIJO + "igpu_apagada")
            lineas += parrafo([(" " * SANGRIA + f"{titulo}. {explicacion}", "tenue")], ancho, sangria=SANGRIA)
        if self.prueba.informe is not None:
            fecha = formato_fecha(self.prueba.informe.fecha)
            lineas.append(t((" " * SANGRIA + ayuda.entrada(PREFIJO + "fecha")[0].format(fecha=fecha), "tenue")))
        return lineas

    def _filas_accion(self) -> List[Text]:
        t = self.app.t
        return [
            self.app.t_fila(("▶", "acento"), (" " + texto, "elegido")) if i == self.sel else t((" " + " " + texto, "texto"))
            for i, (_clave, texto) in enumerate(self._acciones())
        ]

    def cuerpo(self, ancho, sitio):
        if not self._preparar():
            return [self.app.spinner(ayuda.linea("terminal_detectando_equipo").rstrip(".") + "…")], 0
        t, fase = self.app.t, self._fase()
        inst = self.prueba.instantanea()
        self.sel = min(self.sel, max(0, len(self._acciones()) - 1))
        if fase == PREPARANDO:
            titulo, explicacion = ayuda.entrada(PREFIJO + "preparando")
            return [self.app.spinner(titulo + "…"), t(), *self.app.parrafo([(" " * SANGRIA + explicacion, "tenue")], ancho, sangria=SANGRIA)], 0
        if fase == ERROR:
            return estado_error(self.app, self.prueba.error) + [t()] + self._filas_accion(), 2
        if fase == OCUPADO:
            titulo, explicacion = ayuda.entrada(PREFIJO + "ocupado")
            aviso = self.app.parrafo(
                [(" " * SANGRIA + "⚠ ", "aviso"), (titulo + ". ", "aviso bold"), (explicacion.format(n=inst.reposo_pct), "texto")], ancho, sangria=SANGRIA + 2,
            )
            return aviso + [t()] + self._filas_accion(), len(aviso) + 1 + self.sel
        lineas: List[Text] = []
        mejor, dos = elegir_mejor(inst.resultados)
        if fase == EN_CURSO:
            lineas += self._barra(inst, ancho) + [t()]
        lineas += self._tabla(inst, ancho, mejor if fase == TERMINADA else None) + [t()]
        if fase == EN_CURSO:
            titulo, explicacion = ayuda.entrada(PREFIJO + "consejo")
            lineas += self.app.parrafo([(" " * SANGRIA + explicacion, "tenue")], ancho, sangria=SANGRIA)
            return lineas, 0
        lineas += self._notas(inst, ancho, dos) + [t()]
        foco = len(lineas) + self.sel
        lineas += self._filas_accion()
        return lineas, foco

    # ------------------------------------------------------------ teclas
    def tecla(self, k):
        if self.prueba is None:
            return False  # mientras detecta, solo se puede volver
        if self.midiendo:
            if k in (ESC, "q"):
                self._cancelar()
            return True  # mientras mide, solo vale Esc: ni «?» ni «t»
        acciones = self._acciones()
        if k in (ARRIBA, "k") and acciones:
            self.sel = (self.sel - 1) % len(acciones)
        elif k in (ABAJO, "j") and acciones:
            self.sel = (self.sel + 1) % len(acciones)
        elif k == ENTER and acciones:
            self._hacer(self._accion())
        else:
            return False
        return True

    def _cancelar(self) -> None:
        """Esc: para la medición, descarta lo medido y vuelve sin cambiar nada."""
        self.prueba.cancelar()
        self.app.volver((ayuda.linea(PREFIJO + "cancelada"), "tenue"))

    def al_salir(self) -> None:
        if self.prueba is not None and self._fase() in (PREPARANDO, OCUPADO, EN_CURSO):
            self.prueba.cancelar()

    def _hacer(self, accion: str) -> None:
        if accion == DE_TODOS_MODOS:
            self.prueba.iniciar(forzar=True)
            self.sel = 0
        elif accion == OTRA_VEZ:
            self._empezar()
        elif accion == APLICAR:
            self._pedir_aplicar()

    def _no_aplica(self) -> str:
        return ayuda.linea("recomendacion_no_aplica").format(motivo=self.app.mgr.last_error.rstrip("."))

    def _pedir_aplicar(self) -> None:
        mejor, _dos = self._mejor()
        if mejor is None:
            return
        config = self.app.mgr.load()
        if self.app.mgr.last_error:  # guardar pisaría lo que el usuario tiene escrito en un archivo que no se lee
            self.app.avisar("⚠ " + self._no_aplica(), "error")
            return
        nuevo = copy.deepcopy(config)
        aplicar_candidato(nuevo, mejor.candidato)
        cambios = configurar.diferencias(config, nuevo)
        if not cambios:
            self.app.avisar("✔ " + ayuda.entrada(PREFIJO + "ya")[0], "ok")
            return
        self.app.abrir(Confirmacion(
            self.app, cambios, lambda: self._aplicar(mejor),
            encabezado=ayuda.linea("terminal_se_guardara").format(archivo=self.app.mgr.path.name).rstrip(".") + ":",
        ))

    def _aplicar(self, mejor: Resultado) -> None:
        config = self.app.mgr.load()
        if self.app.mgr.last_error:
            self.app.avisar("⚠ " + self._no_aplica(), "error")
            return
        aplicar_candidato(config, mejor.candidato)
        self.app.mgr.save(config)
        self.app.config = config
        self.app.avisar("✔ " + ayuda.linea(PREFIJO + "aplicado"), "ok")
