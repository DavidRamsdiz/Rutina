#!/usr/bin/env python3
"""Comprobaciones estaticas del proyecto Android, sin necesidad de toolchain.

No sustituye a una compilacion real, pero pilla lo que se rompe con mas facilidad al
editar a mano: XML mal formado, recursos referenciados que no existen, desajustes entre
el paquete Java y el namespace de Gradle, placeholders de getString que no cuadran y
delimitadores desbalanceados.

Uso:  python tools/check_project.py
"""

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "android" / "app" / "src" / "main" / "res"
JAVA = ROOT / "android" / "app" / "src" / "main" / "java" / "es" / "davidramos" / "rutina" / "MainActivity.java"
MANIFEST = ROOT / "android" / "app" / "src" / "main" / "AndroidManifest.xml"
APP_GRADLE = ROOT / "android" / "app" / "build.gradle.kts"

failures = []


def fail(msg):
    failures.append(msg)
    print("  FALLO: %s" % msg)


def names_in(path):
    return set(re.findall(r'name="([^"]+)"', path.read_text(encoding="utf-8")))


def check_xml_wellformed():
    files = sorted(Path(ROOT / "android").rglob("*.xml"))
    for f in files:
        try:
            ET.parse(f)
        except Exception as e:
            fail("XML mal formado %s: %s" % (f.relative_to(ROOT), e))
    print("1) %d ficheros XML parseados" % len(files))
    return files


def check_resource_refs(xml_files):
    strings = names_in(RES / "values" / "strings.xml")
    colors = names_in(RES / "values" / "colors.xml")
    styles = names_in(RES / "values" / "themes.xml")
    mipmaps = {p.stem for p in RES.glob("mipmap-*/*")}

    for f in xml_files:
        text = f.read_text(encoding="utf-8")
        for kind, pool in (("string", strings), ("color", colors),
                           ("mipmap", mipmaps), ("style", styles)):
            for ref in re.findall(r"@%s/([A-Za-z0-9_]+)" % kind, text):
                if ref not in pool:
                    fail("@%s/%s no existe (referenciado en %s)" % (kind, ref, f.name))
    print("2) strings=%d colors=%d styles=%d mipmaps=%s"
          % (len(strings), len(colors), len(styles), sorted(mipmaps)))
    return strings


def check_java_strings(java, strings):
    raw = dict(re.findall(r'<string name="([^"]+)">(.*?)</string>',
                          (RES / "values" / "strings.xml").read_text(encoding="utf-8"),
                          re.S))
    # (?<!android\.) para no confundir R.string.ok de la app con android.R.string.ok,
    # que es una cadena del framework y no vive en nuestro strings.xml
    for ref in sorted(set(re.findall(r"(?<!android\.)R\.string\.([A-Za-z0-9_]+)", java))):
        if ref not in strings:
            fail("R.string.%s no existe" % ref)

    # getString con formato: el numero de argumentos debe igualar los placeholders
    for m in re.finditer(r"getString\(R\.string\.([A-Za-z0-9_]+)((?:,[^()]*)?)\)", java):
        key, args = m.group(1), m.group(2)
        placeholders = len(set(re.findall(r"%(\d)\$", raw.get(key, ""))))
        passed = len([a for a in args.split(",") if a.strip()])
        if placeholders != passed:
            fail("getString(R.string.%s) pasa %d argumentos y la cadena declara %d"
                 % (key, passed, placeholders))
    print("3) R.string y placeholders de formato comprobados")


def check_identity(java):
    pkg = re.search(r"package\s+([\w.]+);", java).group(1)
    ns = re.search(r'namespace\s*=\s*"([^"]+)"',
                   APP_GRADLE.read_text(encoding="utf-8")).group(1)
    app_id = re.search(r'applicationId\s*=\s*"([^"]+)"',
                       APP_GRADLE.read_text(encoding="utf-8")).group(1)
    if pkg != ns:
        fail("paquete Java (%s) distinto del namespace de Gradle (%s)" % (pkg, ns))

    mani = MANIFEST.read_text(encoding="utf-8")
    activity = re.search(r'<activity[^>]*android:name="([^"]+)"', mani, re.S).group(1)
    expected = "." + JAVA.stem
    if activity != expected:
        fail("el manifest declara la actividad %s y la clase es %s" % (activity, expected))

    if "android.permission.INTERNET" not in mani:
        fail("falta el permiso INTERNET, la sincronizacion via Gist no funcionaria")

    print("4) paquete=%s applicationId=%s actividad=%s" % (pkg, app_id, activity))


