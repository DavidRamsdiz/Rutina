package es.davidramos.rutina;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.ViewGroup;
import android.webkit.JavascriptInterface;
import android.webkit.JsPromptResult;
import android.webkit.JsResult;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.Toast;

import androidx.webkit.WebViewAssetLoader;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.Collections;

/**
 * Contenedor nativo de la PWA "Rutina".
 *
 * Los contenidos (index.html y las fuentes) van dentro del APK, en assets/www, y se
 * sirven con WebViewAssetLoader bajo https://appassets.androidplatform.net/. Se usa un
 * origen https y no file:// por dos razones: localStorage queda ligado a un origen
 * estable y persistente, y las APIs que la web espera solo funcionan en un contexto
 * seguro.
 */
public class MainActivity extends Activity {

    private static final String DOMAIN = "appassets.androidplatform.net";
    private static final String START_URL = "https://" + DOMAIN + "/assets/www/index.html";
    private static final String GOOGLE_FONTS_HOST = "fonts.googleapis.com";
    private static final int REQ_FILE_CHOOSER = 1001;

    private WebView webView;
    private WebViewAssetLoader assetLoader;
    private ValueCallback<Uri[]> pendingFileCallback;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        assetLoader = new WebViewAssetLoader.Builder()
                .setDomain(DOMAIN)
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();

