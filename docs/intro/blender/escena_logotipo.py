"""Construye y renderiza el logotipo 3D de la introducción de Recorder. Se ejecuta con Blender:

    blender -b -P docs\\intro\\blender\\escena_logotipo.py -- <carpeta de salida> [--solo N]

Parte de una escena vacía (no toca ningún archivo abierto), modela el micrófono del icono
(packaging/generar_icono.py) en 3D con los colores de recorder/paleta.py, anima el revelado y
escribe la secuencia PNG con fondo transparente en la carpeta de salida. Guarda la escena en
docs/intro/blender/logotipo_recorder.blend. `--solo N` renderiza únicamente el fotograma N (prueba).

Los fotogramas que salen de aquí son el material en bruto: docs/intro/blender/preparar_assets.py
los reduce de peso y los deja en recorder/assets/intro/.
"""
import importlib.util
import math
import pathlib
import sys

import bmesh
import bpy

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parents[2]
BLEND = AQUI / "logotipo_recorder.blend"


def _cargar(nombre: str, ruta: pathlib.Path):
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


paleta = _cargar("paleta", RAIZ / "recorder" / "paleta.py")
ritmo = _cargar("ritmo", AQUI / "ritmo.py")

# La identidad es la del icono: los colores del tema oscuro, por token.
TEMA = paleta.TEMAS["oscuro"]
TOKEN_BALDOSA, TOKEN_SOPORTE, TOKEN_CAPSULA, TOKEN_PUNTO, TOKEN_REJILLA = "fondo", "acento", "mic", "error", "fondo"

# Geometría del icono (packaging/generar_icono.py), en su cuadrado 0..1 con la y hacia abajo.
BALDOSA = (0.04, 0.04, 0.96, 0.96)
BALDOSA_RADIO = 0.20
ARCO_CENTRO, ARCO_RADIO = (0.50, 0.45), 0.25
GROSOR = 0.07
PIE = ((0.50, 0.69), (0.50, 0.83))
BASE = ((0.34, 0.83), (0.66, 0.83))
CAPSULA = (0.36, 0.16, 0.64, 0.57)
REJILLA_Y = (0.30, 0.37, 0.44)
REJILLA_GROSOR = 0.015
PUNTO_CENTRO, PUNTO_RADIO, PUNTO_ANILLO = (0.80, 0.21), 0.095, 0.03

# Puesta en escena
LADO = 2.0  # el cuadrado del icono mide 2 unidades de Blender
FONDO_BALDOSA = 0.20  # grosor de la baldosa
SALIENTE_MIC = 0.42  # cuánto flota el micrófono por delante de la baldosa
SALIENTE_PUNTO = 0.10
ENCUADRE = 2.2  # lado que abarca la cámara ortográfica
MUESTRAS = 48


def lineal(hexa: str) -> tuple:
    """"#rrggbb" (sRGB) a RGBA lineal, que es lo que esperan los materiales."""
    def canal(c: int) -> float:
        c /= 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return tuple(canal(int(hexa[i:i + 2], 16)) for i in (1, 3, 5)) + (1.0,)


def xz(x: float, y: float) -> tuple:
    """Del cuadrado del icono al plano frontal de Blender (X a la derecha, Z arriba)."""
    return (x - 0.5) * LADO, (0.5 - y) * LADO


def material(nombre: str, token: str, rugosidad: float = 0.45, emision: float = 0.0):
    m = bpy.data.materials.new(nombre)
    m.use_nodes = True
    bsdf = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    color = lineal(TEMA[token])
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rugosidad
    if emision:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = emision
    return m


def objeto(nombre: str, datos, coleccion, padre, mat):
    o = bpy.data.objects.new(nombre, datos)
    coleccion.objects.link(o)
    o.parent = padre
    if mat is not None:
        datos.materials.append(mat)
    return o


def malla(nombre: str, bm) -> bpy.types.Mesh:
    m = bpy.data.meshes.new(nombre)
    bm.to_mesh(m)
    bm.free()
    return m


def baldosa(coleccion, padre, mat):
    """Rectángulo redondeado extruido en profundidad, con un bisel fino en los cantos."""
    x0, z1 = xz(BALDOSA[0], BALDOSA[1])
    x1, z0 = xz(BALDOSA[2], BALDOSA[3])
    r = BALDOSA_RADIO * LADO
    pasos = 16
    perfil = []
    for cx, cz, desde in ((x1 - r, z1 - r, 0), (x0 + r, z1 - r, 90), (x0 + r, z0 + r, 180), (x1 - r, z0 + r, 270)):
        for i in range(pasos + 1):
            a = math.radians(desde + 90 * i / pasos)
            perfil.append((cx + r * math.cos(a), cz + r * math.sin(a)))
    bm = bmesh.new()
    frente = [bm.verts.new((x, -FONDO_BALDOSA / 2, z)) for x, z in perfil]
    fondo = [bm.verts.new((x, FONDO_BALDOSA / 2, z)) for x, z in perfil]
    bm.faces.new(list(reversed(frente)))
    bm.faces.new(fondo)
    n = len(perfil)
    for i in range(n):
        cara = bm.faces.new((frente[i], frente[(i + 1) % n], fondo[(i + 1) % n], fondo[i]))
        cara.smooth = True
    bm.normal_update()
    o = objeto("Baldosa", malla("Baldosa", bm), coleccion, padre, mat)
    bisel = o.modifiers.new("Bisel", "BEVEL")
    bisel.width, bisel.segments, bisel.limit_method, bisel.angle_limit = 0.03, 4, "ANGLE", math.radians(50)
    return o


