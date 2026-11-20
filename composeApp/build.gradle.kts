import java.io.FileInputStream
import java.util.Properties

plugins {
    id("org.jetbrains.kotlin.multiplatform")
    id("com.android.application")
    id("org.jetbrains.compose")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
    id("org.jetbrains.kotlin.kapt")
}

val localProperties = Properties().apply {
    val localPropsFile = rootProject.file("local.properties")
    if (localPropsFile.exists()) {
        load(FileInputStream(localPropsFile))
    }
}
val backendApiKey: String = localProperties.getProperty("API_KEY") ?: "dev-key-CHANGE-ME"
val releaseApiUrl: String = localProperties.getProperty("RELEASE_API_URL") ?: ""

// Debug backend address. Overridable from local.properties (which is gitignored)
// so pointing the app at a laptop on the LAN is a config edit, not a source
// change: the previous hardcoded value meant every network change required
// editing tracked code and rebuilding, and a stale address looks exactly like a
// server outage from the phone. Default stays the emulator loopback.
// Validated at CONFIGURATION time so a bad value fails the build with a message
// naming local.properties, instead of failing the app at launch. `?:` alone was
// not enough: Properties.getProperty returns "" for a present-but-empty key, so
// `API_BASE_URL=` silently shipped an empty baseUrl and crashed MainActivity on
// first composition. Properties also preserves TRAILING whitespace, and a
// trailing space is the nastiest case of all — /predict still works while every
// Grad-CAM and original image 404s, because Coil resolves the relative
// /static/... path against a corrupted base.
val debugApiUrl: String =
    (localProperties.getProperty("API_BASE_URL")?.trim()?.takeIf { it.isNotEmpty() }
        ?: "http://10.0.2.2:8000/")
        .also { url ->
            require(url.startsWith("http://") || url.startsWith("https://")) {
                "local.properties: API_BASE_URL must start with http:// or https:// — got \"$url\""
            }
            // The value is interpolated verbatim into generated Java by
            // buildConfigField, so a stray quote or backslash produces
            // uncompilable source with an error that never mentions
            // local.properties. Reject it here instead.
            require(!url.contains('"') && !url.contains('\\')) {
                "local.properties: API_BASE_URL must not contain quotes or backslashes — " +
                    "write it unquoted, e.g. API_BASE_URL=http://192.168.1.10:8000/ — got \"$url\""
            }
            require(url.endsWith("/")) {
                "local.properties: API_BASE_URL must end with '/' (Retrofit baseUrl requirement) " +
                    "— got \"$url\""
            }
        }

kotlin {
    androidTarget {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }

    listOf(
        iosX64(),
        iosArm64(),
        iosSimulatorArm64()
    ).forEach { iosTarget ->
        iosTarget.binaries.framework {
            baseName = "ComposeApp"
            isStatic = true
        }
    }

    sourceSets {
        val iosMain by creating {
            dependencies {
                implementation("io.ktor:ktor-client-darwin:2.3.12")
            }
        }
        androidMain.dependencies {
            implementation(compose.preview)
            implementation("androidx.activity:activity-compose:1.9.0")
            implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.2")
            implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.2")
            implementation("androidx.compose.material3:material3-window-size-class:1.2.1")
            implementation("androidx.compose.material:material-icons-extended")
            implementation("io.ktor:ktor-client-okhttp:2.3.12")

            // --- CameraX (rasm olish) ---
            val camerax = "1.4.2"
            implementation("androidx.camera:camera-core:$camerax")
            implementation("androidx.camera:camera-camera2:$camerax")
            implementation("androidx.camera:camera-lifecycle:$camerax")
            implementation("androidx.camera:camera-view:$camerax")

            // --- ML Kit (ko'z/iris joylashuvini aniqlash — kamera sifat nazorati uchun) ---
            implementation("com.google.mlkit:face-detection:16.1.6")

            // Offline AI (TFLite)
            implementation("org.tensorflow:tensorflow-lite:2.14.0")
            implementation("org.tensorflow:tensorflow-lite-support:0.4.4")

            // --- Olingan suratni EXIF burilishini hisobga olib dekodlash ---
            implementation("androidx.exifinterface:exifinterface:1.3.7")

            // --- Rasm yuklash (heatmap URL'ni ko'rsatish uchun) ---
            implementation("io.coil-kt:coil-compose:2.6.0")

            // --- Persistensiya (eslatma sozlamalari, mashq statistikasi) ---
            implementation("androidx.datastore:datastore-preferences:1.1.1")

            // --- Room (o'tgan skrininglar tarixini lokal saqlash) ---
            // 2.6.1 emas — undagi kapt annotatsiya protsessori Kotlin 2.2
            // metadata (v2.2.0)ni qo'llab-quvvatlamaydi.
            implementation("androidx.room:room-runtime:2.7.1")
            implementation("androidx.room:room-ktx:2.7.1")

            // --- DB shifrlash (SQLCipher) ---
            implementation("net.zetetic:android-database-sqlcipher:4.5.4")
            implementation("androidx.sqlite:sqlite-framework:2.4.0")
            implementation("androidx.security:security-crypto:1.1.0-alpha06")

            // --- Fon rejimi: 20-20-20 eslatma ---
            implementation("androidx.work:work-runtime-ktx:2.9.1")

            // --- Compose animatsiya (ko'z mashqlari uchun) ---
            implementation("androidx.compose.animation:animation")
            implementation("androidx.compose.ui:ui-tooling-preview")
        }
        commonMain.dependencies {
            implementation(compose.runtime)
            implementation(compose.foundation)
            implementation(compose.material3)
            implementation(compose.ui)
            implementation(compose.components.resources)
            implementation(compose.components.uiToolingPreview)

            implementation("io.ktor:ktor-client-core:2.3.12")
            implementation("io.ktor:ktor-client-content-negotiation:2.3.12")
            implementation("io.ktor:ktor-serialization-kotlinx-json:2.3.12")
            implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.7.3")
        }
    }
}

