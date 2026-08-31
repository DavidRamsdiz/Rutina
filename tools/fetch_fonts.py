#!/usr/bin/env python3
"""Empaqueta las tipografias de Google Fonts dentro del APK.

index.html carga Oswald / IBM Plex Sans / IBM Plex Mono desde fonts.googleapis.com.
Dentro de la app eso significaria que sin conexion la rutina se ve con la fuente por
defecto del sistema. Este script baja la hoja de estilos y todos los .woff2, los guarda
en android/app/src/main/assets/www/fonts/ y reescribe las URLs para que apunten al
origen local que sirve WebViewAssetLoader.

MainActivity intercepta las peticiones a fonts.googleapis.com y devuelve el fonts.css
generado aqui, asi que la app no habla nunca con Google.

Uso:  python tools/fetch_fonts.py
"""

import re
import sys
import urllib.request
from pathlib import Path

FONTS_CSS_URL = (
    "https://fonts.googleapis.com/css2"
    "?family=Oswald:wght@500;600;700"
    "&family=IBM+Plex+Sans:wght@400;500;600"
    "&family=IBM+Plex+Mono:wght@500"
    "&display=swap"
)

# Con un User-Agent de Chrome, Google devuelve woff2 (el formato mas compacto).
# Con el UA por defecto de urllib devolveria ttf, que pesa varias veces mas.
CHROME_UA = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36"
)

LOCAL_ORIGIN = "https://appassets.androidplatform.net/assets/www/fonts"

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "android" / "app" / "src" / "main" / "assets" / "www" / "fonts"


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": CHROME_UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    css = get(FONTS_CSS_URL).decode("utf-8")
    urls = sorted(set(re.findall(r"https://fonts\.gstatic\.com/[^)\s]+\.woff2", css)))
    if not urls:
        print("error: la hoja de estilos no traia ninguna url woff2", file=sys.stderr)
        return 1

    # Nombres estables y cortos: el mismo orden de URLs da siempre el mismo fichero,
    # asi que reejecutar el script no genera ruido en el diff.
    total = 0
    for i, url in enumerate(urls, start=1):
        name = "font%02d.woff2" % i
        data = get(url)
        (OUT_DIR / name).write_bytes(data)
        css = css.replace(url, "%s/%s" % (LOCAL_ORIGIN, name))
        total += len(data)
        print("  %-14s %6.1f KB  <- %s" % (name, len(data) / 1024, url.split("/")[-1]))

    if "fonts.gstatic.com" in css:
        print("error: quedaron urls de gstatic sin reescribir", file=sys.stderr)
        return 1

    header = "/* Generado por tools/fetch_fonts.py. No editar a mano. */\n"
    (OUT_DIR / "fonts.css").write_text(header + css, encoding="utf-8")

    # Limpia ficheros de ejecuciones anteriores con mas fuentes que la actual.
    keep = {"fonts.css"} | {"font%02d.woff2" % i for i in range(1, len(urls) + 1)}
    for stale in OUT_DIR.iterdir():
        if stale.name not in keep:
            stale.unlink()
            print("  eliminado sobrante: %s" % stale.name)

    print("\n%d fuentes, %.0f KB en total -> %s" % (len(urls), total / 1024, OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main())
