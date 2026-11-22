# EYE DETECT AI — Android integration guide

For the Kotlin team. Everything below matches the deployed backend.

| | |
|---|---|
| **Production URL** | `https://eye-detect-backend.vercel.app/` |
| **Swagger UI** | https://eye-detect-backend.vercel.app/docs (ReDoc: `/redoc`, schema: `/openapi.json`) |
| **Engine** | Claude vision (`claude-sonnet-5-5`, prompt `v1`), mode `shadow` |
| **Verified** | 2026-11-22: live smoke test passed (REFER / NO_REFER / not-a-fundus / blurred) |

> **This is a screening/triage tool, not a diagnosis.** Until the Android
> privacy items in §9 are done and the accuracy evaluation has passed, use
> **only synthetic, public or consented test images**, never real patients.

---

## 1. Quick start

Put these in `local.properties` at the repo root. The file is git-ignored and must stay that way:

```properties
RELEASE_API_URL=https://eye-detect-backend.vercel.app/
API_KEY=<the app key, shared with you privately by the backend owner>
```

- `RELEASE_API_URL` must be `https://` and end with `/` (a Retrofit/Ktor `baseUrl` requirement). The release build fails if it isn't HTTPS or if `API_KEY` is still the placeholder.
- For a local backend in debug builds, use `API_BASE_URL=http://<your-LAN-IP>:8000/` (see `backend/README.md` §3).

---

## 2. Authentication

- Send `X-API-Key: <app key>` on **every** `/api/v1/*` request.
- No key needed for: `HEAD /`, `GET /health`, `GET /health/live`, `GET /health/ready`, `/docs`, `/redoc`, `/openapi.json`.
- Missing or wrong key → **401** `{"error": "unauthorized", "detail": "Kirish rad etildi — API kalit noto'g'ri"}`.
- **Treat the app key as extractable:** it is compiled into the APK.
  - Keep it only in `local.properties`. Never commit it, log it or show it in the UI.
  - If an APK leaks, tell the backend owner: the key gets rotated and you ship a new build.
