#!/usr/bin/env python3
"""Genera los iconos de lanzador de la app a partir del diseno del manifest.

El manifest de index.html lleva los iconos como SVG dentro de un data: URI. Android no
puede usar eso: necesita PNG en varias densidades, mas un icono adaptativo (fondo y
primer plano separados) para Android 8 en adelante.

Para que el icono de la app sea exactamente el mismo dibujo que el de la PWA, aqui se
reproducen los primitivos del SVG original tal cual, incluido el renderizado de los
arcos con la parametrizacion endpoint-to-center de la especificacion SVG. Se dibuja a
4x y se reduce con LANCZOS para tener bordes suaves sin depender de un rasterizador.

Uso:  python tools/make_icons.py
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

RED = (0xE0, 0x3A, 0x3E, 255)
INK = (0x0B, 0x0B, 0x0B, 255)

SS = 4  # factor de supermuestreo

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android" / "app" / "src" / "main" / "res"

LEGACY_SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
FOREGROUND_SIZES = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}

# El SVG del manifest trabaja sobre un lienzo de 192x192 con el balon en (96, 96) r=55.
DESIGN = 192.0
BALL_CX, BALL_CY, BALL_R = 96.0, 96.0, 55.0

# Los trazos del balon, copiados del SVG del manifest:
#   <circle cx=96 cy=96 r=55 stroke-width=8/>
#   <line x1=41 y1=96 x2=151 y2=96 stroke-width=6/>
#   <path d='M96 41 A55 55 0 0 1 96 151' stroke-width=6/>
#   <path d='M73 55 A75 75 0 0 1 63 137' stroke-width=5/>
#   <path d='M129 55 A75 75 0 0 0 129 137' stroke-width=5/>
BALL_ARCS = [
    # (x1, y1, rx, ry, large_arc, sweep, x2, y2, stroke_width)
    (96.0, 41.0, 55.0, 55.0, 0, 1, 96.0, 151.0, 6.0),
    (73.0, 55.0, 75.0, 75.0, 0, 1, 63.0, 137.0, 5.0),
    (129.0, 55.0, 75.0, 75.0, 0, 0, 129.0, 137.0, 5.0),
]


def arc_points(x1, y1, rx, ry, large_arc, sweep, x2, y2, steps=160):
    """Convierte un arco SVG en una polilinea (parametrizacion endpoint-to-center)."""
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [(x1, y1), (x2, y2)]

    rx, ry = abs(rx), abs(ry)
    dx2, dy2 = (x1 - x2) / 2.0, (y1 - y2) / 2.0

    # Si los radios son demasiado pequenos para unir los extremos, se escalan (F.6.6).
    lam = (dx2 * dx2) / (rx * rx) + (dy2 * dy2) / (ry * ry)
    if lam > 1:
        scale = math.sqrt(lam)
        rx, ry = rx * scale, ry * scale

    num = rx * rx * ry * ry - rx * rx * dy2 * dy2 - ry * ry * dx2 * dx2
    den = rx * rx * dy2 * dy2 + ry * ry * dx2 * dx2
    coef = math.sqrt(max(0.0, num / den))
    if large_arc == sweep:
        coef = -coef

    cxp = coef * rx * dy2 / ry
    cyp = -coef * ry * dx2 / rx
    cx = cxp + (x1 + x2) / 2.0
    cy = cyp + (y1 + y2) / 2.0

    theta1 = math.atan2((dy2 - cyp) / ry, (dx2 - cxp) / rx)
    theta2 = math.atan2((-dy2 - cyp) / ry, (-dx2 - cxp) / rx)
    delta = theta2 - theta1
    if sweep == 0 and delta > 0:
        delta -= 2 * math.pi
    elif sweep == 1 and delta < 0:
        delta += 2 * math.pi

    return [
        (cx + rx * math.cos(theta1 + delta * i / steps),
         cy + ry * math.sin(theta1 + delta * i / steps))
        for i in range(steps + 1)
    ]


def draw_ball(draw, scale, ox, oy):
    """Dibuja el balon en unidades de diseno, transformado por scale y offset."""
    def tx(x, y):
        return (ox + x * scale, oy + y * scale)

    def w(width):
        return max(1, round(width * scale))

    # El circulo se dibuja como polilinea y no con draw.ellipse porque PIL pinta el
    # grosor del contorno hacia dentro del rectangulo, mientras que en SVG el trazo va
    # centrado sobre el path. Mezclar ambos convenios deja escalones visibles donde el
    # arco vertical se apoya sobre el contorno.
    circle = [
        (BALL_CX + BALL_R * math.cos(2 * math.pi * i / 240),
         BALL_CY + BALL_R * math.sin(2 * math.pi * i / 240))
        for i in range(241)
    ]
    draw.line([tx(px, py) for px, py in circle], fill=INK, width=w(8.0), joint="curve")

    a = tx(41.0, 96.0)
    b = tx(151.0, 96.0)
    draw.line([a, b], fill=INK, width=w(6.0))

    for spec in BALL_ARCS:
        pts = arc_points(*spec[:8])
        draw.line([tx(px, py) for px, py in pts], fill=INK, width=w(spec[8]),
                  joint="curve")


def render(size, shape):
    """shape: 'square' (icono clasico), 'circle' (icono redondo) o 'fg' (adaptativo)."""
    big = size * SS
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if shape == "square":
        draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=big * (28.0 / DESIGN),
                               fill=RED)
        scale = big / DESIGN
        ox = oy = 0.0
    elif shape == "circle":
        draw.ellipse([0, 0, big - 1, big - 1], fill=RED)
        # el recorte circular come esquinas, asi que el balon va algo mas pequeno
        scale = big / DESIGN * 0.88
        ox = oy = (big - DESIGN * scale) / 2.0
    elif shape == "fg":
        # El primer plano adaptativo se recorta: solo el 66/108 central esta garantizado,
        # asi que el balon se encaja dentro de esa zona segura.
        target_r = big * 0.25
        scale = target_r / BALL_R
        ox = big / 2.0 - BALL_CX * scale
        oy = big / 2.0 - BALL_CY * scale
    else:
        raise ValueError("forma desconocida: %s" % shape)

    draw_ball(draw, scale, ox, oy)
    return img.resize((size, size), Image.LANCZOS)


def write_adaptive_xml(path):
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/theme_red" />\n'
        '    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n'
        '    <monochrome android:drawable="@mipmap/ic_launcher_foreground" />\n'
        '</adaptive-icon>\n',
        encoding="utf-8")


def main():
    written = 0
    for density, legacy in LEGACY_SIZES.items():
        out = RES / ("mipmap-" + density)
        out.mkdir(parents=True, exist_ok=True)
        render(legacy, "square").save(out / "ic_launcher.png")
        render(legacy, "circle").save(out / "ic_launcher_round.png")
        render(FOREGROUND_SIZES[density], "fg").save(out / "ic_launcher_foreground.png")
        written += 3
        print("  mipmap-%-8s %3dpx clasico / %3dpx primer plano"
              % (density, legacy, FOREGROUND_SIZES[density]))

    anydpi = RES / "mipmap-anydpi-v26"
    anydpi.mkdir(parents=True, exist_ok=True)
    write_adaptive_xml(anydpi / "ic_launcher.xml")
    write_adaptive_xml(anydpi / "ic_launcher_round.xml")
    written += 2

    # Vista previa grande, util para revisar el resultado sin instalar nada.
    preview = ROOT / "tools" / "icon-preview.png"
    render(512, "square").save(preview)

    print("\n%d ficheros de icono en %s" % (written, RES))
    print("vista previa: %s" % preview)
    return 0


if __name__ == "__main__":
    sys.exit(main())
