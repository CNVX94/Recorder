"""La grabación desde la terminal: `daily` sin más.

Lo mismo que la ventana, sobre la misma `RecorderSession`, pero en la propia consola y barato:
las frases, los avisos y las fuentes que caen o vuelven se imprimen como líneas normales (se
quedan en el historial de la terminal, se pueden copiar y desplazar) y debajo vive un pie de
tres líneas que se redibuja solo cuando cambia: la cabecera (`status_text`), los medidores
(`meter_text`) y las teclas. En silencio no se escribe nada y el proceso no gasta CPU.

Teclas: [p] pausar/continuar · [c] captura · [r] reconectar audio · [a] abrir la nota · [q] salir
(Ctrl+C también sale). Al salir con cola pendiente se pregunta en el pie, como en la ventana:
[e] esperar a que se transcriba · [s] salir perdiéndola · [c] cancelar.

Con la salida redirigida (`daily > log.txt`) no hay pie: las líneas van tal cual, los cambios de
cabecera también, y Ctrl+C cierra igual de limpio.

Se prueba con la sesión de mentira de tests/test_session.py: la sesión, el lector de teclas, la
espera, la consola y cómo se abre la nota se inyectan (tests/test_cli_live.py).
"""
import collections
import msvcrt
import os
import signal
import time
from typing import Callable, Deque, List, Optional, Sequence, Tuple

from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..config.schema import describe_runtime
from ..session import Event, Line, Notice, RecorderSession, SourceChanged, Status, StatusSnapshot
from .consola import asciify, make_console

INTERVALO = 0.2  # segundos entre sondeos, como la ventana (POLL_MS)
CTRL_C = "\x03"  # lo que el manejador de SIGINT mete en la cola de teclas

TECLAS = (("p", "pausar"), ("c", "captura"), ("r", "reconectar audio"), ("a", "abrir nota"), ("q", "salir"))
TECLAS_PAUSA = (("p", "continuar"),) + TECLAS[1:]
TECLAS_CIERRE = (("e", "esperar"), ("s", "salir perdiéndolos"), ("c", "cancelar"))
TECLAS_TERMINANDO = (("s", "salir sin esperar, perdiendo lo pendiente"),)

Partes = List[Tuple[str, str]]  # trozos (texto, estilo) de una línea


def leer_tecla() -> Optional[str]:
    """La tecla pulsada si hay alguna esperando; None si no. No bloquea.

    Las teclas especiales (flechas, F1…) llegan como un prefijo \\x00 o \\xe0 y un segundo
    carácter: se consume y se ignoran.
    """
    if not msvcrt.kbhit():
        return None
    ch = msvcrt.getwch()
    if ch in ("\x00", "\xe0"):
        msvcrt.getwch()
        return None
    return ch


def partes_teclas(ayudas: Sequence[Tuple[str, str]]) -> Partes:
    """(("p", "pausar"), …) → «[p] pausar · [c] captura…», con la tecla en acento."""
    partes: Partes = []
    for tecla, ayuda in ayudas:
        if partes:
            partes.append((" · ", "tenue"))
        partes += [(f"[{tecla}]", "acento"), (f" {ayuda}", "tenue")]
    return partes


def _ahora() -> str:
    return time.strftime("%H:%M:%S")


