# EYE DETECT AI Android — Xavfsizlik va maxfiylik (PHI) tuzatishlari

**Sana:** 2026-08-03
**Holat:** Tasdiqlangan (foydalanuvchi tomonidan)

## Kontekst

`PLAN.md` bo'lim 1 ("Xavfsizlik va maxfiylik (PHI)") — bemor ID va fundus
rasm shaxsiy tibbiy ma'lumot (PHI) bo'lgani uchun 🔴 muhim deb belgilangan,
ishlab chiqarishga chiqishdan oldin shart bo'lgan to'rtta band:

1. Backend bilan autentifikatsiya yo'q.
2. `usesCleartextTraffic="true"` — HTTP har doim ruxsat etilgan.
3. `HttpLoggingInterceptor.Level.BODY` release buildda ham yoqilgan — bemor
   ID va rasm baytlari logga yoziladi.
4. Kameradan olingan vaqtinchalik rasm fayllari (`cacheDir`) faqat "qayta
   olish"da o'chadi — muvaffaqiyatli yuborilgandan keyin yoki xatoda qoladi.

Loyihada avval (2026-07-31) tasdiqlangan
`2026-07-31-clean-architecture-refactor-design.md` mavjud — u Clean
Architecture refaktoringi bilan birga shu bandlardan 1, 2, 4 ni ham qamrab
oladi, lekin hali amalga oshirilmagan (kod hozircha eski tekis strukturada).
Foydalanuvchi bilan kelishilgan tartib: **avval xavfsizlik tuzatishlari
hozirgi (tekis) struktura ustida qilinadi, Clean Architecture refaktoringi
alohida, keyingi vazifa sifatida qoladi.** Refaktor paytida bu spec'dagi
o'zgarishlar (`AuthInterceptor`, `network_security_config.xml`, tozalash
mantiqi) yangi joylarga (`di/NetworkModule.kt` va h.k.) ko'chiriladi —
qamrovdan tashqarida qoldiriladi.

## Maqsad

To'rtta xavfsizlik bandini hozirgi fayl strukturasida (arxitekturani
o'zgartirmasdan) tuzatish:

1. Har bir backend so'roviga statik API key header qo'shish.
2. Release buildda faqat HTTPS, debug buildda LAN/emulyator uchun HTTP
   ruxsat etish.
3. Release buildda HTTP logging'ni `BASIC` darajasiga tushirish (body yo'q).
4. Vaqtinchalik fundus rasm fayllarini yuborilgach (muvaffaqiyat yoki xato)
   va ilova ishga tushganda (eski qoldiqlar) tozalash.

Xatti-harakat (UI oqimi, ekranlar) o'zgarmaydi — bu sof xavfsizlik
tuzatishi.

## 1. Backend autentifikatsiyasi (statik API key)

- `local.properties`ga `API_KEY=<tasodifiy kalit>` qo'shiladi (bu fayl
  `.gitignore`da, git'ga tushmaydi). Kalit foydalanuvchi bilan generatsiya
  qilingan (`openssl rand -hex 32`).
