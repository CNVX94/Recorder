"""El bucle y el marco de las pantallas de `daily menu`: lee teclas, las reparte entre la pantalla de arriba
de la pila y las globales, y pinta el cuadro si cambió.

Se pinta con rich.Live en la pantalla alternativa: al salir, la terminal queda como estaba. Cada INTERVALO s
se lee una tecla; el cuadro se recompone al pulsar algo, en el tic de TIC s (la cabecera: nota de hoy,
calidad, motor que se usaría y equipo), al cambiar el tamaño de la ventana o mientras gira un spinner, y
solo se redibuja si cambió: quieto no escribe nada. El cuadro ocupa la altura entera (ver marco.py):
cabecera, regla y ruta arriba; el cuerpo en medio (recortado alrededor de lo elegido si no cabe, con
«↑ N más arriba» y «↓ N más abajo»); abajo la línea de ayuda de lo elegido, el aviso y el pie de teclas.
Con color real se pinta el fondo de la paleta y la fila elegida con el de la superficie; en ASCII y en
16 colores, no.

Lo que usa la terminal entera (Calibrar, Reagrupar, Recomendación) se ejecuta fuera de la pantalla
alternativa, como en el menú numerado, y se vuelve al pulsar una tecla. Grabar y la ventana terminan el
menú. Una pantalla puede abrirse directamente (`inicial`, sin pasar por Inicio: Esc sale a la terminal) y
cerrarse dejando un aviso a la anterior (`volver(aviso)`).

Las pruebas inyectan el lector de teclas, la espera, el reloj, la plataforma, la detección de Opciones y el
muestreo de Rendimiento (tests/test_cli_pantallas.py).
"""
import contextlib
import os
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from rich.cells import cell_len
from rich.console import Console, Group
from rich.live import Live
from rich.style import Style
from rich.text import Text

from ... import ayuda, paleta
from ...config.hardware import cached_hardware, describe_hardware, peek_hardware
from ...config.manager import ConfigManager
from ...config.schema import describe_quality
from ...metricas import Muestreador
from .. import app as despacho, configurar, teclas
from ..consola import (
    ELIDIDO, ELIDIDO_ASCII, JUEGO_ASCII, fotograma, juego_de, partes_teclas, presentar, tema_de,
)
from ..teclas import ESC
from .base import INTERVALO, TIC, Pantalla, Partes, detectar_entorno, motor_previsto, nota_de_hoy
from .marco import (
    ALTO_AVISO, ALTO_MINIMO, ANCHO_MINIMO, MARGEN, SANGRIA_LISTA, TECLA_AYUDA, alto_ayuda, demasiado_pequena,
    pie_que_cabe, respiros, ventana,
)

COLORES_PROPIOS = ("256", "truecolor")  # con estos hay color real para pintar el fondo propio


