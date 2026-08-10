# EYE DETECT AI — Android: Keyingi ishlar rejasi

> Joriy holat: ishlaydigan skelet. Bemor → Kamera → Natija oqimi ishlaydi,
> lekin ko'p joyda ko'rgazmali/soddalashtirilgan yechimlar bor. Quyida shu
> bo'shliqlarni yopish uchun aniq ish rejasi, muhimlik darajasi bo'yicha
> guruhlangan.

Muhimlik belgilari: 🔴 muhim (ishlab chiqarishga chiqishdan oldin shart)
· 🟡 o'rta (sifat/UX uchun kerak) · 🟢 keyinroq (nice-to-have)

---

## 1. Xavfsizlik va maxfiylik (PHI) 🔴

Bemor ID va fundus rasm — shaxsiy tibbiy ma'lumot.

- [x] `usesCleartextTraffic`ni release buildda `false` qildik, faqat HTTPS
      (`AndroidManifest.xml` + `network_security_config.xml`) — debug buildda
      `src/debug/res/xml/network_security_config.xml` orqali cleartext hali
      ruxsat etilgan (lokal backend bilan test uchun).
- [x] `ApiClient.kt`dagi `HttpLoggingInterceptor.Level`ni `BuildConfig.DEBUG`
      shartiga bog'ladik — release buildda faqat `BASIC` (URL/status/vaqt),
      body (bemor ID, rasm bytelari) logga yozilmaydi; `X-API-Key` headeri
      ham `redactHeader` bilan logdan yashirilgan.
- [x] Backend bilan autentifikatsiya qo'shildi: `ApiClient.kt`dagi
      `authInterceptor` har bir so'rovga `X-API-Key: BuildConfig.API_KEY`
      headerini qo'shadi (kalit `local.properties`/build config orqali).
- [x] `cacheDir`dagi vaqtinchalik fundus rasm fayli endi har doim
      o'chiriladi: `ScreeningViewModel.uploadFile()`dagi `finally` bloki
      (muvaffaqiyat ham, xato ham) + `MainActivity.cleanupStaleCaptures()`
      ilova ishga tushganda qolib ketgan eski `fundus_*.jpg` fayllarni
      tozalaydi (masalan, jarayon kutilmagan o'chishidan keyin).

## 2. Kamera va sifat nazorati 🔴

- [x] `QualityPanel`dagi fokus/yorug'lik qiymatlarini haqiqiy qilish:
      CameraX `ImageAnalysis` + Laplasian variansi orqali fokus, histogram
      o'rtacha yorqinligi orqali yorug'lik (`vision/FrameQualityAnalyzer.kt`,
      `CameraScreen.kt`ga ulandi). Chegaralar taxminiy kalibrlangan — haqiqiy
      qurilmalarda sinovdan so'ng sozlash kerak. Sifat past bo'lsa
      (`BAD`), rasm olingach ko'rib chiqish varag'ida ogohlantirish
      chiqadi (qat'iy bloklanmaydi — qayta olishga undaydi).
- [x] `QualityPanel`dagi "joylashuv" (ko'z markazdami) endi ML Kit
      `FaceDetector` orqali real: tanlangan ko'z (`vm.eye`ga mos
      `LEFT_EYE`/`RIGHT_EYE` landmarki) kadr markaziga qanchalik yaqinligi
      hisoblanadi (`vision/EyeDetectionAnalyzer.kt`). Hali qilinmagan:
      - Yuz umuman aniqlanmasa (masalan juda yaqin makro surat, faqat
        ko'z to'ldirilgan kadr) landmark topilmaydi — hozircha `WARN`
        qaytariladi, iris-darajasidagi to'g'ridan-to'g'ri aniqlash (yuzsiz)
        keyingi bosqich.
      - Old kamera bilan o'z-o'zini suratga olishda chap/o'ng ko'z
        moslashuvi oyna-effektiga qarab tekshirilmagan (hozir orqa
        kamera ishlatiladi).
- [x] Mahalliy CV evristikasi (xiralik/opacity + qizil refleks) qo'shildi:
      olingan surat ustida `vision/PupilHeuristics.kt` ML Kit (aniq rejim)
      bilan ko'z hududini topib, eng qorong'i piksellarning rangini (HSV)
      tahlil qiladi — normal qorachiq qop-qora, oqarish/kulranglashish
      xiralik belgisi, qizg'ish aks esa normal qizil refleks hisoblanadi.
      Natija `ResultScreen`da backend natijasidan alohida, aniq
      "tashxis emas" ogohlantirishi bilan ko'rsatiladi (`ScreeningViewModel`
      `localHeuristic` oqimi, `EyeComponents.kt` `PupilHeuristicCard`).
      Hali qilinmagan:
      - Ikki ko'z simmetriyasi endi qo'shildi — pastga qarang (4-band,
        Room ustiga qurilgan).
- [x] Flash boshqaruvi qo'shildi: `CameraScreen.kt`da yuqori chapdagi chip
      orqali YOQILGAN/AVTO/O'CHIQ o'rtasida almashtirish mumkin
      (`ImageCapture.flashMode`, standart holat — YOQILGAN, chunki qizil
      refleks testi flash bilan olingan suratda ancha ishonchli). Faqat
      surat olish payti bir marta yonadi (doimiy torch emas) — shu tarzda
      batareya/qizib ketishdan saqlanadi.
- [x] `imageCapture.takePicture`ning `onError` holatida foydalanuvchiga xato
      ko'rsatiladi (`CameraScreen.kt` — `captureError` holati, `WarningBanner`
      + `camera_capture_error` matni), fayl o'chiriladi va natija ekraniga
      o'tilmaydi — foydalanuvchi qayta bosishi kerak.