def esfera(nombre, centro, radio, coleccion, padre, mat, aplastar=1.0):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=radio)
    for cara in bm.faces:
        cara.smooth = True
    o = objeto(nombre, malla(nombre, bm), coleccion, padre, mat)
    o.location = centro
    o.scale = (1.0, aplastar, 1.0)
    return o


def cilindro(nombre, centro, radio, largo, coleccion, padre, mat, hacia_camara=False):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=64, radius1=radio, radius2=radio, depth=largo)
    for cara in bm.faces:
        cara.smooth = len(cara.verts) == 4
    o = objeto(nombre, malla(nombre, bm), coleccion, padre, mat)
    o.location = centro
    if hacia_camara:
        o.rotation_euler = (math.radians(90), 0, 0)
    return o


def tubo(nombre, trazos, radio, coleccion, padre, mat, cerrado=False):
    """Curva con grosor: cada trazo es una lista de puntos (x, y, z)."""
    c = bpy.data.curves.new(nombre, "CURVE")
    c.dimensions = "3D"
    c.bevel_depth, c.bevel_resolution, c.use_fill_caps = radio, 8, True
    for puntos in trazos:
        s = c.splines.new("POLY")
        s.points.add(len(puntos) - 1)
        for p, (x, y, z) in zip(s.points, puntos):
            p.co = (x, y, z, 1.0)
        s.use_cyclic_u = cerrado
    return objeto(nombre, c, coleccion, padre, mat)


def construir():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    escena = bpy.context.scene
    escena.name = "IntroRecorder"
    col = bpy.data.collections.new("LogotipoRecorder")
    escena.collection.children.link(col)

    m_baldosa = material("Baldosa", TOKEN_BALDOSA, 0.55)
    m_soporte = material("Soporte", TOKEN_SOPORTE, 0.40)
    m_capsula = material("Capsula", TOKEN_CAPSULA, 0.35)
    m_rejilla = material("Rejilla", TOKEN_REJILLA, 0.60)
    m_punto = material("Punto", TOKEN_PUNTO, 0.35, emision=0.35)

    raiz = bpy.data.objects.new("Logotipo", None)
    col.objects.link(raiz)
    baldosa(col, raiz, m_baldosa)

    y_mic = -FONDO_BALDOSA / 2 - SALIENTE_MIC
    mic = bpy.data.objects.new("Microfono", None)
    col.objects.link(mic)
    mic.parent = raiz
    # El micrófono crece desde el centro de la cápsula
    cx, cz_alto = xz((CAPSULA[0] + CAPSULA[2]) / 2, CAPSULA[1])
    _, cz_bajo = xz(0, CAPSULA[3])
    mic.location = (cx, y_mic, (cz_alto + cz_bajo) / 2)

    def local(x, z):  # del plano frontal a coordenadas del vacío «Microfono»
        return x - mic.location.x, 0.0, z - mic.location.z

    radio = (CAPSULA[2] - CAPSULA[0]) / 2 * LADO
    alto, bajo = cz_alto - radio, cz_bajo + radio
    cilindro("CapsulaCuerpo", local(cx, (alto + bajo) / 2), radio, alto - bajo, col, mic, m_capsula)
    esfera("CapsulaArriba", local(cx, alto), radio, col, mic, m_capsula)
    esfera("CapsulaAbajo", local(cx, bajo), radio, col, mic, m_capsula)

    aros = []
    for y in REJILLA_Y:
        _, z = xz(0, y)
        aros.append([(radio * 1.005 * math.cos(a), radio * 1.005 * math.sin(a), z - mic.location.z)
                     for a in (2 * math.pi * i / 96 for i in range(96))])
    tubo("Rejilla", aros, REJILLA_GROSOR * LADO, col, mic, m_rejilla, cerrado=True)

    ax, az = xz(*ARCO_CENTRO)
    r_arco = ARCO_RADIO * LADO
    arco = [local(ax + r_arco * math.cos(a), az + r_arco * math.sin(a))
            for a in (math.pi + math.pi * i / 64 for i in range(65))]
    pie = [local(*xz(*p)) for p in PIE]
    base = [local(*xz(*p)) for p in BASE]
    r_tubo = GROSOR / 2 * LADO
    tubo("Soporte", [arco, pie, base], r_tubo, col, mic, m_soporte)
    for i, punta in enumerate((arco[0], arco[-1], base[0], base[1])):  # remates redondos
        esfera(f"SoporteRemate{i + 1}", punta, r_tubo, col, mic, m_soporte)

    px, pz = xz(*PUNTO_CENTRO)
    punto = bpy.data.objects.new("PuntoGrabando", None)
    col.objects.link(punto)
    punto.parent = raiz
    punto.location = (px, -FONDO_BALDOSA / 2 - SALIENTE_PUNTO, pz)
    r_punto = PUNTO_RADIO * LADO
    esfera("Punto", (0, 0, 0), r_punto, col, punto, m_punto, aplastar=0.55)
    cilindro("PuntoAnillo", (0, SALIENTE_PUNTO / 2, 0), r_punto + PUNTO_ANILLO * LADO, SALIENTE_PUNTO * 0.9,
             col, punto, m_rejilla, hacia_camara=True)

    # Cámara ortográfica de frente: el último fotograma coincide con el icono
    cam = bpy.data.objects.new("CamaraIntro", bpy.data.cameras.new("CamaraIntro"))
    col.objects.link(cam)
    cam.data.type, cam.data.ortho_scale = "ORTHO", ENCUADRE
    cam.location, cam.rotation_euler = (0, -10, 0), (math.radians(90), 0, 0)
    escena.camera = cam

    def luz(nombre, tipo, energia, giro, **extra):
        datos = bpy.data.lights.new(nombre, tipo)
        datos.energy = energia
        for k, v in extra.items():
            setattr(datos, k, v)
        o = bpy.data.objects.new(nombre, datos)
        col.objects.link(o)
        o.rotation_euler = tuple(math.radians(g) for g in giro)
        return o

    luz("LuzPrincipal", "SUN", 2.6, (52, 0, -32), angle=math.radians(12))  # arriba a la izquierda
    luz("LuzRelleno", "SUN", 0.9, (80, 0, 50), angle=math.radians(40))
    mundo = bpy.data.worlds.new("MundoIntro")
    mundo.use_nodes = True
    fondo = next(n for n in mundo.node_tree.nodes if n.type == "BACKGROUND")
    fondo.inputs["Color"].default_value = (1, 1, 1, 1)
    fondo.inputs["Strength"].default_value = 0.55
    escena.world = mundo

    animar(escena, raiz, mic, punto)
    ajustar_render(escena)
    return escena


