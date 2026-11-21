# Migration plan — Claude vision engine + Vercel deployment

Status: Phase 0 done, ready for Phase 1 · Owner: backend · Date: 2026-11-21

> **§12 (Phase 0 decisions) overrides §3.3, §3.6, §3.8, §3.10, §4 and §6 where they differ.**

## 0. Goal and scope

Replace the PyTorch / ONNX / Grad-CAM inference layer with Claude vision
(Anthropic API) for `POST /api/v1/predict`, and make the backend run on
Vercel. Keep every layer that carries a safety rule, the wire contract, and
the test suite's guarantees.

**In scope:** Phases 0–4 below (`/predict`, `/predict/async`, storage,
database, deploy, accuracy eval).
**Later (Phase 5, not now):** `/api/v1/analyze` (external eye, skin, oral,
nail) through Claude.
**Out of scope for backend:** Android changes (listed in §10 for the app
developer).

Success = the app works unchanged against the Vercel URL; every existing
contract test still passes (except the listed ones that legitimately change);
and the Phase 4 eval report exists. Clinical use additionally needs the eval
pass bar in §8 and the ophthalmologist's sign-off.

---

## 1. Current state (audited)

- Wire contract: `app/schemas.py` — 15 legacy keys plus `request_id`, `mode`.
  The app (`composeApp`, kotlinx.serialization with `ignoreUnknownKeys`)
  matches it.
- `EYE_MODE=demo` uses `mock_engine.py`: grade from image brightness
  (mean gray ≥ 140 → 4, ≥ 120 → 2, else 0). **No demo result so far was a
  real analysis.**
- Real engines (`torch_engine.py`, `onnx_engine.py`) need weights that are
  not in the repo. Grad-CAM is a radial gradient in demo mode.
- **The app calls `POST /api/v1/predict/async`** and polls
  `GET /api/v1/predict/status/{task_id}` every 2 s for up to 120 s. The async
  path uses a Celery worker (`app/worker.py`).
- Storage: `./storage/images`, `./storage/heatmaps`, served unauthenticated
  at `/static/...`. Database: SQLite by default, Postgres supported.
- Test suite: 130 contract, 49 integration, 78 unit, 4 perf, 18 frozen-kit.

## 2. Issues to fix during the migration

