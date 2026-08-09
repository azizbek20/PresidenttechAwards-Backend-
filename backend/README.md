# EYE DETECT AI — backend

Diabetik retinopatiya (DR) uchun **skrining/triaj** backend'i: telefon fundus
rasm yuboradi, server sifatni tekshiradi, baho beradi va `REFER` / `NO_REFER` /
`UNGRADABLE` qarorini qaytaradi.

> **Bu diagnoz emas.** Yakuniy tashxis oftalmolog mas'uliyatida.
> **Demo rejimi faqat sintetik yoki rozilik berilgan test ma'lumotlari bilan
> ishlaydi** (C13) — Android tarafdagi PHI ishlari (C8, quyida) bajarilgunicha.

`SPEC.md` — yagona haqiqat manbai. Bu fayl bilan ziddiyat bo'lsa, `SPEC.md`
ustun turadi.

---

## 1. Run it locally

Python 3.11. The install order matters and is identical in the venv, the
Dockerfile and CI — torch resolves only from its own pinned index, and PyPI
packages only from PyPI (dependency-confusion guard):

```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements-torch.txt
pip install -r requirements-dev.txt
```

Then the **one extra step nobody guesses**, described in §6 below:

```bash
pip uninstall -y opencv-python
pip install --force-reinstall --no-deps opencv-python-headless==4.10.0.84
python -c "import cv2; print(cv2.__version__)"   # -> 4.10.0
```

Run:

```bash
cp .env.example .env          # then edit: at minimum set EYE_API_KEY
EYE_API_KEY=demo123 uvicorn app.main:app --port 8000

# admin panel — step 5 of the demo script
API_URL=http://localhost:8000 EYE_API_KEY=demo123 streamlit run admin/dashboard.py
```

Checks:

```bash
pytest -q -m "not model and not perf"    # the default suite, mock engine
ruff check && mypy app       # rule set pinned by ruff.toml / mypy.ini

python scripts/make_test_images.py                    # -> scripts/out/, 5 files
bash scripts/smoke_test.sh http://localhost:8000 demo123
```

`scripts/make_test_images.py` imports the generators from the **frozen**
`tests/synthetic.py` rather than re-implementing them, so the smoke test and
the test suite can never disagree about which image is REFER. Measured values:

| file | mean gray | blur var | expected |
|---|---|---|---|
| `refer.jpg` | 160.02 | 1554 | `REFER` (mock grade 4) |
| `no_dr.jpg` | 100.19 | 1246 | `NO_REFER` (mock grade 0) |
| `blurry.jpg` | 100.15 | **2.25** | `UNGRADABLE` (blur gate) |
| `dark.jpg` | **8.06** | 411 | `UNGRADABLE` (brightness gate) |
| `not_an_image.txt` | — | — | `400 invalid_image` |

---

## 2. Run it in Docker

Built **natively for the host architecture**. On Apple silicon that is
`linux/arm64` — never pass `--platform amd64`; an emulated torch build is slow
and proves nothing the native one does not.

```bash
cd backend
cp .env.example .env      # set EYE_API_KEY; keep the placeholders elsewhere
mkdir -p models           # bind-mount source for the read-only weights volume

docker build -t eye-backend:dev .
docker compose up -d api admin        # api :8000, admin :8501
docker compose logs -f api
docker compose down
```

* `api` and `admin` share **one image** — `admin/dashboard.py` is inside it on
  purpose (the v1 Dockerfile copied only `app/` and the admin container
  crashed on startup).
* `models/` is mounted `:ro`. Weights are delivered air-gapped; the API never
  downloads anything at import or request time.
* Storage is a named volume, and the sqlite file lives on it, so
  `down && up` does not silently empty the admin panel.
* Postgres is behind a profile: `docker compose --profile prod up -d`. Set a
  real `POSTGRES_PASSWORD` in `.env` first — the compose default is a
  placeholder, not a password.
