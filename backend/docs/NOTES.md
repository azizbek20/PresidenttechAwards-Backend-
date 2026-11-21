# Migration notes

Claude Code appends here at the end of every session. Newest entries at the
bottom of each section. Never paste keys or patient data here.

## Baseline

<!-- Phase 0: exact ruff / mypy / pytest results before any change. -->

### 2026-11-21 — Phase 0, at `d339fc5` (kit commit on `main` @ `212f773`)

Environment: macOS arm64, **Python 3.11.18**. `python3.11` was not installed, so a uv-managed CPython 3.11 was used (`uv python install 3.11`), then the CLAUDE.md "BEFORE Phase 1" commands ran verbatim: torch 2.3.1, torchvision 0.18.1, numpy 1.26.4, opencv-python-headless 4.10.0.84. Surprise: `grad-cam` did **not** pull in GUI `opencv-python` this time, so the uninstall step printed "Skipping opencv-python as it is not installed" (harmless).

| Command (from `backend/`) | Exit | Result |
|---|---|---|
| `ruff check app tests` | 0 | `All checks passed!` |
| `mypy app` | 0 | `Success: no issues found in 35 source files` (note: `mypy.ini: unused section(s): [mypy-tests.*]`) |
| `EYE_MODE=demo pytest -q -m "not model and not perf"` | 0 | `277 passed, 7 deselected in 50.62s` |

**Failures: 0. Errors: 0. Skipped: 0.** The 7 deselected are the 4 `perf` tests in `tests/perf/test_latency.py` and 3 `model` tests in `tests/unit/test_torch_engine.py`.

Collected (all markers): **284** = contract 133, integration 49, unit 80, perf 4, frozen-kit 18. Plan §1 says 130 contract and 78 unit, but the code has **133 and 80**. The other three directories match.

Expected default count after Phase 1: 277 − 24 (`test_torch_engine.py`, default-selected) − 13 (`test_gradcam.py`) = **240**, or 239 if `integration/test_static_serving.py::test_heatmap_png_is_on_disk` is deleted rather than changed (see Test impact). `contract/test_static_serving.py` (7) changes assertions only, so its count holds.

## Test impact

<!-- Phase 0: confirmed list of tests that change, with reasons. -->

### 2026-11-21 — Phase 0, confirmed by grep of `tests/`

Patterns searched: `torch`, `gradcam|grad_cam`, `onnx`, `heatmap`,
`celery|worker|apply_async|eager`, `download_model|export_onnx`, `EYE_DEVICE`,
`EYE_MODEL_SHA256`, `EYE_INPUT_SIZE`, `static/heatmaps|heatmaps_dir`,
`EYE_MODEL_SOURCE`.

**§4 list: confirmed.**

| File | Confirmed by | Phase |
|---|---|---|
| `tests/unit/test_torch_engine.py` (delete) | imports `app.inference.torch_engine`, sets `EYE_INPUT_SIZE`/`EYE_DEVICE` | 1 |
| `tests/unit/test_gradcam.py` (delete) | imports `app.inference.gradcam` | 1 |
| `tests/contract/test_static_serving.py` | `test_heatmap_url_serves_a_png` asserts a truthy `heatmap_url` (L42–44) and `== /static/heatmaps/<id>.png` (L53) | 1 |
| `tests/perf/test_latency.py` | **no torch-specific cases**: "torch" and "heatmap" appear only in comments/docstrings (L6, L115). Nothing to change | 1 (no-op) |
| `tests/integration/test_predict_async.py` | `eager` fixture imports `app.worker.celery_app` and sets `task_always_eager` (L21–31) | 3 |

**Missed by §4: add these.**

| File / test | Why it changes | Phase |
|---|---|---|
| `tests/integration/test_static_serving.py::test_heatmap_png_is_on_disk` (L51–54) | Asserts `storage/heatmaps/<exam_id>.png` exists and is a PNG. Removing step 8 means no file is written, so it fails. Change to "no heatmap file is written" or delete | 1 |
| `tests/integration/test_static_serving.py::test_startup_creates_both_media_subdirectories` (L37–40) | Asserts `storage/heatmaps` is a directory. Passes only while `storage.ensure_dirs()` still creates it. Either keep creating the dir (and the `/static/heatmaps` mount) through Phase 3, or change the assertion in the same test-only commit as above | 1 or 3 |

