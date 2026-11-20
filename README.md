# EYE DETECT AI — Android ilova (Kotlin + Compose + CameraX)

DR skrining demo mobil qismi: kamera bilan fundus rasm olish → backendga yuborish →
svetofor natijasi (🔴/🟢/⚪) + ishonch % + Grad-CAM heatmap ko'rsatish.

> **Skelet eslatmasi:** bu ishlaydigan skelet — asosiy zanjir tayyor, ustiga qurasiz.

## Papka tuzilishi

```
android/
├── settings.gradle.kts
├── build.gradle.kts                 # root plaginlar
├── gradle.properties
└── app/
    ├── build.gradle.kts             # <-- API_BASE_URL local.properties'dan o'qiladi
    ├── proguard-rules.pro
    └── src/main/
        ├── AndroidManifest.xml      # CAMERA + INTERNET ruxsatlari
        ├── res/values/…             # strings, themes
        └── java/com/eyedetect/ai/
            ├── MainActivity.kt      # 3 ekran navigatsiyasi
            ├── ScreeningViewModel.kt# yuborish logikasi + UI holati
            ├── data/
            │   ├── ApiService.kt    # Retrofit endpoint (POST /predict)
            │   ├── ApiClient.kt     # Retrofit/OkHttp sozlamasi
            │   └── PredictResponse.kt# API kontrakti (javob modeli)
            └── ui/
                ├── PatientScreen.kt # bemor ID + ko'z
                ├── CameraScreen.kt  # CameraX + galereya zaxira
                └── ResultScreen.kt  # svetofor + heatmap
```

## Ishga tushirish

1. **Android Studio** (Giraffe yoki yangiroq) da `android/` papkasini oching.
   Studio Gradle wrapper va SDK'larni avtomatik sozlaydi/yuklaydi.
   *(CLI'da qurish uchun avval `gradle wrapper` bilan wrapper yarating.)*

2. **Backend manzilini sozlang** — `local.properties` (repo ildizida, git'ga
   kirmaydi). Kodni tahrirlash SHART EMAS:
   ```properties
   API_KEY=demo123
   API_BASE_URL=http://<NOUTBUK-LAN-IP>:8000/
   ```
   - Emulyator (host'dagi backend): kalitni yozmang — standart `http://10.0.2.2:8000/`
   - Real telefon (bir Wi-Fi): `http://<NOUTBUK-LAN-IP>:8000/` (`ipconfig getifaddr en0`)
   - ngrok: `https://xxxx.ngrok-free.app/`
   > Oxirida `/` bo'lishi SHART — qiymat qurish paytida tekshiriladi.
   > Cleartext `http://` faqat **debug** buildda ruxsat etilgan
   > (`app/src/debug/res/xml/network_security_config.xml`); asosiy manifestda
   > `usesCleartextTraffic="false"`, ya'ni release build HTTPS talab qiladi.
   > Telefondan hotspot ulashsangiz noutbuk IP'si o'zgaradi — qayta tekshiring.

3. **Sync + Run** — real qurilmada (kamera bor) ishga tushiring.
   Emulyatorda kamera cheklangan — **galereya zaxira rejimi**ni ishlating.

## Oqim (3 ekran)

Bemor ID/ko'z → Kamera (rasm olish yoki galereyadan tanlash) → Natija (svetofor + % + heatmap).

## Qo'shimcha funksiyalar

- **Ko'z mashqlari** (`ui/eyecare/`) — 3 ta interaktiv mashq (Nuqtani kuzatish, Yaqin-uzoq
  fokus, Pilpirash + Palming), 20-20-20 fon eslatmasi va **Pomodoro** — ekran vaqtini
  kuzatib, fokus/tanaffus davrlari almashganda ogohlantiradigan taymer
  (`eyecare/PomodoroWorker.kt`). Ilova yopiq yoki ekran qulflangan bo'lsa ham WorkManager
  orqali fon rejimida ishlaydi va bildirishnoma chiqaradi.
- **Natijani ulashish** — Natija ekranida "🔗 Ulashish" tugmasi tizimning standart
  ulashish oynasini (`Intent.ACTION_SEND`) ochadi; foydalanuvchi natijani istalgan ilova
  (Telegram, SMS, email) orqali o'zi yuboradi — hech narsa avtomatik jo'natilmaydi.

## Bog'lamalar (asosiy)

Jetpack Compose (Material3), CameraX (1.3.4), Retrofit + OkHttp (multipart),
Coil (heatmap rasmini yuklash). To'liq ro'yxat — `app/build.gradle.kts`.

## Keyingi qadamlar (skeletdan tashqari)

Xato holatlarini kengaytirish, rasmni yuborishdan oldin ko'rsatish (preview/confirm),
real fundus linza/adapter bilan sifat, offline rejim (3-hujjat: Room + WorkManager).
