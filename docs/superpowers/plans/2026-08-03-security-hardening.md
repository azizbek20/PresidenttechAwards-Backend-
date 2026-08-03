# Xavfsizlik va maxfiylik (PHI) tuzatishlari — Implementatsiya rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `PLAN.md` bo'lim 1 (Xavfsizlik va maxfiylik) dagi to'rtta 🔴 bandni
hozirgi tekis fayl strukturasida tuzatish: API key auth, HTTPS-only
release build, release loggingni cheklash, vaqtinchalik rasm fayllarini
tozalash.

**Architecture:** Mavjud uchta faylga (`ApiClient.kt`, `ScreeningViewModel.kt`,
`MainActivity.kt`) nuqtali o'zgartirishlar + ikkita yangi
`network_security_config.xml` (debug/main) + `AndroidManifest.xml`
o'zgartirishi. Yangi qatlam yoki modul yaratilmaydi — spec bo'yicha Clean
Architecture refaktoringi alohida, keyingi ish.

**Tech Stack:** Kotlin, OkHttp 4.12.0 (`Interceptor`), Android Network
Security Config (XML), Android Gradle Plugin `BuildConfig` (debug/release
source setlar).

## Global Constraints

- Loyihada hozircha test infratuzilmasi yo'q (JUnit/MockWebServer
  o'rnatilmagan) — bu spec doirasida **qamrovdan tashqarida**
  (`docs/superpowers/specs/2026-08-03-security-hardening-design.md`,
  "Testlar" bo'limi). Har bir task tekshiruvi **qo'lda** (build +
  `adb`/log tekshiruvi) orqali amalga oshiriladi, avtomatlashtirilgan test
  yozilmaydi.
- `local.properties` git'ga tushmaydi (`.gitignore`da `/local.properties`)
  — API key shu faylga yoziladi, hech qachon commit qilinmaydi.
- Clean Architecture refaktoringi (Hilt DI, domain/data/presentation
  qatlamlari) — qamrovdan tashqarida, alohida reja
  (`2026-07-31-clean-architecture-refactor-design.md`) asosida keyinroq
  bajariladi.
- Har bir task oxirida alohida commit.

---

### Task 1: ApiClient — statik API key header + release log darajasi

**Files:**
- Modify: `local.properties` (yangi qator, git'ga tushmaydi)
- Modify: `app/build.gradle.kts`
- Modify: `app/src/main/java/com/eyedetect/ai/data/ApiClient.kt`

**Interfaces:**
- Produces: `BuildConfig.API_KEY: String` (Gradle tomonidan generatsiya
  qilinadi, `com.eyedetect.ai.BuildConfig` paketida) — Task 1 ichida
  ishlatiladi, boshqa taskka bog'liqlik yo'q.
- Produces: har bir chiquvchi so'rovda `X-API-Key` HTTP header'i mavjud
  bo'ladi (keyingi tasklar buni o'zgartirmaydi).

- [ ] **Step 1: `local.properties`ga API key qo'shish**

Yangi tasodifiy kalit generatsiya qiling:

```
openssl rand -hex 32
```

Natijada chiqqan satrni `local.properties` faylining oxiriga (mavjud
`sdk.dir` qatoridan keyin) qo'shing:

```properties
API_KEY=<yuqoridagi buyruq natijasi>
```

(Bu — Anthropic/Claude API kaliti EMAS, faqat shu ilova bilan uning o'z
backend'i orasidagi, o'zingiz generatsiya qiladigan maxfiy satr. Qiymatni
shu reja hujjatiga yoki boshqa git'ga tushadigan faylga yozmang —
`local.properties` `.gitignore`da bo'lgani uchun xavfsiz, plan hujjati esa
commit qilinadi.)

- [ ] **Step 2: `build.gradle.kts`ni `local.properties`ni o'qiydigan qilish**

`app/build.gradle.kts` fayl boshiga (`plugins {}` blokidan oldin) qo'shing:

```kotlin
import java.io.FileInputStream
import java.util.Properties
```

`android {}` blokidan oldin (fayl darajasida) qo'shing:

```kotlin
val localProperties = Properties().apply {
    val localPropsFile = rootProject.file("local.properties")
    if (localPropsFile.exists()) {
        load(FileInputStream(localPropsFile))
    }
}
val backendApiKey: String = localProperties.getProperty("API_KEY") ?: "dev-key-CHANGE-ME"
```

`defaultConfig {}` bloki ichida, mavjud `buildConfigField("String",
"API_BASE_URL", ...)` qatoridan keyin qo'shing:

```kotlin
buildConfigField("String", "API_KEY", "\"$backendApiKey\"")
```

- [ ] **Step 3: Build qilib, `BuildConfig.API_KEY` generatsiya bo'lganini tekshirish**

Run:
```
./gradlew :app:assembleDebug
```

Expected: `BUILD SUCCESSFUL`. So'ng generatsiya qilingan faylni tekshiring:

```
Get-Content app/build/generated/source/buildConfig/debug/com/eyedetect/ai/BuildConfig.java | Select-String "API_KEY"
```

Expected chiqish `local.properties`dagi qiymat bilan mos keladigan qator,
masalan: `public static final String API_KEY = "<Step 1'da generatsiya
qilingan qiymat>";` (placeholder `"dev-key-CHANGE-ME"` emas, chunki Step
1'da haqiqiy qiymat qo'yilgan).

- [ ] **Step 4: `ApiClient.kt`ga auth interceptor va release log darajasini qo'shish**

`app/src/main/java/com/eyedetect/ai/data/ApiClient.kt` faylida `import
okhttp3.OkHttpClient` qatoridan keyin qo'shing:

```kotlin
import okhttp3.Interceptor
```

`private val logging = ...` bloki va undan keyingi `okHttp` bloki hozir
shunday:

```kotlin
    private val logging = HttpLoggingInterceptor().apply {
        level = HttpLoggingInterceptor.Level.BODY
    }

    private val okHttp = OkHttpClient.Builder()
        .addInterceptor(logging)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)   // CPU inference 1-3s, ehtiyot uchun 30s
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()
```

Buni shu bilan almashtiring:

```kotlin
    private val authInterceptor = Interceptor { chain ->
        val request = chain.request().newBuilder()
            .addHeader("X-API-Key", BuildConfig.API_KEY)
            .build()
        chain.proceed(request)
    }

    private val logging = HttpLoggingInterceptor().apply {
        level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY
                else HttpLoggingInterceptor.Level.BASIC
    }

    private val okHttp = OkHttpClient.Builder()
        .addInterceptor(authInterceptor)
        .addInterceptor(logging)
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)   // CPU inference 1-3s, ehtiyot uchun 30s
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()
```

- [ ] **Step 5: Build qilib, header ishlashini tekshirish**

Run:
```
./gradlew :app:assembleDebug
```

Expected: `BUILD SUCCESSFUL` (kompilyatsiya xatosiz o'tishi kifoya —
`Interceptor` SAM-konstruktor to'g'ri ishlatilganini tasdiqlaydi).

Keyin ilovani emulyator/qurilmada ishga tushiring, bemor ID kiritib rasm
yuboring (yoki backend ishlamasa ham, so'rov chiqishi yetarli), va Logcat
filtrini `okhttp.OkHttpClient` yoki `OkHttp` ga qo'yib, chiquvchi so'rov
log'ida `X-API-Key:` header qatorini toping. Debug buildda `Level.BODY`
tufayli barcha headerlar loglanadi.

Expected: log'da `X-API-Key: <Step 1'da generatsiya qilingan qiymat>`
qatori ko'rinadi.

- [ ] **Step 6: Commit**

```
git add local.properties app/build.gradle.kts app/src/main/java/com/eyedetect/ai/data/ApiClient.kt
git commit -m "security: add static API key auth header and release-safe log level"
```

(Eslatma: `local.properties` `.gitignore`da bo'lgani uchun `git add` uni
qo'shmaydi / commitga kirmaydi — bu kutilgan xatti-harakat, git ogohlantirish
bermaydi, shunchaki faylni e'tiborsiz qoldiradi.)

---

### Task 2: HTTPS-only release build (Network Security Config)

**Files:**
- Create: `app/src/main/res/xml/network_security_config.xml`
- Create: `app/src/debug/res/xml/network_security_config.xml`
- Modify: `app/src/main/AndroidManifest.xml`

**Interfaces:**
- Task 1'dan mustaqil — boshqa fayllarga bog'liq emas.
- Produces: release APK'da cleartext (HTTP) trafik butunlay bloklanadi,
  debug APK'da ruxsat etiladi. Keyingi tasklarga interfeys ta'sir
  qilmaydi.

- [ ] **Step 1: Release (main) network security config yaratish**

Create `app/src/main/res/xml/network_security_config.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="false" />
</network-security-config>
```

- [ ] **Step 2: Debug override yaratish**

Create `app/src/debug/res/xml/network_security_config.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<network-security-config>
    <base-config cleartextTrafficPermitted="true" />
</network-security-config>
```

- [ ] **Step 3: `AndroidManifest.xml`ni yangilash**

`app/src/main/AndroidManifest.xml`da hozirgi `<application ...>` bloki:

```xml
    <application
        android:allowBackup="true"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@style/Theme.EyeDetectAI"
        android:usesCleartextTraffic="true">
        <!-- android:icon o'chirildi — Android Studio "Image Asset" bilan
             ic_launcher yaratib, shu yerga qo'shsangiz bo'ladi. -->
        <!-- Demo skelet uchun tizim standart ikonkasi ishlatiladi. -->
        <!-- usesCleartextTraffic=true: demo uchun http:// (LAN/ngrok) ga ruxsat.
             Ishlab chiqarishda HTTPS ishlatib, buni olib tashlang. -->
```

Buni shu bilan almashtiring:

```xml
    <application
        android:allowBackup="true"
        android:label="@string/app_name"
        android:supportsRtl="true"
        android:theme="@style/Theme.EyeDetectAI"
        android:usesCleartextTraffic="false"
        android:networkSecurityConfig="@xml/network_security_config">
        <!-- android:icon o'chirildi — Android Studio "Image Asset" bilan
             ic_launcher yaratib, shu yerga qo'shsangiz bo'ladi. -->
        <!-- Demo skelet uchun tizim standart ikonkasi ishlatiladi. -->
        <!-- Cleartext (HTTP) faqat debug buildda ruxsat etiladi, ko'ring
             src/debug/res/xml/network_security_config.xml. Release faqat
             HTTPS. -->
```

- [ ] **Step 4: Debug va release manifestlarini build qilib tekshirish**

Run:
```
./gradlew :app:processDebugMainManifest
./gradlew :app:processReleaseMainManifest
```

Expected: ikkalasi ham `BUILD SUCCESSFUL`. Keyin merge qilingan
manifestlarni toping va tarkibini ko'ring (aniq yo'l AGP versiyasiga qarab
farq qilishi mumkin, agar quyidagi yo'l topilmasa
`Get-ChildItem -Recurse -Filter AndroidManifest.xml app/build` bilan qidiring):

```
Get-Content app/build/intermediates/merged_manifest/debug/AndroidManifest.xml | Select-String "cleartextTraffic|networkSecurityConfig"
Get-Content app/build/intermediates/merged_manifest/release/AndroidManifest.xml | Select-String "cleartextTraffic|networkSecurityConfig"
```

Expected: ikkalasida ham `usesCleartextTraffic="false"` va
`networkSecurityConfig="@xml/network_security_config"` ko'rinadi (bu
manifest darajasida bir xil — haqiqiy farq resource merge orqali qaysi
`network_security_config.xml` ishlatilishida, quyidagi qadamda tekshiriladi).

- [ ] **Step 5: Har bir variant qaysi XML resursni ishlatishini tekshirish**

Run:
```
./gradlew :app:assembleDebug :app:assembleRelease
Get-ChildItem -Recurse -Filter network_security_config.xml app/build/intermediates/merged_res
```

Expected: `debug` variant papkasidagi faylda `cleartextTrafficPermitted="true"`,
`release` variant papkasidagi faylda `cleartextTrafficPermitted="false"`
bo'lishi kerak (`Get-Content` bilan har birini oching va solishtiring) —
bu debug source set'dagi fayl asosiy (`main`) resursni to'g'ri override
qilganini tasdiqlaydi.

- [ ] **Step 6: Commit**

```
git add app/src/main/res/xml/network_security_config.xml app/src/debug/res/xml/network_security_config.xml app/src/main/AndroidManifest.xml
git commit -m "security: restrict cleartext traffic to debug builds only"
```

---

### Task 3: Vaqtinchalik fundus rasm fayllarini tozalash

**Files:**
- Modify: `app/src/main/java/com/eyedetect/ai/ScreeningViewModel.kt`
- Modify: `app/src/main/java/com/eyedetect/ai/MainActivity.kt`

**Interfaces:**
- Task 1 va 2'dan mustaqil.
- Consumes: hech narsa (mavjud `File`, `Context` turlaridan foydalanadi).
- Produces: `uploadFile(file: File)` — imzosi o'zgarmaydi, lekin endi
  chaqiruv tugagach (muvaffaqiyat/xato, ikkalasida ham) `file`ni
  o'chiradi. Bu xatti-harakat o'zgarishi `CameraScreen.kt`ga ta'sir
  qilmaydi (u faqat `vm.uploadFile(file)` chaqiradi, faylni o'zi
  boshqarmaydi).

- [ ] **Step 1: `ScreeningViewModel.uploadFile`ni `send()`ni ichiga olib, `finally`da faylni o'chiradigan qilib qayta yozish**

`app/src/main/java/com/eyedetect/ai/ScreeningViewModel.kt`da hozirgi:

```kotlin
    /** Faylni (kameradan) yuboradi. */
    fun uploadFile(file: File) {
        val part = MultipartBody.Part.createFormData(
            name = "file",
            filename = file.name,
            body = file.asRequestBody("image/jpeg".toMediaTypeOrNull()),
        )
        send(part)
    }
```

va pastroqdagi:

```kotlin
    private fun send(part: MultipartBody.Part) {
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            try {
                doRequest(part)
            } catch (e: Exception) {
                _uiState.value = UiState.Error(friendly(e))
            }
        }
    }
```

Buni shu ikkitasiga almashtiring — `send()` olib tashlanadi, mantiq
`uploadFile`ga ko'chadi:

```kotlin
    /** Faylni (kameradan) yuboradi; yuborilgach (muvaffaqiyat yoki xato) faylni o'chiradi. */
    fun uploadFile(file: File) {
        val part = MultipartBody.Part.createFormData(
            name = "file",
            filename = file.name,
            body = file.asRequestBody("image/jpeg".toMediaTypeOrNull()),
        )
        viewModelScope.launch {
            _uiState.value = UiState.Loading
            try {
                doRequest(part)
            } catch (e: Exception) {
                _uiState.value = UiState.Error(friendly(e))
            } finally {
                file.delete()
            }
        }
    }
```

- [ ] **Step 2: Build qilib xatosiz o'tishini tekshirish**

Run:
```
./gradlew :app:compileDebugKotlin
```

Expected: `BUILD SUCCESSFUL` (`send()` boshqa joyda ishlatilmagani
tasdiqlanadi — aks holda "unresolved reference: send" xatosi chiqadi).

- [ ] **Step 3: `MainActivity.kt`ga eski qoldiq fayllarni tozalash funksiyasini qo'shish**

`app/src/main/java/com/eyedetect/ai/MainActivity.kt`da import bloki
boshiga qo'shing:

```kotlin
import android.content.Context
```

`MainActivity` klassidan keyin (fayl darajasida, `enum class Screen`dan
keyin yoki oldin — mavjud tartibga ta'sir qilmaydi) qo'shing:

```kotlin
/** Ilova ishga tushganda cacheDir'da qolib ketgan eski fundus rasm fayllarini (masalan, oldingi
 * ilova to'satdan yopilishi qoldiqlari) tozalaydi. */
private fun cleanupStaleCaptures(context: Context) {
    context.cacheDir.listFiles { f -> f.name.startsWith("fundus_") && f.name.endsWith(".jpg") }
        ?.forEach { it.delete() }
}
```

`MainActivity.onCreate()`ni shunday o'zgartiring — hozirgi:

```kotlin
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
```

Buni shu bilan almashtiring:

```kotlin
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        cleanupStaleCaptures(applicationContext)
        setContent {
```

- [ ] **Step 4: Build qilib tekshirish**

Run:
```
./gradlew :app:compileDebugKotlin
```

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 5: Qo'lda tekshirish — muvaffaqiyatli yuborilgandan keyin fayl o'chishi**

Ilovani emulyator/qurilmada ishga tushiring (backend ishlab turgan
bo'lishi shart emas — xato holatida ham `finally` ishlaydi). Rasm oling,
"Yuborish"ni bosing, so'rov tugashini kuting (muvaffaqiyat yoki xato
ekrani chiqadi). Keyin:

```
adb shell run-as com.eyedetect.ai ls cache/
```

Expected: `fundus_*.jpg` fayli **yo'q** ro'yxatda (avval yuborilgan fayl
o'chirilgan).

- [ ] **Step 6: Qo'lda tekshirish — ishga tushishda eski qoldiq tozalanishi**

Ilovani to'xtating. Qo'lda qoldiq fayl yaratish:

```
adb shell run-as com.eyedetect.ai touch cache/fundus_test_stale.jpg
adb shell run-as com.eyedetect.ai ls cache/
```

Expected: `fundus_test_stale.jpg` ro'yxatda ko'rinadi. Ilovani qayta
ishga tushiring (`adb shell am start -n com.eyedetect.ai/.MainActivity`
yoki qo'lda ochish), keyin:

```
adb shell run-as com.eyedetect.ai ls cache/
```

Expected: `fundus_test_stale.jpg` **yo'q** — `cleanupStaleCaptures`
`onCreate`da uni o'chirgan.

- [ ] **Step 7: Commit**

```
git add app/src/main/java/com/eyedetect/ai/ScreeningViewModel.kt app/src/main/java/com/eyedetect/ai/MainActivity.kt
git commit -m "security: delete temp fundus images after upload and on stale startup cleanup"
```

---

## Yakuniy tekshiruv (barcha tasklar tugagach)

- [ ] **To'liq build**: `./gradlew :app:assembleDebug :app:assembleRelease`
  — ikkalasi ham `BUILD SUCCESSFUL` bo'lishi kerak.
- [ ] `PLAN.md` bo'lim 1'dagi to'rtta band `[x]` deb belgilanadi (backend
  auth header qo'shildi — token/login emas, statik API key, spec bilan
  mos).
