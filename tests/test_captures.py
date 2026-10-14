"""Buffer circular de capturas y enlaces que no se rompen. Sin pantalla: la imagen la da un falso."""
import datetime as dt
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from PIL import Image, JpegImagePlugin

from recorder.actions.capture_buffer import BUFFER_DIR, CaptureBuffer, nearest_frame, should_buffer
from recorder.actions.notes import NotesSession, rebase_links
from recorder.actions.power import AWAKE_GRACE_SEC
from recorder.actions.screenshot import capture_name


class TestPoliticas(unittest.TestCase):
    def test_nearest_frame(self):
        self.assertEqual(nearest_frame([100.0, 105.0, 110.0], 106.9, 10), 105.0)
        self.assertEqual(nearest_frame([100.0, 105.0, 110.0], 108.0, 10), 110.0)
        self.assertIsNone(nearest_frame([100.0], 130.0, 10), "a más de max_gap no vale: mejor el plan B")
        self.assertIsNone(nearest_frame([], 1.0, 10))

    def test_should_buffer_solo_en_reunion(self):
        self.assertTrue(should_buffer(1000.0, 990.0, paused=False))
        self.assertFalse(should_buffer(1000.0, 990.0, paused=True))
        self.assertFalse(should_buffer(1000.0 + AWAKE_GRACE_SEC, 1000.0, paused=False))

    def test_capture_name_usa_la_hora_dada(self):
        t = dt.datetime(2026, 9, 25, 18, 8, 50).timestamp()
        self.assertEqual(capture_name("Aquí", t, "jpg"), "2026-09-25_18-08-50_aqui.jpg")


