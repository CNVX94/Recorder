"""Genera el icono de Recorder (recorder/assets/recorder.ico) con Pillow.

Un micrófono sobre su soporte y un punto rojo de «grabando», con la paleta de la ventana
(Catppuccin Mocha, recorder/ui/theme.py). Cada tamaño se dibuja aparte, con sobremuestreo,
para que a 16 px siga siendo un micrófono y no una mancha.

    python packaging\\generar_icono.py                       # escribe recorder/assets/recorder.ico
    python packaging\\generar_icono.py --vista-previa p.png  # además, un mosaico PNG para mirarlo

No hace falta ejecutarlo a mano: el .ico está en el repositorio, y packaging\\build.ps1 lo
regenera solo si falta. Vale cualquier Python con Pillow (requirements.txt lo trae).
"""
import argparse
import pathlib

from PIL import Image, ImageDraw

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "recorder" / "assets" / "recorder.ico"
TAMANOS = (16, 20, 24, 32, 40, 48, 64, 128, 256)

# Paleta de recorder/ui/theme.py (Catppuccin Mocha)
FONDO = "#1e1e2e"
ACENTO = "#f9e2af"  # soporte del micrófono
MIC = "#89b4fa"  # cápsula
ROJO = "#f38ba8"  # punto de «grabando»


def dibujar(tamano: int, escala: int = 8) -> Image.Image:
    """El icono a `tamano` px, dibujado a `escala`× y reducido con LANCZOS (antialias limpio)."""
    s = tamano * escala
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def p(x: float) -> float:  # coordenada relativa (0..1) a píxeles del lienzo grande
        return x * s

    # Baldosa redondeada de fondo, un poco metida para que no toque el borde
    d.rounded_rectangle([p(0.04), p(0.04), p(0.96), p(0.96)], radius=p(0.20), fill=FONDO)

    # Soporte: una U alrededor de la cápsula, el pie y la base (en acento)
    grosor = max(1, round(p(0.07)))
    d.arc([p(0.25), p(0.20), p(0.75), p(0.70)], start=0, end=180, fill=ACENTO, width=grosor)
    d.line([p(0.50), p(0.69), p(0.50), p(0.83)], fill=ACENTO, width=grosor)
    d.line([p(0.34), p(0.83), p(0.66), p(0.83)], fill=ACENTO, width=grosor)
    for x in (0.34, 0.66):  # remates redondos de la base
        d.ellipse([p(x) - grosor / 2, p(0.83) - grosor / 2, p(x) + grosor / 2, p(0.83) + grosor / 2], fill=ACENTO)

    # Cápsula del micrófono (azul)
    d.rounded_rectangle([p(0.36), p(0.16), p(0.64), p(0.57)], radius=p(0.14), fill=MIC)
    if tamano >= 48:  # rejilla sutil, solo donde se puede ver
        for y in (0.30, 0.37, 0.44):
            d.line([p(0.42), p(y), p(0.58), p(y)], fill=FONDO, width=max(1, round(p(0.015))))

    # Punto rojo de «grabando», con un anillo del color del fondo para despegarlo de la cápsula
    cx, cy, r = p(0.80), p(0.21), p(0.095)
    anillo = p(0.03)
    d.ellipse([cx - r - anillo, cy - r - anillo, cx + r + anillo, cy + r + anillo], fill=FONDO)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=ROJO)

    return img.resize((tamano, tamano), Image.LANCZOS)


def generar(salida: pathlib.Path) -> list:
    imagenes = [dibujar(t) for t in TAMANOS]
    salida.parent.mkdir(parents=True, exist_ok=True)
    # Pillow usa la imagen de append_images cuyo tamaño coincide, en vez de reescalar la primera
    mayor = imagenes[-1]
    mayor.save(salida, format="ICO", sizes=[(t, t) for t in TAMANOS], append_images=imagenes[:-1])
    return imagenes


def vista_previa(imagenes: list, destino: pathlib.Path) -> None:
    """Mosaico: cada tamaño a escala real sobre claro y oscuro, y los pequeños ampliados ×8."""
    margen = 12
    ancho = sum(i.width for i in imagenes) + margen * (len(imagenes) + 1)
    ampliados = [i.resize((i.width * 8, i.height * 8), Image.NEAREST) for i in imagenes[:4]]
    alto_fila = max(i.height for i in imagenes) + margen * 2
    alto_ampl = max(a.height for a in ampliados) + margen * 2
    lienzo = Image.new("RGB", (max(ancho, sum(a.width for a in ampliados) + margen * 5), alto_fila * 2 + alto_ampl), "#ffffff")
    for fila, fondo in enumerate(("#f3f3f3", "#202020")):
        y0 = fila * alto_fila
        ImageDraw.Draw(lienzo).rectangle([0, y0, lienzo.width, y0 + alto_fila], fill=fondo)
        x = margen
        for i in imagenes:
            lienzo.paste(i, (x, y0 + margen), i)
            x += i.width + margen
    x, y0 = margen, alto_fila * 2 + margen
    for a in ampliados:
        lienzo.paste(a, (x, y0), a)
        x += a.width + margen
    lienzo.save(destino)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera recorder/assets/recorder.ico con Pillow.")
    parser.add_argument("--salida", type=pathlib.Path, default=SALIDA, help=f"ruta del .ico (por defecto {SALIDA})")
    parser.add_argument("--vista-previa", type=pathlib.Path, help="PNG con un mosaico de todos los tamaños, para revisarlo")
    args = parser.parse_args()
    imagenes = generar(args.salida)
    print(f"Icono escrito en {args.salida} ({', '.join(str(t) for t in TAMANOS)} px)")
    if args.vista_previa:
        vista_previa(imagenes, args.vista_previa)
        print(f"Vista previa en {args.vista_previa}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