        if (isDebuggable()) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        webView = new WebView(this);
        FrameLayout root = new FrameLayout(this);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        // DOM storage es lo que respalda localStorage, donde la app guarda las semanas.
        // No se habilita WebSQL: index.html no lo usa y la API esta retirada.
        settings.setDomStorageEnabled(true);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        // el HTML vive en assets, no hay motivo para dar acceso al sistema de ficheros
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);

        webView.setBackgroundColor(0xFFE9C99A);
        webView.setWebViewClient(new AppWebViewClient());
        webView.setWebChromeClient(new AppWebChromeClient());
        webView.addJavascriptInterface(new AndroidBridge(), "RutinaAndroid");

        // restoreState devuelve null si el bundle no traia estado de navegacion, y en ese
        // caso el WebView se quedaria en blanco. Por eso el loadUrl es el respaldo.
        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl(START_URL);
        }
    }

    // ---------------------------------------------------------------- WebViewClient

    private final class AppWebViewClient extends WebViewClient {

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            Uri url = request.getUrl();

            // El service worker solo existe para dar soporte offline en la web. Dentro
            // del APK los assets ya son locales, asi que instalarlo solo anadiria una
            // capa de cache inutil y una recarga extra en el primer arranque. Se
            // responde 404 y el register() de index.html cae en su .catch() vacio.
            String path = url.getPath();
            if (DOMAIN.equals(url.getHost()) && path != null && path.endsWith("/sw.js")) {
                return notFound();
            }

            WebResourceResponse fonts = localFonts(url);
            if (fonts != null) {
                return fonts;
            }

            return assetLoader.shouldInterceptRequest(url);
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri url = request.getUrl();
            if (DOMAIN.equals(url.getHost())) {
                return false;
            }
            // Cualquier enlace externo se abre fuera. Este WebView tiene un puente JS
            // expuesto y no debe cargar nunca contenido de terceros.
            openExternally(url);
            return true;
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            view.evaluateJavascript(DOWNLOAD_SHIM_JS, null);
        }
    }

    /**
     * Sirve la hoja de estilos de Google Fonts desde el APK. La copia local ya apunta a
     * los .woff2 empaquetados, asi que la tipografia se ve bien sin conexion y no se
     * hace ninguna peticion a Google.
     */
    private WebResourceResponse localFonts(Uri url) {
        if (url == null || !GOOGLE_FONTS_HOST.equals(url.getHost())) {
            return null;
        }
        try {
            InputStream in = getAssets().open("www/fonts/fonts.css");
            WebResourceResponse resp = new WebResourceResponse("text/css", "UTF-8", in);
            resp.setResponseHeaders(
                    Collections.singletonMap("Access-Control-Allow-Origin", "*"));
            return resp;
        } catch (IOException e) {
            return null;
        }
    }

    private WebResourceResponse notFound() {
        WebResourceResponse resp = new WebResourceResponse(
                "text/plain", "UTF-8",
                new ByteArrayInputStream("not found".getBytes(StandardCharsets.UTF_8)));
        resp.setStatusCodeAndReasonPhrase(404, "Not Found");
        return resp;
    }

    private void openExternally(Uri url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, url));
        } catch (Exception ignored) {
            // sin navegador disponible no hay nada sensato que hacer
        }
    }

    // ------------------------------------------------------------- WebChromeClient
    // El WebChromeClient por defecto ignora alert/confirm/prompt. index.html los usa
    // para confirmar la restauracion y pedir el token del Gist, asi que hay que
    // implementarlos a mano.

    private final class AppWebChromeClient extends WebChromeClient {

        @Override
        public boolean onJsAlert(WebView view, String url, String message, final JsResult result) {
            new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setCancelable(true)
                    .setPositiveButton(android.R.string.ok, (d, w) -> result.confirm())
                    .setOnCancelListener(d -> result.cancel())
                    .show();
            return true;
        }

        @Override
        public boolean onJsConfirm(WebView view, String url, String message, final JsResult result) {
            new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setCancelable(true)
                    .setPositiveButton(android.R.string.ok, (d, w) -> result.confirm())
                    .setNegativeButton(android.R.string.cancel, (d, w) -> result.cancel())
                    .setOnCancelListener(d -> result.cancel())
                    .show();
            return true;
        }

        @Override
        public boolean onJsPrompt(WebView view, String url, String message,
                                  String defaultValue, final JsPromptResult result) {
            final EditText input = new EditText(MainActivity.this);
            input.setSingleLine(true);
            if (defaultValue != null) {
                input.setText(defaultValue);
            }
            new AlertDialog.Builder(MainActivity.this)
                    .setMessage(message)
                    .setView(input)
                    .setCancelable(true)
                    .setPositiveButton(android.R.string.ok,
                            (d, w) -> result.confirm(input.getText().toString()))
                    .setNegativeButton(android.R.string.cancel, (d, w) -> result.cancel())
                    .setOnCancelListener(d -> result.cancel())
                    .show();
            return true;
        }

        /** Necesario para el boton de restaurar copia (input type="file"). */
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                         FileChooserParams params) {
            if (pendingFileCallback != null) {
                pendingFileCallback.onReceiveValue(null);
            }
            pendingFileCallback = callback;
            try {
                startActivityForResult(params.createIntent(), REQ_FILE_CHOOSER);
                return true;
            } catch (Exception e) {
                pendingFileCallback = null;
                return false;
            }
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE_CHOOSER) {
            if (pendingFileCallback != null) {
                pendingFileCallback.onReceiveValue(
                        WebChromeClient.FileChooserParams.parseResult(resultCode, data));
                pendingFileCallback = null;
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    // --------------------------------------------------------- descarga de la copia
    // index.html exporta la copia de seguridad creando un blob: y pulsando un
    // <a download>. Un WebView ignora eso por completo: no hay descarga ni error.
    // Este shim intercepta ese click, pasa el contenido al lado nativo y lo escribe
    // en la carpeta Descargas del telefono.

    private static final String DOWNLOAD_SHIM_JS = String.join("\n",
            "(function(){",
            "  if (window.__rutinaDownloadShim) return;",
            "  window.__rutinaDownloadShim = true;",
            "  var orig = HTMLAnchorElement.prototype.click;",
            "  HTMLAnchorElement.prototype.click = function(){",
            "    var self = this;",
            "    var href = this.getAttribute('href') || '';",
            "    var name = this.getAttribute('download');",
            "    if (!name || href.indexOf('blob:') !== 0) {",
            "      return orig.apply(this, arguments);",
            "    }",
            "    fetch(href).then(function(r){ return r.blob(); }).then(function(b){",
            "      var fr = new FileReader();",
            "      fr.onload = function(){",
            "        var s = String(fr.result);",
            "        var type = b.type || 'application/octet-stream';",
            "        RutinaAndroid.saveToDownloads(name, type, s.slice(s.indexOf(',') + 1));",
            "      };",
            "      fr.onerror = function(){ orig.call(self); };",
            "      fr.readAsDataURL(b);",
            "    }).catch(function(){ orig.call(self); });",
            "  };",
            "})();");

    private final class AndroidBridge {

        @JavascriptInterface
        public void saveToDownloads(String name, String mime, String base64) {
            final String fileName = sanitize(name);
            final byte[] bytes;
            try {
                bytes = Base64.decode(base64, Base64.DEFAULT);
            } catch (IllegalArgumentException e) {
                runOnUiThread(() -> toast(getString(R.string.save_failed)));
                return;
            }
            runOnUiThread(() -> writeToDownloads(fileName, mime, bytes));
        }
    }

    private void writeToDownloads(String fileName, String mime, byte[] bytes) {
        Uri target = null;
        try {
            ContentValues values = new ContentValues();
            values.put(MediaStore.MediaColumns.DISPLAY_NAME, fileName);
            values.put(MediaStore.MediaColumns.MIME_TYPE, mime);
            values.put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS);

            target = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
            if (target == null) {
                throw new IOException("MediaStore no devolvio una uri");
            }

            OutputStream out = getContentResolver().openOutputStream(target);
            if (out == null) {
                throw new IOException("no se pudo abrir el stream de escritura");
            }
            try {
                out.write(bytes);
                out.flush();
            } finally {
                out.close();
            }
            toast(getString(R.string.saved_to_downloads, fileName));
        } catch (Exception e) {
            if (target != null) {
                // no dejar una entrada vacia colgando en Descargas
                try {
                    getContentResolver().delete(target, null, null);
                } catch (Exception ignored) {
                    // nada que hacer
                }
            }
            toast(getString(R.string.save_failed));
        }
    }

    private static String sanitize(String name) {
        if (name == null || name.trim().isEmpty()) {
            return "rutina_backup.json";
        }
        String clean = name.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        return clean.isEmpty() ? "rutina_backup.json" : clean;
    }

    // ------------------------------------------------------------------ ciclo de vida

    // No se sobrescribe onBackPressed. index.html es una sola pagina que cambia de vista
    // por JavaScript, sin pushState ni enlaces internos, asi que el WebView nunca acumula
    // historial: canGoBack() seria siempre false y lo unico que haria el override es usar
    // una API obsoleta para acabar cerrando la app igualmente. Atras sale de la app, que
    // es lo que se espera.

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (webView != null) {
            webView.saveState(outState);
        }
    }

    @Override
    protected void onPause() {
        if (webView != null) {
            webView.onPause();
        }
        super.onPause();
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (webView != null) {
            webView.onResume();
        }
    }

    private boolean isDebuggable() {
        return (getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0;
    }

    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }
}
