# EYE DETECT AI Android — Clean Architecture refaktoringi

**Sana:** 2026-07-31 (xavfsizlik bo'limi 2026-08-03'da yangilandi)
**Holat:** Tasdiqlangan (foydalanuvchi tomonidan)

## Kontekst

Loyihaga `clean-code-solid-dry-kiss.md` (Clean Code/SOLID/DRY/KISS qo'llanmasi)
qo'shildi va foydalanuvchi shu qo'llanma asosida loyiha strukturasini qayta
ko'rib chiqishni so'radi. Joriy holat — ishlaydigan skelet (bemor → kamera →
natija oqimi), lekin arxitektura tekis: `ScreeningViewModel` to'g'ridan-to'g'ri
`ApiClient` singletoniga (Retrofit) bog'langan, UI qatlami tarmoq DTO'sini
(`PredictResponse`) bevosita iste'mol qiladi va uning ustida xom-string
solishtirish (`decision == "REFER"`) 3 joyda takrorlangan.

Bu — `PLAN.md`da (`plan/` papkasiga ko'chirilgan) reja qilingan keyingi
qadamlarning bir qismi: arxitektura + xavfsizlik (bo'lim 1) ustida ishlash.

**Yangilanish (2026-08-03):** PLAN.md bo'lim 1'dagi xavfsizlik tuzatishlari
(HTTP body logging faqat debug buildda, release cleartext traffic cheklash,
`X-API-Key` auth header, vaqtinchalik fayllarni tozalash) shu refaktordan
mustaqil ravishda, joriy tekis strukturada allaqachon bajarilgan
(`ApiClient.kt`, `AndroidManifest.xml` + `network_security_config.xml`,
`MainActivity.kt`). Shuningdek `API_BASE_URL` endi build-turiga bog'liq
(`app/build.gradle.kts`dagi `RELEASE_API_URL`/`checkReleaseSecrets`, DI'dan
mustaqil, gradle darajasida qoladi). Quyidagi "Xavfsizlik tuzatishlari"
bo'limi endi yangi funksionallik emas — mavjud, ishlayotgan xavfsizlik
mantiqini Hilt `NetworkModule`ga **ko'chirish** vazifasini tavsiflaydi.

## Maqsad

1. `data/`/`domain/`/`presentation/` qatlamlariga bo'lingan Clean Architecture
   strukturasiga o'tish, DIP'ga rioya qilish (ViewModel → UseCase → Repository
   interfeysi, konkret Retrofit klientiga emas).
2. Hilt orqali Dependency Injection.
3. `plan/` papkasi: `PLAN.md` + `clean-code-solid-dry-kiss.md`.
4. Mavjud xavfsizlik mantiqini (auth header, debug-only body logging,
   `BuildConfig.API_BASE_URL`) `ApiClient.kt` singletonidan Hilt
   `NetworkModule`ga ko'chirish — xatti-harakat o'zgarmaydi.
5. Yangi qatlamlar uchun asosiy unit testlar (UseCase, Repository, ViewModel).

Xatti-harakat (UI oqimi, ekranlar tashqi ko'rinishi) o'zgarmaydi — bu sof
struktura refaktoringi + xavfsizlik tuzatishi, yangi funksionallik emas.

## Arxitektura

```
app/src/main/java/com/eyedetect/ai/
├── EyeDetectApp.kt                    # @HiltAndroidApp Application
├── data/
│   ├── remote/
│   │   ├── ApiService.kt              # Retrofit interfeysi (o'zgarishsiz)
│   │   └── PredictResponse.kt         # tarmoq DTO (@SerializedName, wire-format)
│   └── repository/
│       └── ScreeningRepositoryImpl.kt # DTO -> domain model mapping shu yerda
├── domain/
│   ├── model/
│   │   └── ScreeningResult.kt         # domain model + Decision enum
│   ├── repository/
│   │   └── ScreeningRepository.kt     # interfeys (DIP)
│   └── usecase/
│       └── SubmitScreeningUseCase.kt  # validatsiya + repository chaqiruvi
├── presentation/
│   ├── MainActivity.kt                # @AndroidEntryPoint
│   ├── screening/
│   │   └── ScreeningViewModel.kt      # @HiltViewModel, UseCase'ga bog'liq
│   ├── screens/
│   │   ├── PatientScreen.kt
│   │   ├── CameraScreen.kt
│   │   └── ResultScreen.kt
│   ├── components/
│   │   └── EyeComponents.kt
│   └── theme/
│       └── (Color.kt, Dimens.kt, Theme.kt, Type.kt)
└── di/
    ├── NetworkModule.kt               # OkHttp/Retrofit/ApiService (Hilt @Provides)
    └── RepositoryModule.kt            # ScreeningRepository -> Impl bog'lanishi (@Binds)
```

## Komponentlar

### `domain/model/ScreeningResult.kt`
UI'ga mos, tarmoq formatidan mustaqil domain model:
```kotlin
enum class Decision { REFER, NO_REFER, UNGRADABLE }

data class ScreeningResult(
    val examId: String,
    val patientId: String?,
    val eye: String?,
    val decision: Decision,
    val decisionText: String,
    val confidence: Double,        // probability
    val icdrGrade: Int,
    val gradeLabel: String,
    val quality: String,
    val heatmapUrl: String?,       // allaqachon absolyut URL (mapping bosqichida hal qilinadi)
    val imageUrl: String?,         // allaqachon absolyut URL
    val disclaimer: String,
)
```
`Decision`ga mapping: backend `decision` maydoni `"REFER"`/`"NO_REFER"` dan
tashqari qiymat qaytarsa (masalan `"UNGRADABLE"` yoki noma'lum), `UNGRADABLE`
sifatida talqin qilinadi — hozirgi UI mantig'i
(`decision != "REFER" && decision != "NO_REFER"`) bilan bir xil xulq.

### `domain/repository/ScreeningRepository.kt`
```kotlin
interface ScreeningRepository {
    suspend fun submitScreening(
        patientId: String?,
        eye: String,
        imageBytes: ByteArray,
        fileName: String,
        mimeType: String,
    ): ScreeningResult
}
```
Domain qatlami Android/Retrofit/OkHttp turlaridan mustaqil — faqat oddiy
Kotlin turlari.

### `domain/usecase/SubmitScreeningUseCase.kt`
`operator fun invoke(...)` — `eye` bo'sh emasligini va `imageBytes` bo'sh
emasligini tekshiradi (`IllegalArgumentException`), so'ng repository'ga
delegatsiya qiladi. Xato xabar matnlari (lokalizatsiya) bu yerda emas —
presentation qatlamida.

### `data/repository/ScreeningRepositoryImpl.kt`
`ApiService` va `baseUrl: String` konstruktorda inject qilinadi
(`di/NetworkModule.kt`ga qo'shiladigan
`@Provides @Named("baseUrl") fun provideBaseUrl(): String = BuildConfig.API_BASE_URL`
orqali). `imageBytes`dan `MultipartBody.Part` quradi, `ApiService.predict()`
chaqiradi, so'ng shu faylning o'zida yozilgan
`private fun PredictResponse.toDomain(baseUrl: String): ScreeningResult`
extension-mapper orqali domain modelga aylantiradi (shu yerda
`heatmapUrl`/`imageUrl` nisbiy yo'llar absolyutga aylantiriladi — hozirgi
`ApiClient.absoluteUrl()` mantig'i shu yerga, xususiy `fun absoluteUrl(baseUrl, path)`
yordamchi funksiyasiga ko'chadi). Noma'lum/kutilmagan `decision` qiymati
`Decision.UNGRADABLE`ga tushadi (§Komponentlar → `ScreeningResult`).

### `presentation/screening/ScreeningViewModel.kt`
`@HiltViewModel class ScreeningViewModel @Inject constructor(
    private val submitScreening: SubmitScreeningUseCase,
) : ViewModel()`

`uploadFile(file: File)` va `uploadUri(context: Context, uri: Uri)` — bu
ikkalasi ham Android I/O (`File.readBytes()` / `ContentResolver.openInputStream`)
orqali `ByteArray`ga aylantiriladi (Context faqat shu yerda, presentation
qatlamida ishlatiladi — domain va data qatlamlari Context'ni bilmaydi), so'ng
`SubmitScreeningUseCase`ni chaqiradi. `UiState` sealed interfeysi va
`friendly()` xato xabar tarjimasi o'zgarishsiz qoladi (`UiState.Success`
endi `PredictResponse` emas, `ScreeningResult` saqlaydi).

### `di/NetworkModule.kt`
Joriy `ApiClient.kt`dagi auth interceptor, logging interceptor va Retrofit
qurilishini bir xil xatti-harakat bilan Hilt `@Provides` metodlariga
ko'chiradi:
```kotlin
@Module @InstallIn(SingletonComponent::class)
object NetworkModule {
    @Provides @Singleton
    fun provideAuthInterceptor(): Interceptor = Interceptor { chain ->
        chain.proceed(
            chain.request().newBuilder()
                .addHeader("X-API-Key", BuildConfig.API_KEY)
                .build()
        )
    }

    @Provides @Singleton
    fun provideLoggingInterceptor(): HttpLoggingInterceptor =
        HttpLoggingInterceptor().apply {
            redactHeader("X-API-Key")
            level = if (BuildConfig.DEBUG) Level.BODY else Level.BASIC
        }

    @Provides @Singleton
    fun provideOkHttp(
        auth: Interceptor,
        logging: HttpLoggingInterceptor,
    ): OkHttpClient = OkHttpClient.Builder()
        .addInterceptor(auth)
        .addInterceptor(logging)
        .connectTimeout(15, SECONDS).readTimeout(30, SECONDS).writeTimeout(30, SECONDS)
        .build()

    @Provides @Singleton
    fun provideApiService(okHttp: OkHttpClient): ApiService = Retrofit.Builder()
        .baseUrl(BuildConfig.API_BASE_URL)
        .client(okHttp)
        .addConverterFactory(GsonConverterFactory.create())
        .build()
        .create(ApiService::class.java)
}
```
Xatti-harakat joriy `ApiClient.kt` bilan bir xil: auth header har doim
qo'shiladi (backend uni talab qiladi), logging har doim qo'shiladi lekin
darajasi build turiga qarab (`BASIC` release'da — URL/status/vaqt, tana
yo'q; `BODY` debug'da), `X-API-Key` logda hech qachon ko'rinmaydi
(`redactHeader`). `ApiClient.absoluteUrl()` mantig'i
`ScreeningRepositoryImpl`dagi `PredictResponse.toDomain(baseUrl)`
mapperiga ko'chadi (quyida).

### `di/RepositoryModule.kt`
```kotlin
@Module @InstallIn(SingletonComponent::class)
abstract class RepositoryModule {
    @Binds abstract fun bindScreeningRepository(
        impl: ScreeningRepositoryImpl,
    ): ScreeningRepository
}
```

## Xavfsizlik — joriy holat (o'zgartirilmaydi, faqat ko'chiriladi)

Quyidagilar PLAN.md bo'lim 1 doirasida bu refaktordan mustaqil, alohida
ishlarda (2026-08-03 gacha) allaqachon bajarilgan. Refaktor davomida
xatti-harakat bir xil qolishi shart — faqat kod joyi o'zgaradi:

1. **HTTP logging** — release'da `BASIC`, debug'da `BODY`
   (`di/NetworkModule.kt`ga ko'chadi, yuqorida).
2. **Cleartext traffic** — `AndroidManifest.xml`da
   `android:usesCleartextTraffic="false"` + `network_security_config.xml`
   (debug flavor'da alohida config orqali HTTP ruxsat etiladi). Bu
   manifest/res darajasida, refaktordan ta'sirlanmaydi — o'zgarishsiz qoladi.
3. **Auth header** — `X-API-Key` (`di/NetworkModule.kt`ga ko'chadi, yuqorida).
4. **Vaqtinchalik fayllar** — `ScreeningViewModel`da upload tugagach
   (`finally { file.delete() }`) va `MainActivity`da ilova ishga tushganda
   eski `fundus_*.jpg` qoldiqlarini tozalash. `presentation/` qatlamiga
   ko'chganda ham xuddi shu joyda (ViewModel/MainActivity), faqat yangi
   paket yo'lida qoladi.
5. **Release `API_BASE_URL`** — `app/build.gradle.kts`dagi
   `RELEASE_API_URL` (`local.properties`, HTTPS majburiy) +
   `checkReleaseSecrets` gradle task'i. Bu Gradle konfiguratsiya darajasida,
   DI qatlamiga bog'liq emas — o'zgarishsiz qoladi.

## Testlar

- `domain/usecase/SubmitScreeningUseCaseTest.kt` — bo'sh `eye`, bo'sh
  `imageBytes` uchun `IllegalArgumentException`; to'g'ri holatda
  repository'ga to'g'ri parametrlar bilan delegatsiya qilinishini tekshiradi
  (fake/mock `ScreeningRepository`).
- `data/repository/ScreeningRepositoryImplTest.kt` — MockWebServer bilan:
  muvaffaqiyatli javob → to'g'ri `ScreeningResult` mapping (jumladan
  `Decision` enum va absolyut URL'lar), 4xx/5xx → `HttpException` ko'tariladi,
  timeout → `SocketTimeoutException`.
- `presentation/screening/ScreeningViewModelTest.kt` — fake
  `ScreeningRepository`/`SubmitScreeningUseCase` bilan `UiState` o'tishlari:
  Idle → Loading → Success, Idle → Loading → Error (turli xato turlari uchun
  `friendly()` xabarlari).

Test kutubxonalari: `junit`, `kotlinx-coroutines-test`, `mockwebserver`
(OkHttp), `truth` (assertion).

## Qamrovdan tashqari (keyingi bosqichlar, PLAN.md'da)

Kamera sifat nazorati (Laplasian variansi), rasm siqish, retry/cancel
logikasi, offline (Room/WorkManager), navigatsiya holatini saqlash,
lokalizatsiya, ProGuard/R8 yoqish — bularning barchasi shu refaktordan keyin,
alohida ishlar sifatida qoladi.

## Riskler / diqqat talab qiladigan joylar

- `hilt-compiler` KSP annotatsiya protsessori qo'shilishi build vaqtini
  biroz oshiradi — kichik loyiha uchun sezilarli emas.
- `PredictResponse` → `ScreeningResult` mapping xato bo'lsa (masalan
  noma'lum `decision` qiymati), `UNGRADABLE`ga tushishi kerak — mapper
  testda bu holat alohida tekshiriladi.
- `ScreeningViewModel` konstruktor imzosi o'zgargani sababli
  `AppRoot()`dagi `viewModel()` chaqiruvi `hiltViewModel()`ga almashtiriladi
  — `MainActivity` `@AndroidEntryPoint` bo'lishi shart, aks holda runtime
  xato beradi.
- `AndroidManifest.xml`da `<application android:name=".EyeDetectApp" ...>`
  qo'shilishi shart — aks holda Hilt komponent grafigi ishga tushmaydi va
  ilova darhol crash beradi (`@HiltAndroidApp` faqat sinf darajasida yetarli
  emas, manifest bilan bog'lanishi kerak).
