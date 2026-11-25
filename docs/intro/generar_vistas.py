"""Dibuja la introducción tal como la describe recorder/assets/intro/intro.json, para revisarla sin la app.

    python docs\\intro\\generar_vistas.py            # miniaturas, tira del logotipo, terminal y vistas animadas
    python docs\\intro\\generar_vistas.py --contraste  # solo la tabla de contraste del logotipo de terminal

Es un reproductor de referencia: no usa nada que Tkinter no pueda hacer (fotogramas PNG, texto,
rectángulos y líneas, y fundidos como mezcla de color con el fondo). Todo sale del contrato y de
recorder/paleta.py; aquí no hay tiempos ni colores propios. Escribe en docs/intro/img/. Necesita
Pillow y las fuentes de Windows.
"""
import importlib.util
import json
import math
import pathlib
import re
import sys

from PIL import Image, ImageDraw, ImageFont

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
ASSETS = RAIZ / "recorder" / "assets" / "intro"
IMG = AQUI / "img"
FUENTES = pathlib.Path("C:/Windows/Fonts")
SOBREMUESTREO = 2  # se dibuja al doble y se reduce: bordes limpios
PX_POR_PUNTO = 96 / 72
INSTANTES_MS = (1500, 2400, 2800, 4450, 5900, 7300)  # una miniatura por momento clave
FPS_VISTA = 24
FONDOS_TERMINAL = {"negro": "#000000", "azul-powershell": "#012456"}  # docs/plan-pulido-terminal.md §1
FUENTE_TERMINAL = {"completo": "CascadiaMono.ttf", "consola": "consola.ttf", "ascii": "consola.ttf"}
CUERPO_TERMINAL = 20

_spec = importlib.util.spec_from_file_location("paleta", RAIZ / "recorder" / "paleta.py")
paleta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(paleta)

C = json.loads((ASSETS / "intro.json").read_text(encoding="utf-8"))
D = C["duraciones_ms"]
CURVAS = {
    "ease_out": lambda t: 1 - (1 - t) ** 3,
    "ease_in_out": lambda t: 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2,
    "lineal": lambda t: t,
}


def mezclar(a: str, b: str, t: float) -> str:
    """Como recorder/ui/animacion.py: el color entre `a` (t=0) y `b` (t=1)."""
    t = min(1.0, max(0.0, t))
    ca, cb = (tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in (a, b))
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def paso(escena: str, elemento: str, accion: str) -> dict:
    e = next(e for e in C["escenas"] if e["id"] == escena)
    p = next(p for p in e["pasos"] if p["elemento"] == elemento and p["accion"] == accion)
    return {**p, "t0": e["inicio_ms"] + p["inicio_ms"]}


def avance(p: dict, t: float, retraso: float = 0.0) -> float:
    """De 0 a 1, ya con su curva, cuánto lleva el paso `p` en el instante `t`."""
    crudo = (t - p["t0"] - retraso) / D[p["duracion"]]
    return CURVAS[p["curva"]](min(1.0, max(0.0, crudo)))


def fuente(estilo: dict, escala: float) -> ImageFont.FreeTypeFont:
    archivo = "seguisb.ttf" if estilo.get("peso") == "semibold" else "segoeui.ttf"
    if not (FUENTES / archivo).exists():
        archivo = "segoeuib.ttf"
    return ImageFont.truetype(str(FUENTES / archivo), round(estilo["puntos"] * PX_POR_PUNTO * escala))


def texto_en(t: float, elemento: str):
    """(clave de texto, opacidad) de «titulo» o «subtitulo»: el anterior se va y después entra el nuevo."""
    clave, opacidad = None, 0.0
    for e in C["escenas"]:
        for p in e["pasos"]:
            if p["elemento"] != elemento or e["inicio_ms"] + p["inicio_ms"] > t:
                continue
            p = {**p, "t0": e["inicio_ms"] + p["inicio_ms"]}
            if p["accion"] == "fundido_entrada":
                clave, opacidad = p["texto"], avance(p, t)
            elif p["accion"] == "fundido_cruzado":
                salida = avance(p, t)
                if salida < 1:
                    opacidad *= 1 - salida
                else:
                    entra = {**p, "t0": p["t0"] + D[p["duracion"]], "duracion": "fundido_texto"}
                    clave, opacidad = p["texto"], avance(entra, t)
    return clave, opacidad