**Expected to keep passing unchanged. Confirmed, plus one more.**

- Listed in §4, confirmed: `tests/test_frozen_kit.py` (L185–197 shadow+mock → `match="shadow"`, shadow+torch without digest → `match="SHA256"`), `tests/contract/test_model_unavailable.py`, `tests/contract/test_audit_regressions.py`.
- **Not listed in §4:** `tests/contract/test_analyze.py::shadow_client` (L148–159) uses shadow + `torch` + a dummy SHA to prove `/analyze` is 503 without a model. It is another reason the legacy `torch` value must stay.
- `tests/test_frozen_kit.py::test_demo_defaults_are_safe` (L204) asserts `s.eye_device == "cpu"`. **`eye_device` must not be removed** (§3.2 allows removal only "if nothing else reads them"; this frozen test reads it).
- Unaffected: `contract/test_auth.py` L84 (heatmap check is conditional), `contract/test_predict_contract.py` L72 (allows `None`), `contract/test_ungradable_wire.py` L41 (already `None`), `integration/test_persistence.py` (writes `heatmap_path` through `crud` directly, which keeps the column), `fixtures/golden_predict.json` (frozen; `heatmap_url` is a string, and `str | None` still validates).

**Watch-out.** `tests/contract/_shim.py` installs a stub `app.inference.gradcam` whenever the real file is absent. Once Phase 1 deletes `gradcam.py`, a forgotten `import app.inference.gradcam` in `predict.py` would still pass the **contract** suite on the stub.

*Correction (Phase 1):* the integration suite does not catch it either. `integration/test_auth.py`, `test_db_failure.py` and `test_static_serving.py` also call `_shim.install()`, the finder lives in `sys.meta_path` for the whole pytest process, and `mypy.ini` sets `ignore_missing_imports = True`. The reliable guard is a plain `python -c "import app.main"` outside pytest, plus a grep.

## Edit map

<!-- Phase 0: files and functions each phase will change; plan-vs-code conflicts. -->

### 2026-11-21 — Phase 0

**Phase 1 (delete model code)**