- [x] Rasmni yuborishdan oldin siqish/kichraytirish qo'shildi:
      `vision/BitmapLoader.compressForUpload()` (uzun tomoni ~1500px gacha,
      JPEG quality ~85%) `ScreeningViewModel`da yuborishdan oldin chaqiriladi;
      birlik testlar bilan qoplangan (`BitmapLoaderTest`).
- [x] Kamera ruxsati rad etilganda tushuntirish matni + "Sozlamalarga o'tish"
      tugmasi qo'shildi (`CameraScreen.kt` — `camera_open_settings`,
      `Settings.ACTION_APPLICATION_DETAILS_SETTINGS`ga olib boradi).

## 3. Tarmoq va ishonchlilik 🟡

- [x] HTTP xato kodlarini alohida ushlab, tushunarli xabar berish:
      `friendly()` endi `retrofit2.HttpException`ni ham taniydi
      (`httpErrorMessage()`) — avval backend xato tanasidagi
      `{"detail": "..."}` (odatiy FastAPI validatsiya formati) bo'lsa
      o'shani ko'rsatadi, bo'lmasa kod oralig'iga qarab (400/422, 401/403,
      404, 429, 5xx, boshqa) lokalizatsiya qilingan xabar beradi
      (`error_bad_request`/`error_unauthorized`/... `strings.xml`, uz/ru/en).
- [x] Qayta urinish (retry): xato bo'lsa (`UiState.Error.canRetry`),
      so'nggi yuborilgan fayl/URI o'chirilmay saqlanadi va `vm.retry()`
      xuddi shu rasmni qayta suratga olmasdan qayta yuboradi — natija
      ekranidagi "Qayta urinish" tugmasi endi shuni chaqiradi (faqat
      manba topilmasa yoki muvaffaqiyatli/UNGRADABLE holatda eski
      "kameraga qaytish" xulqiga qaytadi). `MainActivity.kt`dagi `AppRoot`
      shu farqni `uiState`ga qarab hal qiladi.
- [x] Ekrandan chiqishda so'rovni bekor qilish: `ScreeningViewModel`
      `activeJob`ni kuzatadi; Natija ekranida (Loading paytida) orqaga
      qaytilsa `vm.cancelUpload()` chaqiriladi (`AppRoot`dagi `pop()`),
      `LoadingState`dagi (avvaldan mavjud, lekin ulanmagan) "Bekor qilish"
      tugmasi endi ishlaydi. Fayl faqat fon ishi to'liq to'xtagach
      o'chiriladi (`Job.join()` orqali) — aks holda hali o'qilayotgan
      faylni o'chirishga urinish (masalan Windows'da) muvaffaqiyatsiz
      tugashi mumkin edi.