def check_delimiters(java):
    """Cuenta llaves y parentesis ignorando comentarios, cadenas y caracteres."""
    backslash = chr(92)
    quote = chr(34)
    apostrophe = chr(39)
    opens = {"{": 0, "(": 0}
    closes = {"}": "{", ")": "("}

    i, n = 0, len(java)
    while i < n:
        c = java[i]
        if c == "/" and i + 1 < n and java[i + 1] == "/":
            nl = java.find("\n", i)
            i = n if nl < 0 else nl
            continue
        if c == "/" and i + 1 < n and java[i + 1] == "*":
            end = java.find("*/", i + 2)
            i = n if end < 0 else end + 2
            continue
        if c in (quote, apostrophe):
            i += 1
            while i < n and java[i] != c:
                i += 2 if java[i] == backslash else 1
            i += 1
            continue
        if c in opens:
            opens[c] += 1
        elif c in closes:
            opens[closes[c]] -= 1
        i += 1

    if opens["{"] != 0:
        fail("llaves desbalanceadas (delta %d)" % opens["{"])
    if opens["("] != 0:
        fail("parentesis desbalanceados (delta %d)" % opens["("])
    print("5) delimitadores balanceados")


def check_assets():
    fonts = ROOT / "android" / "app" / "src" / "main" / "assets" / "www" / "fonts"
    css = fonts / "fonts.css"
    if not css.exists():
        fail("falta assets/www/fonts/fonts.css, ejecuta tools/fetch_fonts.py")
        return
    text = css.read_text(encoding="utf-8")
    if "fonts.gstatic.com" in text:
        fail("fonts.css sigue apuntando a gstatic: la app pediria las fuentes a Google")
    referenced = set(re.findall(r"/([A-Za-z0-9_]+\.woff2)", text))
    present = {p.name for p in fonts.glob("*.woff2")}
    missing = referenced - present
    extra = present - referenced
    if missing:
        fail("fonts.css referencia ficheros que no estan: %s" % sorted(missing))
    if extra:
        fail("hay woff2 empaquetados que nadie usa: %s" % sorted(extra))

    if not (ROOT / "index.html").exists():
        fail("falta index.html en la raiz, copyWebApp fallaria")

    print("6) %d woff2 empaquetados y coherentes con fonts.css" % len(present))


def check_start_url(java):
    """La URL de arranque tiene que cuadrar con el path handler y con los assets."""
    url = re.search(r'START_URL\s*=\s*"https://"\s*\+\s*DOMAIN\s*\+\s*"([^"]+)"', java)
    if not url:
        fail("no se pudo leer START_URL")
        return
    path = url.group(1)
    handler = re.search(r'addPathHandler\("([^"]+)"', java).group(1)
    if not path.startswith(handler):
        fail("START_URL (%s) no cae bajo el path handler (%s)" % (path, handler))
    if not path.endswith("/www/index.html"):
        fail("START_URL apunta a %s y copyWebApp deja el fichero en www/index.html" % path)
    print("7) START_URL %s coherente con el handler %s" % (path, handler))


def main():
    java = JAVA.read_text(encoding="utf-8")
    xml_files = check_xml_wellformed()
    strings = check_resource_refs(xml_files)
    check_java_strings(java, strings)
    check_identity(java)
    check_delimiters(java)
    check_assets()
    check_start_url(java)

    print()
    if failures:
        print("%d problema(s) encontrado(s)" % len(failures))
        return 1
    print("Sin problemas. La compilacion real la hace el workflow de GitHub Actions.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