* **MinIO is deliberately absent.** An S3 service with no S3 adapter in the
  code is decoration; it returns at pilot phase with the adapter that uses it.

The image runs as **uid 10001**, single worker (`--workers 1` — the inference
semaphore and the dedup window are per-process state), and its `HEALTHCHECK`
polls `/health/ready`, not `/health/live`, because a container that is alive
but cannot reach its database should not be considered up.

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

**Step 3 — set the API key** in `local.properties` at the repo root (this file
is git-ignored and must stay that way):

```properties
API_KEY=demo123
```

**Step 4 — ⚠️ EDIT THE BASE URL. `API_BASE_URL` IS NOT READ FROM
`local.properties`.**

This is the single most likely reason a phone test fails. Only `API_KEY` comes
from `local.properties` (`app/build.gradle.kts:17`). The URL is **hardcoded**
at `app/build.gradle.kts:38`:

```kotlin
buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000/\"")
```

`10.0.2.2` is the **Android emulator's** alias for the host loopback. On a real
phone it resolves to nothing and every request fails. Change line 38 to this
machine's LAN IP and rebuild:

```kotlin
buildConfigField("String", "API_BASE_URL", "\"http://192.168.1.108:8000/\"")
```

The trailing `/` is mandatory (Retrofit `baseUrl` requirement).

| target | value for line 38 |
|---|---|
| Emulator on this host | `http://10.0.2.2:8000/` (the default) |
| Real phone, same Wi-Fi | `http://192.168.1.108:8000/` |
| ngrok fallback (different networks / captive Wi-Fi) | `https://xxxx.ngrok-free.app/` |

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
verdict is computed:

```python
p_ref = round(sum(pred["probs"][2:]), 4)     # P(ICDR >= 2) = referable DR
referable = p_ref >= threshold
```

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
  image is `UNGRADABLE` and `engine.predict` is never called — pinned by
  `tests/contract/test_engine_spy.py`.
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
  `DEDUP_WINDOW_MIN` (default 10) and replays the stored response. Known demo
  limitation: check-then-insert has a small race window for two genuinely
  concurrent identical uploads; a locking upgrade is pilot work.

### Device policy

`SPEC.md` ships with **no §10 macOS/MPS addendum**, so the device contract is
pinned in `app/config.py` instead:

* `EYE_DEVICE=cpu` — the default, and **mandatory** for tests, CI, Docker and
  every gate assertion. MPS never gates anything.
* `EYE_DEVICE=mps` — Apple-silicon dev runs only.
* `EYE_DEVICE=auto` — mps when genuinely available, else cpu with a WARNING.
* Grad-CAM always runs on cpu regardless of this setting.

### Mode enforcement (C9)

`EYE_MODE=demo` may use the mock engine, and every response carries
`mode="demo"` + `model_version="mock-v0"` so it cannot be mistaken for a live
model. `EYE_MODE=shadow` requires `EYE_MODEL_SOURCE=torch` **and** a
digest-verified artifact; without a loaded model `/health/ready` stays 503 and
`/api/v1/predict` returns `503 model_unavailable`. It never serves mock output.
The v1 `auto` model source was deleted: silently degrading to mock predictions
in a live deployment is a safety failure, not a convenience.

---

## 5. CI

`.github/workflows/backend-ci.yml` (repo root), triggered on `backend/**`
changes:

```
lint (ruff + mypy) -> pytest -m "not model and not perf" -> docker build
  -> compose up api (mock, sqlite) -> scripts/smoke_test.sh -> compose down
```

No secrets, no push, no deploy. The API key in the workflow is a literal
CI-only string so the smoke test's "wrong key → 401" step is meaningful; it
protects nothing.

`model` tests need a licensed checkpoint that is never in CI; `perf` tests are
a timing guard a shared runner cannot measure honestly. Both are excluded by
marker, not skipped silently.

---

## 6. The opencv packaging trap (read before debugging a container)

