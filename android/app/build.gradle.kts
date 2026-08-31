plugins {
    id("com.android.application")
}

// index.html no se duplica dentro de assets: se copia desde la raiz del repo en cada
// build. Asi la app empaqueta siempre la misma version que esta publicada en la web y
// no hay dos copias que puedan quedar desincronizadas.
//
// sw.js no se copia a proposito. El service worker existe solo para dar soporte offline
// en el navegador; dentro del APK los assets ya son locales. MainActivity responde 404
// a /sw.js para que el register() de index.html falle limpio en su .catch() vacio.
val webAppSource = rootProject.file("../index.html")

val copyWebApp by tasks.registering(Copy::class) {
    from(webAppSource)
    into(layout.buildDirectory.dir("generated/webapp/www"))
    doFirst {
        if (!webAppSource.exists()) {
            throw GradleException(
                "No se encuentra ${webAppSource.path}. El proyecto android/ espera vivir " +
                    "dentro del repo Rutina, junto a index.html."
            )
        }
    }
}

tasks.named("preBuild") {
    dependsOn(copyWebApp)
}

android {
    namespace = "es.davidramos.rutina"
    compileSdk = 35

    defaultConfig {
        applicationId = "es.davidramos.rutina"
        // Android 10. MediaStore.Downloads, que es lo que usa la exportacion de la
        // copia de seguridad, existe a partir de aqui y no pide permisos.
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    sourceSets {
        getByName("main") {
            // las fuentes empaquetadas viven en src/main/assets/www/fonts,
            // index.html lo aporta copyWebApp
            assets.srcDirs(
                "src/main/assets",
                layout.buildDirectory.dir("generated/webapp")
            )
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = false
    }
}

dependencies {
    implementation("androidx.webkit:webkit:1.12.1")
}