class TestCaptureBuffer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.caps = pathlib.Path(self.tmp.name) / "capturas"
        self.grabs = 0

    def tearDown(self):
        self.tmp.cleanup()

    def grab(self):
        self.grabs += 1
        return Image.new("RGB", (80, 60), (10 * self.grabs % 255, 90, 160))

    def buffer(self, quality="normal"):
        return CaptureBuffer(self.caps, quality, grab=self.grab, active=lambda: True)

    def test_take_mueve_el_fotograma_mas_cercano_sin_recomprimir(self):
        b = self.buffer()
        for t in (100.0, 105.0, 110.0):
            b.snap(t)
        crudo = (self.caps / BUFFER_DIR / "105.000.jpg").read_bytes()
        dest = b.take(106.0, self.caps / "2026-09-25_18-08-50_aqui.png")
        self.assertEqual(dest.name, "2026-09-25_18-08-50_aqui.jpg", "la extensión es la del buffer")
        self.assertEqual(dest.read_bytes(), crudo)
        self.assertEqual(sorted(p.name for p in (self.caps / BUFFER_DIR).iterdir()), ["100.000.jpg", "110.000.jpg"])

    def test_take_sin_fotograma_cercano_devuelve_none(self):
        b = self.buffer()
        b.snap(100.0)
        self.assertIsNone(b.take(200.0, self.caps / "x.jpg"))
        self.assertFalse((self.caps / "x.jpg").exists())

    def test_purge_y_clear(self):
        b = self.buffer()
        for t in (100.0, 105.0, 110.0):
            b.snap(t)
        b.purge_before(106.0)
        self.assertEqual([p.name for p in (self.caps / BUFFER_DIR).iterdir()], ["110.000.jpg"])
        b.clear()
        self.assertEqual(list((self.caps / BUFFER_DIR).iterdir()), [])

    def test_calidades(self):
        reescalados = []
        original = Image.Image.resize

        def resize(img, size, resample=None, *a, **k):
            reescalados.append(resample)
            return original(img, size, resample, *a, **k)

        with mock.patch.object(Image.Image, "resize", resize):
            ligera = CaptureBuffer(self.caps / "l", "light", grab=self.grab, active=lambda: True).snap(1.0)
        with Image.open(ligera) as img:
            self.assertEqual((img.format, img.size), ("JPEG", (40, 30)))
        self.assertEqual(reescalados, [Image.LANCZOS], "a media resolución se reduce con LANCZOS, no con NEAREST")

        normal = CaptureBuffer(self.caps / "n", "normal", grab=self.grab, active=lambda: True).snap(1.0)
        with Image.open(normal) as img:
            self.assertEqual((img.format, img.size), ("JPEG", (80, 60)))
            self.assertEqual(JpegImagePlugin.get_sampling(img), 0, "4:4:4: sin submuestreo de color, el texto pequeño no se emborrona")
            self.assertLessEqual(img.quantization[0][0], 5, "calidad 85 o más (la tabla de luminancia de q70 empieza en 10)")

        alta = CaptureBuffer(self.caps / "h", "high", grab=self.grab, active=lambda: True).snap(1.0)
        with Image.open(alta) as img:
            self.assertEqual((img.format, img.size), ("PNG", (80, 60)))  # sin pérdida, como la captura de siempre
        self.assertFalse(list(self.caps.rglob("*.tmp")), "no quedan archivos a medio escribir")

    def test_stop_vacia_el_buffer(self):
        b = self.buffer()
        b.start()
        b.snap(100.0)
        b.stop()
        self.assertEqual(list((self.caps / BUFFER_DIR).iterdir()), [], "al parar no queda nada de la pantalla")

    def test_sin_reunion_tambien_se_purga_lo_viejo(self):
        # El worker purga al transcribir; si no transcribe nada (silencio, pausa), el propio hilo
        # borra lo más viejo que la retención en cada vuelta.
        b = CaptureBuffer(self.caps, "normal", grab=self.grab, active=lambda: False, interval=0.02, retention=1.0)
        b.start()  # start() vacía lo que hubiera: los fotogramas van después
        try:
            b.snap(time.time() - 3.0)  # viejo
            reciente = b.snap(time.time())
            fin = time.time() + 2
            while len(list((self.caps / BUFFER_DIR).iterdir())) > 1 and time.time() < fin:
                time.sleep(0.02)
            self.assertEqual([p.name for p in (self.caps / BUFFER_DIR).iterdir()], [reciente.name])
            self.assertEqual(self.grabs, 2, "sin reunión no se captura")
        finally:
            b.stop()

    def test_el_primer_fallo_se_avisa_una_vez(self):
        fallos = []

        def grab_rota():
            raise OSError("no está la unidad")

        b = CaptureBuffer(self.caps, "normal", grab=grab_rota, active=lambda: True, interval=0.02, on_error=fallos.append)
        b.start()
        try:
            fin = time.time() + 2
            while b.errors < 3 and time.time() < fin:
                time.sleep(0.02)
            self.assertGreaterEqual(b.errors, 3, "un fallo no para el hilo")
            self.assertEqual(len(fallos), 1)
            self.assertIsInstance(fallos[0], OSError)
        finally:
            b.stop()

    def test_el_hilo_solo_captura_si_hay_reunion(self):
        activo = [False]
        b = CaptureBuffer(self.caps, "normal", grab=self.grab, active=lambda: activo[0], interval=0.02)
        b.start()
        try:
            time.sleep(0.15)
            self.assertEqual(self.grabs, 0)
            activo[0] = True
            fin = time.time() + 2
            while self.grabs < 2 and time.time() < fin:
                time.sleep(0.02)
            self.assertGreaterEqual(self.grabs, 2)
        finally:
            b.stop()


class TestEnlacesAlMoverLaNota(unittest.TestCase):
    def test_rebase_links(self):
        texto = (
            "- **10:00:00** hola\n  - 📸 `aqui` → ![](capturas/a.png)\n"
            "- **10:01:00** 📸 captura manual → ![](D:/fuera/b.png)\n"
        )
        nuevo = rebase_links(texto, r"C:\n\Dailies", r"C:\n\Vault\Input")
        self.assertIn("![](../../Dailies/capturas/a.png)", nuevo)
        self.assertIn("![](D:/fuera/b.png)", nuevo, "una ruta absoluta no se toca")
        con_alt = rebase_links("ver ![la pantalla](capturas/c.png) y ![](http://x/y.png)", r"C:\n\Dailies", r"C:\n\Vault")
        self.assertEqual(con_alt, "ver ![la pantalla](../Dailies/capturas/c.png) y ![](http://x/y.png)")

    def test_move_notes_mantiene_las_imagenes_enlazadas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            (base / "a" / "capturas").mkdir(parents=True)
            (base / "a" / "capturas" / "x.png").write_bytes(b"png")
            s = NotesSession(base / "a", custom_name="d.md")
            s.write_line("  - 📸 `aqui` → ![](capturas/x.png)")
            s.move_notes(base / "b" / "c")
            ref = s.file_path.read_text(encoding="utf-8").split("![](")[1].split(")")[0]
            self.assertTrue((s.file_path.parent / ref).resolve().is_file(), ref)


if __name__ == "__main__":
    unittest.main()