class Terminal:
    """El bucle: lee teclas, reparte entre la pantalla de arriba de la pila y las globales, y
    pinta el cuadro si cambió. `run` devuelve el código de salida, como el menú numerado."""

    def __init__(
        self,
        consola: Console,
        comandos: Dict,
        mgr: ConfigManager,
        *,
        leer_tecla: Optional[teclas.Lector] = None,  # None: el teclado de la terminal
        dormir: Callable[[float], None] = time.sleep,
        reloj: Callable[[], float] = time.monotonic,
        windows: bool = os.name == "nt",
        detectar: Callable[[], configurar.Entorno] = detectar_entorno,
        muestreador: Optional[Callable[[], Muestreador]] = None,
        inicial: Optional[Callable[["Terminal"], Pantalla]] = None,  # None: el Inicio; si no, esa pantalla sola
    ):
        from .inicio import Inicio  # aquí y no arriba: Inicio abre pantallas por el registro y usa Terminal

        self.consola, self.comandos, self.mgr = consola, comandos, mgr
        self._leer_tecla, self._dormir, self.reloj = leer_tecla, dormir, reloj
        self.windows = windows
        self._detectar = detectar
        self.nuevo_muestreador = muestreador or (lambda: Muestreador(None, lambda: (0, 0.0)))
        self.juego = juego_de(consola)
        self.ascii = self.juego == JUEGO_ASCII
        # color real (VT activo, no ASCII): se pinta el fondo de la paleta; con 16 colores no se toca el de la consola
        self.fondo = not self.ascii and consola.color_system in COLORES_PROPIOS
        self.config = mgr.load()
        self.pila: List[Pantalla] = [(inicial or Inicio)(self)]
        self.aviso: Tuple[str, str] = ("", "tenue")  # dura hasta la siguiente tecla
        self._fin, self._salida = False, None  # dejar la pantalla y, si hay, la acción a ejecutar fuera
        self._entorno: Optional[configurar.Entorno] = None
        self._hilo_entorno: Optional[threading.Thread] = None
        self.error_entorno = ""
        self._tema = self.config.theme  # el pintado: entra en la firma del cuadro
        self._tema_puesto = False
        self._cabecera: Tuple = ()
        self._ultimo_tic: Optional[float] = None
        self._firma = None
        self._animando = False  # el último cuadro tenía un spinner: se recompone en cada vuelta
        self._ancho = consola.size[0] - 2 * MARGEN  # el ancho útil del cuadro que se está componiendo

    # ------------------------------------------------------------ para las pantallas
    @property
    def elidido(self) -> str:
        """Lo que se pone donde se corta un texto: «…», o «...» en ASCII."""
        return ELIDIDO_ASCII if self.ascii else ELIDIDO

    def presentar(self, texto: str) -> str:
        """`texto` con los símbolos del juego activo."""
        return presentar(texto, self.consola)

    def _estilo(self, estilo: str):
        """Un estilo de rich o varios nombres juntos («elegido fila»): se combinan."""
        if " " not in estilo.strip():
            return estilo
        return Style.combine([self.consola.get_style(e) for e in estilo.split()])

    def _texto(self, partes: Partes, partir: bool = False) -> Text:
        """Los trozos como un texto de rich: de una línea (se recorta) o, con `partir`, para partirlo por palabras."""
        return Text.assemble(*[(self.presentar(s), self._estilo(e)) for s, e in partes], no_wrap=not partir)

    def _recortar(self, texto: Text, ancho: int) -> Text:
        """Corta a `ancho` celdas con «…» al final («...» en ASCII, que no tiene «…»)."""
        if cell_len(texto.plain) <= ancho:
            return texto
        if self.ascii:
            texto.truncate(max(0, ancho - len(ELIDIDO_ASCII)), overflow="crop")
            texto.append(ELIDIDO_ASCII)
        else:
            texto.truncate(ancho, overflow="ellipsis")
        return texto

    def t(self, *partes: Tuple[str, str]) -> Text:
        """Trozos (texto, estilo) → una línea que no se parte: lo que sobra se corta con «…» (con «...» en
        ASCII). Sin marcado de rich: un «[música]» en un título no desaparece."""
        return self._recortar(self._texto(partes), self._ancho)

    def t_fila(self, *partes: Tuple[str, str]) -> Text:
        """Como `t`, para la fila elegida: con fondo de superficie hasta el borde cuando hay color real."""
        if not self.fondo:
            return self.t(*partes)
        texto = self._recortar(self._texto([(s, f"{e} fila") for s, e in partes]), self._ancho)
        texto.append(" " * max(0, self._ancho - cell_len(texto.plain)), self._estilo("fila"))
        return texto

    def parrafo(self, partes: Partes, ancho: int, sangria: int = 4) -> List[Text]:
        """Trozos → líneas partidas al ancho, con las de continuación sangradas."""
        texto = self._texto(partes, partir=True)
        lineas = texto.wrap(self.consola, max(20, ancho - sangria))
        return [linea if i == 0 else Text(" " * sangria) + linea for i, linea in enumerate(lineas)]

    def spinner(self, texto: str) -> Text:
        """«• texto…»: un fotograma cada TIC_ANIMACION s, de los de Consolas en el juego «consola»."""
        self._animando = True
        return self.t((fotograma(self.juego, self.reloj()) + " ", "acento"), (texto, "tenue"))

    def avisar(self, texto: str, estilo: str = "tenue") -> None:
        self.aviso = (texto, estilo)

    def abrir(self, pantalla: Pantalla) -> None:
        self.pila.append(pantalla)

    def volver(self, aviso: Optional[Tuple[str, str]] = None) -> None:
        """Cierra la pantalla de arriba (y sale si era la última). `aviso` (texto, estilo) es lo que ve
        quien queda debajo, hasta la siguiente tecla."""
        self.pila.pop().al_salir()
        if not self.pila:
            self.salir()
        elif aviso:
            self.avisar(*aviso)

    def salir(self, accion: Optional[str] = None) -> None:
        self._fin, self._salida = True, accion

    def entorno(self) -> Optional[configurar.Entorno]:
        """Lo que Opciones ofrece elegir; None mientras se detecta. Una sola detección por menú y
        en su hilo: PortAudio no se puede inicializar dos veces a la vez."""
        if self._hilo_entorno is None:
            def detectar():
                try:
                    self._entorno = self._detectar()
                except Exception as e:  # que Opciones no se quede girando: lo dice y se puede volver
                    self.error_entorno = f"⚠ No se pudo detectar el entorno: {e.__class__.__name__}: {e}"

            self._hilo_entorno = threading.Thread(target=detectar, daemon=True, name="opciones")
            self._hilo_entorno.start()
        return self._entorno

    def poner_tema(self, nombre: str) -> None:
        if self._tema_puesto:
            self.consola.pop_theme()
        self.consola.push_theme(tema_de(self.consola, nombre))
        self._tema_puesto, self._tema = True, nombre

    def alternar_tema(self) -> str:
        """Del oscuro al claro o al revés («sistema» se resuelve primero), y se guarda como hace
        la ventana. Con config.json ilegible se cambia solo aquí: guardar pisaría lo del usuario."""
        nuevo = "claro" if paleta.resolver(self.config.theme) == "oscuro" else "oscuro"
        self.poner_tema(nuevo)
        config = self.mgr.load()
        if self.mgr.last_error:
            self.avisar("⚠ Tema cambiado solo en esta terminal: config.json no se puede leer y no se guarda.", "error")
        else:
            config.theme = nuevo
            self.mgr.save(config)
            self.config = config
            self.avisar(f"✔ Tema {nuevo} guardado: vale también para la ventana.", "ok")
        return nuevo

    # ------------------------------------------------------------ teclas
    def _tecla(self, k: str) -> None:
        self.aviso = ("", "tenue")
        pantalla = self.pila[-1]
        if len(k) == 1 and not pantalla.escribiendo:
            k = k.lower()  # Q, T y J valen como q, t y j
        if pantalla.tecla(k):
            return
        if k in (ESC, "q"):
            self.volver()
        elif k == TECLA_AYUDA and pantalla.abre_ayuda:
            from .registro import clase_de

            self.abrir(clase_de("ayuda")(self))
        elif k == "t":
            self.alternar_tema()

    # ------------------------------------------------------------ pintar
    def _refrescar_cabecera(self) -> None:
        self.config = self.mgr.load()  # se relee: otra ventana u Opciones pueden haberla cambiado
        hw = peek_hardware()
        self._cabecera = (
            nota_de_hoy(self.config.notes_dir),
            describe_quality(self.config),
            motor_previsto(self.config, hw).texto if hw else "",
            describe_hardware(hw) if hw else "",
            self.mgr.last_error,
        )

    def _lineas_cabecera(self) -> List[Text]:
        """La cabecera de tres líneas del inicio: nota, calidad y motor, y el equipo."""
        nota, calidad, motor, equipo, error = self._cabecera
        uno = self.t(("Recorder", "bold"), (" · nota de hoy: ", "tenue"), (nota, "texto"))
        if error:
            dos = self.t((f"⚠ {error}", "error"))
        else:
            dos = self.t((calidad, "tenue"), (" · se usaría " if motor else "", "tenue"), (motor, "texto"))
        tres = self.t(("Equipo: ", "tenue"), (equipo, "tenue")) if equipo else self.spinner(ayuda.linea("terminal_detectando_equipo").rstrip(".") + "…")
        return [uno, dos, tres]

    def _linea_cabecera(self) -> Text:
        """La cabecera de una línea de las demás pantallas: «Recorder · nota · calidad»."""
        nota, calidad, _motor, _equipo, error = self._cabecera
        if error:
            return self.t(("Recorder", "bold"), (" · ", "tenue"), (f"⚠ {error}", "error"))
        return self.t(("Recorder", "bold"), (" · ", "tenue"), (nota, "texto"), (" · ", "tenue"), (calidad, "tenue"))

    def _partida(self, partes: Partes, ancho: int) -> List[Text]:
        if not partes or not "".join(s for s, _e in partes):
            return []
        return list(self._texto(partes, partir=True).wrap(self.consola, ancho))

    def _linea_ruta(self, ancho: int) -> Text:
        """«Inicio › Opciones › Guardar» a la izquierda y la marca de la pantalla («● cambios sin guardar») a la derecha."""
        pantalla = self.pila[-1]
        izquierda = self._texto([(" › ".join(p.titulo for p in self.pila), "bold")])
        marca, estilo = pantalla.marca()
        derecha = self._texto([(marca, estilo)]) if marca else Text()
        hueco = ancho - cell_len(izquierda.plain) - cell_len(derecha.plain)
        if not marca or hueco < 1:
            return self._recortar(izquierda, ancho)
        return izquierda + Text(" " * hueco) + derecha

    def _pie(self, pantalla: Pantalla, ancho: int) -> Text:
        def cabe(ts) -> bool:
            return cell_len(self.presentar("".join(s for s, _e in partes_teclas(ts)))) <= ancho

        mas = (TECLA_AYUDA, ayuda.entrada("pie_mas")[0])
        return self.t(*partes_teclas(pie_que_cabe(pantalla.teclas(), cabe, mas)))

    def _con_marcador(self, clave: str, n: int) -> Text:
        titulo = ayuda.entrada(clave)[0].format(n=n)
        flecha = "↑" if clave.endswith("arriba") else "↓"
        return self.t((" " * SANGRIA_LISTA + f"{flecha} {titulo}", "tenue"))

    def _enmarcar(self, linea: Text, ancho: int) -> Text:
        """La línea con su margen, rellena hasta el ancho y, con color real, sobre el fondo de la paleta."""
        marco = Text.assemble(" " * MARGEN, linea)
        marco.pad_right(max(0, ancho - cell_len(marco.plain)))
        if self.fondo:
            marco.style = "fondo"
        return marco

    def _pequena(self, ancho: int) -> List[Text]:
        """Lo único que se pinta por debajo del tamaño mínimo: el aviso, que se va solo al agrandar."""
        titulo, texto = ayuda.entrada("terminal_pequena")
        self._ancho = max(1, ancho)
        return [self.t((titulo, "bold"))] + [
            linea for linea in self._partida([(texto.format(columnas=ANCHO_MINIMO, lineas=ALTO_MINIMO), "tenue")], max(1, ancho))
        ]

    def marco(self) -> List[Text]:
        """El cuadro entero, de la altura de la terminal (docs/terminal-especificacion.md, sección 1)."""
        ancho, alto = self.consola.size
        self._animando = False
        if not self._cabecera:
            self._refrescar_cabecera()
        if demasiado_pequena(ancho, alto):
            return self._pequena(ancho)
        util = ancho - 2 * MARGEN
        self._ancho = util
        pantalla = self.pila[-1]
        cabecera = self._lineas_cabecera() if pantalla.cabecera_completa else [self._linea_cabecera()]
        arriba = cabecera + [self.t(("─" * util, "borde")), self._linea_ruta(util)]
        texto, estilo = pantalla.ayuda()
        alto_ay = alto_ayuda(ancho)
        explicacion = self._partida([(texto, estilo)], util)
        if len(explicacion) > alto_ay:  # no cabe: la última línea acaba en «…»
            explicacion = explicacion[:alto_ay]
            explicacion[-1] = self._recortar(self._texto([(explicacion[-1].plain.rstrip() + ELIDIDO, estilo)]), util)
        explicacion += [Text()] * (alto_ay - len(explicacion))
        aviso = self._partida([self.aviso], util)[:ALTO_AVISO + 1] or [Text()]
        abajo = explicacion + aviso + [self._pie(pantalla, util)]
        libre = alto - len(arriba) - len(abajo)
        r_arriba, r_abajo = respiros(libre)
        sitio = max(1, libre - r_arriba - r_abajo)
        cuerpo, foco = pantalla.cuerpo(util, sitio)
        filas, ocultas_arriba, ocultas_abajo = ventana(len(cuerpo), foco, sitio)
        visibles = [cuerpo[i] for i in filas]
        if ocultas_arriba:
            visibles.insert(0, self._con_marcador("terminal_mas_arriba", ocultas_arriba))
        if ocultas_abajo:
            visibles.append(self._con_marcador("terminal_mas_abajo", ocultas_abajo))
        lineas = (
            arriba + [Text()] * r_arriba + visibles + [Text()] * (sitio - len(visibles)) + [Text()] * r_abajo + abajo
        )
        return [self._enmarcar(linea, ancho) for linea in lineas]

    def _pintar(self, live: Live, forzar: bool) -> None:
        ahora = self.reloj()
        tic = self._ultimo_tic is None or ahora - self._ultimo_tic >= TIC
        if tic:
            self._ultimo_tic = ahora
            self._refrescar_cabecera()
        if not (forzar or tic or self._animando):
            return
        lineas = self.marco()
        firma = (tuple(l.plain for l in lineas), self._tema, self.consola.size)
        if firma != self._firma:
            self._firma = firma
            live.update(Group(*lineas), refresh=True)

    # ------------------------------------------------------------ bucle
    def _teclado(self):
        return contextlib.nullcontext(self._leer_tecla) if self._leer_tecla else teclas.teclado()

    def _navegar(self) -> Optional[str]:
        """Las pantallas, hasta salir o hasta elegir algo que se ejecuta fuera (su acción)."""
        self._fin, self._salida, self._firma = False, None, None
        tam, tecla = None, None
        with self._teclado() as leer, Live(console=self.consola, screen=True, auto_refresh=False) as live:
            while True:
                self._pintar(live, forzar=tecla is not None or self.consola.size != tam)
                tam = self.consola.size
                tecla = leer()
                if tecla is None:
                    self._dormir(INTERVALO)
                    continue
                self._tecla(tecla)
                if self._fin:
                    return self._salida  # tras una tecla se repinta sin esperar

    def _ejecutar(self, accion: str) -> Optional[int]:
        """Lo elegido que usa la terminal entera. Grabar y la ventana terminan el menú (su código);
        un comando vuelve a las pantallas tras pulsar una tecla (None)."""
        if self._hilo_entorno is not None:
            self._hilo_entorno.join()  # su PyAudio debe estar cerrado antes de abrir otro
        if accion == "grabar":
            from ..live import grabar

            return grabar(consola=self.consola)
        if accion == "ventana":
            return despacho.abrir_ventana()
        self.consola.print(*self._partida([(ayuda.linea("menu_" + accion), "tenue")], self.consola.width), sep="\n")
        despacho.ejecutar_comando(accion, (), self.consola, self.comandos)
        self.consola.print(self.t(*partes_teclas((("una tecla", "volver al menú"),))))
        with self._teclado() as leer:
            while leer() is None:
                self._dormir(INTERVALO)
        return None

    def run(self) -> int:
        if peek_hardware() is None:
            threading.Thread(target=cached_hardware, daemon=True, name="equipo").start()
        try:
            while True:
                accion = self._navegar()
                if accion is None:
                    return 0
                codigo = self._ejecutar(accion)
                if codigo is not None:
                    return codigo
        except KeyboardInterrupt:
            return 0
        finally:
            for pantalla in self.pila:
                pantalla.al_salir()
