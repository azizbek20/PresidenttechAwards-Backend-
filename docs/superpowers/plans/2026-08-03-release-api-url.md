# Release API manzilini build-turlariga ajratish — Implementatsiya rejasi

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `PLAN.md` bo'lim 8'ni yopish: release build `API_BASE_URL`ni
`local.properties`dan (`RELEASE_API_URL`) o'qiydigan qilish, debug qiymatini
o'zgartirmasdan, va release build vaqtida (faqat `assembleRelease`/
`bundleRelease`da) HTTPS URL va haqiqiy API key mavjudligini tekshiradigan
guard qo'shish.

**Architecture:** Yagona faylga (`app/build.gradle.kts`) nuqtali
o'zgartirish — mavjud `API_KEY` o'qish naqshiga mos ravishda yangi
`releaseApiUrl` fayl darajasidagi `val`, `buildTypes.release` blokida
`buildConfigField` override, va `afterEvaluate` orqali release tasklariga
bog'langan alohida guard task.

**Tech Stack:** Kotlin DSL (Gradle), Android Gradle Plugin `BuildConfig`
mexanizmi.

## Global Constraints

- Loyihada avtomatlashtirilgan test infratuzilmasi yo'q — tekshirish
  qo'lda, Gradle buyruqlari orqali (`docs/superpowers/specs/2026-08-03-release-api-url-design.md`,
  "Testlar" bo'limi).
- `local.properties` git'ga tushmaydi — real qiymatlar (RELEASE_API_URL,
  API_KEY) hech qachon commit qilinmaydi.
- Staging build-turi qo'shilmaydi — faqat debug/release (YAGNI, spec
  bilan tasdiqlangan).
- Guard faqat `assembleRelease`/`bundleRelease` bajarilganda ishlashi
  shart, boshqa buyruqlarga (jumladan `assembleDebug`) ta'sir qilmasligi
  kerak.