def fotograma(t: float, tema: str, escala: float = 1.0) -> Image.Image:
    """La introducción en el instante `t` (ms) con el tema `tema`."""
    P = paleta.TEMAS[tema]
    s = escala * SOBREMUESTREO
    fondo = P[C["lienzo"]["color"]]
    img = Image.new("RGB", (round(C["lienzo"]["ancho"] * s), round(C["lienzo"]["alto"] * s)), fondo)
    d = ImageDraw.Draw(img)
    disp, tipo, ilu = C["disposicion"], C["tipografia"], C["ilustracion"]

    def caja(x0, y0, x1, y1, **kw):
        d.rectangle([x0 * s, y0 * s, x1 * s, y1 * s], **kw)

    def tinta(token: str, opacidad: float) -> str:
        return mezclar(fondo, P[token], opacidad)

    # --- ilustración: equipo, trazos y captura
    ox, oy = disp["ilustracion"]["origen"]
    eq = ilu["equipo"]
    a_equipo = avance(paso("transcribe", "equipo", "fundido_entrada"), t)
    a_base = a_equipo * (1 - avance(paso("notas", "equipo_base", "fundido_salida"), t))
    if a_equipo > 0:
        x0, y0, x1, y1 = eq["pantalla"]
        caja(ox + x0, oy + y0, ox + x1, oy + y1, outline=tinta(eq["color"], a_equipo), width=round(eq["grosor"] * s))
    if a_base > 0:
        x0, y0, x1, y1 = eq["base"]
        d.line([(ox + x0) * s, (oy + y0) * s, (ox + x1) * s, (oy + y1) * s], fill=tinta(eq["color"], a_base),
               width=round(eq["grosor_base"] * s))

    onda, lineas, nota = ilu["onda"], ilu["lineas"], ilu["nota"]
    entra = paso("graba", "onda", "fundido_entrada")
    a_onda = avance(entra, t)
    if a_onda > 0:
        conv, tenir = paso("graba", "onda", "convertir_en_lineas"), paso("transcribe", "lineas", "teñir")
        reord = paso("notas", "lineas", "reordenar_en_nota")
        grosor = ilu["grosor_trazo"]
        por_linea = len(lineas["trazos"]) // 3
        for i, (lin, nt) in enumerate(zip(lineas["trazos"], nota["trazos"])):
            fase = 2 * math.pi * (t - entra["t0"]) / D["onda_periodo"] + i * onda["desfase_rad"]
            alto = onda["alto_min"] + (onda["alto_max"] - onda["alto_min"]) * onda["envolvente"][i] * (0.5 + 0.5 * math.sin(fase))
            barra = (onda["x_primera"] + i * onda["paso"], onda["centro_y"], onda["ancho"], alto)
            a, b = avance(conv, t, i * D[conv["escalonado"]]), avance(reord, t)
            x, y, w, h = (barra[k] + ((lin + [grosor])[k] - barra[k]) * a for k in range(4))
            x, y, w = x + (nt[0] - x) * b, y + (nt[1] - y) * b, w + (nt[2] - w) * b
            color_linea = lineas["color_clave"] if i == lineas["trazo_clave"] else lineas["color"]
            color_nota = {nota["trazo_marca"]: nota["color_marca"], nota["trazo_titulo"]: nota["color_titulo"]}.get(i, nota["color"])
            color = mezclar(P[onda["color"]], P[color_linea], avance(tenir, t, (i // por_linea) * D[tenir["escalonado"]]))
            color = mezclar(color, P[color_nota], b)
            caja(ox + x, oy + y - h / 2, ox + x + w, oy + y + h / 2, fill=mezclar(fondo, color, a_onda))

    cap = ilu["captura"]
    a_cap = avance(paso("notas", "captura", "fundido_entrada"), t)
    if a_cap > 0:
        x0, y0, x1, y1 = cap["caja"]
        caja(ox + x0, oy + y0, ox + x1, oy + y1, fill=tinta(cap["fondo"], a_cap), outline=tinta(cap["borde"], a_cap), width=round(s))
        x0, y0, x1, y1 = cap["franja"]
        caja(ox + x0 + 1, oy + y0 + 1, ox + x1 - 1, oy + y1, fill=tinta(cap["color_franja"], a_cap))

    # --- textos
    a_rotulo = avance(paso("logotipo", "rotulo", "fundido_entrada"), t) * (1 - avance(paso("graba", "rotulo", "fundido_salida"), t))
    if a_rotulo > 0:
        x, y = disp["rotulo"]["centro"]
        d.text((x * s, y * s), C["textos"]["intro.nombre"], font=fuente(tipo["rotulo"], s), anchor="mm",
               fill=tinta(tipo["rotulo"]["color"], a_rotulo))
    for elemento in ("titulo", "subtitulo"):
        clave, opacidad = texto_en(t, elemento)
        if clave and opacidad > 0:
            x, y = disp[elemento]["origen"]
            f = fuente(tipo[elemento], s)
            if f.getlength(C["textos"][clave]) > disp[elemento]["ancho"] * s:
                raise SystemExit(f"«{C['textos'][clave]}» no cabe en el ancho de «{elemento}»")
            d.text((x * s, y * s), C["textos"][clave], font=f, fill=tinta(tipo[elemento]["color"], opacidad))
    x, y = disp["pista"]["origen"]
    d.text((x * s, y * s), C["textos"]["intro.pista"], font=fuente(tipo["pista"], s), anchor="lm", fill=P[tipo["pista"]["color"]])

    # --- botón: «Saltar» desde el primer fotograma; al final pasa a «Comenzar»
    cambio = avance(paso("comenzar", "boton", "pasar_a_principal"), t)
    sec, pri = C["boton"]["secundario"], C["boton"]["principal"]
    x0, y0, x1, y1 = disp["boton"]["caja"]
    caja(x0, y0, x1, y1, fill=mezclar(P[sec["fondo"]], P[pri["fondo"]], cambio),
         outline=mezclar(P[sec["borde"]], P[pri["borde"]], cambio), width=round(s))
    estado = pri if cambio >= 0.5 else sec
    d.text(((x0 + x1) / 2 * s, (y0 + y1) / 2 * s), C["textos"][estado["rotulo"]], font=fuente(tipo["boton"], s), anchor="mm",
           fill=mezclar(P[sec["texto"]], P[pri["texto"]], cambio))

    img = img.resize((img.width // SOBREMUESTREO, img.height // SOBREMUESTREO), Image.LANCZOS)

    # --- logotipo: el fotograma que toca, donde toca
    logo = C["logotipo"]
    n = min(logo["fotogramas"], int(t * logo["fps"] / 1000) + 1)
    hoja = Image.open(ASSETS / logo["patron"].format(n=n)).convert("RGBA")
    lado = round(logo["lado"] * escala)
    hoja = hoja.resize((lado, lado), Image.LANCZOS)
    mov = avance(paso("graba", "logotipo", "desplazar"), t)
    cx, cy = (a + (b - a) * mov for a, b in zip(logo["centro_inicial"], logo["centro_final"]))
    img.paste(hoja, (round(cx * escala - lado / 2), round(cy * escala - lado / 2)), hoja)
    return img


def miniaturas() -> None:
    for tema in paleta.TEMAS:
        for n, t in enumerate(INSTANTES_MS, start=1):
            fotograma(t, tema).save(IMG / f"escena-{n}-{tema}.png", optimize=True)
        cuadros = [fotograma(i * 1000 / FPS_VISTA, tema, escala=0.75) for i in range(round(D["total"] * FPS_VISTA / 1000))]
        cuadros += [cuadros[-1]] * FPS_VISTA  # un segundo quieto antes de repetir
        cuadros[0].save(IMG / f"vista-previa-{tema}.webp", save_all=True, append_images=cuadros[1:],
                        duration=round(1000 / FPS_VISTA), loop=0, quality=80, method=6)


def tira_logotipo() -> None:
    logo = C["logotipo"]
    elegidos = [1, 3, 5, 8, 12, 16, 20, 24, 28, logo["fotogramas"]]
    lado = 120
    tira = Image.new("RGB", (lado * len(elegidos), lado * len(paleta.TEMAS)))
    for fila, tema in enumerate(paleta.TEMAS.values()):
        for col, n in enumerate(elegidos):
            hoja = Image.open(ASSETS / logo["patron"].format(n=n)).convert("RGBA").resize((lado, lado), Image.LANCZOS)
            celda = Image.new("RGBA", (lado, lado), tema["fondo"])
            celda.alpha_composite(hoja)
            tira.paste(celda.convert("RGB"), (col * lado, fila * lado))
    tira.save(IMG / "logotipo-tira.png", optimize=True)


def estilos_terminal(estilo: str, P: dict):
    """(color, visible) de un estilo de rich del contrato («bold acento», «tenue», «oculto»)."""
    from_rich = {"texto": "texto", "tenue": "texto_tenue", "acento": "acento", "mic": "mic", "error": "error"}  # consola.ESTILOS
    nombre = estilo.split()[-1]
    return (None, False) if nombre == "oculto" else (P[from_rich[nombre]], True)


def terminal() -> None:
    P = paleta.TEMAS[paleta.POR_DEFECTO]
    T = C["terminal"]
    final = T["pasos"][-1]["estilos"]
    for juego, archivo in T["juegos"].items():
        lineas = (ASSETS / archivo).read_text(encoding="utf-8").replace("{lema}", C["textos"]["intro.terminal.lema"]).split("\n")
        f = ImageFont.truetype(str(FUENTES / FUENTE_TERMINAL[juego]), CUERPO_TERMINAL)
        ancho_celda, alto_celda = f.getlength("M"), round(CUERPO_TERMINAL * 1.2)
        columnas = max(len(re.sub(r"\[/?\w*\]", "", l)) for l in lineas) + 2
        if columnas > 60:
            raise SystemExit(f"El logotipo «{juego}» ocupa {columnas} columnas: no cabe en 60")
        ancho, alto = round(columnas * ancho_celda), alto_celda * len(lineas)
        hoja = Image.new("RGB", (ancho, alto * len(FONDOS_TERMINAL)))
        d = ImageDraw.Draw(hoja)
        for fila, fondo in enumerate(FONDOS_TERMINAL.values()):
            d.rectangle([0, fila * alto, ancho, (fila + 1) * alto], fill=fondo)
            for j, linea in enumerate(lineas):
                col = 0
                for papel, tramo, suelto in re.findall(r"\[(\w+)\](.*?)\[/\]|([^\[]+)", linea):
                    color, visible = estilos_terminal(final[papel], P) if papel else (None, False)
                    if visible:
                        d.text((col * ancho_celda, fila * alto + j * alto_celda), tramo, font=f, fill=color)
                    col += len(tramo or suelto)
        hoja.save(IMG / f"terminal-{juego}.png", optimize=True)


def contraste() -> None:
    P = paleta.TEMAS[paleta.POR_DEFECTO]
    usados = sorted({e.split()[-1] for p in C["terminal"]["pasos"] for e in p["estilos"].values()} - {"oculto"})
    print("| Estilo | " + " | ".join(FONDOS_TERMINAL) + " |\n| :--- | " + " | ".join(":-:" for _ in FONDOS_TERMINAL) + " |")
    for estilo in usados:
        color, _ = estilos_terminal(estilo, P)
        print(f"| `{estilo}` | " + " | ".join(f"{paleta.contraste(color, f):.1f}:1" for f in FONDOS_TERMINAL.values()) + " |")


def main() -> int:
    if "--contraste" not in sys.argv:
        IMG.mkdir(exist_ok=True)
        miniaturas()
        tira_logotipo()
        terminal()
        peso = sum(f.stat().st_size for f in IMG.iterdir())
        print(f"Vistas en {IMG} ({peso / 1024:.0f} KB)")
    contraste()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
