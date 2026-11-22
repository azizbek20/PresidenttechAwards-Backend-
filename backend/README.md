# EYE DETECT AI — backend

Diabetik retinopatiya (DR) uchun **skrining/triaj** backend'i: telefon fundus
rasm yuboradi, server sifatni tekshiradi, baho beradi va `REFER` / `NO_REFER` /
`UNGRADABLE` qarorini qaytaradi.

> **Bu diagnoz emas.** Yakuniy tashxis oftalmolog mas'uliyatida.
> **Demo rejimi faqat sintetik yoki rozilik berilgan test ma'lumotlari bilan
> ishlaydi** (C13) — Android tarafdagi PHI ishlari (C8, quyida) bajarilgunicha.

`SPEC.md` — yagona haqiqat manbai. Bu fayl bilan ziddiyat bo'lsa, `SPEC.md`
ustun turadi.

The DR assessment is made by **Claude vision** (Anthropic API) since the
migration in `docs/MIGRATION_PLAN.md`; the PyTorch / ONNX / Grad-CAM engine is
gone. For the inference engine, decision rules, storage and deployment, the
plan takes precedence over `SPEC.md` (see `CLAUDE.md`). What was done,
measured and is still open is logged in `docs/NOTES.md`.

---

## 1. Run it locally

Python 3.11 locally and in CI; Vercel runs 3.12 (`.python-version`). One
install, everything from PyPI:

```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pip install -r requirements-admin.txt    # only for the admin panel
```

Run with the **mock engine** (no key, no cost):

```bash
cp .env.example .env          # then edit: at minimum set EYE_API_KEY
EYE_MODE=demo EYE_MODEL_SOURCE=mock EYE_API_KEY=demo123 uvicorn app.main:app --port 8000

# admin panel — step 5 of the demo script
API_URL=http://localhost:8000 EYE_API_KEY=demo123 streamlit run admin/dashboard.py
```

Run with **Claude** (each screening that passes the quality gate is one
billed API call). Put `ANTHROPIC_API_KEY` in `backend/.env` (git-ignored) or
your shell, never in a tracked file:

```bash
EYE_MODE=shadow EYE_MODEL_SOURCE=claude EYE_API_KEY=demo123 \
  QUALITY_BLUR_MIN_VAR=8 uvicorn app.main:app --port 8000
```

* Without `ANTHROPIC_API_KEY` the app still starts, but `/health/ready` is 503
  and `/api/v1/predict` returns `503 model_unavailable`.
* Shadow mode with `claude` refuses to boot without a non-empty `EYE_API_KEY`.
* **Two keys.** `EYE_API_KEY` (header `X-API-Key`) is the app key; it is built
  into the APK, so treat it as extractable. `EYE_ADMIN_API_KEY` (header
  `X-Admin-Key`, must differ) additionally guards `/api/v1/exams` and
  `/api/v1/exams/{id}`, which list every exam and its photo URL; only the admin
  panel calls them, and it sends the admin key from its own
  `EYE_ADMIN_API_KEY`. Without an admin key those two endpoints accept the app
  key alone, and a shadow deployment logs a startup warning.
* `QUALITY_BLUR_MIN_VAR=8`: the config default of 50 rejects most sharp real
  fundus photos (the IDRiD calibration is in `.env.example`).
* An `eye.db` created before the migration lacks the new `assessment_json`
  column (`create_all` never alters an existing table). Delete it and let the
  app recreate it.

On Windows, `start_24_7.vbs` runs `run_backend_hidden.bat` (uvicorn in the
background, settings from `.env`), and `stop_backend.bat` stops it.

Checks:

```bash
EYE_MODE=demo pytest -q -m "not model and not perf"    # the default suite
ruff check app tests && mypy app    # rule set pinned by ruff.toml / mypy.ini

python scripts/make_test_images.py                    # -> scripts/out/, 5 files
bash scripts/smoke_test.sh http://localhost:8000 demo123
```

The test suite never calls the real Claude API; it uses a fake client.