- **Diqqat:** hozirgi `local.properties` faylida `API_KEY` qatori yo'q
  (avvalgi xavfsizlik ishi paytida faqat vaqtinchalik worktree'ga
  qo'shilgan edi, gitignored fayl bo'lgani uchun `main`ga o'tmagan).
  Demak hozircha `BuildConfig.API_KEY` "dev-key-CHANGE-ME" placeholder
  qiymatida — bu ishning tekshiruv qadamlarida hisobga olinadi.

---

### Task 1: `RELEASE_API_URL` o'qish, release override va guard

**Files:**
- Modify: `app/build.gradle.kts`
- Modify: `local.properties` (qo'lda, faqat tekshiruv uchun — commit
  qilinmaydi, gitignored)

**Interfaces:**
- Produces: `BuildConfig.API_BASE_URL` release variantda
  `local.properties`dagi `RELEASE_API_URL` qiymatiga teng bo'ladi (debug
  variantda o'zgarishsiz `http://10.0.2.2:8000/` qoladi).
- Boshqa taskka bog'liqlik yo'q — bu reja bitta task.

- [ ] **Step 1: `releaseApiUrl` o'qish qatorini qo'shish**

`app/build.gradle.kts`da mavjud qator:

```kotlin
val backendApiKey: String = localProperties.getProperty("API_KEY") ?: "dev-key-CHANGE-ME"
```

qatoridan keyin qo'shing:

```kotlin
val releaseApiUrl: String = localProperties.getProperty("RELEASE_API_URL") ?: ""
```

- [ ] **Step 2: `release` buildType'ga `API_BASE_URL` override qo'shish**

Hozirgi:

```kotlin
    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
```

Buni shu bilan almashtiring:

```kotlin
    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            buildConfigField("String", "API_BASE_URL", "\"$releaseApiUrl\"")
        }
    }
```

- [ ] **Step 3: Build qilib, `defaultConfig`dagi qiymat hali debugga tegishli ekanini tekshirish**

Run:
```
./gradlew :app:assembleDebug
```

Expected: `BUILD SUCCESSFUL`. Keyin:

```
Get-Content app/build/generated/source/buildConfig/debug/com/eyedetect/ai/BuildConfig.java | Select-String "API_BASE_URL"
```

Expected: `public static final String API_BASE_URL = "http://10.0.2.2:8000/";`
(debug o'zgarmagan).

- [ ] **Step 4: Guard task va uni release tasklariga bog'lashni qo'shish**

`app/build.gradle.kts`da `android { ... }` blokidan keyin (va
`dependencies { ... }` blokidan oldin) qo'shing:

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

- [ ] **Step 5: Guard ishlashini tekshirish — `local.properties`da hech narsa yo'q holatda `assembleRelease` muvaffaqiyatsiz bo'lishi kerak**

`local.properties`da hozircha `RELEASE_API_URL` ham, `API_KEY` ham yo'q
(Global Constraints'da qayd etilgan holat). Run:

```
./gradlew :app:assembleRelease
```

Expected: build **BUILD FAILED** bilan to'xtaydi, xato xabarida
`checkReleaseSecrets` task nomi va `"RELEASE_API_URL local.properties'da
topilmadi yoki HTTPS emas."` matni ko'rinadi (birinchi `check()` avval
ishga tushgani uchun shu xabar chiqadi).

- [ ] **Step 6: `local.properties`ga test qiymatlarini qo'shib, guard o'tishini tekshirish**

`local.properties` faylining oxiriga qo'shing (agar `API_KEY` qatori hali
yo'q bo'lsa, uni ham qo'shing — `openssl rand -hex 32` bilan yangi qiymat
generatsiya qiling, oldingi xavfsizlik ishidagi kabi):

```properties
API_KEY=<openssl rand -hex 32 natijasi, agar hali yo'q bo'lsa>
RELEASE_API_URL=https://api.example.com/
```

Run:
```
./gradlew :app:assembleRelease
```

Expected: `BUILD SUCCESSFUL`.

- [ ] **Step 7: Release `BuildConfig`da to'g'ri URL borligini tekshirish**

Run:
```
Get-Content app/build/generated/source/buildConfig/release/com/eyedetect/ai/BuildConfig.java | Select-String "API_BASE_URL"
```

Expected: `public static final String API_BASE_URL = "https://api.example.com/";`

- [ ] **Step 8: `assembleDebug` guard'dan ta'sirlanmasligini tasdiqlash**

`local.properties`dan `RELEASE_API_URL` qatorini vaqtincha o'chirib
qo'ying (yoki shunchaki keyingi buyruqni joriy holatda ishga tushiring —
`assembleDebug` `RELEASE_API_URL` mavjud yoki yo'qligidan qat'i nazar
ishlashi kerak). Run:

```
./gradlew :app:assembleDebug
```

Expected: `BUILD SUCCESSFUL` (guard faqat `assembleRelease`/
`bundleRelease`ga bog'langan, `assembleDebug`ga bog'lanmagan — shuning
uchun bu buyruq `RELEASE_API_URL` holatidan qat'i nazar har doim
o'tishi kerak).

- [ ] **Step 9: Commit**

Faqat `app/build.gradle.kts` commit qilinadi — `local.properties`
gitignored, `git add` uni e'tiborsiz qoldiradi:

```bash
git add app/build.gradle.kts
git commit -m "build: split API_BASE_URL per build type with a release guard

- release build reads RELEASE_API_URL from local.properties (debug
  keeps the hardcoded LAN/emulator URL)
- assembleRelease/bundleRelease now fail loudly if RELEASE_API_URL
  isn't HTTPS or API_KEY is still the placeholder, instead of silently
  shipping an unreachable or unauthenticated release build"
```

## Self-Review Notes

- Spec coverage: spec's 3 items (RELEASE_API_URL read, release
  buildConfigField override, combined guard) are all covered by Steps
  1-2 (read+override) and Step 4 (guard). ✅
- The spec's "Testlar" section's three manual scenarios map directly to
  Steps 5 (guard fails), 6-7 (guard passes + correct value), and 8
  (debug unaffected). ✅
- No placeholders — every step has literal code/commands and expected
  output.
