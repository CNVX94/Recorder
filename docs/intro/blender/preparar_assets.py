"""Deja en recorder/assets/intro/ los fotogramas del logotipo listos para la aplicación.

    python docs\\intro\\blender\\preparar_assets.py <carpeta con los logo_NNNN.png de Blender>

Cada fotograma en bruto de escena_logotipo.py (RGBA, ~170 KB) se reduce a un PNG de paleta con
transparencia, que es lo que lo hace caber en el presupuesto: el interior opaco va a una paleta
propia con tramado (sin él, las sombras suaves salen a manchas) y el borde suavizado de la silueta
a unos pocos niveles de transparencia. Escribe además el fotograma estático de reserva y comprueba
que la secuencia coincide con lo que declara recorder/assets/intro/intro.json. Necesita Pillow.
"""
import json
import pathlib
import sys

from PIL import Image, ImageStat

import ritmo

RAIZ = pathlib.Path(__file__).resolve().parents[3]
DESTINO = RAIZ / "recorder" / "assets" / "intro"
CONTRATO = DESTINO / "intro.json"
PRESUPUESTO_BYTES = 3 * 1024 * 1024
NIVELES_BORDE = 16  # entradas de la paleta para el borde: de transparente a casi opaco
COLORES_INTERIOR = 256 - NIVELES_BORDE
OPACO = 250  # a partir de esta opacidad un píxel cuenta como interior


def reducir(img: Image.Image) -> Image.Image:
    """RGBA a paleta de 256 entradas: interior tramado + borde de la silueta en NIVELES_BORDE opacidades."""
    alfa = img.getchannel("A")
    rgb = img.convert("RGB")
    interior = alfa.point(lambda a: 255 if a >= OPACO else 0)
    if not interior.getbbox():  # nada opaco (no debería pasar): el método directo de Pillow
        return img.quantize(256, method=Image.Quantize.FASTOCTREE)
    # La paleta sale solo de los píxeles opacos: el resto se rellena con su color medio para no gastar entradas
    medio = tuple(round(c) for c in ImageStat.Stat(rgb, mask=interior).mean)
    solido = Image.composite(rgb, Image.new("RGB", rgb.size, medio), interior)
    paleta = solido.quantize(COLORES_INTERIOR, method=Image.Quantize.MEDIANCUT)
    indices = solido.quantize(palette=paleta, dither=Image.Dither.FLOYDSTEINBERG)

    borde = alfa.point(lambda a: 255 if 0 < a < OPACO else 0)
    color_borde = tuple(round(c) for c in ImageStat.Stat(rgb, mask=borde).mean) if borde.getbbox() else medio
    nivel = alfa.point(lambda a: COLORES_INTERIOR + round(a / 255 * (NIVELES_BORDE - 1)))
    crudos = Image.frombytes("L", img.size, indices.tobytes())  # los índices tal cual, no su color
    salida = Image.frombytes("P", img.size, Image.composite(crudos, nivel, interior).tobytes())
    colores = (paleta.getpalette() + [0] * 768)[:COLORES_INTERIOR * 3] + list(color_borde) * NIVELES_BORDE
    salida.putpalette(colores)
    salida.info["transparency"] = bytes([255] * COLORES_INTERIOR
                                        + [round(k / (NIVELES_BORDE - 1) * 255) for k in range(NIVELES_BORDE)])
    return salida


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    brutos = sorted(pathlib.Path(sys.argv[1]).glob("logo_*.png"))
    if len(brutos) != ritmo.FOTOGRAMAS:
        raise SystemExit(f"Se esperaban {ritmo.FOTOGRAMAS} fotogramas y hay {len(brutos)}")
    contrato = json.loads(CONTRATO.read_text(encoding="utf-8"))["logotipo"]
    carpeta = DESTINO / pathlib.Path(contrato["patron"]).parent
    carpeta.mkdir(parents=True, exist_ok=True)
    for viejo in carpeta.glob("*.png"):
        viejo.unlink()

    for n, ruta in enumerate(brutos, start=1):
        reducir(Image.open(ruta).convert("RGBA")).save(DESTINO / contrato["patron"].format(n=n), optimize=True)
    reducir(Image.open(brutos[-1]).convert("RGBA")).save(DESTINO / contrato["estatico"], optimize=True)

    declarado = (contrato["fps"], contrato["fotogramas"], contrato["lado_px"])
    real = (ritmo.FPS, ritmo.FOTOGRAMAS, Image.open(brutos[0]).width)
    if declarado != real:
        raise SystemExit(f"intro.json declara (fps, fotogramas, lado) = {declarado} y la secuencia es {real}")
    peso = sum(f.stat().st_size for f in DESTINO.rglob("*") if f.is_file())
    print(f"{ritmo.FOTOGRAMAS} fotogramas en {carpeta}; peso total de {DESTINO.name}/: {peso / 1024:.0f} KB")
    if peso > PRESUPUESTO_BYTES:
        raise SystemExit("Se pasa del presupuesto de 3 MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
