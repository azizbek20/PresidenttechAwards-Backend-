# EYE DETECT AI — Backend v4: Parallel Worktree Execution Plan for Claude Code

> **What this is:** v4 = v3 re-audited against repo HEAD `f6e4a0c` (the repo advanced
> mid-review: commit `3679077` "network reliability" added retry/cancel/health-check,
> `a6abc0b` added upload compression). Idempotency is now P0, persistence is strictly
> durable everywhere, and the error `detail` string is user-visible on the phone.
> Correction table in §8, client evidence with file:line cites in §9.
> One orchestrator session does Phase 0 (frozen interfaces) and Phase 2 (merge +
> verify). Four parallel Claude Code sessions implement disjoint modules in
> Phase 1. Agents execute; they do not redesign.
>
> **Commit this file as `backend/SPEC.md` in Phase 0** so every worktree session
> can read it.

---

## 0. Execution model — read this before spawning anything

**Why Phase 0 must be serial:** parallel agents are only faster when the
interfaces between their modules are frozen *before* they start. This is the
same principle as Doc 5's frozen Android↔backend contract: Komiljon and the
backend partner never waited on each other because the JSON was agreed on day 1
at 09:00. Here, `schemas.py`, the engine Protocol, and the CRUD signatures play
that role between agents. If agents invent their own interfaces, the merge
costs more than the parallelism saves.

**Honest speedup estimate (Amdahl):** Phase 0 ≈ 30–45 min serial, Phase 1
parallel (the big block), Phase 2 ≈ 45–60 min serial. Expect ~2–2.5× wall-clock
speedup vs one session, not 4×. Still worth it.

**Hard rules for every agent (also goes into `backend/CLAUDE.md`):**

1. You may create/modify **only the paths listed in your worktree brief** (§5).
2. Frozen files (§4.2 list) are read-only. If an interface looks wrong, **STOP
   and report in your final message — do not change it** (Doc 5 §6.3 rule:
   interfaces change only at the orchestrator level, by adding, never renaming).
3. Every function you implement must match the exact signature in this spec.
4. Your definition of done is the exact command list in your brief exiting 0.
   Never claim a test passed that was skipped or not run.
5. Commit small and often on your own branch. Never merge, rebase, or touch
   other branches. Never push.

---

## 1. Corrections baked into this v2 (delta vs the v1 spec)

These came out of the second review; they are **decisions, already made** —
agents implement, not re-litigate:

| # | Change | Rule |
|---|---|---|
| C1 | **Model licensing** | Do **NOT** use `sakshamkr1/ResNet50-APTOS-DR` — it is CC-BY-NC-4.0 (non-commercial) and ships a full pickled model. Demo/research candidate (NOT "the production model" — nothing is a production model until locally validated) = `jdelgado2002/diabetic_retinopathy_detection` (MIT) **or** a timm `efficientnet_b0` fine-tune loaded as a plain **state_dict**. Never call `torch.load(..., weights_only=False)` on any downloaded artifact. Record artifact SHA-256 in config and verify on startup. |
| C2 | **Server-generated patient ID** | The Android UI promises "ID kiritilmasa avtomatik raqam beriladi" but sends nothing when blank. When `patient_id` is absent: backend generates `"P-" + uuid4().hex[:6].upper()` (e.g. `P-9F3A1C`), persists it, and **returns it in `patient_id`**. Contract-safe: the app displays the response's `patient_id` on the result screen. |
| C3 | **UNGRADABLE without data contamination** | Wire format stays non-null (the deployed APK crashes on nulls). DB stores the truth. UNGRADABLE placeholders on the wire: `referable=false, probability=0.0, icdr_grade=0, grade_label="Baholab bo'lmadi"`. DB columns `results.probability` and `results.icdr_grade` are **NULLABLE** and store `NULL` for UNGRADABLE, so future training exports are clean. |
| C4 | **Error envelope stays frozen** | `{"error": "...", "detail": "..."}` exactly (Doc 5 §3.6). No RFC 9457 / problem+json. Custom handlers must override FastAPI defaults (the default validation shape `{"detail":[...]}` violates the contract). |
| C5 | **Streamlit admin stays in scope** | It is step 5 of the demo script (Doc 4 §7) — required, not optional. |
| C6 | **Media URLs: stable relative paths** | `/static/...` with UUID4 filenames, unauthenticated (Coil sends no API key). Signed URLs rejected for now: the app persists URLs in Room, and short-lived tokens would break future history thumbnails. Revisit at pilot phase together with an Android change. |
| C7 | **Deferred to pilot phase (do not build now)** | Per-device hashed credentials, multi-tenant RLS, consent tables, outbox, MinIO, encounters/DME model. Listed in README "Next phase". |
| C8 | **Android backlog (out of backend scope, note in README)** | `allowBackup="true"` + unencrypted Room = PHI exposure; "ISHONCH %" label shows referable-probability even for NO_REFER (misleading "6% confidence" on healthy patients). Fix on the Android side later. |
| C9 | **Mode enforcement — no silent fallback** | `EYE_MODE=demo\|shadow`. The `auto` model source is DELETED. Shadow refuses readiness without a digest-verified, license-cleared artifact; predict returns `503 model_unavailable` — never mock output. Every demo response carries `mode="demo"` and `model_version="mock-v0"`. |
| C10 | **Strict persistence — unconditional** | ANY mode: DB write failure → `500 persistence_error`. The admin panel is step 5 of the demo script, so a phone result missing from the panel breaks the demonstrated chain too; one code path, one test. Doc 4's lenient rule is retired. |
| C11 | **Upload hygiene** | Stream with a byte cap — never buffer-then-check; sniff magic bytes; store with the TRUE extension (`.jpg`/`.png`) — never hardcode `.jpg` for PNG bytes. |
| C12 | **Additive response keys only** | `request_id` and `mode` are ADDED (the installed APK's Gson ignores unknown keys — safe). Existing required fields stay non-null on the wire; the nullable-fields migration remains a pilot-phase, Android-coordinated change. |
| C13 | **Demo = synthetic/non-PHI data only** | Until the Android PHI items (C8) land, this stack runs `demo` mode with synthetic or consented test data only — stated in the README and enforced by team policy. |
| C14 | **Idempotency is P0 (client-verified at HEAD)** | `retry()` resends the SAME retained file/URI bytes (`ScreeningViewModel.kt:150`, test at `ScreeningViewModelTest.kt:167`), so server-success + client-timeout + retry = duplicate exam. The client sends no header, so the backend dedups by **content fingerprint**: `sha256(bytes)+patient_code+eye` within `DEDUP_WINDOW_MIN` (default 10) → replay the stored response, run inference once. An optional `Idempotency-Key` header is also accepted for the future Android patch and takes precedence when present. |
| C15 | **Error `detail` is user-visible** | The client now parses `{"detail": ...}` from error bodies and shows it (`ScreeningViewModel.kt:328`). Every envelope `detail` must be a short, human-readable **Uzbek string** (never a FastAPI list — `optString` on an array silently yields ""). |
| C16 | **Client facts at HEAD the backend must serve** | `ApiClient.ping()` sends `HEAD` to the base URL and counts ANY HTTP response as online (`ApiClient.kt:61-64`) → `HEAD /` → 204 is REQUIRED, unauthenticated. Uploads are now client-compressed (~1500 px, q85) → typical payload 200–600 KB. The client can cancel mid-request on navigation → the server must release the inference semaphore on disconnect (context-manager acquire). |

Everything else from v1 stands: quality gate before verdict, threshold only on
server, sensitivity-first, all 15 response keys always present, 30 s phone
timeout budget, single-worker containers, air-gapped model delivery.

---

## 2. Orchestrator — exact command sequence

Run these yourself (the orchestrator Claude Code session) from the repo root.
Use extended thinking (`ultrathink`) only in Phase 0 and Phase 2; Phase 1 agents
need no deep thinking — their briefs are prescriptive.

```bash
# ---- SETUP ----
git status   # verify a clean tree; the user has explicitly authorized the
             # branch/worktree/merge operations in this plan (do NOT assume this elsewhere)
git checkout main && git pull
git checkout -b backend-base

# ---- PHASE 0 (serial): create the frozen kit (§4), then: ----
mkdir -p backend && cd backend
# ... create all §4 files exactly as specified ...
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/test_frozen_kit.py -q          # sanity: kit imports, fixture validates
cd .. && git add backend && git commit -m "backend: phase0 frozen interface kit"

# ---- SPAWN 4 WORKTREES ----
git branch feature/inference backend-base
git branch feature/db        backend-base
git branch feature/api       backend-base
git branch feature/ops       backend-base
git worktree add ../eye-wt-a feature/inference
git worktree add ../eye-wt-b feature/db
git worktree add ../eye-wt-c feature/api
git worktree add ../eye-wt-d feature/ops
```

Then start **four Claude Code sessions**, one per worktree directory, and give
each exactly this kickoff prompt (replace the letter):

> You are Agent **A** working in this worktree on branch `feature/inference`.
> Read `backend/SPEC.md` fully, then execute your brief in §5-A. Obey the hard
> rules in §0 and the file-ownership list — touch nothing outside it. Create
> your venv from `backend/requirements-dev.txt`. Your task is done only when
> every command in your Definition-of-Done block exits 0; paste their output in
> your final report. Commit on this branch only.

```bash
# ---- PHASE 2 (serial, after all four report done): merge in this order ----
cd <main-repo>
git checkout backend-base
for BR in feature/inference feature/db feature/api feature/ops; do
  git merge --no-ff "$BR" -m "merge $BR"
  (cd backend && source venv/bin/activate && pip install -r requirements-dev.txt -q && pytest -q -m "not model and not perf") || { echo "GATE FAILED after $BR"; exit 1; }
done

# full verification (§6), then:
git checkout main && git merge --no-ff backend-base
git worktree remove ../eye-wt-a ../eye-wt-b ../eye-wt-c ../eye-wt-d
git branch -d feature/inference feature/db feature/api feature/ops
```

File ownership is disjoint by design, so merges should be conflict-free; any
conflict means an agent violated §0 rule 1 — resolve by taking the owning
agent's version.

---

## 3. Target layout and ownership map

```
backend/
├── SPEC.md                    FROZEN (this file)
├── CLAUDE.md                  FROZEN (§0 rules, copied verbatim)
├── requirements.txt           FROZEN
├── requirements-dev.txt       FROZEN
├── app/
│   ├── main.py                Agent C
│   ├── config.py              FROZEN
│   ├── schemas.py             FROZEN
│   ├── core/errors.py         FROZEN (handlers) 
│   ├── core/security.py       Agent C
│   ├── api/deps.py            Agent C
│   ├── api/predict.py         Agent C
│   ├── api/exams.py           Agent C
│   ├── inference/engine.py    FROZEN (Protocol + factory skeleton)
│   ├── inference/mock_engine.py   FROZEN (needed by C's tests from day 1)
│   ├── inference/torch_engine.py  Agent A
│   ├── inference/preprocess.py    Agent A
│   ├── inference/quality.py       Agent A
│   ├── inference/gradcam.py       Agent A
│   ├── inference/decision.py      FROZEN
│   ├── db/base.py             Agent B
│   ├── db/models.py           Agent B
│   ├── db/crud.py             FROZEN signatures → Agent B fills bodies
│   └── storage/local.py       Agent C
├── admin/dashboard.py         Agent D
├── scripts/                   Agent D (make_test_images.py, smoke_test.sh, download_model.py)
├── tests/
│   ├── conftest.py            FROZEN
│   ├── test_frozen_kit.py     FROZEN
│   ├── fixtures/golden_predict.json   FROZEN
│   ├── unit/                  Agent A
│   ├── contract/              Agent C
│   └── integration/           Agent B (persistence) + C (static/auth)
├── Dockerfile                 Agent D
├── docker-compose.yml         Agent D
├── .dockerignore              Agent D
├── .env.example               Agent D
└── .github/workflows/backend-ci.yml   Agent D (place at repo root .github/)
```

---

## 4. PHASE 0 — the frozen kit (orchestrator writes these EXACTLY)

### 4.1 `requirements.txt` / `requirements-dev.txt`

`requirements.txt` — one requirement per line (valid pip syntax):

```
fastapi==0.115.*
uvicorn[standard]==0.30.*
python-multipart==0.0.9
pydantic-settings==2.*
sqlalchemy==2.0.*
pillow==10.*
opencv-python-headless==4.10.*
numpy==1.26.*
timm==1.0.*
grad-cam==1.5.*
huggingface_hub==0.24.*
streamlit==1.37.*
psycopg[binary]==3.2.*
```

`requirements-torch.txt` — separate file with a pinned index so torch never
resolves from PyPI and PyPI packages never resolve from the torch index
(dependency-confusion guard):

```
--index-url https://download.pytorch.org/whl/cpu
torch==2.3.*
torchvision==0.18.*
```

Install order — identical in venv, Dockerfile, and CI:
`pip install -r requirements-torch.txt && pip install -r requirements.txt`

`requirements-dev.txt`: `pytest==8.*`, `pytest-asyncio`, `httpx`, `ruff`, `mypy`.

### 4.2 Frozen files list (read-only for all agents)

`SPEC.md, CLAUDE.md, requirements*.txt, app/config.py, app/schemas.py,
app/core/errors.py, app/inference/engine.py, app/inference/mock_engine.py,
app/inference/decision.py, app/db/crud.py (signatures — bodies are Agent B's),
tests/conftest.py, tests/test_frozen_kit.py, tests/fixtures/golden_predict.json`

### 4.3 `app/schemas.py` — verbatim

```python
"""Frozen wire contract. Doc 5 §3 + Android PredictResponse.kt. DO NOT EDIT."""
from typing import Literal
from pydantic import BaseModel, Field

Decision = Literal["REFER", "NO_REFER", "UNGRADABLE"]
Eye = Literal["right", "left"]
Quality = Literal["good", "poor"]

DISCLAIMER = "Bu skrining/triaj vositasi; yakuniy tashxis oftalmolog mas'uliyati."

class PredictResponse(BaseModel):
    exam_id: str
    patient_id: str | None
    eye: Eye | None
    referable: bool
    probability: float = Field(ge=0.0, le=1.0)
    icdr_grade: int = Field(ge=0, le=4)
    grade_label: str
    decision: Decision
    decision_text: str
    quality: Quality
    heatmap_url: str | None
    image_url: str | None
    model_version: str
    processed_at: str          # ISO-8601 UTC "....Z"
    disclaimer: str
    # C12 additive keys — safe: the installed APK's Gson ignores unknown fields
    request_id: str            # uuid4 per request; also goes in server logs
    mode: Literal["demo", "shadow"]

class ExamSummary(BaseModel):
    exam_id: str
    patient_id: str | None
    eye: Eye | None
    referable: bool
    probability: float
    icdr_grade: int
    decision: Decision
    processed_at: str

class ErrorEnvelope(BaseModel):
    error: str    # invalid_image|unauthorized|not_found|payload_too_large|validation_error|inference_error|persistence_error|model_unavailable
    detail: str   # C15: USER-VISIBLE on the phone — short, human-readable Uzbek string, never a list
```

### 4.4 `app/core/errors.py` — verbatim behavior spec

```python
class ApiError(Exception):
    def __init__(self, status: int, error: str, detail: str): ...

def register_handlers(app):
    """MUST override: ApiError, RequestValidationError (→422 validation_error),
    StarletteHTTPException (map 404→not_found, else pass code with generic error
    name), Exception (→500 inference_error, log traceback, NEVER leak it).
    Every response body is exactly {"error": ..., "detail": ...}."""
```

### 4.5 `app/inference/engine.py` + `mock_engine.py` — verbatim

```python
class Prediction(TypedDict):
    grade: int                 # 0..4
    probs: list[float]         # len 5, sums to 1.0
    model_version: str

class InferenceEngine(Protocol):
    model_loaded: bool
    def predict(self, img: "np.ndarray") -> Prediction: ...

def get_engine(settings) -> InferenceEngine:
    """mock | torch | auto (torch if checkpoint dir non-empty else mock+warning).
    Import torch_engine lazily so the mock path never imports torch."""
```

MockEngine (fully implemented in Phase 0, deterministic **and
fixture-controllable** — a hash-modulo mock cannot guarantee that the demo
shows both 🔴 and 🟢):
`m = mean gray of the decoded RGB image` →
`grade = 4 if m >= 140 else (2 if m >= 120 else 0)`;
`probs = 0.85` on the chosen grade, remainder spread evenly over the other four;
`model_version = "mock-v0"`, `model_loaded = True`. Fixture generators target
the bands: the REFER fixture aims for mean ≈ 160, the NO_REFER fixture for
mean ≈ 100 (the quality gate still rules blurry/dark inputs UNGRADABLE before
the mock is ever consulted). Full chain, no model weights — the Doc 5
`EYE_MODEL_SOURCE=mock` behavior, made demo-deterministic.

### 4.6 `app/inference/decision.py` — verbatim

```python
GRADE_LABELS = {0: "DR yo'q", 1: "Yengil NPDR", 2: "O'rtacha NPDR",
                3: "Og'ir NPDR", 4: "Proliferativ DR"}

@dataclass(frozen=True)
class DecisionResult:
    decision: str; referable: bool; probability: float
    icdr_grade: int; grade_label: str; decision_text: str; quality: str
    # DB-truth fields (C3): None for UNGRADABLE, mirror wire values otherwise
    db_probability: float | None
    db_icdr_grade: int | None

def decide(pred: Prediction | None, quality_ok: bool, threshold: float) -> DecisionResult:
    if not quality_ok or pred is None:
        return DecisionResult("UNGRADABLE", False, 0.0, 0, "Baholab bo'lmadi",
                              "Sifatsiz rasm — qayta suratga oling", "poor",
                              db_probability=None, db_icdr_grade=None)
    p_ref = round(sum(pred["probs"][2:]), 4)
    referable = p_ref >= threshold
    return DecisionResult(
        "REFER" if referable else "NO_REFER", referable, p_ref,
        pred["grade"], GRADE_LABELS[pred["grade"]],
        "Referable DR — oftalmologga yuboring" if referable
        else "Referable DR aniqlanmadi — 12 oydan keyin qayta tekshiruv",
        "good", db_probability=p_ref, db_icdr_grade=pred["grade"])
```

### 4.7 `app/db/crud.py` — frozen SIGNATURES (Agent B implements bodies)

```python
def generate_patient_code() -> str:
    """'P-' + uuid4().hex[:6].upper()  (C2)."""

def get_or_create_patient(session, patient_code: str) -> "Patient": ...

def create_exam_with_result(session, *, exam_id: str, patient_code: str | None,
    eye: str | None, image_path: str, content_sha256: str, quality: str,
    blur_var: float | None, mean_gray: float | None, result: DecisionResult,
    model_version: str, heatmap_path: str | None, processed_at: datetime) -> None:
    """One transaction. patient_code may already be server-generated by caller."""

def find_recent_duplicate(session, *, content_sha256: str, patient_code: str | None,
                          eye: str | None, window_min: int) -> dict | None:
    """C14: predict-shaped dict of the newest matching exam inside the window, else None."""

def list_exams(session, limit: int = 50, offset: int = 0,
               patient_code: str | None = None) -> list[dict]: ...

def get_exam(session, exam_id: str) -> dict | None:
    """Returns predict-shaped dict (§4.3 keys) or None."""
```

### 4.8 `tests/conftest.py` + `tests/fixtures/golden_predict.json`

conftest fixtures (frozen): `refer_jpeg_bytes` (synthetic 640×640 fundus-like:
disc circle + speckle noise, sharp, mean gray ≈ 160 → mock grade 4),
`norefer_jpeg_bytes` (same geometry, mean gray ≈ 100 → mock grade 0),
`blurry_jpeg_bytes` (norefer → `cv2.GaussianBlur(k=21)`),
`dark_jpeg_bytes` (mean < 15), `text_file_bytes`; `client` (httpx TestClient, `EYE_MODEL_SOURCE=mock`, tmp
storage dir, sqlite tmp DB); `authed_client` (same + `EYE_API_KEY=testkey` env
and header helper).

`golden_predict.json` = the §1.1 JSON from the v1 spec verbatim (the same
sample the Android `ApiServiceTest` parses) **plus** `"request_id":"<uuid4>"`
and `"mode":"demo"` (C12). `test_frozen_kit.py` asserts:
`PredictResponse.model_validate(golden)` passes; all 15 legacy keys present;
mock engine determinism **and band contract** (refer fixture → grade 4,
norefer fixture → grade 0); `decide()` worked example
(`probs=[0.05,0.10,0.25,0.45,0.15] → grade 3, p=0.85, REFER`) and UNGRADABLE
override (`quality_ok=False, probs=[0,0,0,0,1] → UNGRADABLE, db fields None`).

### 4.9 `app/config.py` — frozen fields (C9)

Same vars as the v1 spec §4 with these changes: **`EYE_MODE`** = `demo` |
`shadow`, default `demo`; **`EYE_MODEL_SOURCE`** = `mock` | `torch`, default
`mock` — the `auto`-falls-back-to-mock behavior is DELETED (silent mock
predictions in a live deployment are a safety failure, not a convenience);
**`EYE_MODEL_SHA256`** required when `EYE_MODE=shadow`. Startup rules:
`shadow` requires `EYE_MODEL_SOURCE=torch` and a digest-verified artifact,
otherwise `/health/ready` stays 503 and `/api/v1/predict` returns
`503 {"error":"model_unavailable",...}` — it never serves mock output. `demo`
may use the mock, and every response carries `mode="demo"` +
`model_version="mock-v0"` so it cannot be mistaken for a live model.

---

## 5. PHASE 1 — the four worktree briefs

Every brief is self-contained: ownership list, tasks, exact behaviors,
Definition of Done (DoD) commands. Agents run `pip install -r
backend/requirements-dev.txt` in their own venv first.

---

### 5-A. Agent A — worktree `../eye-wt-a`, branch `feature/inference`

**Owns:** `app/inference/{preprocess,quality,torch_engine,gradcam}.py`,
`tests/unit/**`, `tests/fixtures/aptos_samples/` (3 small lawfully-sourced fundus JPEGs
≤ 300 KB, one per class band: `no_dr.jpg`, `moderate.jpg`, `severe.jpg`).
Synthetic stand-ins may exercise the execution path only — **never** grade
assertions. If real labeled samples are unavailable, the grade test is skipped
with a stated reason, not faked.

**A1 `preprocess.py`:**
```python
def load_rgb(raw: bytes) -> "np.ndarray | None"      # Pillow decode + exif_transpose + RGB; None on failure
def retina_crop(img: np.ndarray) -> np.ndarray       # threshold gray<10 border, bbox, center square crop
def to_model_input(img: np.ndarray, size: int) -> np.ndarray  # resize, float32, ImageNet mean/std, CHW
def display_copy(img: np.ndarray) -> np.ndarray      # 512px RGB uint8 for gradcam overlay
```
Determinism requirement: same bytes → bit-identical output, twice.

**A2 `quality.py`:**
```python
@dataclass(frozen=True)
class QualityReport: ok: bool; quality: str; blur_var: float; mean_gray: float
def assess(img_rgb: np.ndarray, settings) -> QualityReport
```
Rules: grayscale at 512 px; `ok = blur_var >= settings.quality_blur_min_var
(default 50.0) and 20 <= mean_gray <= 235 and min(h,w) >= 300`.

**A3 `torch_engine.py`** (respect C1 — licensing):
- Loader order: (1) plain state_dict at `EYE_MODEL_DIR/model.pt` into timm
  arch from `EYE_MODEL_DIR/arch.txt` (default `efficientnet_b0`,
  `num_classes=5`); (2) `jdelgado2002/diabetic_retinopathy_detection` layout
  if present locally. **Never** `torch.load(weights_only=False)`; use
  `weights_only=True` or safetensors. If `EYE_MODEL_SHA256` is set, verify the
  file digest before loading; mismatch → refuse, `model_loaded=False`.
- `eval()` + `inference_mode()`; softmax → `Prediction`;
  `model_version = settings.eye_model_version`.
- No network access at import or load time (air-gapped rule).

**A4 `gradcam.py`:**
```python
def render_heatmap(model, input_tensor, display_rgb, out_path: Path) -> bool
```
grad-cam on last conv block, 40% alpha overlay, PNG. Whole body in try/except →
`False` on any failure. Also `def mock_heatmap(display_rgb, out_path) -> bool`
(radial gradient overlay) used by the mock path.

**A5 `tests/unit/`:** `test_preprocess.py` (determinism, EXIF, non-square),
`test_quality.py` (sharp passes / blurred fails on `QUALITY_BLUR_MIN_VAR`;
dark fails on brightness; assert the actual measured `blur_var` of the sharp
fixture is ≥ 3× the threshold so the test isn't knife-edge),
`test_torch_engine.py` marked `@pytest.mark.model` (skips without a checkpoint
OR without real labeled samples; asserts severe.jpg grade ≥ 2 on real samples
only), `test_gradcam.py` (mock_heatmap writes a valid
PNG; render failure path returns False without raising).

**DoD:**
```bash
cd backend && source venv/bin/activate
ruff check app/inference tests/unit && mypy app/inference
pytest tests/unit tests/test_frozen_kit.py -q -m "not model"
```

---

### 5-B. Agent B — worktree `../eye-wt-b`, branch `feature/db`

**Owns:** `app/db/{base,models}.py`, bodies of `app/db/crud.py`,
`tests/integration/test_persistence.py`.

**B1 `models.py`** (SQLAlchemy 2.0 typed ORM, portable SQLite↔Postgres):
tables `patients / exams / results` per the v1 schema **with correction C3**:

```
results.probability  REAL     NULL      ← nullable (C3)
results.icdr_grade   INTEGER  NULL CHECK (icdr_grade BETWEEN 0 AND 4)
results.referable    BOOLEAN  NOT NULL
results.decision     TEXT     NOT NULL CHECK (decision IN ('REFER','NO_REFER','UNGRADABLE'))
```
All PKs = TEXT uuid4. TZ-aware UTC datetimes. Indexes:
`exams(created_at DESC)`, `exams(patient_id, created_at DESC)`,
unique `results(exam_id, model_version)`, unique `patients(patient_code)`;
`exams.content_sha256 TEXT NOT NULL` with index
`(content_sha256, created_at DESC)` for the C14 dedup lookup.
Plus a minimal append-only **`audit_log`** (Doc 3 §4.2): `id TEXT PK,
ts TIMESTAMP NOT NULL, action TEXT NOT NULL, exam_id TEXT NULL, detail TEXT
NULL` — the codebase must contain no UPDATE/DELETE path for it.

**B2 `base.py`:** engine from `settings.database_url`; sqlite →
`connect_args={"check_same_thread": False}`; `init_db()` = `create_all`;
`get_session()` context manager committing/rolling back.

**B3 `crud.py` bodies** exactly per §4.7. `create_exam_with_result` writes
`result.db_probability` / `result.db_icdr_grade` (NULLs for UNGRADABLE), while
`referable`/`decision` are always stored; it also appends one `audit_log` row
(`action='predict'`) in the same transaction. Patient-code collisions (unique
constraint) are handled by regenerate-and-retry inside the create path. `get_exam` reconstructs the wire
shape: when DB values are NULL, emit the C3 placeholders
(`probability=0.0, icdr_grade=0, grade_label="Baholab bo'lmadi"`).

**B4 `tests/integration/test_persistence.py`** (tmp sqlite, no HTTP):
create→read roundtrip equals input; same patient_code twice → 1 patient,
2 exams; UNGRADABLE result stores NULL probability/grade in DB **and**
`get_exam` returns placeholder wire values; `list_exams` ordering + pagination
+ patient filter; `find_recent_duplicate` hits inside the window, misses outside
it and misses on a different eye/patient; concurrent `get_or_create_patient`
race resolved by unique constraint (two threads, one row).

**DoD:**
```bash
cd backend && source venv/bin/activate
ruff check app/db tests/integration/test_persistence.py && mypy app/db
pytest tests/integration/test_persistence.py tests/test_frozen_kit.py -q
python - <<'PY'
from app.db.base import init_db; init_db(); print("create_all OK")
PY
```

---

### 5-C. Agent C — worktree `../eye-wt-c`, branch `feature/api`

**Owns:** `app/main.py`, `app/core/security.py`, `app/api/**`,
`app/storage/local.py`, `tests/contract/**`,
`tests/integration/{test_static_serving,test_auth,test_db_failure}.py`, and
`tests/perf/test_latency.py` (G5 owner: mock p95 < 300 ms; 4 concurrent
predicts each finish < 25 s; marked `perf`).

Agent C codes **against** the frozen crud signatures and the frozen mock
engine; it never edits `app/db/*` or `app/inference/*`. Until merge, its tests
run with whatever `crud.py` stub behavior exists — write a tiny in-test
monkeypatch shim ONLY inside `tests/` if stubs raise, never in `app/`.

**C1 `main.py`:** app factory; `register_handlers`; CORS allow-all on
`/api/v1/*`; mount `StaticFiles(directory=settings.storage_dir)` at `/static`
with subdirs `images/`, `heatmaps/`; startup: init storage dirs, `init_db()`,
`get_engine()`; `HEAD /` → 204 (one
line, harmless). `GET /health` → `{"status":"ok","model_loaded":bool}` (open).
`GET /health/live` → 200 always. `GET /health/ready` → 200 only when the DB
pings, the storage dir is writable, and (shadow mode) the model is loaded with
a verified digest — otherwise 503. Compose healthchecks use `/health/ready`.

**C2 `security.py` + `deps.py`:** dependency `require_api_key`: if
`settings.eye_api_key` unset → pass + one WARNING log at startup; else
constant-time compare (`secrets.compare_digest`) of header `X-API-Key` →
mismatch/missing raises `ApiError(401, "unauthorized", ...)`. Applied to
`/api/v1/*` router only — never `/health`, never `/static`.

**C3 `storage/local.py`:**
```python
def sniff_ext(raw: bytes) -> str | None   # b'\\xff\\xd8\\xff'->'.jpg', PNG magic->'.png', else None
def save_original(raw: bytes, exam_id: str) -> tuple[Path, str]   # ext from sniff_ext — NEVER hardcode .jpg (C11)
def heatmap_target(exam_id: str) -> tuple[Path, str]              # → (fs path, "/static/heatmaps/{id}.png")
```
Filenames come ONLY from server-side exam_id (never client filename).

**C4 `api/predict.py`** — the exact flow:
```
file: UploadFile = File(...), patient_id: str|None = Form(None), eye: str|None = Form(None)
1. eye not in (None,"right","left") → ApiError(422,"validation_error",...)
2. Content-Length > MAX_UPLOAD_MB → 413 immediately; else read in 1 MB chunks,
   aborting with 413 the moment the cap is crossed (never buffer-then-check, C11);
   0 bytes → 400 invalid_image
3. sniff_ext(raw) is None → 400 invalid_image; img = load_rgb(raw); None → 400 invalid_image
3b. C14 dedup: fp = sha256(raw); key = request header "Idempotency-Key" or fp;
    prior = crud.find_recent_duplicate(fp/key, patient_id, eye, DEDUP_WINDOW_MIN)
    → if hit, RETURN the stored response verbatim (same exam_id; inference NOT re-run).
    Known demo limitation, documented: check-then-insert has a small race window for
    two truly concurrent identical uploads; pilot adds a locking upgrade.
4. exam_id = str(uuid4()); save_original
5. q = quality.assess(img)
6. pred = None
   if q.ok:
       tensor = to_model_input(retina_crop(img), engine_input_size)
       async with app.state.infer_sem:                      # Semaphore(INFERENCE_CONCURRENCY)
           pred = await run_in_threadpool(engine.predict, tensor)
       (engine exception → ApiError(500,"inference_error",...))
7. d = decide(pred, q.ok, settings.referable_threshold)
8. heatmap_url = None
   if q.ok: best-effort render_heatmap/mock_heatmap → heatmap_url on success
9. patient_code = patient_id or generate_patient_code()      # C2 correction — ALWAYS non-null from here
10. crud.create_exam_with_result(...) — on ANY failure (C10, unconditional):
    ApiError(500, "persistence_error", "Natija saqlanmadi — qayta urining") —
    never show a result the admin panel cannot corroborate
11. return PredictResponse(patient_id=patient_code, eye=eye, ...,
    processed_at=utcnow "Z", request_id=str(uuid4()), mode=settings.eye_mode)
```

**C5 `api/exams.py`:** list (limit≤100/offset/patient_id filter) → `ExamSummary`;
detail → predict-shaped dict or `ApiError(404,"not_found",...)`.

**C6 `tests/contract/`** (all with mock engine):
- `test_predict_contract.py`: 200; all 15 legacy keys present AND the full body
  validates against frozen `PredictResponse` (17 keys incl. request_id, mode); types;
  `decision` in enum; `processed_at` regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`;
  `heatmap_url` null or `/static/heatmaps/` prefix; response validates against
  frozen `PredictResponse`.
- `test_patient_autogen.py` (C2): no `patient_id` part → 200 and
  `patient_id` matches `^P-[0-9A-F]{6}$`; provided `P-0001` → echoed exactly.
- `test_ungradable_wire.py` (C3): blurry fixture → `decision=UNGRADABLE`,
  `quality="poor"`, `referable=false`, `probability=0.0`, `icdr_grade=0`,
  `heatmap_url=null`.
- `test_error_envelope.py` (C4): text file → 400/invalid_image; **missing
  `file` part → 422 body exactly `{"error":"validation_error","detail":...}`**;
  unknown exam → 404/not_found; oversized → 413; engine monkeypatched to raise
  → 500/inference_error. Assert NO response ever has shape `{"detail":[...]}`.
- `test_auth.py`: with key set: absent→401, wrong→401, right→200; `/health` and
  a saved static file fetch succeed WITHOUT the header (the Coil rule).
- `test_static_serving.py`: predict → GET its `image_url` → 200 + JPEG magic;
  `heatmap_url` → PNG magic.
- `test_db_failure.py` (C10): monkeypatch `create_exam_with_result` to raise →
  500 `persistence_error` in BOTH modes; the retained client file makes retry safe.
- `test_duplicate_retry.py` (C14): POST the same bytes+patient+eye twice → same
  `exam_id`, ONE exams row, and an engine spy proves inference ran exactly once;
  different eye or expired window → new exam. With an `Idempotency-Key` header:
  same key replays; same key + different bytes → 409 `idempotency_conflict`.
- `test_error_detail_is_string.py` (C15): every error path yields `detail` of
  type str (never a list) and non-empty.
- `test_engine_spy.py` (safety regression): monkeypatch `engine.predict` to raise
  `AssertionError`; POST the blurry fixture → 200 UNGRADABLE — proves the DR
  engine is never invoked after a quality-gate failure.
- `test_model_unavailable.py` (C9): `EYE_MODE=shadow` with no model → predict
  returns 503 `model_unavailable`, never a mock prediction.

**DoD:**
```bash
cd backend && source venv/bin/activate
ruff check app/main.py app/api app/core/security.py app/storage tests/contract && mypy app/api app/storage
pytest tests/contract tests/integration/test_static_serving.py tests/integration/test_auth.py tests/integration/test_db_failure.py tests/test_frozen_kit.py -q
uvicorn app.main:app --port 8000 &  sleep 3
curl -fsS localhost:8000/health && kill %1
```

---

### 5-D. Agent D — worktree `../eye-wt-d`, branch `feature/ops`

**Owns:** `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`,
`admin/dashboard.py`, `scripts/**`, `.github/workflows/backend-ci.yml`,
`backend/README.md`.

**D1 Dockerfile / compose:** v1 spec §9 as the base, with corrections:
`COPY app/ admin/ scripts/ ./` — the admin service runs `admin/dashboard.py`
from the same image, so it must exist inside it (the v1 Dockerfile copied only
`app/` and the admin container would have crashed); install
`requirements-torch.txt` then `requirements.txt` (§4.1); multi-stage, non-root
uid 10001, `--workers 1`; HEALTHCHECK hits `/health/ready`; compose =
`api`+`admin` default, `postgres` under `profiles: ["prod"]`; **MinIO is
removed** until an S3 storage adapter actually uses it (an unused declared
service is decoration, not production support — it returns at pilot phase with
the adapter); models `:ro` volume; storage volume. `.env.example` lists every §4
config var with safe placeholders — **no real secrets ever**.

**D2 `scripts/make_test_images.py`:** writes `refer.jpg` (sharp, mean≈160 →
mock REFER), `no_dr.jpg` (sharp, mean≈100 → mock NO_REFER), `blurry.jpg`,
`dark.jpg`, `not_an_image.txt` into `scripts/out/` — same generators as the
frozen conftest fixtures, so smoke-test colors are deterministic.

**D3 `scripts/smoke_test.sh`** (bash, `set -euo pipefail`, requires `jq`,
takes BASE_URL + API_KEY args):
1. `GET /health` → `.status=="ok"`.
2. predict refer.jpg → all 15 legacy keys exist (`jq -e`) and `.decision=="REFER"`.
3. predict no_dr.jpg → `.decision=="NO_REFER"`; predict blurry.jpg →
   `.decision=="UNGRADABLE"` and `.probability==0.0`.
4. predict with no patient_id → `.patient_id | test("^P-[0-9A-F]{6}$")`.
5. missing-file POST → HTTP 422 and `.error=="validation_error"`.
6. `GET /api/v1/exams` length ≥ 3; fetch first `image_url` → HTTP 200.
7. wrong API key → 401 (only when key arg given).
8. re-POST the exact refer.jpg bytes with the same patient_id/eye →
   `.exam_id` equals step 2's (C14 dedup live).
Exit non-zero on any failure with a named step message.

**D4 `admin/dashboard.py`** (C5 — required): reads the API
(`API_URL`, `EYE_API_KEY` env): exams table (date, patient, eye, decision,
probability, model_version); row select → original + heatmap side-by-side
(prefix relative URLs with API_URL); stats header (total, REFER count/%,
UNGRADABLE %). Read-only, no login (documented as demo-only).

**D5 CI `backend-ci.yml`:** jobs on backend/** changes:
`lint(ruff)+mypy → pytest -m "not model and not perf" → docker build →
compose up api (mock, sqlite) → scripts/smoke_test.sh http://localhost:8000 →
compose down`. No secrets, no push, no deploy.

**D6 `backend/README.md`:** run locally / Docker / point the phone
(LAN IP + `local.properties` API_KEY, ngrok fallback); where the threshold
lives and why the client never re-derives it; C7 "Next phase" list; C8 Android
backlog notes (allowBackup/Room encryption, ISHONCH label semantics).

**DoD:**
```bash
cd backend
docker build -t eye-backend:dev .            # must succeed w/o models present
docker compose config -q
python scripts/make_test_images.py && ls scripts/out | wc -l   # == 5
bash -n scripts/smoke_test.sh
```
(D cannot run the full smoke against a live API pre-merge — that is a Phase 2
gate, not yours.)

---

## 6. PHASE 2 — merge verification protocol (orchestrator, serial)

After the four merges (§2 loop) all pass their per-merge gate:

```bash
cd backend && source venv/bin/activate && pip install -r requirements-dev.txt -q

# G1: full suite, mock engine
pytest -q -m "not model and not perf"

# G2: live server + smoke (mock)
EYE_API_KEY=demo123 EYE_MODEL_SOURCE=mock uvicorn app.main:app --port 8000 &
sleep 3 && bash scripts/smoke_test.sh http://localhost:8000 demo123 && kill %1

# G3: container parity — same key for compose AND smoke (env-mismatch fix)
set -a; source .env; set +a
docker compose up -d api admin
sleep 20 && bash scripts/smoke_test.sh http://localhost:8000 "$EYE_API_KEY"
docker compose down

# G4: torch path (only if a licensed checkpoint is present — C1)
EYE_MODEL_SOURCE=torch pytest -q -m model
# then repeat G2 with EYE_MODEL_SOURCE=torch and eyeball grades on the 3 samples

# G5: perf guard
pytest -q -m perf        # mock p95<300ms; 4 concurrent predicts all <25s
```

**G6 — phone gate (human + device, from Doc 5 §5.2):** point the debug APK at
the LAN IP with the matching `API_KEY`; verify 🔴 REFER + heatmap renders,
🟢 NO_REFER, ⚪ UNGRADABLE, blank-patient-ID shows a `P-XXXXXX` on the result
screen, airplane-mode shows the friendly error, then **re-enable network and tap
Qayta urinish** — the retry succeeds and the admin panel shows exactly ONE row
for that capture (C14), History persists the exam, and the Streamlit table
shows the phone's exams. Twice, back to back.

Only after G1–G5 (and G6 when hardware is available): merge `backend-base` →
`main`. The final report must paste real command output for every gate and
list anything skipped (e.g. G4 without a checkpoint) explicitly.

---

## 7. What agents must NOT do (recap)

No response fields beyond frozen `schemas.py` (15 legacy + `request_id`,
`mode`), no renamed JSON keys, no problem+json, no nullable wire fields, no
auth on `/static`, no mock predictions outside `EYE_MODE=demo`, no duplicate exams from a
resent payload, no non-string error `detail`, no runtime model downloads, no
`torch.load(weights_only=False)`, no CC-BY-NC model artifacts, no editing
frozen files, no cross-branch operations, no pushes, no claims of untested
success. When blocked → finish what is unblocked, report the blocker.

---

## 8. Correction table — external (GPT) review items → v3 resolution

| GPT item | Status | v3 resolution |
|---|---|---|
| 1. Nullable wire fields + mandatory Android patch first | ✳️ Partial | Additive keys `request_id`, `mode` added (§4.3, C12) — backward-compatible. Nullable-ing existing required fields REJECTED for this phase: breaks every installed APK; C3 (non-null wire placeholders, NULL in DB) preserves both compatibility and clean data. Nullable migration = pilot phase, Android-coordinated. |
| 2. Idempotency is P0 | ✅ ACCEPTED in v4 | My rejection was correct only for the snapshot I had cloned (`0b90402`); commit `3679077`, pushed mid-review, added true retry that resends the retained bytes (§9 evidence). v4: C14 content-fingerprint dedup that works with today's header-less client + optional `Idempotency-Key`. |
| 3. No 200 after persistence failure | ✅ Accepted | C10 + §5-C step 10 + `test_db_failure.py`: shadow → `500 persistence_error`; demo keeps Doc 4 lenient behavior. Full state machine/sweeper/outbox remains pilot scope. |
| 4. No unauthenticated static media | ✳️ Partial | Resolved by GPT's own rule: demo runs synthetic/non-PHI only (C13), so capability-URLs expose nothing. Authed-Coil / refresh-URL design = pilot phase with the Android change (C6). |
| 5. No silent mock fallback; model wording | ✅ Accepted | C9 + §4.9: `auto` deleted, `EYE_MODE` enforcement, `503 model_unavailable`, digest-verified artifacts; MIT model relabeled demo/research candidate. |
| 6. Quality heuristic is demo-only | ✳️ Partial | Labeled demo-grade; engine-spy regression test added (§5-C). Validated multi-property QualityEngine = the Doc 3 weeks-4–8 roadmap it always was; the heuristic is literally Doc 4's specified requirement. |
| 7. Upload streaming + extension bug | ✅ Accepted | C11: chunked read with cap before buffering; `sniff_ext` magic bytes; true extension stored (§5-C steps 2–3, storage spec). |
| 8. 20-table Postgres/Alembic/RLS now | ❌ Rejected as P0 | Doc 4 mandates SQLite→Postgres path; schema is portable by construction; tenancy/consent/outbox serve actors that don't exist yet. Conceded: append-only `audit_log` (§5-B) + collision-retry for patient codes. |
| 9. Encounters + DME model | ❌ Deferred | Pilot data model; `patient_id`+`eye` already give bilateral linkage (how the app's own symmetry feature works). |
| 10. HEAD / + live/ready endpoints | ✅ ACCEPTED in v4 | Premise now TRUE at HEAD: `ApiClient.ping()` sends HEAD to the base URL (`ApiClient.kt:61-64`); any HTTP response counts as online. `HEAD /` → 204 is required and unauthenticated (C16). |
| 11. Error model: keep detail, add code/request_id | ✳️ Partial | `request_id` added additively; `error` IS the stable code (frozen envelope kept); `503 model_unavailable` + `500 persistence_error` added. 429/rate-limit deferred. |
| 12. Android PHI before real data | ✅ Accepted | C13 framing adopted: demo = synthetic/non-PHI only until C8 Android items land. |
| 13. requirements.txt syntax / index risk | ✅ Accepted | §4.1 rewritten: one-per-line + separate pinned-index torch file. |
| 14. Docker wiring (admin missing; unused MinIO) | ✅ Accepted | §5-D D1: `COPY app/ admin/ scripts/`; MinIO removed until an S3 adapter uses it; healthcheck on `/health/ready`. |
| 15. Git authorization; env mismatch; worktrees-after-kit | ✳️ Partial | `git status` first + explicit authorization note (§2); G3 sources `.env` (§6). "Kit before worktrees" was already the v2 design — not a correction. |
| 16. Mock determinism; unowned perf test; synthetic ≠ model evidence | ✅ Accepted | Intensity-band mock (§4.5) + matching fixtures/smoke; perf test assigned to Agent C; grade assertions require real labeled samples or skip (§5-A). |
| 17–18. Test matrix / clinical validation separation | ✳️ Convergent | Demo-scope subset implemented (§5, §6); pilot-scope items tracked in C7; clinical validation gate unchanged from v1 (patient-level splits, measured ≥90% sensitivity target, locked datasets outside CI). |

---

## 9. Client evidence appendix — verified at repo HEAD `f6e4a0c` (2026-08-09)

The repository advanced during the review rounds. My earlier retry/HEAD
rejections were verified against `0b90402` (HEAD at clone time, 09:19 +05);
commit `3679077` — *"Add network reliability: HTTP error mapping, retry,
cancel, upload progress, health check"* — landed 48 minutes later and changed
the facts. The external reviewer audited the newer commit and was right.
Lesson encoded here: **re-fetch before every audit claim; a depth-1 clone is a
snapshot, not the repo.**

Verified at `f6e4a0c` (all reachable from `3679077` unless noted):

| Claim | Evidence |
|---|---|
| Retry resends the same payload | `ScreeningViewModel.kt:44-46` (`Error.canRetry` documented as "source file/URI still exists"), `:150` (`fun retry()`), `:195` (file deleted only after successful `doRequest`), `:200`/`:235` (`canRetry = true` on failure) |
| UI triggers real retry | `MainActivity.kt:140-141` — `if (s is UiState.Error && s.canRetry) vm.retry()` |
| Test pins the behavior | `ScreeningViewModelTest.kt:167` — *"uploadFile keeps the temp file when the request fails, so retry can resend it"*; `:176` asserts the temp file survives |
| HEAD health ping | `ApiClient.kt:59-65` — `ping()` sends `HEAD` to `baseUrl`; ANY HTTP response (even an error code) counts as online; only a network exception counts as offline |
| Health polling in UI | `ScreeningViewModel.kt:89-106` (`backendOnline: StateFlow<Boolean?>`, `checkBackendHealth()`), `PatientScreen.kt:41-42,66-69` — optimistic `true` only while the first check is pending (`backendOnline ?: true`) |
| Error `detail` is displayed | `ScreeningViewModel.kt:323-329` — `friendly()` parses `errorBody` JSON and shows `optString("detail")`; an array-valued `detail` silently degrades to the generic message |
| Uploads compressed client-side | commit `a6abc0b` — `BitmapLoader.compressForUpload` (+ unit tests in `f6e4a0c`) |
| No idempotency header exists yet | grep over `app/src/main` at `f6e4a0c`: zero matches for `Idempotency` — hence the C14 fingerprint design that needs no client change |

Corrections I accept beyond the retry/HEAD reversal: `patient_id + eye` is a
**linkage**, not an encounter identifier — it can pair images from different
visits (the app's own symmetry feature shares this caveat per its `PLAN.md`);
the encounters model stays at pilot with that corrected justification.
"SQLite → PostgreSQL" is code-portable by construction here, but the migration
**event** is not a URL flip: it requires an Alembic baseline, a data
migration, and the integration suite re-run against real PostgreSQL — that is
an explicit pilot gate. The canonical nullable response schema
(`PredictResponseV2`, UNGRADABLE fields null) is defined as an **unrouted
stub** next to the active legacy serializer and activates only together with
the Android nullability patch at pilot; the non-null placeholders are a
versioned compatibility surface, not the permanent contract.
