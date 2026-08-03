# EYE DETECT AI — Android: Keyingi ishlar rejasi

> Joriy holat: ishlaydigan skelet. Bemor → Kamera → Natija oqimi ishlaydi,
> lekin ko'p joyda ko'rgazmali/soddalashtirilgan yechimlar bor. Quyida shu
> bo'shliqlarni yopish uchun aniq ish rejasi, muhimlik darajasi bo'yicha
> guruhlangan.

Muhimlik belgilari: 🔴 muhim (ishlab chiqarishga chiqishdan oldin shart)
· 🟡 o'rta (sifat/UX uchun kerak) · 🟢 keyinroq (nice-to-have)

---

## 1. Xavfsizlik va maxfiylik (PHI) 🔴

Bemor ID va fundus rasm — shaxsiy tibbiy ma'lumot. Hozir bular himoyasiz.

- [ ] `usesCleartextTraffic="true"`ni olib tashlash, faqat HTTPS orqali ishlash
      (`AndroidManifest.xml`). Real backend HTTPS bo'lgandan keyin o'chirish.
- [ ] `ApiClient.kt`dagi `HttpLoggingInterceptor.Level.BODY`ni faqat debug
      build uchun yoqish (`BuildConfig.DEBUG` sharti bilan) — hozir release
      buildda ham to'liq so'rov/javob tanasi (bemor ID, rasm bytelari) logga
      yoziladi.
- [ ] Backend bilan autentifikatsiya (API key yoki token header) qo'shish —
      hozir `ApiService.kt`da hech qanday auth yo'q.
- [ ] `cacheDir`dagi vaqtinchalik rasm fayllarini (kamera surati) yuborilgach
      yoki ilova yopilganda tozalash (hozir faqat "qayta olish"da o'chadi).

## 2. Kamera va sifat nazorati 🔴

- [ ] `QualityPanel`dagi fokus/yorug'lik/joylashuv qiymatlarini haqiqiy
      qilish: CameraX `ImageAnalysis` + Laplasian variansi orqali fokus,
      histogram orqali yorug'lik (README'da ham "keyingi qadam" deb
      belgilangan, hozir `CameraScreen.kt`da qattiq kodlangan
      `GOOD/WARN/GOOD` qiymatlar).
- [ ] `imageCapture.takePicture`ning `onError` holatida foydalanuvchiga xato
      ko'rsatish, natija ekraniga o'tmaslik (hozir xato bo'lsa ham yuborishga
      urinadi).
- [ ] Rasmni yuborishdan oldin siqish/kichraytirish (masalan, uzun tomoni
      ~1500px gacha, JPEG quality ~85%) — hozir to'liq o'lchamdagi rasm
      yuboriladi, sekin/qimmat mobil internetga mos emas.
- [ ] Kamera ruxsati rad etilganda tushuntirish + "Sozlamalarga o'tish"
      tugmasi (hozir faqat statik matn).

## 3. Tarmoq va ishonchlilik 🟡

- [ ] HTTP xato kodlarini (4xx/5xx, Retrofit `HttpException`) alohida
      ushlab, tushunarli xabar berish — hozir `friendly()` faqat
      ulanish/timeout xatolarini biladi, qolgani xom `e.message`.
- [ ] Qayta urinish (retry) tugmasi/logikasi tarmoq xatosida.
- [ ] Ekrandan chiqishda so'rovni bekor qilish (coroutine cancellation) —
      hozir foydalanuvchi orqaga qaytsa ham so'rov davom etadi.
- [ ] Haqiqiy yuklash progressini ko'rsatish (hozir `LoadingState`
      qadam-indikatori qattiq kodlangan, real progress emas).
- [ ] `StatusBadge(online = true)`ni haqiqiy tarmoq/backend health-check
      bilan almashtirish (`PatientScreen.kt`, hozir doim "online").

## 4. Ma'lumotlarni saqlash (offline) 🟡

README'da ham belgilangan, hali boshlanmagan:

- [ ] Room DB: o'tgan skrininglar tarixini (bemor ID, ko'z, natija, sana)
      lokal saqlash.
- [ ] WorkManager: internet yo'q paytda rasmni navbatga qo'yib, ulanish
      tiklanganda avtomatik yuborish.
- [ ] Bemor tarixini ko'rish ekrani (ixtiyoriy, agar talab qilinsa).

## 5. Holatni saqlash va navigatsiya 🟡

- [ ] `MainActivity.kt`dagi ekran holati (`Screen` enum) hozir faqat
      `remember`da — ekran aylanishi yoki jarayon o'chishida yo'qoladi.
      `rememberSaveable` yoki `SavedStateHandle`ga o'tkazish.
- [ ] Compose Navigation (yoki hech bo'lmasa orqaga tugmasi/back-stack
      mantiqi) qo'shishni ko'rib chiqish — hozir qo'lda `when` bilan
      almashtiriladi, orqaga tugmasi tabiiy ishlamaydi.

## 6. Lokalizatsiya 🟢

- [ ] Barcha qattiq kodlangan o'zbekcha matnlarni (`EyeComponents.kt`,
      ekranlar) `strings.xml`ga chiqarish — hozir faqat `app_name`
      tashqarida, qolgani Kotlin ichida qattiq yozilgan. Kelajakda rus/ingliz
      tili qo'shilsa, bu qadam shart bo'ladi.

## 7. Test qamrovi 🔴

Hozir loyihada birorta test yo'q (`test/`, `androidTest/` mavjud emas).

- [ ] Unit testlar: `ScreeningViewModel` (holat o'tishlari: Idle → Loading →
      Success/Error), `friendly()` xato xabarlari xaritalash.
- [ ] UI/instrumentation testlar (Compose test): asosiy oqim — bemor ID
      kiritish → rasm olish (fake) → natija ko'rsatilishi.
- [ ] `ApiService`ni MockWebServer bilan sinash (muvaffaqiyat, 4xx, 5xx,
      timeout holatlari).

## 8. Relizga tayyorlik 🟢

- [ ] `isMinifyEnabled = true` + to'liq ProGuard qoidalarini tekshirish
      (`app/build.gradle.kts:29`, hozir R8 o'chirilgan).
- [ ] Haqiqiy ilova ikonkasi qo'shish (hozir standart tizim ikonkasi
      ishlatilmoqda).
- [x] `API_BASE_URL`ni build-turlariga (debug/staging/release) ajratish —
      release endi `local.properties`dagi `RELEASE_API_URL`ni ishlatadi
      (HTTPS majburiy), `assembleRelease`/`bundleRelease` oldidan
      `checkReleaseSecrets` orqali tekshiriladi.
- [ ] Versiya nomlash strategiyasi (`versionName = "0.1.0"` dan keyin).

---

## Tavsiya etilgan tartib

1. **Xavfsizlik (1)** va **Test asosi (7)** — parallel boshlash, chunki
   qolgan barcha o'zgarishlar shular ustiga quriladi.
2. **Kamera sifat nazorati (2)** — mahsulotning asosiy qiymati shu yerda.
3. **Tarmoq ishonchliligi (3)** va **Holat saqlash (5)**.
4. **Offline rejim (4)** — backend/ML qismi barqarorlashgandan keyin.
5. **Lokalizatsiya (6)** va **Reliz sayqallash (8)** — oxirida.