- Delete `app/inference/torch_engine.py`, `app/inference/onnx_engine.py`, `app/inference/gradcam.py`, `scripts/download_model.py`, `scripts/export_onnx.py` (imports `torch_engine`), `requirements-torch.txt`.
- `app/inference/engine.py` `get_engine()`: drop the `onnx` branch (L97–107) and the "expected mock|torch|onnx" message (L109). Keep the `torch` branch: its `ImportError` path already returns `UnavailableEngine`. The module docstring still says "DO NOT EDIT"; update it to match the kit's CLAUDE.md.
- `app/config.py`: `eye_model_source` Literal drop `"onnx"` (L53). Keep `eye_device` (frozen test reads it), `engine_input_size` (`predict._to_tensor` and `worker.py` L82 read it) and `eye_model_sha256` (validator + frozen test). Update the docstring's Grad-CAM line (L22).
- `app/api/predict.py`: remove `import app.inference.gradcam as heatmaps` (L38) and `_render_heatmap()` (L177–193). Step 8 (L351–358) becomes `heatmap_url = None`. `_persist(heatmap_url=None)` and `wire_response(heatmap_url=None)` keep their signatures.
- `app/worker.py` **(not in CLAUDE.md's editable list, see conflict 1)**: step 8 (L91–96) calls `predict_flow._render_heatmap`. It must become `heatmap_url = None` in Phase 1, or the eager async tests break.
- `app/storage/local.py` `heatmap_target()`: unused after step 8 goes. Delete it, or leave it until Phase 3. `ensure_dirs()` keeps or drops `heatmaps/`, decided together with the two `integration/test_static_serving.py` tests above.
- `requirements.txt`: keep `celery`/`pika`/`redis` (L14–16) until Phase 3, because `app/worker.py` stays until then and imports Celery. Phase 1 removes `onnxruntime`, `onnx`, `timm`, `grad-cam`, `huggingface_hub` (L19–25), see conflict 2. Split out `requirements-admin.txt` (streamlit).
- `Dockerfile` (L30–46, L59, L80–82) and `.github/workflows/backend-ci.yml` (L62–79, L111–122): drop `requirements-torch.txt`, the opencv-fix step and the `import torch, pytorch_grad_cam` smoke.

**Phase 2 (Claude engine)**

- New: `app/inference/claude_engine.py`, `app/inference/assessment.py`. The prompt `app/inference/prompts/fundus_v1.md` is already committed.
- `app/inference/engine.py`: add `ClaudePrediction` TypedDict and the `claude` branch in `get_engine()`. See conflict 3 on the return type.
- `app/config.py`: Literal adds `"claude"`. Add `anthropic_api_key`, `claude_model`, `claude_timeout_s`, `claude_max_tokens`, `prompt_version`, `uncertain_refers`. Restructure `_enforce_mode()` (L87–104), see conflict 4.
- `app/inference/decision.py`: add `decide_from_assessment()` next to the frozen `decide()`. The `GRADE_LABELS` and Uzbek texts are reused as-is.
- `app/api/predict.py` step 6 (L327–346): `wants_jpeg` branch (`await engine.assess(raw)` inside `semaphore_for`). The tensor path stays for the mock. Step 7 (L349): pick `decide_from_assessment` when `"assessment" in pred`. Step 10 (L364–381): `model_version` from the engine, pass `assessment_json`, see conflict 5.
- `app/db/models.py` `Result` (L186–218): add `assessment_json: Mapped[str | None] = mapped_column(Text, nullable=True)`. `model_version` is `String(64)`, and `"claude-sonnet-5-5/prompt-v1"` (27 chars) fits.
- `app/api/deps.py` `engine_for()` (L36–47): return type follows conflict 3. No other change.

**Phase 3 (Vercel)**

- `app/api/predict.py`: extract steps 1–11 into `run_screening()`. `predict_async()` (L435–491) runs it inline and returns `replay:<exam_id>` + `PROCESSING`. Its dedup lookup (L464–471) has no try/except: issue 10 confirmed. `get_predict_status()` drops the Celery branch (L514–530). The replay branch (L498–512) already exists and returns `SUCCESS`.
- Delete `app/worker.py`. Remove `celery`, `pika`, `redis` from requirements.
- New `app/storage/blob.py` plus a selector in `app/storage/__init__.py`. See conflict 6 on the return type.
- `app/main.py`: `create_app()` calls `storage.ensure_dirs()` at import (L108) and `app = create_app()` runs at import (L228), confirming issue 3. `lifespan()` also calls `ensure_dirs()` (L56). `_storage_ok()` (L84–94) writes a probe. The `/static/images` and `/static/heatmaps` mounts are at L213–222. All of these get gated on `EYE_STORAGE=local`.
- `app/config.py`: `eye_storage`, plus a `database_url` scheme-rewrite validator.
- `app/db/base.py` `_build()` (L41–46): `create_engine(url, connect_args=..., pool_pre_ping=True)`. Add `pool_size=2, max_overflow=2` for Postgres only (SQLite's pool rejects those kwargs).
- New: `backend/.python-version`, `backend/vercel.json`, a Claude smoke script beside `scripts/smoke_test.sh`.

**Plan-vs-code conflicts (need a decision before the phase starts)**

1. **`app/worker.py` must change in Phase 1.** It reuses `predict._render_heatmap` (worker L95), but CLAUDE.md's "Unfrozen" list omits `app/worker.py`. Proposal: allow a Phase 1 edit to step 8 there (`heatmap_url = None`).
2. **`onnxruntime` is still used by `/analyze`.** `app/analysis/analyzer.py` `OnnxAnalyzer` (L110–123) lazy-imports `onnxruntime` to serve the real skin model (`models/analysis/skin.onnx`, per `training/README.md`). §3.10 removes `onnxruntime` "everywhere" in Phase 1, but `/analyze` is Phase 5 scope. After removal, a deployment with `skin.onnx` loses the real skin model: shadow gets 503 via the `except` at analyzer L161, and demo falls back to the mock. Decide whether to keep `onnxruntime` until Phase 5 or accept that loss.
3. **`get_engine() -> InferenceEngine`** (engine.py L67, `# frozen signature`). `InferenceEngine` is a Protocol requiring `predict(img) -> Prediction`. `ClaudeEngine` per §3.3 only has `assess()`, so returning it fails mypy. Options: a return type `InferenceEngine | ClaudeEngine`, or a `predict()` on `ClaudeEngine` that raises. `deps.engine_for()` has the same annotation.
4. **`Settings._enforce_mode()`** (config.py L87–104) rejects every shadow source except `torch` **and** requires `EYE_MODEL_SHA256` for any shadow source. For shadow + claude, the SHA check must apply only when the source is `torch`, the "requires torch" check becomes "refuses mock" (the frozen test only needs `"shadow"` in the message), and the new `EYE_API_KEY` check is added. This matches §3.2's intent. Flagged because the file header still says "Frozen … DO NOT EDIT".
5. **`assessment_json` cannot reach the database without `crud.py`.** `crud.create_exam_with_result()` (crud.py L130–146) has no such parameter, and CLAUDE.md's unfrozen list omits `app/db/crud.py`. It needs an added optional kwarg `assessment_json: str | None = None`. Also, `init_db()` uses `create_all`, which **does not add a column to an existing table**: an existing local `eye.db` (or an earlier Postgres) gets `500 persistence_error` until it is recreated or altered.
6. **Storage return types differ.** `local.save_original()` returns `tuple[Path, str]`, while §3.8 `blob.save_original()` returns `tuple[str, str]`. The selector needs a common type (`tuple[Path | str, str]`, or a Protocol). `predict.py` only uses the URL (`_, image_url = ...`, L315).

**Decisions: all six recommendations approved by the owner on 2026-11-21.** They are binding in `MIGRATION_PLAN.md` §12 and CLAUDE.md.

1. `app/worker.py` gets one Phase 1 edit: step 8 becomes `heatmap_url = None`. Nothing else changes until the file is deleted in Phase 3.
2. Keep `onnxruntime` in `requirements.txt` until Phase 5, so `/analyze` keeps its real skin model. Phase 1 still removes `onnx`, `timm`, `grad-cam`, `huggingface_hub`, torch and torchvision.
3. `get_engine()` and `deps.engine_for()` return `InferenceEngine | ClaudeEngine`.
4. Restructure `Settings._enforce_mode()` as §3.2 describes: shadow refuses `mock` (message contains "shadow"); `EYE_MODEL_SHA256` is required only for `torch`; shadow + `claude` requires `EYE_API_KEY`.
5. `crud.create_exam_with_result()` gets one optional kwarg, `assessment_json: str | None = None`. Recreate local `eye.db` files after the column is added, because `create_all` does not alter existing tables.
6. The storage selector's `save_original()` returns `tuple[Path | str, str]`.

Follow-on for the missed tests: `ensure_dirs()` and the `/static/heatmaps` mount stay until Phase 3, so `test_startup_creates_both_media_subdirectories` stays unchanged in Phase 1. Only `integration/test_static_serving.py::test_heatmap_png_is_on_disk` changes in Phase 1, to assert that no heatmap file is written. The Phase 1 count is therefore 240.

## Phase log

<!-- One entry per phase: date, commits, commands run, counts, surprises. -->

### 2026-11-21 — Phase 0 (baseline, no code changes)

- Commits: `d339fc5` "docs: Claude migration kit", then "docs: phase 0 baseline" (this file only).
- No file under `app/` or `tests/` was modified.
- Commands and counts: see Baseline (ruff 0, mypy 0, `277 passed, 7 deselected`).
- Surprises: plan §1 test counts are off (contract 133 / unit 80, not 130 / 78); six plan-vs-code conflicts are listed under Edit map and need decisions before Phases 1–3; two integration tests are missing from §4.
- `eye-detect-claude-kit.zip` sits untracked at the repo root and was deliberately not committed.

### 2026-11-22 — Phase 1 (delete model code)

- Commits: `e750dd6` (test-only: delete `unit/test_torch_engine.py` and `unit/test_gradcam.py`; `contract/test_static_serving.py` asserts that REFER has `heatmap_url is None`; `integration/test_static_serving.py::test_no_heatmap_file_is_written`). Red before implementation: `2 failed, 238 passed, 4 deselected`. Then `955207f`, the implementation commit "refactor: remove torch/onnx/grad-cam model code (phase 1)", which touches no tests. Review (1c, Sonnet): no blockers. Its one should-fix is the stale `backend/README.md`, listed below.
- Deleted: `app/inference/{torch_engine,onnx_engine,gradcam}.py`, `scripts/{download_model,export_onnx}.py`, `requirements-torch.txt`, and the dead `storage.local.heatmap_target()`.
- Changed:
  - `engine.get_engine()`: onnx branch removed. The torch branch is kept and now always gives `UnavailableEngine`.
  - `config`: `eye_model_source` is `mock | torch`.
  - `predict.py`: no `gradcam` import, `_render_heatmap` removed, step 8 is `heatmap_url = None`, unused `Path` import removed.
  - `worker.py` (§12.1): step 8 is `heatmap_url = None`.
  - Requirements split into `requirements.txt` (prod; keeps `onnxruntime` per §12.2 and celery/pika/redis until Phase 3), `requirements-dev.txt` and `requirements-admin.txt` (streamlit, requests).
  - `Dockerfile`: no torch index, no opencv fix; installs prod + admin requirements; the runtime guard imports `cv2, onnxruntime, streamlit`.
  - CI: single `pip install -r requirements-dev.txt`, opencv-fix steps removed.
- Gate, in a **fresh** venv built only from `requirements-dev.txt` (no torch, torchvision, timm, grad-cam, huggingface_hub or onnx installed; `onnxruntime`, `opencv-python-headless 4.10.0.84` and celery present):
  - `ruff check app tests` → `All checks passed!`
  - `mypy app` → `Success: no issues found in 32 source files`
  - `python -c "import app.main"` outside pytest → ok, `torch`/`gradcam` not in `sys.modules`
  - `EYE_MODE=demo pytest -q -m "not model and not perf"` → **`240 passed, 4 deselected`**, matching the §12 target (277 − 24 − 13).
- Not verified here: `docker build`. Docker is installed but no daemon was running. CI's docker job will be the first real build of the new Dockerfile.
- Not changed (outside Phase 1's file list): `backend/README.md` still documents `pip install -r requirements-torch.txt`, `torch_engine.py`, `download_model.py` and the gradcam layout (L25, L254–268, L392–400). `training/` keeps its own torch venv and is untouched. `app/inference/preprocess.display_copy()` is now unused by the app, but `preprocess.py` is not on the editable list.

### 2026-11-22 — Phase 2 (Claude engine)

- Roles as in PROMPTS.md: tests by a Sonnet test writer, `2d58ca6` (176 tests: decision 119, engine 33, wiring 12, config 12, plus `tests/fakes/`). Implementation `8672baa` and `e956b45`, neither touching tests.
- Implementation:
  - `ClaudeEngine.assess(jpeg)` makes one `AsyncAnthropic.messages.parse(output_format=FundusAssessment, timeout=CLAUDE_TIMEOUT_S)` call, and the client is built with `max_retries=0` (`anthropic==2.12.*`).
  - It raises on refusal, `max_tokens`, a missing parse result, or local validation failure (lower-case enums, grade 0..4, probability 0..1 and finite).
  - `decide_from_assessment()` follows §3.5 exactly, next to the untouched `decide()`.
  - `predict.py` branches on `wants_jpeg`, and its `model_version` is the engine's even on a quality-gate UNGRADABLE. `assessment_json` is persisted, and there is one `claude_call` log line per call with ids, latency, tokens, image type and decision.
  - Config: the `claude` source and its fields, plus the §12.4 validator.
- Additive interface beyond the plan sketch: `ClaudePrediction` also carries `latency_ms`, `input_tokens` and `output_tokens` for the log line, and `wire_response()` takes an optional `request_id` so the logged id matches the response.
- The Celery worker refuses the Claude engine before any side effect. This was a two-line typing guard forced by the §12.3 union return type, and the worker was deleted in Phase 3 anyway.
- Gate: ruff and mypy are clean (34 files); `415 passed, 1 failed, 4 deselected`.
- **The one failure is a test bug, left unedited per hard rule 3 and PROMPTS.md.**
  - `tests/unit/test_claude_engine.py:164` expects `(588, 1568)` for a 1200×3136 portrait.
  - The aspect-preserving result is 1200 × 1568/3136 = **600**, which the engine produces; the reviewer confirmed it independently.
  - Fixed on 2026-11-22 with the owner's approval in a test-only commit (`588` → `600`); see the Phase 3 gate below.
- Review (2c, Sonnet): no blockers. Its should-fix items are open decisions 1 and 2 below; its nit (image prep on the event loop) is fixed in `e956b45`.
- **Not done: the manual real-key check.** It needs your four images in `backend/eval/manual/`, which is git-ignored.

### 2026-11-22 — Phase 3 (Vercel-ready, not deployed)

- Tests by the Sonnet test writer: `05d9f4f` (async rewrite 11, storage switch 14, Postgres 1, config Phase 3 rows, `tests/fakes/blob.py`). Implementation: `ad04f01`, which touches no tests.
- Implementation:
  - `run_screening()` is shared by `/predict` and `/predict/async`. Async runs inline and returns `replay:<exam_id>` with `PROCESSING`; issue 10 is fixed by sharing that path.
  - The status endpoint keeps only the replay branch; `app/worker.py` and Celery, pika and redis are removed.
  - Storage switch: `app/storage/blob.py` uses `vercel.blob.sync.put_blob` (public access, random suffix), and `app.storage` selects the backend. Blob mode writes nothing locally (import, startup, readiness), mounts no `/static`, and readiness checks `BLOB_READ_WRITE_TOKEN`.
  - Database: `postgres://` and `postgresql://` are rewritten to `postgresql+psycopg://`, and Postgres uses `pool_size=2, max_overflow=2`.
  - The rate limiter logs its key and `X-Forwarded-For` once per new bucket (issue 9); keying is unchanged.
  - Also added: `.python-version` (3.12), `vercel.json` (matching Vercel's own FastAPI docs example) and `scripts/smoke_claude.sh`.
- Changed outside CLAUDE.md's editable list, because it was needed: `app/db/models.py` `static_url()` now returns absolute `http(s)` URLs unchanged. Without that, a stored Blob URL read back as `/static/images/...` on status, replay and `/exams`, which the storage tests caught. `app/core/rate_limit.py` changed for issue 9, and `pytest.ini` for the marker.
- `requirements.txt` uses `vercel-blob==0.6.*`, Vercel's standalone Blob client providing the same `vercel.blob` module, instead of the `vercel` meta-package. The meta-package also pulls the Sandbox, Workflow and Queue clients plus websockets.
- Gate, from a **fresh** venv built from `requirements-dev.txt` (`pip check` clean; no torch, timm, grad-cam, onnx, celery, pika, redis or streamlit):
  - ruff and mypy are clean.
  - `import app.main` loads neither celery nor torch.
  - `EYE_MODE=demo pytest -q -m "not model and not perf"` gave `449 passed, 1 failed, 1 skipped, 4 deselected`. The failure was the test bug above. After the approved test-only fix it gives **`450 passed, 1 skipped, 4 deselected`** (ruff and mypy still clean). The skip is `test_postgres_async.py`, because no `TEST_POSTGRES_URL` or Postgres container was available (no Docker daemon).
- Review (3c, Sonnet): no blockers.
  - Blob mode was verified empirically: `import app.main`, startup and `/health/ready` never created `EYE_STORAGE_DIR`.
  - The first async status is `PROCESSING`, both endpoints share `run_screening`, and the URL rewrite and pool are correct.
  - The Python 3.12 Linux wheels exist for every pin.
  - Should-fix items are open decisions 5 and 6 below. Nit: the rate-limit line logs client IPs at INFO, which is intended for issue 9 and noted for privacy.
- Not done here: `vercel deploy`, the live smoke test, and the Postgres round trip. They need your Vercel account and stores; steps below.

## Open decisions for the owner (2026-11-22)

1. ~~**`CLAUDE_MAX_TOKENS=800` versus thinking (Phase 2 review).**~~ — approved and done on 2026-11-22: the default is now **4000** (test `test_claude_defaults` updated first in its own commit; suite `450 passed, 1 skipped, 4 deselected`). The background:
   - The default `claude-sonnet-5-5` runs adaptive thinking when `thinking` is omitted, and thinking tokens count toward `max_tokens`. An answer can therefore hit `max_tokens`, which the engine treats as a 500. That is safe, but it could fail most calls.
   - Options: raise the default (for example to 4000; you pay only for tokens actually used), or send `thinking={"type": "between_tools"}`. Sonnet 5.5 accepts that setting, but `claude-opus-5-5`, the comparison model, rejects it.
   - During the manual check, look at `output_tokens` in the `claude_call` log line to see how much of the 4000 a real call uses.
2. **EXIF in unchanged JPEGs (Phase 2 review).** §3.3 sends a JPEG within 1568 px byte-for-byte, so EXIF and comment segments (GPS, device, any typed comment) reach Claude, which conflicts with CLAUDE.md's "only the image". A lossless metadata strip would also change `test_small_jpeg_is_sent_byte_identical` and `test_jpeg_exactly_at_the_limit_is_unchanged`, so it needs your call.
3. ~~**The test arithmetic bug**~~ — approved and fixed (`588` → `600`, test-only commit). Suite: `450 passed, 1 skipped, 4 deselected`.
4. **`backend/README.md`** still documents the torch install, `download_model.py` and Grad-CAM (Phase 1 review). It is outside every phase's file list. Approve a docs-only update?
5. **`onnxruntime` on Vercel.**
   - It stays in `requirements.txt` per §12.2, but is useless on Vercel, because `skin.onnx` is not deployed there.
   - Measured installed sizes (macOS; Linux is smaller): cv2 152 MB, numpy 60, onnxruntime 59 plus its dependency **sympy 79 and mpmath 5**, anthropic 33, sqlalchemy 20, PIL 14. The whole production set is about 461 MB on macOS.
   - The Phase 3 reviewer estimates 350–400 MB on Linux. Vercel's FastAPI docs give a standard **500 MB** Python bundle limit (up to 5 GB on Fluid compute, in beta), so it should fit.
   - If a deploy fails on size, `onnxruntime` and sympy (about 150 MB) are the first thing to drop. For example, move it to a `requirements-analysis.txt` that only the Dockerfile installs.
6. **Windows launchers (Phase 3 review).** `backend/run_backend_hidden.bat:5` still starts `celery -A app.worker.celery_app worker`, and `stop_backend.bat` kills Celery processes. `app/worker.py` no longer exists, so the launcher would fail. Both files are outside every phase's file list. Approve removing the Celery lines?

## Vercel deploy steps (for the owner; nothing was deployed)

1. Merge or push `feature/claude-engine` as you prefer (the kit forbids me pushing).
2. Vercel → Add New → Project → import the repository. Set **Root Directory = `backend`**. Vercel finds the FastAPI `app` at `app/main.py` and reads `.python-version` (3.12) and `requirements.txt`.
3. Storage → **Blob** → create a store → connect it to the project. This adds `BLOB_READ_WRITE_TOKEN`.
4. Storage or Marketplace → **Postgres** (e.g. Neon) → connect it to the project. Copy its **pooled** URL into `DATABASE_URL`; `postgres://` is fine, the config rewrites it.
5. Settings → Environment Variables: every name in `backend/.env.vercel.example`.
   - `EYE_MODE=shadow`, `EYE_MODEL_SOURCE=claude`, `EYE_STORAGE=blob`, `QUALITY_BLUR_MIN_VAR=8`, `MAX_UPLOAD_MB=4`.
   - `EYE_API_KEY` from `openssl rand -hex 32`, the same value as the app's `API_KEY`.
   - `ANTHROPIC_API_KEY`, and `CLAUDE_MAX_TOKENS` per decision 1.
6. Deploy. Then:
   - `bash scripts/smoke_claude.sh https://<project>.vercel.app <EYE_API_KEY> eval/manual`
   - Check the function logs for `claude_call` lines (and none for the blurred image), and for `rate_limit new_bucket key=... x_forwarded_for=...` (issue 9: is `key` the phone's IP or a proxy IP?).
7. Postgres round trip, run once by hand: `TEST_POSTGRES_URL=<pooled URL> EYE_MODE=demo pytest -q tests/integration/test_postgres_async.py`

## Manual Claude checks

<!-- Phase 2/3: per image — decision, icdr_grade, image_type, latency, tokens. -->

*Pending.* Put `referable.jpg`, `normal.jpg`, `external_eye.jpg` and `blurred.jpg` in `backend/eval/manual/` (git-ignored). Then, with the key in `backend/.env`:
1. Start the server: `EYE_MODE=shadow EYE_MODEL_SOURCE=claude EYE_API_KEY=demo123 QUALITY_BLUR_MIN_VAR=8 uvicorn app.main:app --port 8000`
2. Run the smoke test: `bash scripts/smoke_claude.sh http://localhost:8000 demo123 eval/manual`

These are the only real API calls before Phase 4, and they are billed.

## Eval results

<!-- Phase 4: link to eval/results/*.json and the summary against the pass bar. -->