| # | Sev | Finding | Fix (phase) |
|---|---|---|---|
| 1 | High | Demo verdicts are a brightness rule | Claude engine (2); mock stays as test double |
| 2 | High | App uses `/predict/async`; Vercel runs no Celery worker | Run inline, return a `replay:` task (3) |
| 3 | High | `create_app()` creates `./storage` and mounts `/static` at import; read-only FS on Vercel | Blob adapter; local-only mounts (3) |
| 4 | High | Offline TFLite model in the app shows green results; origin and accuracy unknown | Android (§10) |
| 5 | Med | `QUALITY_BLUR_MIN_VAR` default 50 rejects 64% of sharp real fundus photos (team's IDRiD measurement in `.env.example`) | Set 8 in every real deployment (3) |
| 6 | Med | Status poll may hit a different serverless instance | Shared Postgres mandatory on Vercel (3) |
| 7 | Med | Providers give `postgres://`; SQLAlchemy 2 needs `postgresql+psycopg://`; default pool too big for serverless | Rewrite scheme; small pool (3) |
| 8 | Med | Empty `EYE_API_KEY` disables auth with only a warning | Refuse to boot in shadow without it (2) |
| 9 | Med | Rate limit keyed by connection IP; behind Vercel's proxy this may be one IP | Check after deploy; use `X-Forwarded-For` if needed (3) |
| 10 | Low | `/predict/async` dedup lookup lacks `/predict`'s try/except | Copy it (3) |
| 11 | Low | `scripts/smoke_test.sh` expects mock verdicts | Add a Claude smoke script (3) |
| 12 | Low | Fake heatmap in demo mode | Delete; `heatmap_url = null` (1) |

---

## 3. Target design

### 3.1 Request flow (`POST /api/v1/predict`, step numbers as in `predict.py`)

| Step | Status | Notes |
|---|---|---|
| 1–3 validate, capped read, decode | kept | |
| 3c model gate | kept | Claude: `model_loaded = bool(ANTHROPIC_API_KEY)` |
| 3b dedup / replay | kept | replay → zero Claude calls |
| 4 save original | changed | Blob on Vercel, local disk otherwise |
| 5 quality gate | kept | fail → UNGRADABLE, zero Claude calls |
| 6 inference | **replaced** | `wants_jpeg` engines get JPEG bytes and are awaited |
| 7 decision | changed | `decide_from_assessment()` for Claude |
| 8 heatmap | **deleted** | `heatmap_url = None` |
| 9–10 patient code, persist | changed | + `assessment_json` column; Postgres on Vercel |
| 11 respond | changed | `/predict/async` returns a `replay:` task |

### 3.2 Config (`app/config.py`)

- `eye_model_source: Literal["mock", "torch", "claude"]`. `onnx` is removed in
  Phase 1; `claude` is added in Phase 2. **`torch` stays as a legacy value**:
  its engine file is deleted, so `get_engine()` already returns
  `UnavailableEngine` for it (503 everywhere). It must stay because the frozen
  `tests/test_frozen_kit.py::test_shadow_mode_requires_a_digest` pins the
  shadow + torch + SHA-256 rule, and the shadow fixtures in
  `test_model_unavailable.py` / `test_audit_regressions.py` use it to prove
  "no model → 503".
- New fields: `anthropic_api_key` (`ANTHROPIC_API_KEY`, optional),
  `claude_model` (`CLAUDE_MODEL`, default `claude-sonnet-5-5`),
  `claude_timeout_s` (`CLAUDE_TIMEOUT_S`, default 25.0),
  `claude_max_tokens` (`CLAUDE_MAX_TOKENS`, default 800),
  `prompt_version` (`PROMPT_VERSION`, default `v1`),
  `uncertain_refers` (`UNCERTAIN_REFERS`, default true),
  `eye_storage` (`EYE_STORAGE`, `local` | `blob`, default `local`) — Phase 3.
- Remove `eye_model_sha256`, `eye_device`, `engine_input_size` only if nothing
  else reads them; otherwise leave them (harmless).
- Mode validator (keep the existing checks, add the claude ones):
  - `shadow` + `mock` → refuse to boot, message contains "shadow" (frozen test).
  - `shadow` + `torch` without `EYE_MODEL_SHA256` → refuse to boot, message
    contains "SHA256" (frozen test). Unchanged.
  - `shadow` + `claude` requires a non-empty `EYE_API_KEY` → else refuse to
    boot (issue 8).
  - A missing `ANTHROPIC_API_KEY` does **not** refuse boot: it is a runtime
    condition, `model_loaded = False` → 503 `model_unavailable`, readiness 503
    — the same behaviour a missing checkpoint has today.
  - `demo` keeps `mock`; `demo` + `claude` is allowed for local trials, and
    responses then carry `mode="demo"`.
- `database_url`: rewrite a leading `postgres://` or `postgresql://` to
  `postgresql+psycopg://` (Phase 3).

### 3.3 Engine (`app/inference/claude_engine.py`, new)

```python
class ClaudeEngine:
    wants_jpeg = True
    def __init__(self, settings, client=None): ...   # client injectable for tests
    @property
    def model_loaded(self) -> bool: ...               # bool(settings.anthropic_api_key)
    @property
    def model_version(self) -> str: ...               # f"{claude_model}/prompt-{prompt_version}"
    async def assess(self, jpeg: bytes) -> ClaudePrediction: ...
```

- `get_engine()` returns it for `EYE_MODEL_SOURCE=claude`.
- `assess()` sends one user message: an image block (base64 JPEG) plus a short
  text instruction; system prompt = `app/inference/prompts/fundus_<PROMPT_VERSION>.md`
  loaded once, with its leading `<!-- ... -->` header comment stripped. A
  missing prompt file is a boot error, not a runtime fallback. Uses `messages.parse(..., output_format=FundusAssessment)`,
  `max_tokens=CLAUDE_MAX_TOKENS`, timeout `CLAUDE_TIMEOUT_S`, `max_retries=0`.
- Image prep: if the long side > 1568 px, resize with Pillow (keep aspect) and
  re-encode JPEG quality 90; otherwise send the uploaded bytes unchanged.
  PNG uploads are re-encoded to JPEG.
- Validate the parsed output locally: lower-case enum strings; `icdr_grade`
  in 0..4; `referable_probability` in 0..1. Anything else raises.
- Any SDK exception, timeout or validation failure propagates; `predict.py`
  maps it to 500 `inference_error`. **No fallback verdict.**
- Never put `patient_id`, `eye` or any request metadata into the request.

```python
class ClaudePrediction(TypedDict):     # app/inference/engine.py, additive
    assessment: "FundusAssessment"
    model_version: str
```

### 3.4 Output schema (`app/inference/assessment.py`, new)

```python
from typing import Literal
from pydantic import BaseModel

Presence = Literal["present", "absent", "uncertain"]
QualityIssue = Literal["blur", "too_dark", "overexposed", "small_field", "obstruction"]

class Lesions(BaseModel):
    microaneurysms: Presence
    retinal_hemorrhages: Presence
    hard_exudates: Presence
    cotton_wool_spots: Presence
    venous_beading: Presence
    irma: Presence
    neovascularization: Presence
    preretinal_or_vitreous_hemorrhage: Presence

class FundusAssessment(BaseModel):
    image_type: Literal["fundus", "external_eye", "other"]
    gradable: bool
    quality_issues: list[QualityIssue]
    lesions: Lesions
    hemorrhages_in_all_4_quadrants: bool
    macular_edema_signs: Presence
    icdr_grade: int                 # 0..4, checked locally
    referable_probability: float    # 0..1, checked locally
    rationale: str                  # max 2 sentences; logs/admin only
```

### 3.5 Decision (`decide_from_assessment()` in `app/inference/decision.py`, additive)

Signature: `decide_from_assessment(a: FundusAssessment | None, quality_ok: bool,
threshold: float, uncertain_refers: bool) -> DecisionResult`.

1. `quality_ok` is False or `a` is None → return exactly what `decide(None, False, threshold)`
   returns today.
2. `a.image_type != "fundus"` → UNGRADABLE, quality `poor`, decision_text
   `"Bu ko'z tubi (fundus) rasmi emas — fundus kamera yoki adapter bilan oling"`.
3. `a.gradable` is False → UNGRADABLE, quality `poor`, decision_text
   `"Baholab bo'lmadi: <reasons> — qayta suratga oling"`, reasons from
   `quality_issues`: blur → "rasm xira", too_dark → "juda qorong'i",
   overexposed → "juda yorug'", small_field → "ko'z tubi to'liq ko'rinmaydi",
   obstruction → "to'siq bor" (joined with ", "; generic
   `"Sifatsiz rasm — qayta suratga oling"` when the list is empty).
4. Rule grade from lesions (`present` only):
   neovascularization or preretinal_or_vitreous_hemorrhage → 4;
   venous_beading or irma or hemorrhages_in_all_4_quadrants → 3;
   retinal_hemorrhages or hard_exudates or cotton_wool_spots → 2;
   microaneurysms → 1; else 0.
5. `final_grade = max(a.icdr_grade, rule_grade)`.
6. Refer if any of: `final_grade >= 2`; `macular_edema_signs` is `present` or
   `uncertain`; `uncertain_refers` and any of the grade-≥2 lesions
   (retinal_hemorrhages, hard_exudates, cotton_wool_spots, venous_beading,
   irma, neovascularization, preretinal_or_vitreous_hemorrhage) is `uncertain`.
7. `probability = round(a.referable_probability, 4)`, then clamped:
   REFER → `max(p, threshold)`; NO_REFER →
   `max(0.0, min(p, round(threshold - 0.0001, 4)))` (strictly below the
   threshold, never negative).
8. Texts and labels reuse today's: `GRADE_LABELS[final_grade]`,
   `"Referable DR — oftalmologga yuboring"` /
   `"Referable DR aniqlanmadi — 12 oydan keyin qayta tekshiruv"`, quality `good`.
9. C3: UNGRADABLE → wire `probability=0.0`, `icdr_grade=0`,
   `grade_label="Baholab bo'lmadi"`; `db_probability=None`, `db_icdr_grade=None`.

Note: if REFER came only from rule 6's edema/uncertain clauses while
`final_grade < 2`, the wire still shows `final_grade` (e.g. 1) with REFER —
intended and documented; the decision field is what the app colours.

(Uzbek wording: the team checks it once; then it is fixed by tests.)

### 3.6 `predict.py` changes

- Step 6: `if getattr(engine, "wants_jpeg", False): pred = await engine.assess(raw)`
  inside `async with semaphore_for(request.app)`; otherwise the existing tensor
  path. Same exception mapping as today.
- Step 7: `decide_from_assessment(...)` when `pred` carries `"assessment"`,
  else the existing `decide(...)`.
- Step 8: removed; `heatmap_url = None`.
- Step 10: persist `assessment_json = assessment.model_dump_json()` (nullable
  `Text` column on the result row; `None` for mock and UNGRADABLE-by-gate).
  `model_version` = engine's `model_version` when Claude.
- Extract steps 1–11 into `async def run_screening(...) -> PredictResponse`
  shared by `/predict` and `/predict/async` (Phase 3).

### 3.7 `/predict/async` on Vercel (Phase 3)

Run `run_screening()` inline, then return
`TaskResponse(task_id=f"replay:{exam_id}", status="PROCESSING",
message="Rasm tahlil qilindi, natija tayyorlanmoqda...")`.
The existing `GET /predict/status/replay:<id>` loads the exam from the database
and returns `SUCCESS`. The first status **must** be `PENDING` or `PROCESSING`:
the app's polling loop throws on any other first status. Errors are raised as
HTTP errors immediately (the app shows `detail`). Delete `app/worker.py` and
the Celery branch of the status endpoint.

### 3.8 Storage (Phase 3)

- `app/storage/blob.py`: `save_original(raw: bytes, exam_id: str) -> tuple[str, str]`
  uploads `images/<exam_id><ext>` to Vercel Blob with public access and a random
  suffix, returns `(pathname, absolute_url)`. Uses the `vercel` package's Blob
  client (reads `BLOB_READ_WRITE_TOKEN`). Same `sniff_ext` and `_checked_id`
  guards as `local.py`.
- `app/storage/__init__.py` (or a small selector) picks `local` or `blob` by
  `EYE_STORAGE`. Callers keep using `storage.save_original` and
  `storage.sniff_ext`.
- `main.py`: `ensure_dirs()` and both `/static/...` mounts only when
  `EYE_STORAGE=local`; readiness `_storage_ok()` checks the Blob token instead
  of writing a probe file when `blob`.
- The app already treats absolute `http(s)` URLs as-is.

### 3.9 Database (Phase 3)

Postgres via `DATABASE_URL` (pooled URL from the provider). Scheme rewrite in
config (§3.2). For Postgres: `pool_size=2, max_overflow=2, pool_pre_ping=True`
unless the provider's docs say otherwise. `init_db()` creates tables on start.
New nullable column `assessment_json` (Text) on the result table.

### 3.10 Requirements (Phase 1)

- `requirements.txt` (production only): fastapi, uvicorn[standard],
  python-multipart, pydantic-settings, sqlalchemy, pillow, numpy==1.26.*,
  opencv-python-headless, psycopg[binary], anthropic (Phase 2),
  vercel (Phase 3).
- `requirements-dev.txt`: `-r requirements.txt` + pytest, pytest-asyncio,
  httpx, requests, ruff, mypy.
- `requirements-admin.txt`: streamlit (admin panel, run locally).
- Delete `requirements-torch.txt`. Remove onnx, onnxruntime, timm, grad-cam,
  huggingface_hub, celery, pika, redis, torch, torchvision everywhere.

### 3.11 Vercel files (Phase 3)

- `backend/.python-version` → `3.12` (Vercel default; numpy 1.26 has no wheels
  for 3.13+).
- `backend/vercel.json` → `{"functions": {"app/main.py": {"maxDuration": 60}}}`.
- Vercel project Root Directory = `backend`. `app/main.py` exports `app`.
- Env vars: see `backend/.env.vercel.example`.

---

## 4. Tests that legitimately change

| File | Change | Phase |
|---|---|---|
| `tests/unit/test_torch_engine.py` | delete | 1 |
| `tests/unit/test_gradcam.py` | delete | 1 |
| `tests/contract/test_static_serving.py` | REFER no longer has a heatmap: assert `heatmap_url is None`; keep the image assertions | 1 |
| `tests/perf/test_latency.py` | drop torch-specific cases if any (perf is excluded by default) | 1 |
| `tests/integration/test_predict_async.py` | Celery eager mode → inline: POST returns `replay:<id>` + PROCESSING; status returns SUCCESS with the same exam | 3 |

**Expected to keep passing unchanged** (good regression guards):
`tests/test_frozen_kit.py` (shadow + mock / shadow + torch rules),
`tests/contract/test_model_unavailable.py` and
`tests/contract/test_audit_regressions.py` (their shadow + torch fixtures now
always get `UnavailableEngine`, so "no model → 503" stays pinned).
`tests/contract/_shim.py` builds a stub for a missing
`app.inference.gradcam`; harmless once `predict.py` stops importing it.

Phase 0 confirms this list by grep and adds anything missed, with reasons.

## 5. New tests

| File | Covers | Phase |
|---|---|---|
| `tests/unit/test_decision_claude.py` | every rule in §3.5, table-driven; C3 split; probability clamp both sides; Uzbek texts | 2 |
| `tests/unit/test_claude_engine.py` | fake client: request has one image block + text, schema attached, model from env, no `patient_id`/`eye` anywhere in the request; >1568 px is resized; PNG → JPEG; SDK error → raises; timeout → raises; bad enum/number → raises; `model_loaded` false without key | 2 |
| `tests/contract/test_claude_wiring.py` | app with a fake Claude engine: quality-gate failure → 0 calls; dedup replay → 0 calls; engine error → 500 `inference_error` and nothing persisted; non-fundus → UNGRADABLE with the fundus text; `assessment_json` stored; response keys == LEGACY_KEYS + `request_id`, `mode` | 2 |
| `tests/unit/test_config_claude.py` | shadow + claude without `EYE_API_KEY` → boot error; shadow + claude without Anthropic key → boots, `/predict` and `/health/ready` 503, `/health/live` 200; postgres URL rewrite (Phase 3) | 2–3 |
| `tests/integration/test_storage_switch.py` | `EYE_STORAGE=blob` with a fake Blob client: absolute URL returned, no local dirs created, no `/static` mounts | 3 |
| `tests/integration/test_postgres_async.py` | async → status round trip on a real Postgres (Docker), marked `postgres`, run manually | 3 |

Fakes live in `tests/fakes/`. No test calls the real Anthropic or Blob APIs.

---

## 6. Phases and done criteria

**Phase 0 — baseline (no code changes).** Branch, venv, run lint/types/suite,
record exact counts in `docs/NOTES.md`, confirm §4, map where each later edit
lands. Done: NOTES.md has the baseline and the confirmed list.

**Phase 1 — delete model code.** Delete `app/inference/torch_engine.py`,
`onnx_engine.py`, `gradcam.py`, `scripts/download_model.py`,
`scripts/export_onnx.py`, `requirements-torch.txt`; remove the onnx branch
from `engine.get_engine` and `onnx` from config (keep the `torch` value and
branch — it now always yields `UnavailableEngine`, see §3.2); remove step 8;
trim requirements (§3.10);
update the Dockerfile and CI install lines to match. Keep `app/worker.py` until
Phase 3 (its test still runs). Done: `ruff check app tests && mypy app` and the
default suite pass; count = baseline − deleted tests ± the listed changes.

**Phase 2 — Claude engine.** §3.2–3.6 except storage/async. Tests first (§5,
Phase 2 rows). Done: lint, types, suite pass; then a manual
run with a real key (§7 layer 6 images, run locally) prints the expected
decisions; NOTES.md records latency and tokens per image.

**Phase 3 — Vercel.** §3.6 `run_screening`, §3.7–3.11, issues 7, 9, 10, 11.
Tests first. Done: lint, types, suite pass; `vercel deploy` succeeds; the
Claude smoke script passes against the deployed URL.

**Phase 4 — accuracy eval.** `eval/run_claude_eval.py`, adapted from
`training/eval_backend_dr.py`: runs the backend's own path
(load → quality gate → Claude → decide_from_assessment) on a labelled CSV
(`image_path, icdr_grade, patient_id, split`). Reports, per model: sensitivity
and specificity for referable DR (grade ≥ 2) with Wilson 95% CIs; confusion
matrix; ungradable rate; non-fundus rejection rate (separate folder of phone
eye photos); p50/p95 latency; tokens and cost per scan. Writes
`eval/results/<date>-<model>-<prompt>.json`. Done: report for Sonnet 5.5 (and
Opus 5.5 if requested). No threshold or rule change without the ophthalmologist.

## 7. Verification layers

1. `ruff check app tests && mypy app` — 0 errors.
2. Default suite on the mock — same count as baseline minus listed deletions.
3. Claude unit tests with a fake client — all rules covered.
4. Call counts — 0 Claude calls on gate failure and on dedup replay.
5. Async path on Postgres — same `exam_id` and verdict from POST and status.
6. Live smoke on the deployed URL — `/health`; wrong key → 401; 5 MB → 413;
   one referable public fundus image → REFER; one normal → NO_REFER; one phone
   photo of an eye → UNGRADABLE (fundus text); one blurred image → UNGRADABLE
   with no tokens logged.
7. Accuracy eval — pass bar in §8.
8. Phone end to end — gallery fundus → red/green; camera eye photo → grey;
   airplane mode → queued; admin panel shows the exam and its assessment.
9. Production monitoring — one log line per exam; weekly ophthalmologist review
   of every REFER and a sample of NO_REFER.

## 8. Accuracy pass bar

On held-out labelled fundus images (≥ 100 referable, ≥ 100 non-referable;
both eyes of a patient on the same side of any split):
sensitivity ≥ 90% and specificity ≥ 80% for referable DR; 100% of non-fundus
photos UNGRADABLE. Until then, results are decision support only and every
result is confirmed by an ophthalmologist.

## 9. Reviewer checklist

- Response keys == `schemas.LEGACY_KEYS` + `request_id`, `mode`; types unchanged.
- `git diff <base> -- tests/` is empty in implementation commits; test commits
  touch only the files §4/§5 allow.
- No code path returns NO_REFER after an exception; no fallback verdict.
- Zero Claude calls before the quality gate and on replay.
- No patient data in any Claude request; no key, image bytes or patient ID in logs.
- Secrets only from env; `.env` not committed.
- `PROMPT_VERSION` bumped whenever the prompt file changes; `model_version`
  reflects model and prompt.
- Frozen files unchanged (`git diff <base> -- app/schemas.py app/analysis/schemas.py
  app/core/errors.py app/inference/mock_engine.py tests/conftest.py
  tests/test_frozen_kit.py tests/fixtures/golden_predict.json` is empty).

## 10. For the Android developer (not backend work)

- Offline `dr_model.tflite`: origin and accuracy unknown; refers at grade > 0
  while the server refers at ≥ 2. Until validated, offline mode shows
  "queued for server check", never a green NO_REFER.
- Release URL: `RELEASE_API_URL=https://<project>.vercel.app/` in
  `local.properties`; `API_KEY` = the backend's `EYE_API_KEY`.
- `quality` is shown raw (`good` / `poor`); map it to Uzbek strings.
- The heatmap card shows nothing when `heatmap_url` is null — expected now.

## 11. Phase 5 (later): `/analyze` through Claude

Same pattern: a Claude analyzer returns a score per catalogue condition
(in `catalog.py` order) plus `image_matches_type`; mismatch →
`risk_level="ungradable"`; keep `overall_risk()` and the 0.30 high-risk
escalation; `is_demo=false`. Skin and nail include melanoma suspicion — start
only after DR passes §8, and evaluate the same way.

## 12. Phase 0 decisions (approved 2026-11-21)

The evidence for each decision is in `docs/NOTES.md`, under "Edit map", in the
conflicts list.

1. **`app/worker.py` (Phase 1).** Step 8 calls `predict._render_heatmap`, so
   Phase 1 changes it to `heatmap_url = None` in the worker too. No other
   worker change; the file is deleted in Phase 3 as planned.
2. **`onnxruntime` stays until Phase 5** (overrides §3.10).
   `app/analysis/analyzer.py` `OnnxAnalyzer` serves the real skin model
   (`models/analysis/skin.onnx`) through it. Phase 1 still removes `onnx`,
   `timm`, `grad-cam`, `huggingface_hub`, `torch` and `torchvision`.
3. **Engine return type** (§3.3). `get_engine()` and `deps.engine_for()` are
   annotated `InferenceEngine | ClaudeEngine`, because `InferenceEngine` is a
   Protocol that requires `predict()`, and `ClaudeEngine` only has `assess()`.
4. **Mode validator** (§3.2, unchanged intent). In `Settings._enforce_mode()`:
   shadow refuses `mock` (the message contains "shadow"); `EYE_MODEL_SHA256`
   is required only when the source is `torch` (the message contains
   "SHA256"); shadow + `claude` requires a non-empty `EYE_API_KEY`.
5. **`assessment_json` persistence** (§3.6). `crud.create_exam_with_result()`
   gains one optional kwarg, `assessment_json: str | None = None`. Since
   `init_db()` uses `create_all`, which never alters an existing table, local
   `eye.db` files must be recreated after the column is added. Vercel's
   Postgres starts empty.
6. **Storage return type** (§3.8). The selector's `save_original()` returns
   `tuple[Path | str, str]` (local returns a `Path`, Blob a `str`). Callers
   use only the URL.

**Test list additions** (extends §4).

| File | Change | Phase |
|---|---|---|
| `tests/integration/test_static_serving.py::test_heatmap_png_is_on_disk` | Assert that no heatmap file is written | 1 |

`storage.ensure_dirs()` keeps creating `heatmaps/`, and the
`/static/heatmaps` mount stays, until Phase 3 makes both local-only. So
`test_startup_creates_both_media_subdirectories` stays unchanged in Phase 1.
`tests/contract/test_analyze.py` (a shadow + `torch` fixture) is another
regression guard that must keep passing unchanged.

**Phase 1 done count** (§6): 277 − 24 − 13 = **240 passed** on the default
suite, with 4 deselected (the `model` tests go away with
`test_torch_engine.py`).
