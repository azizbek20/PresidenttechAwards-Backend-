---
name: android-build
description: Build, test and run the Kotlin Multiplatform / Jetpack Compose Android app in composeApp/ (Gradle wrapper, local.properties keys, debug vs release API URL, unit vs instrumented tests, emulator vs phone backend address). Use when touching composeApp/, when a Gradle build fails, when wiring the phone to a backend, or when preparing a release APK.
---

# Android app (composeApp/)

KMP module `:composeApp` (Android target plus iOS stubs). Package `com.eyedetect.ai`, minSdk 24, compile/target 35/34, JVM 17.
Shared network code is in `src/commonMain/.../data/` (Ktor plus kotlinx.serialization). Everything else is in `src/androidMain/`.

## Commands (run from repo root)

```bash
./gradlew :composeApp:assembleDebug              # debug APK
./gradlew :composeApp:testDebugUnitTest          # JVM unit tests (src/test/java)
./gradlew :composeApp:connectedDebugAndroidTest  # instrumented (src/androidTest), needs device/emulator
./gradlew :composeApp:assembleRelease            # minified + shrunk, needs RELEASE_API_URL
```

A single unit test: `./gradlew :composeApp:testDebugUnitTest --tests "com.eyedetect.ai.ScreeningViewModelTest"`

## local.properties (repo root, git-ignored, never commit)

```properties
API_KEY=demo123                       # must equal backend EYE_API_KEY
API_BASE_URL=http://10.0.2.2:8000/    # debug build only
RELEASE_API_URL=https://...           # release build only, HTTPS
```

- `API_BASE_URL` is validated at configure time: it must start with `http(s)://`, contain no quotes or backslashes, and **end with `/`**.
- Emulator to the host backend: `http://10.0.2.2:8000/` (the default). Real phone on the same Wi-Fi: `http://<laptop LAN IP>:8000/` (`ipconfig getifaddr en0`). A phone hotspot changes the IP.
- Cleartext `http://` is allowed **only in debug** (`src/debug/res/xml/network_security_config.xml`). Release is HTTPS-only.

## Things that bite

- The on-device models (`src/androidMain/assets/dr_model.tflite`, `face_landmarker.task`) are binary assets, and `.tflite` is `noCompress`. Do not rename them without updating `OfflineDrClassifier.kt` / `IrisLandmarker.kt`.
- History and the pending-upload queue are one Room + SQLCipher database (`ScreeningHistoryDatabase`, version 3). It currently uses `fallbackToDestructiveMigration(true)` because the app is unreleased, so a version bump **wipes local history**. Once the app ships, replace that with real `Migration`s.
- Background work (uploads, Pomodoro, 20-20-20 reminders) is WorkManager. Test workers with the existing `*WorkerTest.kt` pattern.
- UI strings live in `res/values` (Uzbek, the default), `values-ru` and `values-en`. Add every new string to all three.
- Any change to the JSON the app reads is a cross-language contract change. Use the `api-contract` skill.
- The emulator camera is limited. Use the gallery fallback on the camera screen.