`scripts/make_test_images.py` imports the generators from the **frozen**
`tests/synthetic.py` rather than re-implementing them, so the smoke test and
the test suite can never disagree about which image is REFER. Measured values
(the expected verdicts are the mock engine's):

| file | mean gray | blur var | expected |
|---|---|---|---|
| `refer.jpg` | 160.02 | 1554 | `REFER` (mock grade 4) |
| `no_dr.jpg` | 100.19 | 1246 | `NO_REFER` (mock grade 0) |
| `blurry.jpg` | 100.15 | **2.25** | `UNGRADABLE` (blur gate) |
| `dark.jpg` | **8.06** | 411 | `UNGRADABLE` (brightness gate) |
| `not_an_image.txt` | — | — | `400 invalid_image` |

For the Claude engine, `scripts/smoke_claude.sh` checks real images instead.
Put `referable.jpg`, `normal.jpg`, `external_eye.jpg` and `blurred.jpg` in
`eval/manual/` (git-ignored; never patient images), then run it against a
server started with `EYE_MODEL_SOURCE=claude`. It makes up to four billed
calls:

```bash
bash scripts/smoke_claude.sh http://localhost:8000 demo123 eval/manual
```

---

## 2. Run it in Docker

The image runs the **mock demo stack** (`EYE_MODE=demo`,
`EYE_MODEL_SOURCE=mock`). The Claude engine runs locally (§1) or on Vercel
(§6), not here: compose passes no `ANTHROPIC_API_KEY`, and `.dockerignore`
drops every `.md` file, including the prompt in `app/inference/prompts/`.

Built **natively for the host architecture**. On Apple silicon that is
`linux/arm64` — never pass `--platform amd64`; an emulated build is slow and
proves nothing the native one does not.

```bash
cd backend
cp .env.example .env      # set EYE_API_KEY; keep the placeholders elsewhere
mkdir -p models           # bind-mount source for the read-only models volume

docker build -t eye-backend:dev .
docker compose up -d api admin        # api :8000, admin :8501
docker compose logs -f api
docker compose down
```

* `api` and `admin` share **one image** — `admin/dashboard.py` is inside it on
  purpose (the v1 Dockerfile copied only `app/` and the admin container
  crashed on startup).
* `models/` is mounted `:ro`. The DR engine needs no weights; the folder only
  holds the optional `/analyze` skin model (`models/analysis/skin.onnx`).
  Nothing is downloaded at import or request time.
* Storage is a named volume, and the sqlite file has its own volume, so
  `down && up` does not silently empty the admin panel.
* Postgres is behind a profile: `docker compose --profile prod up -d`. Set a
  real `POSTGRES_PASSWORD` in `.env` first — the compose default is a
  placeholder, not a password.
* **MinIO is deliberately absent.** An S3 service with no S3 adapter in the
  code is decoration.
* The build fails if a GUI `opencv-python` ever comes back (slim images have
  no libGL), so that regression cannot reach production. `libgl1` is
  deliberately **not** installed: the bug must fail loudly, not hide.

The image runs as **uid 10001**, single worker (`--workers 1` — the inference
semaphore, the dedup window and the rate limiter are per-process state), and
its `HEALTHCHECK` polls `/health/ready`, not `/health/live`, because a
container that is alive but cannot reach its database should not be
considered up.

---

## 3. Point a real phone at it

This is the part that most often fails, and there is exactly one likely reason.

**Step 1 — find this Mac's LAN IP** (phone and laptop on the same Wi-Fi):

```bash
ipconfig getifaddr en0     # e.g. 192.168.1.108
```

**Step 2 — bind the server to all interfaces**, not just loopback:

```bash
EYE_API_KEY=demo123 uvicorn app.main:app --host 0.0.0.0 --port 8000
```

(`docker compose up api` already publishes on all interfaces.)

**Step 3 — point the app at this machine** in `local.properties` at the repo
root (git-ignored, and it must stay that way). Both values live here; no
tracked source needs editing:

```properties
API_KEY=demo123
API_BASE_URL=http://192.168.1.108:8000/
```

Find this machine's address with `ipconfig getifaddr en0`.

| target | `API_BASE_URL` |
|---|---|
| Emulator on this host | omit the key — the default is `http://10.0.2.2:8000/` |
| Real phone, same Wi-Fi | `http://<THIS-MACHINE-LAN-IP>:8000/` |
| ngrok fallback (different networks / captive Wi-Fi) | `https://xxxx.ngrok-free.app/` |
| Deployed on Vercel (§6) | `https://<project>.vercel.app/` (release builds: `RELEASE_API_URL`) |

`10.0.2.2` is the **Android emulator's** alias for the host loopback. On a real
phone it resolves to nothing and every request fails, which is why it is only
the fallback default.

⚠️ **If you tether from the phone, the laptop's address changes.** Sharing the
phone's hotspot moves the laptop onto the hotspot's subnet and it gets a new IP
(e.g. `192.168.1.108` → `10.104.167.232`). A stale `API_BASE_URL` is
indistinguishable from a server outage on the phone — the badge just reads
offline. Re-check with `ipconfig getifaddr en0` after any network change.

The value is validated at build time: it must start with `http://` or
`https://` and end with `/` (a Retrofit `baseUrl` requirement), must not be
quoted, and is trimmed. A bad value fails the build with a message naming
`local.properties` rather than crashing the app at launch.

**Cleartext HTTP is already allowed in the debug build** —
`app/src/debug/res/xml/network_security_config.xml` sets
`cleartextTrafficPermitted="true"`, so plain `http://` on the LAN needs no
further change. Release builds take `RELEASE_API_URL` from `local.properties`
instead.

ngrok fallback, when the phone and laptop cannot share a network:

```bash
ngrok http 8000     # then paste the https URL into line 38
```

**Step 5 — verify.** `ApiClient.ping()` sends `HEAD` to the base URL and counts
*any* HTTP response as online, so `HEAD /` must answer 204 without a key. If
the app shows "offline" while `curl` works from the laptop, the phone is on a
different network (or the Mac's firewall is blocking inbound 8000), not
mis-keyed.

---

## 4. Where the threshold lives, and why the client never re-derives it

`EYE_REFERABLE_THRESHOLD` (default `0.5`) lives **only** in `app/config.py`,
read from the environment. `app/inference/decision.py` is the only place a
verdict is computed. It has two functions, and both return the same
`DecisionResult`:

* `decide()` (frozen) for the mock engine's five class probabilities:

  ```python
  p_ref = round(sum(pred["probs"][2:]), 4)     # P(ICDR >= 2) = referable DR
  referable = p_ref >= threshold
  ```

* `decide_from_assessment()` for Claude's structured `FundusAssessment`. Not a
  fundus photo, or not gradable, is `UNGRADABLE`. The lesion checklist can
  only raise Claude's grade, never lower it. `REFER` when the final grade is
  2 or more, when macular edema signs are present or uncertain, or (with
  `UNCERTAIN_REFERS=true`, the default) when any grade-2 lesion is uncertain.
  The probability is then clamped so it agrees with the verdict.

The response carries the **already-made decision** (`decision`, `referable`,
`decision_text`) and the phone renders it. The client never compares
`probability` to a number of its own.

That is a safety property, not a style preference:

* **One place to change it.** Screening is sensitivity-first; lowering the
  threshold to refer more borderline patients is a config edit that takes
  effect on every device at once — no app release, no app-store review, no
  fleet of phones running last quarter's cutoff.
* **No split-brain.** A client-side comparison would silently disagree with the
  server the moment either side changed, and the disagreement would be
  invisible: both would show a confident verdict.
* **The stored record matches what the clinician saw.** The admin panel and the
  DB row come from the same computed `DecisionResult` as the phone screen.

Related invariants worth knowing before changing anything:

* **The quality gate runs before the DR engine, always.** A blurry or dark
  image is `UNGRADABLE` and the engine is never called, so it costs zero
  Claude calls — pinned by `tests/contract/test_engine_spy.py` and
  `tests/contract/test_claude_wiring.py`.
* **No fallback verdict.** A Claude API error, a timeout, a refusal or output
  that fails local validation is `500 inference_error`. No error path returns
  `NO_REFER`.
* **Only the image goes to Claude.** The request holds the image and a fixed
  instruction — never `patient_id` or any other patient data. The image's own
  metadata (EXIF GPS and camera data, XMP, comments, data appended after the
  image) is removed first; the pixels are unchanged.
* **C3 split truth.** `UNGRADABLE` goes over the wire with non-null
  placeholders (`probability=0.0`, `icdr_grade=0`, `grade_label="Baholab
  bo'lmadi"`) because the deployed APK crashes on nulls, while the DB stores
  `NULL` so training exports stay clean.
* **C10 persistence is unconditional.** Any DB write failure is
  `500 persistence_error` in every mode. A result the admin panel cannot
  corroborate must never reach the phone.
* **C14 dedup.** The client's `retry()` resends the same retained bytes, so a
  server-success + client-timeout + retry would otherwise create a duplicate
  exam. The server dedups on `sha256(bytes) + patient_code + eye` inside
  `DEDUP_WINDOW_MIN` (default 10) and replays the stored response, without a
  second Claude call. Known demo limitation: check-then-insert has a small
  race window for two genuinely concurrent identical uploads; a locking
  upgrade is pilot work.
* **`/predict/async` runs inline.** There is no background worker (Vercel runs
  none). The screening runs in the request, and the returned task id is
  `replay:<exam_id>`, which the status endpoint answers from the stored exam.

### Mode enforcement (C9)

* `EYE_MODE=demo` may use the mock engine, whose responses carry
  `mode="demo"` + `model_version="mock-v0"` so they cannot be mistaken for a
  live model. `demo` + `claude` is allowed for local trials.
* `EYE_MODE=shadow` never serves mock output: it refuses to boot with
  `EYE_MODEL_SOURCE=mock`, and with `claude` it also refuses to boot without a
  non-empty `EYE_API_KEY`. Without `ANTHROPIC_API_KEY`, `/health/ready` stays
  503 and `/api/v1/predict` returns `503 model_unavailable`.
* Claude responses carry `model_version="<CLAUDE_MODEL>/prompt-<PROMPT_VERSION>"`,
  e.g. `claude-sonnet-5-5/prompt-v1`. Bump `PROMPT_VERSION` whenever the prompt
  file in `app/inference/prompts/` changes.
* `EYE_MODEL_SOURCE=torch` and `EYE_DEVICE` are legacy settings kept only
  because the frozen tests pin them: `torch` always answers 503, and no engine
  reads `EYE_DEVICE`.
* The v1 `auto` model source was deleted: silently degrading to mock
  predictions in a live deployment is a safety failure, not a convenience.

**The Claude engine is not clinically validated.** The accuracy eval (plan
§8, Phase 4) has not been run, and the manual real-key check is still pending
(`docs/NOTES.md`). Nothing here is a production screening model until it
clears that gate.

---

## 5. CI

`.github/workflows/backend-ci.yml` (repo root), triggered on `backend/**`
changes:

```
lint (ruff + mypy) -> pytest -m "not model and not perf" -> docker build
  -> compose up api (mock, sqlite) -> scripts/smoke_test.sh -> compose down
```

No secrets, no push, no deploy, and no Claude calls. The API key in the
workflow is a literal CI-only string so the smoke test's "wrong key → 401"
step is meaningful; it protects nothing.

`perf` tests are a timing guard a shared runner cannot measure honestly, so
they are excluded by marker, not skipped silently. The `model` marker has had
no tests since the torch engine was removed. The one `postgres` test is
skipped unless `TEST_POSTGRES_URL` points at a real Postgres.

---

## 6. Deploy on Vercel

Prepared, not yet deployed. Step-by-step instructions are in `docs/NOTES.md`
under "Vercel deploy steps". In short:

* Vercel project **Root Directory = `backend`**. It runs `app/main.py` as one
  Python 3.12 function (`vercel.json`: `maxDuration` 60 s).
* Media go to **Vercel Blob** (`EYE_STORAGE=blob`, `BLOB_READ_WRITE_TOKEN`).
  Nothing is written to the read-only filesystem, `/static` is not mounted,
  and image URLs are absolute Blob URLs.
* The database is **Postgres**, shared by all instances, so a status poll that
  lands on another instance still finds the exam. `postgres://` URLs are
  rewritten to `postgresql+psycopg://`.
* The variable names are in `.env.vercel.example`. `MAX_UPLOAD_MB=4`, because
  Vercel rejects request bodies over 4.5 MB.

After deploying, run the live check:

```bash
bash scripts/smoke_claude.sh https://<project>.vercel.app "$EYE_API_KEY" eval/manual
```

---

## 7. Next phase — deliberately NOT built now (C7)

These are deferred to the pilot phase. They are absent by decision, not by
oversight; each serves an actor or a data volume that does not exist yet.

* **Per-device hashed credentials** — today a single shared `EYE_API_KEY`.
* **Multi-tenant RLS** — no second tenant exists.
* **Consent tables** — demo runs on synthetic/non-PHI data (C13).
* **Outbox / durable job queue** — `/predict/async` runs inline; no async
  fan-out yet.
* **MinIO / S3 storage adapter** — still absent. The cloud adapter that exists
  is Vercel Blob (`app/storage/blob.py`).
* **Encounters + DME model** — `patient_id`+`eye` is a *linkage*, not an
  encounter identifier: it can pair images from different visits (the app's own
  symmetry feature shares this caveat).
* **Authenticated media / refresh URLs (C6)** — `/static/...` and Blob URLs
  are unauthenticated because Coil sends no API key and the app persists URLs
  in Room, so short-lived tokens would break history thumbnails. Requires a
  coordinated Android change.
* **Nullable wire fields (`PredictResponseV2`)** — **not implemented; planned.**
  SPEC.md §9 describes it as an unrouted stub, but no such model exists in
  `app/schemas.py` today. The intended shape is the canonical schema with null
  UNGRADABLE fields, activated only together with the Android nullability
  patch. The current non-null placeholders are a versioned compatibility
  surface, not the permanent contract.
* **Schema migrations** — the app creates tables with `create_all`, and a
  fresh Postgres starts empty. Moving existing SQLite data, or changing the
  schema of a live database, needs an Alembic baseline first.
* **A shared rate limiter** — today it is in memory, per process: 30 requests
  per minute per client IP on `/api/v1`. On Vercel each instance keeps its own
  window, and whether the key is the phone's IP or a proxy IP is checked after
  the first deploy (plan issue 9).

---

## 8. Android backlog — out of backend scope, tracked here (C8)

Items the backend cannot fix and must not paper over:

**8.1 `allowBackup="true"` + unencrypted Room = PHI exposure.**
The manifest allows Android's cloud/adb backup of the app's data directory, and
the Room database storing exam history is not encrypted. On a real deployment
that copies patient data off the device to a channel nobody audited. Fix on the
Android side: set `allowBackup="false"` (and/or a `dataExtractionRules`
allow-list), and encrypt Room with SQLCipher or a `MasterKey`-derived
passphrase. **Until this lands, this stack is synthetic/non-PHI only (C13)** —
that is the constraint that makes the current demo posture defensible.

**8.2 "ISHONCH %" label semantics are misleading.**
The result screen shows the *referable probability* under a label that reads as
"confidence", for every verdict. On a healthy patient the server returns
`probability = 0.06` and the screen says **"ISHONCH 6%"** — which a clinician
reads as "the system is 6% confident", i.e. the opposite of what it means. It
is 6% probability of *referable DR*: a strong NO_REFER.

The backend deliberately does **not** work around this by inverting the number
for NO_REFER — that would make the wire field mean different things depending
on the verdict, and would break the admin panel and any export. The fix belongs
in the Android label: either relabel it "Referable DR ehtimoli" or show
`1 - probability` under an explicitly named "confidence" field.

**8.3 The heatmap card is always empty now.**
Grad-CAM was removed with the torch engine, so `heatmap_url` is always `null`.
The key stays on the wire (the app expects it); the card simply shows nothing.

---

## 9. Layout

```
backend/
├── SPEC.md                     the original contract
├── CLAUDE.md                   rules for Claude Code during the migration
├── docs/
│   ├── MIGRATION_PLAN.md       Claude engine + Vercel migration plan
│   └── NOTES.md                what was done and measured; open decisions
├── app/
│   ├── config.py               settings + mode enforcement (C9)
│   ├── schemas.py              frozen — wire contract
│   ├── core/                   errors.py (frozen envelope), limits, rate limit, security
│   ├── inference/              engine protocol, mock (frozen), decision,
│   │                           claude_engine + assessment, prompts/,
│   │                           preprocess, quality
│   ├── analysis/               /analyze catalogue and skin analyzer
│   ├── db/                     base, models, crud
│   ├── api/                    predict, analyze, exams, deps
│   └── storage/                local.py (magic-byte sniff, C11), blob.py (Vercel Blob)
├── admin/dashboard.py          Streamlit demo panel (read-only, no login)
├── scripts/
│   ├── make_test_images.py     -> scripts/out/ (5 deterministic fixtures)
│   ├── smoke_test.sh           8 named steps against a running API
│   └── smoke_claude.sh         live check with real images (billed calls)
├── tests/                      conftest + synthetic frozen; unit/contract/integration/perf
├── vercel.json, .python-version, .env.vercel.example
├── Dockerfile, docker-compose.yml, .dockerignore, .env.example
├── start_24_7.vbs, run_backend_hidden.bat, stop_backend.bat   Windows launchers
└── .github/workflows/backend-ci.yml   (at the REPO root)
```

**Never commit** a populated `.env`, the Anthropic key, model weights,
`local.properties` or the images in `eval/manual/`. All are git-ignored, and
the first three are excluded from the Docker build context.