`grad-cam` depends on **`opencv-python`** — the GUI build — while
`requirements.txt` pins **`opencv-python-headless`**. pip installs both, and
they overwrite the *same* `cv2` package directory. Whichever lands last wins.

On a laptop this is invisible: macOS and desktop Linux have the GL libraries.
In a container it fails at `import cv2`:

```
ImportError: libGL.so.1: cannot open shared object file: No such file or directory
```

So the venv, the Dockerfile and CI all run the same two lines after the two
pip installs:

```bash
pip uninstall -y opencv-python
pip install --force-reinstall --no-deps opencv-python-headless==4.10.0.84
```

`--no-deps` keeps numpy's pin intact. Verified: `cv2` reports `4.10.0` and
`pytorch_grad_cam` still imports. The Dockerfile asserts this at build time in
the **runtime** stage (`RUN python -c "import cv2, torch, pytorch_grad_cam"`),
where the shipped system libraries are — so a regression fails the build
instead of production. `libgl1` is deliberately **not** installed in the image:
if it were, the bug would hide instead of failing loudly.

---

## 7. Next phase — deliberately NOT built now (C7)

These are deferred to the pilot phase. They are absent by decision, not by
oversight; each serves an actor or a data volume that does not exist yet.

* **Per-device hashed credentials** — today a single shared `EYE_API_KEY`.
* **Multi-tenant RLS** — no second tenant exists.
* **Consent tables** — demo runs on synthetic/non-PHI data (C13).
* **Outbox / durable job queue** — no async fan-out yet.
* **MinIO / S3 storage adapter** — returns *together with* the adapter that
  uses it, not before.
* **Encounters + DME model** — `patient_id`+`eye` is a *linkage*, not an
  encounter identifier: it can pair images from different visits (the app's own
  symmetry feature shares this caveat).
* **Authenticated media / refresh URLs (C6)** — `/static/...` is
  unauthenticated because Coil sends no API key and the app persists URLs in
  Room, so short-lived tokens would break history thumbnails. Requires a
  coordinated Android change.
* **Nullable wire fields (`PredictResponseV2`)** — the canonical schema with
  null UNGRADABLE fields exists as an **unrouted stub** and activates only with
  the Android nullability patch. The current non-null placeholders are a
  versioned compatibility surface, not the permanent contract.
* **SQLite → PostgreSQL** — code-portable by construction, but the migration
  *event* needs an Alembic baseline, a data migration, and the integration
  suite re-run against real Postgres. An explicit pilot gate, not a URL flip.
* **Rate limiting / 429** — deferred with the error-model work.

---

## 8. Android backlog — out of backend scope, tracked here (C8)

Two items the backend cannot fix and must not paper over:

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

---

## 9. Layout

```
backend/
├── SPEC.md, CLAUDE.md          frozen — the contract
├── app/
│   ├── config.py, schemas.py   frozen — settings + wire contract
│   ├── core/errors.py          frozen — {"error","detail"} envelope
│   ├── inference/              engine protocol, mock, decision (frozen);
│   │                           preprocess/quality/torch/gradcam
│   ├── db/                     models, session, crud
│   ├── api/                    predict, exams, deps
│   └── storage/local.py        magic-byte sniff, true extension (C11)
├── admin/dashboard.py          Streamlit demo panel (read-only, no login)
├── scripts/
│   ├── make_test_images.py     -> scripts/out/ (5 deterministic fixtures)
│   ├── smoke_test.sh           8 named steps against a running API
│   └── download_model.py       operator-run, air-gapped, records SHA-256
├── tests/                      conftest + synthetic frozen; unit/contract/integration
├── Dockerfile, docker-compose.yml, .dockerignore, .env.example
└── .github/workflows/backend-ci.yml   (at the REPO root)
```

**Never commit** a populated `.env`, model weights, or `local.properties`. All
three are git-ignored and excluded from the Docker build context.
