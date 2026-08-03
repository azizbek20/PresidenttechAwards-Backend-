# EYE DETECT AI Android — Release API manzilini build-turlariga ajratish

**Sana:** 2026-08-03
**Holat:** Tasdiqlangan (foydalanuvchi tomonidan)

## Kontekst

`PLAN.md` bo'lim 8: "`API_BASE_URL`ni build-turlariga (debug/staging/release)
ajratish — hozir bitta qattiq kodlangan qiymat."

Bu masala yakuniy xavfsizlik review'ida (`2026-08-03-security-hardening`
branch, final whole-branch review) real muammo sifatida ham qayd etilgan:
xavfsizlik tuzatishlaridan keyin release build cleartext (HTTP) trafikni
butunlay bloklaydi (Network Security Config orqali), lekin `API_BASE_URL`
hamon `defaultConfig`da qattiq kodlangan `http://10.0.2.2:8000/` — demak,
hozirgi holatda release APK yig'ilsa, u umuman backend'ga ulana olmaydi,
va bu jim tarzda, hech qanday build xatosisiz sodir bo'ladi.

Shu bilan bog'liq, xuddi shu turkumdagi yana bir muammo: agar
`local.properties`da `API_KEY` bo'lmasa, release build
`"dev-key-CHANGE-ME"` placeholder bilan jim tarzda o'tib ketaveradi
(`2026-08-03-security-hardening-design.md`da bilib turib qabul qilingan
risk, keyingi CI-hardening ishiga qoldirilgan edi).

## Maqsad

1. Release build uchun `API_BASE_URL`ni `local.properties`dan (`API_KEY`
   bilan bir xil naqshda) o'qiladigan qilish — debug qiymati
   (`http://10.0.2.2:8000/`) o'zgarishsiz qoladi.
2. Release build vaqtida (faqat `assembleRelease`/`bundleRelease`
   bajarilganda, boshqa buyruqlarga ta'sir qilmasdan) ikkita shartni
   tekshiradigan guard qo'shish:
   - `RELEASE_API_URL` mavjud va `https://` bilan boshlanadi;
   - `API_KEY` hali ham `"dev-key-CHANGE-ME"` placeholder emas.
   Shart buzilsa, build **xato bilan to'xtaydi** — noto'g'ri sozlangan
   release APK jim tarzda chiqib ketishining oldi olinadi.

Hali real backend (HTTPS) mavjud emas — bu ham (`API_KEY` kabi)
kelajakka tayyorgarlik: infratuzilma hozir tayyorlanadi, real qiymat
backend tayyor bo'lganda `local.properties`ga qo'yiladi. Staging build-turi
qo'shilmaydi (hozircha ehtiyoj yo'q, YAGNI) — faqat debug/release.

## O'zgarishlar

### `app/build.gradle.kts`

Fayl darajasidagi mavjud blok (`localProperties`, `backendApiKey`) yoniga:

```kotlin
val releaseApiUrl: String = localProperties.getProperty("RELEASE_API_URL") ?: ""
```

`buildTypes { release { ... } }` ichiga (mavjud `isMinifyEnabled`/
`proguardFiles`dan keyin) qo'shiladi:

```kotlin
buildConfigField("String", "API_BASE_URL", "\"$releaseApiUrl\"")
```

Bu `defaultConfig`dagi debug qiymatini faqat `release` variant uchun
almashtiradi (AGP semantikasi: buildType darajasidagi `buildConfigField`
`defaultConfig`nikidan ustun turadi). `defaultConfig`dagi
`API_BASE_URL = "http://10.0.2.2:8000/"` qatori o'zgarishsiz qoladi —
debug build hamon shu qiymatni ishlatadi.

`android {}` blokidan tashqarida, fayl oxiriga yaqin (`dependencies {}`
blokidan oldin yoki keyin — joylashuv ahamiyatsiz, lekin o'qilishi uchun
`android {}`dan keyin tavsiya etiladi):