- There is a second, **admin** key that guards `GET /api/v1/exams` and `GET /api/v1/exams/{id}` (the admin panel's endpoints).
  - The app must **not** have it, and does not need those endpoints.
  - With the app key alone they return **403**. That is expected.

---

## 3. Endpoints the app uses

| Method | Path | Purpose | Status in production |
|---|---|---|---|
| `HEAD` | `/` | Online check, any response = online (no key needed) | ✅ 204 |
| `POST` | `/api/v1/predict/async` | DR screening, **recommended** (KMP app) | ✅ |
| `GET` | `/api/v1/predict/status/{task_id}` | Result of an async screening | ✅ |
| `POST` | `/api/v1/predict` | DR screening, synchronous (old `android` app) | ✅ |
| `GET` | `/api/v1/analysis/types` | Analysis types: `external_eye`, `skin`, `oral`, `nail` | ✅ |
| `POST` | `/api/v1/analyze` | Skin, nail, oral and external-eye analysis | ⚠️ **503**, see §7 |
| `GET` | `/api/v1/analyses` | Analysis history | ✅ (always send `patient_id`, see §7) |
| `GET` | `/api/v1/analyses/{analysis_id}` | One analysis | ✅ |

---

## 4. DR screening

### 4.1 Request: `multipart/form-data`

| Field | Required | Value |
|---|---|---|
| `file` | yes | JPEG or PNG, **at most 4 MB**. Compress on the phone to about 200–600 KB. Anything over 1568 px on the long side is downscaled on the server anyway, so there is no benefit in sending more. |
| `patient_id` | no | Your patient code. A blank value counts as absent. If absent, the server generates `P-XXXXXX` and returns it in the response. |
| `eye` | no | `right` or `left`. Anything else → **422**. |

Optional header:
- `Idempotency-Key: <unique per capture>`. A retry with the same key within 10 minutes replays the stored result.
- The same key with a different image → **409**.

Only the image goes to the AI model. `patient_id` and `eye` are stored by the backend but **never sent to Claude**, and the backend also removes the photo's EXIF and GPS metadata before sending it.

### 4.2 Async flow (recommended)

```
POST /api/v1/predict/async      (multipart, X-API-Key)
→ 200 {"task_id": "replay:3fa85f64-...", "status": "PROCESSING",
       "message": "Rasm tahlil qilindi, natija tayyorlanmoqda..."}

GET  /api/v1/predict/status/replay:3fa85f64-...   (X-API-Key)
→ 200 {"task_id": "replay:3fa85f64-...", "status": "SUCCESS",
       "result": { ...PredictResponse, see §5... }, "error": null}
```

- The screening runs **inside the POST** (there is no background worker on Vercel). The first status is always `PROCESSING`, and the first poll already returns `SUCCESS`.
- Errors (400, 413, 500, …) come back from the **POST itself** as normal HTTP errors (§6), not as a `FAILURE` status.
- `status: "FAILURE"` with `"error": "Natija topilmadi"` means an unknown task id, for example an old one from before the migration.

### 4.3 Sync flow

`POST /api/v1/predict` with the same fields → 200 with the `PredictResponse` directly.

### 4.4 Timing and retries

- **Timing:**
  - A screening normally takes **3–8 s**. The Claude call alone measured 2.5–6 s in production.
  - The first request after idle can add about **3 s** (cold start).
  - The server allows Claude 25 s, and Vercel caps a request at 60 s. **Use a client timeout of 30 s.**
- **Retrying is safe:** sending the **same image bytes + same `patient_id` + same `eye`** within **10 minutes** returns the stored result: same `exam_id`, no second AI call, no duplicate exam. So the "retry" button should resend exactly the retained bytes.

---

## 5. Response: `PredictResponse`

The wire contract is **frozen**: keys are never renamed or removed, but new keys may be added, so **ignore unknown fields** in your JSON parser.

| Key | Type | Notes |
|---|---|---|
| `exam_id` | string (UUID) | |
| `patient_id` | string | Your code, or the generated `P-XXXXXX` |
| `eye` | `"right"` \| `"left"` \| null | |
| `referable` | bool | |
| `probability` | float 0–1 | **Probability of referable DR, not "confidence"**, see §9 |
| `icdr_grade` | int 0–4 | |
| `grade_label` | string (Uzbek) | `DR yo'q`, `Yengil NPDR`, `O'rtacha NPDR`, `Og'ir NPDR`, `Proliferativ DR`, or `Baholab bo'lmadi` |
| `decision` | `"REFER"` \| `"NO_REFER"` \| `"UNGRADABLE"` | **Drive the UI from this** |
| `decision_text` | string (Uzbek) | Show it verbatim |
| `quality` | `"good"` \| `"poor"` | Raw value; map it to Uzbek (§9) |
| `heatmap_url` | null | **Always null now** (Grad-CAM was removed); hide the heatmap card |
| `image_url` | string (absolute `https://…` URL) \| null | Public URL of the uploaded photo; load it with Coil **without** a key |
| `model_version` | string | e.g. `claude-sonnet-5-5/prompt-v1` |
| `processed_at` | string | ISO-8601 UTC, e.g. `2026-11-22T03:17:14Z` |
| `disclaimer` | string (Uzbek) | `Bu skrining/triaj vositasi; yakuniy tashxis oftalmolog mas'uliyati.` Show it |
| `request_id` | string (UUID) | Put it in bug reports; it matches the server logs |
| `mode` | `"shadow"` \| `"demo"` | `shadow` in production; `demo` = mock engine on a local backend |

Example (REFER):

```json
{
  "exam_id": "268128be-4dd1-4dee-9abb-225f361cadd8",
  "patient_id": "P-1A2B3C",
  "eye": "left",
  "referable": true,
  "probability": 0.87,
  "icdr_grade": 2,
  "grade_label": "O'rtacha NPDR",
  "decision": "REFER",
  "decision_text": "Referable DR — oftalmologga yuboring",
  "quality": "good",
  "heatmap_url": null,
  "image_url": "https://<store>.public.blob.vercel-storage.com/images/268128be-...-Xk29aQ.jpg",
  "model_version": "claude-sonnet-5-5/prompt-v1",
  "processed_at": "2026-11-22T03:17:14Z",
  "disclaimer": "Bu skrining/triaj vositasi; yakuniy tashxis oftalmolog mas'uliyati.",
  "request_id": "452f7831-2397-410a-a385-af840794c621",
  "mode": "shadow"
}
```

### 5.1 Decision → UI

| `decision` | Colour | Typical `decision_text` |
|---|---|---|
| `REFER` | red | `Referable DR — oftalmologga yuboring` |
| `NO_REFER` | green | `Referable DR aniqlanmadi — 12 oydan keyin qayta tekshiruv` |
| `UNGRADABLE` | grey | One of the texts below; always ask for a retake or a referral |

`UNGRADABLE` texts:
- `Sifatsiz rasm — qayta suratga oling`: the photo failed the server's blur or brightness check. No AI call is made.
- `Bu ko'z tubi (fundus) rasmi emas — fundus kamera yoki adapter bilan oling`: not a fundus photo, e.g. a photo of the front of the eye.
- `Baholab bo'lmadi: <reasons> — qayta suratga oling`: the AI could not grade it. The reasons are any of `rasm xira`, `juda qorong'i`, `juda yorug'`, `ko'z tubi to'liq ko'rinmaydi`, `to'siq bor`.

For `UNGRADABLE`, `probability` is `0.0` and `icdr_grade` is `0`. These are **placeholders, because the old APK could not parse nulls**. Do not show them as a grade or a percentage.

**Never decide on the phone.** Do not compare `probability` with any threshold: the server's `decision` is the only verdict. The threshold lives on the server, so it can change without an app release.

---

## 6. Errors

Every error is `{"error": "<code>", "detail": "<short Uzbek text>"}`. **Show `detail` to the user.**

| HTTP | `error` | When | `detail` | What the app does |
|---|---|---|---|---|
| 400 | `invalid_image` | Not an image, or a corrupt one | `Rasm yaroqsiz yoki buzilgan — qayta suratga oling` | Ask for a retake |
| 401 | `unauthorized` | Missing or wrong `X-API-Key` | `Kirish rad etildi — API kalit noto'g'ri` | Configuration problem; contact the backend owner |
| 403 | `unauthorized` | Admin-only endpoint (`/api/v1/exams*`) | same as 401 | The app should not call these |
| 409 | `idempotency_conflict` | `Idempotency-Key` reused for a different image | `Bu kalit boshqa rasm uchun ishlatilgan` | Generate a new key per capture |
| 413 | `payload_too_large` | File over 4 MB | `Rasm hajmi juda katta — 4 MB dan oshmasin` | Compress more |
| 422 | `validation_error` | Bad form field, e.g. `eye` | e.g. `Ko'z noto'g'ri — 'right' yoki 'left' bo'lishi kerak` | Fix the request |
| 429 | `too_many_requests` | Over 30 requests/minute from one IP | `So'rovlar juda ko'p — biroz kuting` | Back off and retry later |
| 500 | `inference_error` | AI call failed or timed out | `Tahlil bajarilmadi — qayta urining` | Offer retry (safe, §4.4) |
| 500 | `persistence_error` | The result could not be saved | `Natija saqlanmadi — qayta urining` | Offer retry |
| 503 | `model_unavailable` | Engine (or analysis model) not available | `Model tayyor emas — administratorga murojaat qiling` | Show the message; don't retry in a loop |

**Rules:**
- **No error path ever returns `NO_REFER`.** On any error, show the error. Never show a green result.
- A result that wasn't saved never reaches the phone (a 500 is returned instead).
- Vercel itself can return a non-JSON error (e.g. 504 on a platform timeout). Handle a body that isn't the envelope above with a generic "retry" message.

---

## 7. Skin, nail, oral and external-eye analysis (`/analyze`)

- `POST /api/v1/analyze`, multipart:
  - `file` (required)
  - `analysis_type`, one of `external_eye`, `skin`, `oral`, `nail` (from `GET /api/v1/analysis/types`)
  - `patient_id` (optional)
  - `body_site` (optional, ≤ 64 characters)
- ⚠️ **In production it returns `503 model_unavailable` for every type.** These models aren't deployed. Production never falls back to a mock result, and moving them to Claude is planned (Phase 5). **Hide this feature or mark it "coming soon"** in release builds. A local backend in `demo` mode returns mock results marked `"is_demo": true`, for UI work.
- **History, `GET /api/v1/analyses?patient_id=…&analysis_type=…&limit=…`** (`limit` ≤ 500): **always send `patient_id`.** Without it, the server returns **every patient's** analyses, photo URLs included. This is the one remaining access gap the backend can't close without an app change.

---

## 8. Health and connectivity

- `HEAD /` → **204**, no key needed. Any HTTP response means "online".
- `GET /health` → 200 when the process is up.
- `GET /health/ready` → 200 `{"status": "ready", "checks": {"database": true, "storage": true, "model": true}}`, or **503** when something isn't ready.

---

## 9. Checklist for the app

Must-do before real patients:

1. **App key:** only in `local.properties`; never committed, logged or shown. Never ship the admin key.
2. **Release:** `RELEASE_API_URL` is HTTPS; cleartext HTTP is only allowed in debug builds.
3. **Verdict from the server:** render `decision` and `decision_text`, and never re-derive them from `probability`.
4. **The "ISHONCH %" label is misleading.** `probability` is the probability of *referable DR*. A healthy eye returns e.g. `0.06`, and "ISHONCH 6%" reads as "6% confident", the opposite of the meaning. Relabel it `Referable DR ehtimoli`, or show `1 − probability` under an explicitly named confidence label.
5. **`quality`:** map the raw `good` / `poor` to Uzbek text.
6. **Heatmap card:** hide it when `heatmap_url` is null, which is now always.
7. **Offline TFLite model:**
   - Its origin and accuracy are unknown, and it refers at grade > 0 while the server refers at grade ≥ 2.
   - Offline, show "queued for server check". **Never show a green `NO_REFER`** from it.
8. **`/analyses` history:** always send `patient_id` (§7). Hide `/analyze` in release until it's available.
9. **Privacy:** set `allowBackup="false"` (or `dataExtractionRules`), and **encrypt the Room database** (SQLCipher or a `MasterKey`-derived passphrase). Until this lands: synthetic or consented data only.
10. **Retry:** resend the same retained bytes with the same `patient_id` and `eye` (or the same `Idempotency-Key`). Client timeout 30 s.
11. **Bug reports:** include `request_id`, `exam_id` and the time.

---

## 10. Trying it out

- **Swagger:** https://eye-detect-backend.vercel.app/docs. There's no "Authorize" button; fill the `x-api-key` field on each endpoint.
- **Every screening call is real:** a successful `POST /predict` makes one billed AI call (about $0.015) and stores an exam in the **production** database. Use public or synthetic images only, e.g. fundus photos from Wikimedia Commons.
- **curl:**

```bash
curl -H "X-API-Key: $API_KEY" -F "file=@fundus.jpg" -F "eye=left" \
  https://eye-detect-backend.vercel.app/api/v1/predict
```

```bash
curl -I https://eye-detect-backend.vercel.app/
```

---

## 11. More

- **Backend overview and local setup:** `backend/README.md`.
- **Decisions, measurements and open questions:** `backend/docs/NOTES.md`.
- **Wire schema:** `backend/app/schemas.py` (frozen) and `/openapi.json`.
