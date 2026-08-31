# Rutina para Android

App nativa de Android que empaqueta la PWA de este repositorio. El `index.html` de la
raíz sigue siendo la única fuente de verdad: aquí no hay una copia, Gradle lo copia
dentro del APK en cada compilación.

## Cómo conseguir el APK

No necesitas instalar nada en tu ordenador. Cada push a `main` que toque `index.html`
o `android/` lanza el workflow **Compilar APK**:

1. Abre la pestaña **Actions** del repositorio.
2. Entra en la última ejecución de *Compilar APK*.
3. Descarga el artifact `rutina-apk` (es un zip con `rutina-<commit>.apk`).
4. Pasa el APK al móvil y ábrelo. Android pedirá permiso para instalar apps de
   orígenes desconocidos la primera vez.

También puedes lanzarlo a mano desde Actions → *Compilar APK* → **Run workflow**.

El APK es de tipo *debug*, firmado con la clave de depuración estándar. Se instala sin
problema por sideload. Para publicar en Google Play haría falta un build `release`
firmado con una clave propia.

## Cómo actualizar la rutina

Edita `index.html` como siempre y haz push. Eso actualiza la web y, en paralelo,
genera un APK nuevo. Para que el móvil vea los cambios hay que instalar ese APK
encima del anterior; los datos guardados se conservan porque el `applicationId` no
cambia.

## Compilar en local (opcional)

Requiere JDK 17 y el Android SDK con la plataforma 35.

```bash
cd android
./gradlew assembleDebug
```

El APK queda en `app/build/outputs/apk/debug/app-debug.apk`. También puedes abrir la
carpeta `android/` directamente en Android Studio y darle a Run.

## Cómo funciona

`MainActivity` es un `WebView` con todo lo que la PWA necesita y que un WebView pelado
no trae de fábrica:

- **Origen local seguro.** Los assets se sirven con `WebViewAssetLoader` bajo
  `https://appassets.androidplatform.net/assets/www/`, no con `file://`. Importa porque
  `localStorage` se liga al origen: un origen `https` estable mantiene los datos entre
  actualizaciones de la app, y las APIs que la web usa solo funcionan en contexto seguro.
- **Diálogos JavaScript.** El `WebChromeClient` por defecto ignora `alert`, `confirm` y
  `prompt` sin decir nada. `index.html` los usa para confirmar la restauración de una
  copia y para pedir el token del Gist, así que están implementados con `AlertDialog`.
- **Selector de ficheros.** `onShowFileChooser` hace funcionar el `<input type="file">`
  del botón de restaurar copia.
- **Exportar la copia de seguridad.** La web crea un `blob:` y pulsa un `<a download>`.
  Un WebView ignora eso en silencio. Se inyecta un shim que intercepta ese click, pasa
  el contenido al lado nativo y lo escribe en la carpeta *Descargas* con `MediaStore`.
- **Enlaces externos.** Cualquier navegación fuera del dominio de los assets se abre en
  el navegador del sistema. El WebView tiene un puente JavaScript expuesto y no debe
  cargar nunca contenido de terceros.
- **Tipografías empaquetadas.** Oswald e IBM Plex van dentro del APK (237 KB). Las
  peticiones a `fonts.googleapis.com` se interceptan y se responden con la copia local,
  así que la rutina se ve bien sin conexión y la app no habla con Google.
- **Service worker desactivado.** Se responde 404 a `/sw.js`. Dentro del APK los assets
  ya son locales, así que el service worker solo añadiría una capa de caché inútil y una
  recarga extra en el primer arranque. El `register()` de `index.html` cae en su
  `.catch()` vacío, sin efectos.

Lo único que sale a la red es la sincronización opcional vía Gist, contra
`api.github.com`, exactamente igual que en la web. La app funciona completa sin red.

## Requisitos

- `minSdk 29` (Android 10, de 2019). Es lo que pide `MediaStore.Downloads`, que permite
  guardar la copia de seguridad en Descargas sin solicitar permisos de almacenamiento.
- `targetSdk 34`. Deliberadamente no 35: en 35 Android fuerza el modo *edge-to-edge* y
  el contenido se metería debajo de la barra de estado.

## Regenerar recursos

Los iconos y las tipografías están commiteados, no hace falta regenerarlos para
compilar. Si cambia el diseño del icono en el manifest o la lista de fuentes:

```bash
python tools/make_icons.py    # mipmaps + icono adaptativo, desde el SVG del manifest
python tools/fetch_fonts.py   # baja los woff2 y reescribe fonts.css al origen local
```