```kotlin
val checkReleaseSecrets = tasks.register("checkReleaseSecrets") {
    doLast {
        check(releaseApiUrl.startsWith("https://")) {
            "RELEASE_API_URL local.properties'da topilmadi yoki HTTPS emas. " +
            "Masalan: RELEASE_API_URL=https://api.eyedetect.example.com/"
        }
        check(backendApiKey != "dev-key-CHANGE-ME") {
            "API_KEY local.properties'da o'rnatilmagan (hali placeholder qiymatda)."
        }
    }
}

afterEvaluate {
    tasks.findByName("assembleRelease")?.dependsOn(checkReleaseSecrets)
    tasks.findByName("bundleRelease")?.dependsOn(checkReleaseSecrets)
}
```

`doLast` ichida bo'lgani uchun tekshiruv faqat task **bajarilganda**
ishlaydi (konfiguratsiya bosqichida emas) — shuning uchun
`assembleDebug`/`compileDebugKotlin` kabi buyruqlarga ta'sir qilmaydi,
garchi AGP barcha variantlarni konfiguratsiya bosqichida yaratsa ham.
`afterEvaluate` orqali bog'lanish, chunki `assembleRelease`/`bundleRelease`
tasklari AGP tomonidan `android {}` bloki qayta ishlangandan keyin
yaratiladi — `afterEvaluate`siz `tasks.findByName(...)` hali mavjud
bo'lmagan taskni topa olmasligi mumkin.

## Testlar

Loyihada avtomatlashtirilgan test infratuzilmasi yo'q (alohida PLAN.md
bandi). Tekshirish qo'lda, Gradle buyruqlari orqali:

- `RELEASE_API_URL`/`API_KEY` `local.properties`da yo'q holatda
  `./gradlew :app:assembleRelease` ishga tushirilsa, build
  `checkReleaseSecrets` xatosi bilan to'xtashi kerak.
- `local.properties`ga to'g'ri `RELEASE_API_URL=https://...` va haqiqiy
  `API_KEY` qo'shilgach, `./gradlew :app:assembleRelease` muvaffaqiyatli
  o'tishi va generatsiya qilingan release `BuildConfig.java`da to'g'ri
  `API_BASE_URL` qiymati bo'lishi kerak.
- `./gradlew :app:assembleDebug` — bu ikkala holatda ham (guard
  shartlari bajarilgan yoki bajarilmagan bo'lishidan qat'i nazar)
  muvaffaqiyatli o'tishi kerak (guard faqat release tasklariga bog'langan).

## Qamrovdan tashqari

- Staging build-turi (hozircha ehtiyoj yo'q).
- `API_KEY`/`RELEASE_API_URL` qiymatlarini Gradle string interpolatsiyasida
  escaping qilish (`"` yoki `\` belgilar bo'lsa buziladi) — avvalgi
  xavfsizlik review'ida Minor sifatida qayd etilgan, bu ishning doirasida
  emas.
- CI/CD integratsiyasi (masalan, `RELEASE_API_URL`ni secret sifatida CI
  muhitida saqlash) — hozircha loyihada CI yo'q.

## Riskler / diqqat talab qiladigan joylar

- `afterEvaluate` ichida `tasks.findByName` ishlatilgani — agar kelajakda
  build variant nomlari o'zgarsa (masalan, flavor qo'shilsa,
  `assembleRelease` o'rniga `assembleProdRelease` kabi nom paydo bo'ladi),
  guard ulanmay qoladi va sezilmasdan o'chib qolishi mumkin. Hozircha
  flavor yo'q, shuning uchun bu amaliy xavf emas — lekin flavor
  qo'shilganda shu joy qayta ko'rib chiqilishi kerak.
- Guard faqat `assembleRelease`/`bundleRelease`ga bog'langan;
  `installRelease` yoki boshqa release-bog'liq tasklar to'g'ridan-to'g'ri
  ishga tushirilsa (masalan Android Studio "Run" tugmasi orqali release
  variantni qurilmaga o'rnatish), ular odatda ichki ravishda
  `assembleRelease`ga bog'liq bo'lgani uchun guard baribir ishlaydi —
  lekin bu AGP versiyasiga qarab farq qilishi mumkin, 100% kafolat emas.