- [x] Haqiqiy yuklash progressi: `data/ProgressRequestBody.kt` (okio
      `ForwardingSink` bilan) multipart so'rov baytlarini kuzatadi;
      `ScreeningViewModel.uploadProgress` (0f..1f) orqali `LoadingState`ga
      uzatiladi — yuklash davom etayotganda haqiqiy foiz (`LinearProgressIndicator`)
      ko'rsatiladi, undan keyingi bosqichlar (sifat/tahlil/tayyorlash)
      uchun backend'dan alohida signal yo'qligi sababli avvalgidek umumiy
      spinner qoladi (soxta aniqlik da'vo qilinmaydi).
- [x] `StatusBadge`ni haqiqiy health-check bilan almashtirdik:
      `ApiClient.ping()` backend manziliga qisqa timeout (3s)li HEAD
      so'rovi yuboradi; `PatientScreen` ekranga kirishda
      `vm.checkBackendHealth()`ni chaqiradi, natija kelguncha "online"
      (avvalgi xulq) ko'rsatiladi.

Barchasi uchun testlar yozildi (`ScreeningViewModelTest` — HTTP kod
xaritalash, retry, cancel+fayl o'chirish, health-check; jami 29/29 test
yashil, `./gradlew testDebugUnitTest`).

## 4. Ma'lumotlarni saqlash (offline) 🟡

- [x] Room DB qo'shildi: har bir muvaffaqiyatli skrining natijasi (`examId`,
      `patientId`, `eye`, `decision`/`decisionText`, `icdrGrade`/`gradeLabel`,
      `probability`, `quality`, `imageUrl`/`heatmapUrl`, mavjud bo'lsa
      mahalliy `localOpacity`/`localRedReflex`, `processedAt`) avtomatik
      saqlanadi (`data/history/` — `ScreeningHistoryEntity`,
      `ScreeningHistoryDao`, `ScreeningHistoryDatabase`,
      `ScreeningHistoryRepository`; `ScreeningViewModel.doRequest()`da
      backend javobi kelgach chaqiriladi, xato bo'lsa jim o'tkazib
      yuboriladi — tarix ixtiyoriy, asosiy oqim uchun kritik emas).
      Room `kapt` orqali ishlaydi (KSP emas) — Kotlin 2.2.10 bilan;
      diqqat: Room **2.6.1** kapt annotatsiya protsessori Kotlin 2.2
      metadata (v2.2.0) formatini o'qiy olmaydi ("maximum supported
      version is 2.0.0" xatosi berardi), shu sababli **2.7.1**ga
      ko'tarildi — kelajakda Kotlin versiyasi yana oshsa, Room versiyasini
      ham birga yangilash kerak bo'ladi.
      Hali qilinmagan:
      - Eski yozuvlarni tozalash/limitlash siyosati yo'q (masalan, N ta
        yoki M kundan eski yozuvlarni o'chirish) — hozir cheksiz o'sadi.