class PantallaEnVivo:
    """El bucle de `daily`: sondea la sesión en este hilo, pinta y atiende las teclas."""

    def __init__(
        self,
        session: Optional[RecorderSession] = None,
        *,
        consola: Optional[Console] = None,
        leer_tecla: Callable[[], Optional[str]] = leer_tecla,
        dormir: Callable[[float], None] = time.sleep,
        abrir: Callable[[str], object] = os.startfile,
    ):
        self.session = session or RecorderSession()
        self.consola = consola or make_console()
        self._leer_tecla = leer_tecla
        self._dormir = dormir
        self._abrir = abrir
        self.ascii = getattr(self.consola, "ascii_mode", False)
        self.plano = not self.consola.is_interactive  # salida redirigida: sin pie y sin partir líneas
        self._teclas: Deque[str] = collections.deque()  # lo que mete el manejador de Ctrl+C; va antes que el teclado
        self._live: Optional[Live] = None  # el pie; None en modo plano
        self._preguntando = False  # el pie muestra la pregunta de cerrar con cola pendiente
        self._resumen = ""  # lo que queda sin transcribir, para esa pregunta
        self._pie_pintado: Optional[tuple] = None  # lo último pintado en el pie, para no redibujar lo mismo

    # ------------------------------------------------------------------ pintar
    def _imprimir(self, *partes: Tuple[str, str]) -> None:
        """Una línea por encima del pie (o tal cual sin pie). Sin marcado de rich: una frase con
        corchetes, «[música]», se tomaría por una etiqueta de estilo y desaparecería. Hacia un
        archivo no se parte a 80 columnas: cada frase es una línea del registro."""
        self.consola.print(Text.assemble(*[(asciify(t) if self.ascii else t, e) for t, e in partes]), soft_wrap=self.plano)

    def _linea(self, stamp: str, kind: str, text: str, hits: List[str]) -> None:
        """Como `MainWindow.add_line`: hora, 🎤 si es el micrófono, la frase y las palabras clave."""
        partes: Partes = [(f"{stamp}  ", "tenue")]
        if kind == "mic":
            partes.append(("🎤 ", "mic"))
        partes.append((text, "acento" if hits else "texto"))
        self._imprimir(*partes)
        if hits:
            self._imprimir((f"          📸 captura: {', '.join(hits)}", "tenue"))

    def _pintar(self, ev: Event) -> None:
        if isinstance(ev, Line):
            self._linea(ev.stamp, ev.kind, ev.text, ev.hits)
        elif isinstance(ev, Notice):
            self._imprimir((f"{ev.stamp}  ", "tenue"), (ev.text, "error" if ev.level == "err" else "tenue"))
        elif isinstance(ev, SourceChanged):
            self._linea(ev.stamp, "out", ev.text, [])
        elif isinstance(ev, Status) and self.plano:
            # Sin pie, los cambios de cabecera quedan como líneas: así el registro dice cuándo
            # se cargó el modelo o se quedó escuchando. Con pie ya se ven ahí.
            self._imprimir((f"{_ahora()}  ", "tenue"), (ev.text, "tenue"))

    def _cabecera(self) -> None:
        cfg = self.session.config
        hilos = f"{cfg.cpu_threads} hilos" if cfg.cpu_threads else "hilos de la biblioteca"
        self._imprimir(("Recorder", "bold"), (" · nota: ", "tenue"), (str(self.session.file_path), "texto"))
        self._imprimir((f"{describe_runtime(cfg.model, cfg.beam_size, cfg.device, cfg.compute_type)}, {hilos}", "tenue"))
        self._imprimir(*partes_teclas(TECLAS), ("   (Ctrl+C también sale)", "tenue"))

    def _despedida(self) -> None:
        self._imprimir(("Grabación terminada", "bold"), (" · nota: ", "tenue"), (str(self.session.file_path), "texto"))
        perdido = self.session.request_close()
        if perdido:
            self._imprimir((f"⚠ se perdieron {perdido} sin transcribir", "error"))

    def _teclas_del_pie(self, st: StatusSnapshot) -> Sequence[Tuple[str, str]]:
        if self._preguntando:
            return TECLAS_CIERRE
        if st.draining:
            return TECLAS_TERMINANDO
        return TECLAS_PAUSA if st.paused else TECLAS

    def _pregunta(self) -> Partes:
        return [(f"Quedan {self._resumen} sin transcribir. ", "acento")] + partes_teclas(TECLAS_CIERRE)

    def _actualizar_pie(self, st: StatusSnapshot) -> None:
        """Redibuja el pie solo si algo cambió: en silencio no se escribe nada."""
        if self._live is None:
            return  # modo plano, o aún no arrancó el pie
        teclas = self._teclas_del_pie(st)
        clave = (st.status_text, st.status_highlight, st.meter_text, teclas)
        if clave == self._pie_pintado:
            return
        self._pie_pintado = clave
        partes: Partes = [(st.status_text, "bold" if st.status_highlight else "tenue"), ("\n", ""), (st.meter_text, "tenue"), ("\n", "")]
        if self._preguntando:
            partes += self._pregunta()
        else:
            partes += partes_teclas(teclas)
        self._live.update(Text.assemble(*[(asciify(t) if self.ascii else t, e) for t, e in partes]), refresh=True)

    # ------------------------------------------------------------------ teclas
    def _siguiente_tecla(self) -> Optional[str]:
        return self._teclas.popleft() if self._teclas else self._leer_tecla()

    def _tecla(self, tecla: str) -> bool:
        """Atiende una tecla. False cuando hay que salir del bucle (ya se decidió cerrar)."""
        k = tecla.lower()
        if self._preguntando:
            if k == "e":
                self._preguntando = False
                self._esperar()
            elif k in ("s", CTRL_C):
                return False
            elif k == "c":
                self._preguntando = False
            return True
        if self.session.draining:
            if k in ("s", CTRL_C):
                return False
            if k == "a":
                self._abrir_nota()
            return True
        if k in ("q", CTRL_C):
            return self._pedir_cierre()
        if k == "p":
            self._pintar(self.session.toggle_pause())
        elif k == "c":
            self.session.manual_screenshot()  # la línea llega después por poll(); otra en curso se ignora
        elif k == "r":
            self.session.reconnect_audio()
        elif k == "a":
            self._abrir_nota()
        return True

    def _pedir_cierre(self) -> bool:
        """Como `MainWindow.on_close`: sin cola se cierra; con cola se pregunta (en el pie)."""
        resumen = self.session.request_close()
        if resumen is None:
            return False
        self._resumen = resumen
        self._preguntando = True
        if self.plano:
            self._imprimir(*self._pregunta())
        return True

    def _esperar(self) -> None:
        """Se eligió esperar: la cola solo baja y el bucle acaba cuando `status.finished`."""
        self.session.begin_drain()
        if self.plano:
            self._imprimir((f"{_ahora()}  ", "tenue"), (self.session.status.status_text, "tenue"))

    def _abrir_nota(self) -> None:
        try:
            self._abrir(str(self.session.file_path))
        except OSError as e:
            self._imprimir((f"{_ahora()}  ", "tenue"), (f"⚠ no se pudo abrir la nota: {e}", "error"))

    def _on_sigint(self, _signum, _frame) -> None:
        """Ctrl+C se encola como una tecla y lo atiende el bucle: la primera vez pregunta como
        [q]; preguntando o terminando, sale perdiendo lo pendiente. Así KeyboardInterrupt no
        corta el bucle a medias ni deja el pie a medio pintar."""
        self._teclas.append(CTRL_C)

    # ------------------------------------------------------------------ bucle
    def _bucle(self) -> None:
        """Cada 200 ms, en este hilo: eventos → líneas; una tecla; el pie si cambió."""
        while True:
            for ev in self.session.poll():
                self._pintar(ev)
            if self.session.status.finished:
                return
            tecla = self._siguiente_tecla()
            if tecla is not None and not self._tecla(tecla):
                return
            self._actualizar_pie(self.session.status)
            self._dormir(INTERVALO)

    def run(self) -> int:
        self._cabecera()
        self.session.start()
        try:
            anterior = signal.signal(signal.SIGINT, self._on_sigint)
        except ValueError:  # fuera del hilo principal no se puede; se queda el de siempre
            anterior = None
        try:
            if self.plano:
                self._bucle()
            else:
                # transient: al salir el pie se borra y queda solo la transcripción y la despedida
                with Live(console=self.consola, auto_refresh=False, transient=True) as live:
                    self._live = live
                    self._bucle()
        finally:
            self._live = None
            if anterior is not None:
                signal.signal(signal.SIGINT, anterior)
            self.session.shutdown()  # sin pa.terminate(): ver RecorderSession.shutdown
        self._despedida()
        return 0


def grabar(consola: Optional[Console] = None, **kwargs) -> int:
    """`daily`: la pantalla en vivo con la sesión real. Devuelve el código de salida."""
    return PantallaEnVivo(consola=consola, **kwargs).run()
