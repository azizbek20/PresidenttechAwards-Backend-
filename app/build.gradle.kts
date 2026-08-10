import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
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

// Semantic version is the single source of truth; versionCode is derived so the
// two can never drift apart (e.g. someone bumping versionName and forgetting
// versionCode, which silently blocks Play Store updates). Bump one of these
// three on each release — patch for fixes, minor for features, major for
// breaking/incompatible changes — and versionCode follows automatically.
// Cap: each field must stay below 100 (2 digits) or versionCode collides with
// the next field up.
val versionMajor = 0
val versionMinor = 1
val versionPatch = 0

android {
    namespace = "com.eyedetect.ai"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.eyedetect.ai"
        minSdk = 24
        targetSdk = 34
        versionCode = versionMajor * 10_000 + versionMinor * 100 + versionPatch
        versionName = "$versionMajor.$versionMinor.$versionPatch"

        // ===================================================================
        // MUHIM: backend manzili. local.properties'da API_BASE_URL bilan
        // o'zgartiring (bu fayl git'ga kirmaydi) — kodni tahrirlash shart emas:
        //   - Emulyator + host mashinadagi backend:  http://10.0.2.2:8000/   (standart)
        //   - Real telefon (bir Wi-Fi):               http://<NOUTBUK-LAN-IP>:8000/
        //   - Telefon hotspot ulashsa, noutbuk IP'si O'ZGARADI — `ipconfig
        //     getifaddr en0` bilan tekshiring va local.properties'ni yangilang.
        //   - ngrok:                                  https://xxxx.ngrok-free.app/
        // Oxirida "/" bo'lishi SHART (Retrofit baseUrl talabi).
        // ===================================================================
        buildConfigField("String", "API_BASE_URL", "\"$debugApiUrl\"")
        buildConfigField("String", "API_KEY", "\"$backendApiKey\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiUrl\"")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
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

dependencies {
    // --- Compose ---
    val composeBom = platform("androidx.compose:compose-bom:2024.06.00")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.activity:activity-compose:1.9.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.2")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.2")

    // --- CameraX (rasm olish) ---
    val camerax = "1.4.2"
    implementation("androidx.camera:camera-core:$camerax")
    implementation("androidx.camera:camera-camera2:$camerax")
    implementation("androidx.camera:camera-lifecycle:$camerax")
    implementation("androidx.camera:camera-view:$camerax")

    // --- ML Kit (ko'z/iris joylashuvini aniqlash — kamera sifat nazorati uchun) ---
    implementation("com.google.mlkit:face-detection:16.1.7")

    // --- Olingan suratni EXIF burilishini hisobga olib dekodlash (mahalliy CV evristikasi uchun) ---
    implementation("androidx.exifinterface:exifinterface:1.3.7")

    // --- Tarmoq: Retrofit + OkHttp ---
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    // --- Rasm yuklash (heatmap URL'ni ko'rsatish uchun) ---
    implementation("io.coil-kt:coil-compose:2.6.0")

    // --- Persistensiya (eslatma sozlamalari, mashq statistikasi) ---
    implementation("androidx.datastore:datastore-preferences:1.1.1")

    // --- Room (o'tgan skrininglar tarixini lokal saqlash) ---
    // 2.6.1 emas — undagi kapt annotatsiya protsessori Kotlin 2.2 metadata (v2.2.0)ni
    // qo'llab-quvvatlamaydi ("maximum supported version is 2.0.0" xatosi).
    val room = "2.7.1"
    implementation("androidx.room:room-runtime:$room")
    implementation("androidx.room:room-ktx:$room")
    kapt("androidx.room:room-compiler:$room")

    // --- Fon rejimi: 20-20-20 eslatma ---
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    // --- Compose animatsiya (ko'z mashqlari uchun) ---
    implementation("androidx.compose.animation:animation")

    // --- Debug ---
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.compose.ui:ui-tooling-preview")

    // --- Unit testlar (JVM, `./gradlew testDebugUnitTest`) ---
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.9.0")
    testImplementation("com.squareup.okhttp3:mockwebserver:4.12.0")
    testImplementation("org.robolectric:robolectric:4.13")
    testImplementation("androidx.test:core:1.6.1")

    // --- Instrumentation testlar (qurilma/emulyator, `./gradlew connectedDebugAndroidTest`) ---
    androidTestImplementation(composeBom)
    androidTestImplementation("androidx.test.ext:junit:1.2.1")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.6.1")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
