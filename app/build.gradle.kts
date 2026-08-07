import java.io.FileInputStream
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val localProperties = Properties().apply {
    val localPropsFile = rootProject.file("local.properties")
    if (localPropsFile.exists()) {
        load(FileInputStream(localPropsFile))
    }
}
val backendApiKey: String = localProperties.getProperty("API_KEY") ?: "dev-key-CHANGE-ME"
val releaseApiUrl: String = localProperties.getProperty("RELEASE_API_URL") ?: ""

android {
    namespace = "com.eyedetect.ai"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.eyedetect.ai"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"

        // ===================================================================
        // MUHIM: backend manzili. Bu qiymatni O'ZINGIZNIKIGA o'zgartiring.
        //   - Emulyator + host mashinadagi backend:  http://10.0.2.2:8000/
        //   - Real telefon (bir Wi-Fi):               http://<NOUTBUK-LAN-IP>:8000/
        //   - ngrok:                                  https://xxxx.ngrok-free.app/
        // Oxirida "/" bo'lishi SHART (Retrofit baseUrl talabi).
        // ===================================================================
        buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000/\"")
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

    // --- Tarmoq: Retrofit + OkHttp ---
    implementation("com.squareup.retrofit2:retrofit:2.11.0")
    implementation("com.squareup.retrofit2:converter-gson:2.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    // --- Rasm yuklash (heatmap URL'ni ko'rsatish uchun) ---
    implementation("io.coil-kt:coil-compose:2.6.0")

    // --- Persistensiya (eslatma sozlamalari, mashq statistikasi) ---
    implementation("androidx.datastore:datastore-preferences:1.1.1")

    // --- Fon rejimi: 20-20-20 eslatma ---
    implementation("androidx.work:work-runtime-ktx:2.9.1")

    // --- Compose animatsiya (ko'z mashqlari uchun) ---
    implementation("androidx.compose.animation:animation")

    // --- Debug ---
    debugImplementation("androidx.compose.ui:ui-tooling")
    implementation("androidx.compose.ui:ui-tooling-preview")
}