- [x] **Ikki ko'z simmetriyasini solishtirish** qo'shildi
      (`vision/EyeSymmetryAnalyzer.kt`, klinikadagi Bruckner testi g'oyasiga
      o'xshash): joriy ko'zning mahalliy evristika natijasi (opacity/
      red-reflex + xom HSV qiymatlari) bemor ID bo'yicha qarshi ko'zning
      Room'da saqlangan oxirgi natijasi bilan solishtiriladi. Bitta ko'z
      "normal" ko'rinsa ham, ikki ko'z orasidagi sezilarli farq (masalan,
      biri BAD, ikkinchisi emas, yoki rang farqi katta) alohida
      ogohlantiruvchi belgi sifatida ko'rsatiladi (`ScreeningViewModel`
      `symmetry` oqimi, `EyeSymmetryCard` — faqat bemor ID kiritilgan va
      qarshi ko'z avval skrining qilingan bo'lsa ko'rinadi).
      Texnik eslatma: birinchi saqlashda mahalliy evristika hali tayyor
      bo'lmasligi mumkinligi uchun (ML Kit ACCURATE — sekinroq),
      `ScreeningHistoryDao.updateHeuristic()` orqali keyinroq to'ldiriladi;
      `CompletableDeferred` bilan tarix yozuvi ID'si va evristika
      natijasi bir-biriga bog'lanadi (qaysi biri oldin tugashidan
      qat'i nazar to'g'ri ishlashi uchun). Room sxemasi shu sababli
      v1→v2 (`localHueDeg`/`localSaturation`/`localValue` qo'shildi,
      `fallbackToDestructiveMigration` — loyiha hali relizga chiqmagan).
      Hali qilinmagan: solishtirish yoshi/muddatiga chegara yo'q (masalan,
      6 oy oldingi natija bilan solishtirilishi mumkin — foydalanuvchi
      buni faqat ko'rsatilgan sanadan bilib oladi).
- [x] WorkManager: internet yo'q paytda rasmni navbatga qo'yib, ulanish
      tiklanganda avtomatik yuborish. `ScreeningViewModel.uploadFile()`/`uploadUri()`da
      `UnknownHostException`/`ConnectException` (haqiqiy "ulanish yo'q" holatlari —
      `SocketTimeoutException` ataylab kirmaydi, sekin server bilan aralashmasin deb,
      o'sha holatda odatdagidek "Qayta urinish" xato ekrani chiqadi) ushlanganda rasm
      xato ko'rsatish o'rniga avtomatik navbatga qo'yiladi: baytlar doimiy saqlash
      joyiga (`filesDir/pending_uploads/`, cacheDir emas) yoziladi, yangi
      `pending_uploads` Room jadvaliga (`data/upload/` — `PendingUploadEntity`,
      `PendingUploadDao`, `PendingUploadRepository`; `ScreeningHistoryDatabase`
      v2→v3) yozuv qo'shiladi va `upload/UploadScheduler.enqueue()` orqali
      `NetworkType.CONNECTED` cheklovli, nomlangan (unique, ID bo'yicha) WorkManager
      vazifasi rejalashtiriladi. `upload/UploadWorker.kt` ulanish tiklangach
      `ApiClient.service.predict()`ni chaqiradi — muvaffaqiyat bo'lsa tarixga
      saqlanadi (mahalliy evristikasiz) va bildirishnoma ko'rsatiladi
      (`NotificationHelper.showUploadSuccess`, tap qilinsa Tarix ekraniga —
      `MainActivity.EXTRA_OPEN_HISTORY`); tarmoq xatosi yoki 5xx bo'lsa
      eksponensial orqaga chekinish bilan qayta uriniladi (`Result.retry()`,
      8 urinishgacha); boshqa doimiy xato (masalan 4xx) bo'lsa yozuv
      o'chirilmaydi, `failed = true` bilan belgilanadi va foydalanuvchi
      Tarix ekranidagi "Navbatda" bo'limidan qo'lda qayta urinishi yoki bekor
      qilishi mumkin (`HistoryScreen.kt`). Natija ekranida navbatga qo'yilgan
      holat uchun alohida `UiState.Queued` + `QueuedState` composable qo'shildi.
      `ScreeningViewModel`ga WorkManager chaqiruvi `scheduleUpload` parametri
      orqali inject qilinadi (`healthCheck`dagi kabi sabab — birlik testida
      haqiqiy WorkManager/tarmoq kerak emas).
- [x] Bemor tarixini ko'rish ekrani qo'shildi: Bosh ekrandan "Tarix" kartasi
      orqali ochiladi (`ui/HistoryScreen.kt`) — barcha saqlangan
      skrininglarni sana bo'yicha kamayish tartibida, qaror/ICDR/mahalliy
      evristika bilan ko'rsatadi, har bir yozuvni o'chirish imkoniyati bilan.
      Hali qilinmagan: bemor bo'yicha filtrlash/qidirish (hozir faqat
      to'liq ro'yxat), massaviy tozalash (faqat bittalab o'chirish bor).

## 5. Holatni saqlash va navigatsiya 🟡

- [x] `MainActivity.kt`dagi ekran holati (`Screen` enum) `rememberSaveable`ga
      o'tkazildi: `backStack: SnapshotStateList<Screen>` + `ScreenListSaver`
      (enum nomlarini `List<String>` sifatida saqlaydi/tiklaydi) — ekran
      aylanishida va jarayon o'chib qayta tiklanishida (process death,
      `savedInstanceState`) yo'qolmaydi.
      Eslatma: bu faqat navigatsiya holati (qaysi ekrandaligi) uchun —
      `ScreeningViewModel`ning o'zi (bemor ID, `uiState`) hali
      `SavedStateHandle`ga bog'lanmagan, process death'da yo'qoladi;
      demo skrining oqimi uchun bu muhim emas deb topildi (masalan,
      "Loading" holatida jarayon o'chsa, baribir asl rasm yo'qolgan
      bo'ladi — qaytadan boshlash tabiiy yechim).
- [x] To'liq Compose Navigation kutubxonasiz, lekin haqiqiy back-stack
      mantiqi bilan: `push`/`pop`/`resetTo` + `BackHandler(enabled =
      backStack.size > 1)` — tizim orqaga tugmasi endi to'g'ri ishlaydi
      (har bir ichki ekrandan bir qadam orqaga, Bosh ekranda ilovadan
      chiqadi).

## 6. Lokalizatsiya 🟢

- [x] Qolgan qattiq kodlangan matnlar `strings.xml`ga (uz/ru/en) chiqarildi:
      `EyeComponents.kt` (`TrafficLightCard` va `EyeSelector`dagi
      `contentDescription`lari — "Natija:/ishonch/foiz" va tanlangan ✓
      belgisi), `EyeCareComponents.kt` (`MenuCard`/`GameCard`dagi sarlavha —
      subtitle ajratkichi, `IntervalChipRow`dagi "N daqiqa"/"tanlangan"),
      `HistoryScreen.kt` (ICDR daraja qatori formati, "—" bo'sh joy belgisi)
      va `CameraScreen.kt` (`fileLabel()`dagi standart fayl nomi "rasm.jpg"
      va hajm birligi ", MB"). Ekranlarning o'zi (matn/tugmalar) avvaldan
      deyarli to'liq `stringResource` orqali edi — qolganlari asosan
      TalkBack `contentDescription`lari va yordamchi formatlash edi.

## 7. Test qamrovi 🔴

- [x] Test infratuzilmasi qo'shildi: JUnit4, `kotlinx-coroutines-test`,
      Robolectric, MockWebServer (`testImplementation`) va Compose UI test +
      Espresso (`androidTestImplementation`) `app/build.gradle.kts`ga
      qo'shildi (`testOptions.unitTests.isIncludeAndroidResources` Robolectric
      uchun yoqildi).
- [x] Unit testlar: `ScreeningViewModelTest` (`app/src/test/...`, Robolectric)
      holat o'tishlarini (Idle → Loading → Success/Error) va `friendly()`
      xato xabarlari xaritalashni (UnknownHostException/SocketTimeoutException/
      UnknownServiceException/xabarsiz/xabarli generic xato) sinaydi. Buning
      uchun `ScreeningViewModel`ga `ApiService`ni inject qilish imkoniyati
      qo'shildi (`@JvmOverloads` konstruktor parametri — standart qiymati
      `ApiClient.service`, shu bilan androidx `viewModel()` factory ham
      ishlashda davom etadi). `EyeSymmetryAnalyzerTest` (pure JUnit, Room/
      Android'siz) ham qo'shildi. Barchasi `./gradlew testDebugUnitTest`
      bilan yashil (19/19).
- [x] `ApiServiceTest`: MockWebServer bilan `ApiService`ni to'g'ridan-to'g'ri
      (haqiqiy `ApiClient` singletonini chetlab o'tib) sinaydi — muvaffaqiyat
      (JSON parse), 4xx/5xx (`HttpException`), timeout (`SocketTimeoutException`)
      holatlari.
- [x] UI/instrumentation testlar yozildi: `MainFlowTest` (Bosh ekran →
      "Skrining" → bemor ID → Kamera ekraniga yetib borish — CAMERA ruxsati
      ataylab berilmagan, shu sababli ruxsat so'rash holati tekshiriladi) va
      `ResultScreenTest` (`ResultScreen`ni fake `UiState.Success`/`Error`
      bilan to'g'ridan-to'g'ri, kamera/tarmoqsiz sinaydi). Faqat kompilyatsiya
      tasdiqlandi (`./gradlew compileDebugAndroidTestKotlin` — muvaffaqiyatli);
      bu muhitda ulangan qurilma/emulyator yo'qligi sababli haqiqiy ishga
      tushirish (`./gradlew connectedDebugAndroidTest`) tekshirilmagan.

## 8. Relizga tayyorlik 🟢

- [x] `isMinifyEnabled = true` release build turida yoqildi. Har bir
      kutubxona AAR/jar'ining o'z consumer-rules/`META-INF/proguard`
      qoidalarini olib kelishi tekshirildi (Gradle cache'dan AAR/jar'larni
      ochib): Retrofit, OkHttp, Room, WorkManager, ML Kit — hammasi o'z
      qoidalarini olib keladi, qo'shimcha kerak emas. Faqat **Gson**
      (`converter-gson` ham) hech qanday consumer-rules olib kelmaydi —
      shu sababli `proguard-rules.pro`ga qo'lda qo'shildi: `Signature`/
      `*Annotation*` atributlarini saqlash (aks holda `@SerializedName`
      va generic turlar yo'qoladi) + Gson'ning rasmiy tavsiya qilingan
      `TypeAdapterFactory`/`TypeToken` himoyaviy qoidalari. Mavjud
      `-keep class com.eyedetect.ai.data.** { *; }` (DTO/Room entity/DAO)
      saqlab qolindi. `./gradlew assembleRelease` orqali haqiqiy R8
      minifikatsiya bilan tekshirildi: BUILD SUCCESSFUL, `missing_rules.txt`
      yaratilmadi (R8 hech narsa yetishmayotganini aniqlamadi), `mapping.txt`da
      `PredictResponse` maydonlari va uchta Worker klassi (`UploadWorker`,
      `PomodoroWorker`, `ReminderWorker`) o'z nomlarini saqlab qolgani
      tasdiqlandi (WorkManager ularni ism bo'yicha reflection orqali
      qayta yuklaydi, nomi o'zgarsa ishlamay qoladi).
      Hali qilinmagan: haqiqiy qurilmada release APK'ni ishga tushirib
      to'liq qo'lda sinash (bu muhitda emulyator/qurilma yo'q) —
      release'ga chiqishdan oldin tavsiya etiladi.
- [ ] Haqiqiy ilova ikonkasi qo'shish (hozir standart tizim ikonkasi
      ishlatilmoqda).
- [x] `API_BASE_URL`ni build-turlariga (debug/staging/release) ajratish —
      release endi `local.properties`dagi `RELEASE_API_URL`ni ishlatadi
      (HTTPS majburiy), `assembleRelease`/`bundleRelease` oldidan
      `checkReleaseSecrets` orqali tekshiriladi.
- [x] Versiya nomlash strategiyasi: semver (`versionMajor.versionMinor.versionPatch`,
      `app/build.gradle.kts`) yagona manba, `versionCode` shulardan avtomatik
      hisoblanadi (`major*10000 + minor*100 + patch`) — ikkalasi qo'lda
      alohida yangilanib bir-biridan uzilib qolmasligi uchun (versionCode
      unutilsa Play Store yangilanishni jimgina bloklaydi). Har bir maydon
      2 xonagacha (0-99) bo'lishi shart, aks holda yuqori xonaga kirib ketadi.

---

## Tavsiya etilgan tartib

1. **Xavfsizlik (1)** va **Test asosi (7)** — parallel boshlash, chunki
   qolgan barcha o'zgarishlar shular ustiga quriladi.
2. **Kamera sifat nazorati (2)** — mahsulotning asosiy qiymati shu yerda.
3. **Tarmoq ishonchliligi (3)** va **Holat saqlash (5)**.
4. **Offline rejim (4)** — backend/ML qismi barqarorlashgandan keyin.
5. **Lokalizatsiya (6)** va **Reliz sayqallash (8)** — oxirida.