android {
    buildFeatures { buildConfig = true }
    namespace = "com.eyedetect.ai"
    compileSdk = 35

    sourceSets["main"].manifest.srcFile("src/androidMain/AndroidManifest.xml")
    sourceSets["main"].res.srcDirs("src/androidMain/res")
    sourceSets["main"].resources.srcDirs("src/androidMain/resources")
    sourceSets["main"].assets.srcDirs("src/androidMain/assets")

    // Robolectric testlari R.string resurslarini o'qiy olishi uchun.
    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }

    defaultConfig {
        applicationId = "com.eyedetect.ai"
        minSdk = 24
        targetSdk = 34
        versionCode = 2
        versionName = "1.0.0-rc1"
        buildConfigField("String", "API_BASE_URL", "\"$debugApiUrl\"")
        buildConfigField("String", "API_KEY", "\"$backendApiKey\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiUrl\"")
        }
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }

    // TFLite modelini siqmaslik kerak, aks holda MappedByteBuffer orqali xotiraga yuklab bo'lmaydi
    androidResources {
        noCompress.add("tflite")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

val checkReleaseSecrets = tasks.register("checkReleaseSecrets") {
    doLast {
        check(releaseApiUrl.startsWith("https://")) {
            "RELEASE_API_URL local.properties'da topilmadi yoki HTTPS emas. " +
                "Masalan: RELEASE_API_URL=https://api.eyedetect.example.com/"
        }
        check(backendApiKey.isNotBlank() && backendApiKey != "dev-key-CHANGE-ME") {
            "API_KEY local.properties'da o'rnatilmagan (hali placeholder qiymatda)."
        }
    }
}

afterEvaluate {
    tasks.findByName("assembleRelease")?.dependsOn(checkReleaseSecrets)
    tasks.findByName("bundleRelease")?.dependsOn(checkReleaseSecrets)
}

// Android-variant-specific configurations (kapt, debugImplementation) are not
// reachable from the kotlin.sourceSets.androidMain.dependencies DSL above —
// they live on the top-level dependencies handler instead.
dependencies {
    add("kapt", "androidx.room:room-compiler:2.7.1")
    add("debugImplementation", "androidx.compose.ui:ui-tooling")

    // --- Unit testlar (JVM, `./gradlew :composeApp:testDebugUnitTest`) ---
    add("testImplementation", "junit:junit:4.13.2")
    add("testImplementation", "org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    add("testImplementation", "org.robolectric:robolectric:4.13")
    add("testImplementation", "androidx.test:core:1.6.1")
    add("testImplementation", "io.ktor:ktor-client-mock:2.3.12")
    add("testImplementation", "androidx.work:work-testing:2.9.1")
}