def animar(escena, raiz, mic, punto):
    """Una clave por fotograma con las curvas de ritmo.py: lo que se ve es exactamente esa curva."""
    escena.render.fps = ritmo.FPS
    escena.frame_start, escena.frame_end = 1, ritmo.FOTOGRAMAS
    minimo = 0.001  # Blender no admite escala 0 limpia

    for f in range(1, ritmo.FOTOGRAMAS + 1):
        giro = ritmo.ease_out(ritmo.avance(f, *ritmo.GIRO))
        raiz.rotation_euler = (math.radians(ritmo.CABECEO_INICIAL * (1 - giro)), 0,
                               math.radians(ritmo.GIRO_INICIAL * (1 - giro)))
        e = ritmo.ESCALA_INICIAL + (1 - ritmo.ESCALA_INICIAL) * giro
        raiz.scale = (e, e, e)
        raiz.keyframe_insert("rotation_euler", frame=f)
        raiz.keyframe_insert("scale", frame=f)
        for obj, tramo in ((mic, ritmo.MICROFONO), (punto, ritmo.PUNTO)):
            e = max(minimo, ritmo.ease_out_rebote(ritmo.avance(f, *tramo)))
            obj.scale = (e, e, e)
            obj.keyframe_insert("scale", frame=f)


def ajustar_render(escena):
    r = escena.render
    r.engine = "BLENDER_EEVEE"
    r.resolution_x = r.resolution_y = ritmo.LADO_PX
    r.resolution_percentage = 100
    r.film_transparent = True
    if hasattr(r.image_settings, "media_type"):
        r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "PNG"
    r.image_settings.color_mode = "RGBA"
    r.image_settings.color_depth = "8"
    escena.view_settings.view_transform = "Standard"  # sin curva de película: los colores son los de la paleta
    escena.view_settings.look = "None"
    escena.eevee.taa_render_samples = MUESTRAS


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not args:
        raise SystemExit("Falta la carpeta de salida: blender -b -P escena_logotipo.py -- <carpeta>")
    salida = pathlib.Path(args[0]).resolve()
    salida.mkdir(parents=True, exist_ok=True)
    escena = construir()
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    if "--solo" in args:
        escena.frame_set(int(args[args.index("--solo") + 1]))
        escena.render.filepath = str(salida / f"prueba_{escena.frame_current:03d}.png")
        bpy.ops.render.render(write_still=True)
    else:
        escena.render.filepath = str(salida / "logo_")
        bpy.ops.render.render(animation=True)


main()