- `app/build.gradle.kts`: `local.properties`ni o'qib,
  `buildConfigField("String", "API_KEY", "\"${apiKey}\"")` qo'shiladi.
  `local.properties`da qiymat yo'q bo'lsa, fallback sifatida
  `"dev-key-CHANGE-ME"` ishlatiladi (build muvaffaqiyatsiz bo'lmasligi
  uchun, lekin foydalanuvchiga aniq ko'rinadigan placeholder).
- `ApiClient.kt`ga yangi `Interceptor` (`AuthInterceptor` — shu faylda
  private funksiya yoki kichik ichki klass sifatida) qo'shiladi: har bir
  so'rovga `X-API-Key: BuildConfig.API_KEY` header'ini qo'shadi.
  `okHttp` builder'ga `addInterceptor` bilan ulanadi (logging
  interceptor'dan oldin, chunki logging so'rovni "ko'rib" chiqadi va header
  logda ko'rinishi kerak bo'lsa tartib muhim emas — ikkalasi ham request'ni
  o'zgartirmaydi/logs qiladi, tartib ahamiyatsiz).
- `ApiService.kt`ga o'zgartirish kerak emas — header global interceptor
  darajasida qo'shiladi.
- Backend hali auth tekshirmasa ham ilova ishlayveradi (backend header'ni
  e'tiborsiz qoldiradi); backend tomon key tekshiruvini qo'shganda mos
  tushadi.

## 2. Cleartext traffic (HTTPS majburiy release'da)

- Yangi `app/src/debug/res/xml/network_security_config.xml` (faqat debug
  source setda): `<base-config cleartextTrafficPermitted="true" />` —
  barcha domenlar uchun (LAN IP dev paytida o'zgarib turadi, domenlarni
  qattiq yozib qo'yish amaliy emas).
- `app/src/main/AndroidManifest.xml`:
  `android:usesCleartextTraffic="false"` ga o'zgartiriladi va
  `android:networkSecurityConfig="@xml/network_security_config"` qo'shiladi.
- Yangi `app/src/main/res/xml/network_security_config.xml` (release/asosiy):
  `<base-config cleartextTrafficPermitted="false" />` — aniqlik uchun,
  garchi `usesCleartextTraffic="false"` bilan bir xil ma'noni bersa ham.
- Gradle debug/release source set birlashtirish qoidasi tufayli, debug
  buildda `app/src/debug/res/xml/network_security_config.xml` asosiy
  resursni override qiladi (bir xil nom, debug ustunroq) — shunday qilib
  release APK'da cleartext butunlay o'chiq, debug APK'da yoqiq bo'ladi.

## 3. HTTP logging darajasi

- `ApiClient.kt`da:
  ```kotlin
  private val logging = HttpLoggingInterceptor().apply {
      level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY
              else HttpLoggingInterceptor.Level.BASIC
  }
  ```
- `BASIC` daraja faqat method/URL/status-code/vaqtni yozadi — bemor ID va
  rasm baytlari (body) release buildda logga tushmaydi.

## 4. Vaqtinchalik fayllarni tozalash

- `ScreeningViewModel.uploadFile(file: File)`: hozirgi `send(part)`
  chaqiruvidan keyin (muvaffaqiyat yoki xato — ikkala holatda ham) fayl
  o'chiriladi. Amalga oshirish: `send()` ichidagi `try`/`catch` atrofiga
  `finally { file.delete() }` qo'shish uchun `uploadFile` o'zi faylni
  yopadigan qilib qayta yoziladi (fayl `send()`ga emas, `uploadFile`ga
  tegishli bo'lgani uchun tozalash ham shu yerda):
  ```kotlin
  fun uploadFile(file: File) {
      val part = MultipartBody.Part.createFormData(...)
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
  (Hozirgi alohida `send()` funksiyasi `uploadFile` ichiga integratsiya
  qilinadi, chunki tozalash faqat fayl-asosli yuklashga tegishli;
  `uploadUri` — galereya oqimi — fayl yaratmaydi, unga tegishli emas.)
- `CameraScreen.kt`da `CaptureReviewSheet`'ning `onConfirm` callback'i hozir
  `pendingFile = null; vm.uploadFile(fileToReview); onResult()` qiladi —
  o'zgarishsiz qoladi (fayl endi ViewModel ichida o'chiriladi).
- `ImageCapture.OnImageSavedCallback.onError` (`CameraScreen.kt:225`)
  hozirgidek `vm.uploadFile(...)` chaqiradi — u orqali ham fayl tozalanadi
  (ViewModel darajasida markazlashgan tozalash tufayli qo'shimcha o'zgarish
  shart emas).
- Yangi: `MainActivity.onCreate()`da, `setContent`dan oldin,
  `cleanupStaleCaptures(applicationContext)` xususiy funksiyasi chaqiriladi
  — `cacheDir`dagi `fundus_*.jpg` naqshiga mos fayllarni (oldingi
  crash/kutilmagan chiqish qoldiqlari) o'chiradi. Bu funksiya
  `MainActivity.kt`ning o'zida (fayl darajasida private) joylashadi —
  yangi qatlam/modul kerak emas, doirasi juda kichik.

## Testlar

Loyihada hali test infratuzilmasi yo'q (PLAN.md bo'lim 7, alohida 🔴 band).
Shu spec doirasida test qo'shish **qamrovdan tashqarida** — test
infratuzilmasi (JUnit, MockWebServer sozlash) alohida ish sifatida
qoladi. Qo'lda tekshirish (manual QA) implementatsiya rejasida
belgilanadi: debug/release build farqini, header borligini (masalan
backend log orqali yoki debug HTTP proxy bilan), va fayl tozalanishini
qo'lda tasdiqlash.

## Qamrovdan tashqari

- Clean Architecture refaktoringi (alohida, avval tasdiqlangan spec —
  `2026-07-31-clean-architecture-refactor-design.md`).
- Login/token-asosli autentifikatsiya (hozircha statik API key yetarli).
- Kamera sifat nazorati, rasm siqish, retry/cancel, offline rejim,
  lokalizatsiya, ProGuard — PLAN.md'dagi qolgan bandlar.

## Riskler / diqqat talab qiladigan joylar

- `local.properties`da `API_KEY` bo'lmasa, build placeholder
  (`"dev-key-CHANGE-ME"`) bilan muvaffaqiyatli o'tadi — bu ataylab shunday
  (build'ni buzmaslik uchun), lekin foydalanuvchi buni ko'rib, haqiqiy
  kalitni qo'ymasdan release qilib yubormasligi kerak. Kelajakda CI/release
  jarayonida bu placeholder tekshiruvi (masalan Gradle task orqali
  release build'da placeholder bo'lsa fail qilish) qo'shilishi mumkin —
  hozircha qamrovdan tashqarida, faqat shu risk sifatida qayd etiladi.
- `network_security_config.xml` fayl nomi debug va main source set'larda
  bir xil bo'lishi shart (resource merge orqali override ishlashi uchun).
- `ScreeningViewModel.uploadFile` refaktoringi (`send()`ni ichiga
  integratsiya qilish) mavjud `send()`ning boshqa chaqiruvchisi yo'qligini
  talab qiladi — tekshirildi: `send()` faqat `uploadFile`dan chaqiriladi.
