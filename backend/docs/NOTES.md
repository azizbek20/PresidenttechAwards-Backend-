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
- ~~**Not done: the manual real-key check.**~~ Done on 2026-11-22 with public images: all smoke checks passed. See "Manual Claude checks" below, including two findings (open decisions 8 and 9).

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

### 2026-11-22 — Phase 4 (accuracy eval: script written, not run)

- PR #9 merged phases 0–3 into `main` (merge commit `6391b23`). Phase 4 continues on `feature/claude-engine`, whose tip is in `main`.
- Tests first, by a Sonnet test writer, from an interface spec: `8151c83` adds `tests/unit/test_claude_eval.py` (67 tests). Red before implementation: `67 errors` (module missing), every other test passing. Implementation `d389140` (`eval/run_claude_eval.py`) touches no tests; all 67 passed on the first run.
- Outside the plan's Phase 4 file list, because the test-first rule needs it: the new test file.
- What the script does:
  - Every image takes `/predict`'s own steps: size cap (`MAX_UPLOAD_MB`), format sniff, decode, quality gate, then `ClaudeEngine.assess(raw)` only if the gate passed, then `decide_from_assessment` with the configured threshold and `UNCERTAIN_REFERS`. Settings come from the environment and `.env` as in production; only `EYE_MODE=demo` and `EYE_MODEL_SOURCE=claude` are forced. Nothing changes a threshold, rule or prompt.
  - Claude gets the image bytes only. `patient_id` is used only to refuse a CSV where a patient sits in two splits (§8), and is never sent or written to the report, which names images by file name only.
  - Before any call it runs the local steps on every image, then prints how many will reach Claude and an **upper-bound** cost (every answer at `CLAUDE_MAX_TOKENS`, input estimated from the prepared image size and the prompt length). Above `--max-cost` ($10 default) it sends nothing unless `--yes`. `--limit N` runs a pilot.
  - Concurrency 2. The client matches production (`max_retries=0`), so a timeout or API error is recorded as that image's error, as the phone would get a 500. Any failure on one image (unreadable file, local check, Claude call, decision) is that image's error and the run continues; errors fail the pass bar's `no_errors` criterion.
  - Every finished image is appended to `<date>-<model>-<prompt>-<time>.partial.jsonl` in the results folder, so a crash or Ctrl-C keeps the calls already paid for. It is deleted once the report is written.
  - Report: sensitivity and specificity for referable DR with Wilson 95% CIs, the 5×5 grade confusion, decisions per true grade, ungradable rates (overall, referable, non-referable), non-fundus rejection, p50/p95 latency, mean tokens, cost per scan and total. Written to `eval/results/<date>-<model>-<prompt>.json` and `.md`, never overwriting.
  - Two sensitivity and specificity rows: excluding UNGRADABLE (what the pass bar uses), and counting UNGRADABLE as a miss (see open decision 7).
  - Pass bar (§8): the 100-image minimums count only **scored** images (REFER or NO_REFER), and it never passes unless `--split` names a held-out split (not `all`, `train`, `training` or blank).
  - Prices used: Sonnet 5.5 $2 / $10 per MTok in/out, Opus 5.5 $4 / $20 (`--price-in/--price-out` override).
  - The report names images by file name. If the names carry patient identity (EyePACS uses `<patient>_left.jpeg`), rename the files before committing results.
- Review (Sonnet): no blockers. It confirmed the eval follows `run_screening` step for step and that nothing can be sent before the estimate or above `--max-cost` without `--yes`. Should-fix items, all fixed after new tests: (1) the 100 minimums counted UNGRADABLE images, so a sensitivity on 60 images could pass; (2) excluding UNGRADABLE flatters sensitivity with nothing reporting the strict figure; (3) `--split all` could report PASS on data that is not held out; (4) one unexpected error or Ctrl-C lost the whole run. Nits fixed: retries now match production, and each file is read inside the concurrency limit. Left as documented: file names in the report.
  - Round 2 followed the same order: amended spec, then `74417a0` (test writer: 96 tests, 38 failing against `d389140`, all of them new or changed pass-bar and robustness tests), then `af3675d` (implementation, no tests touched). The test change rewrote the pass-bar tests to the stricter criteria; it does not loosen anything.
- Smoke run of the real CLI with no key (synthetic images, `env -u ANTHROPIC_API_KEY`): `--max-cost 0` printed the estimate and exited 3 with nothing sent; a patient in two splits exited 2; no key exited 2 after the estimate, before any results folder was created. With the fake client the report rendered as expected and the partial file was removed. The upper bound is about **$0.046 per image** on Sonnet, nearly all of it the 4000-token output cap, so a 300-image run shows about $14 and needs `--yes`.
- Gate: ruff (app, tests, eval) and mypy (`app`, and `eval/run_claude_eval.py` separately) clean; `570 passed, 1 skipped, 4 deselected`.
- **Not done: the eval run itself.** It needs a labelled CSV (≥ 100 referable and ≥ 100 non-referable held-out images, no patient on both sides of a split), a folder of non-fundus phone photos, and your go-ahead for the billed calls. The IDRiD official test split (103 images) is too small for §8 on its own.

### 2026-11-22 — Vercel deploy (closes Phase 3)

- Live at **https://eye-detect-backend.vercel.app** (Vercel project `eye-detect-backend`, personal Hobby scope), deployed from a clean `git archive` of `main` at `e9ac308` with the Vercel CLI (66.6.0). The owner signed in, accepted Neon's terms and typed both secrets; nothing secret passed through Claude.
- Resources: Blob store `eye-detect-media` (public access, iad1, production + preview) and Neon Postgres `eye-detect-db` (Free plan, production + preview; the app reads its pooled `DATABASE_URL`). Function region iad1, the same as both stores.
- Production variables: the 13 non-secret values from `.env.vercel.example` (with `CLAUDE_MAX_TOKENS=4000`), plus `ANTHROPIC_API_KEY` and a new random `EYE_API_KEY` as sensitive variables. The owner's local copy of that key is `EYE_API_KEY_VERCEL` in `backend/.env` (git-ignored); it is also the Android app's `API_KEY` for the release build.
- **Gotcha:** the first deploy failed ("The pattern `app/main.py` defined in `functions` doesn't match any Serverless Functions inside the `api` directory"). A project created empty from the CLI gets the Framework Preset **Other**. Setting it to **FastAPI** (`vercel api /v9/projects/eye-detect-backend -X PATCH -F framework=fastapi`) fixed it; no code change. Vercel runs the FastAPI lifespan, so `create_all` made the tables on the empty Neon database.
- Live checks: `/health` 200, `/health/ready` 200 with database, storage and model all true, `HEAD /` 204, no key 401 with the Uzbek detail.
- **Live smoke test (`scripts/smoke_claude.sh`, run by the owner with the production key): all checks passed** — wrong key 401, 5 MB 413, referable REFER, normal NO_REFER, front-of-eye photo UNGRADABLE with the not-a-fundus text, blurred UNGRADABLE.
- Function logs (`vercel logs`), the first real per-call numbers on Sonnet 5.5:

  | Image | latency_ms | input_tokens | output_tokens | Decision |
  |---|---|---|---|---|
  | referable | 5769 | 4186 | 720 | REFER |
  | normal | 2667 | 5640 | 287 | NO_REFER |
  | external_eye | 2533 | 6175 | 263 | UNGRADABLE |

  About **$0.015 per scan** at $2 / $10 per MTok, about a third of the eval's upper bound. The largest answer used 720 output tokens (thinking included), close to the old 800 default and far under 4000 (decision 1). The blurred exam has **no** `claude_call` line: zero Claude calls on a gate failure, confirmed in production.
- Issue 9 answered: the `rate_limit new_bucket` line shows `key` equal to `X-Forwarded-For`, the caller's own public IP, so behind Vercel's proxy the limiter keys per client as intended. No change needed.
- Each app line appears **twice** in Vercel's logs: once from our handler (`INFO eyedetect.predict claude_call ...`) and once raw (`claude_call ...`), because Vercel's runtime also prints the root logger at INFO (httpx's own INFO lines show up too). See open decision 10.
- Not done: pushes to GitHub do not redeploy (CLI upload, no Git connection), and the Postgres async round trip test was not run separately; the live smoke test persisted every exam in Neon before responding (C10). Vercel's Hobby plan is for personal, non-commercial use; a clinical service needs Pro.

## Open decisions for the owner (2026-11-22)

1. ~~**`CLAUDE_MAX_TOKENS=800` versus thinking (Phase 2 review).**~~ — approved and done on 2026-11-22: the default is now **4000** (test `test_claude_defaults` updated first in its own commit; suite `450 passed, 1 skipped, 4 deselected`). The background:
   - The default `claude-sonnet-5-5` runs adaptive thinking when `thinking` is omitted, and thinking tokens count toward `max_tokens`. An answer can therefore hit `max_tokens`, which the engine treats as a 500. That is safe, but it could fail most calls.
   - Options: raise the default (for example to 4000; you pay only for tokens actually used), or send `thinking={"type": "between_tools"}`. Sonnet 5.5 accepts that setting, but `claude-opus-5-5`, the comparison model, rejects it.
   - During the manual check, look at `output_tokens` in the `claude_call` log line to see how much of the 4000 a real call uses.
2. ~~**EXIF in unchanged JPEGs (Phase 2 review).**~~ — approved and done on 2026-11-22 (plan §3.3 amended).
   - The problem: §3.3 sent a JPEG within 1568 px byte-for-byte, so EXIF (GPS, device), XMP, IPTC, comments and data after EOI (phone motion-photo videos, MPF depth images) reached Claude. Also found: the re-encode path leaked the JPEG comment, because Pillow 10.4 copies `im.info["comment"]` into the saved file.
   - Now `prepare_jpeg` makes a **lossless** copy of an upright JPEG within the limit: the entropy data is untouched, so pixels are identical. It keeps only JFIF (rebuilt without a thumbnail, once), the ICC colour profile and Adobe (cut to 12 bytes, once), plus the known decoding markers. Any other marker makes it give up and re-encode. An EXIF-rotated JPEG is re-encoded upright, and every re-encode carries no metadata.
   - A plain JPEG is still byte-identical, so the two existing byte-identity tests did not change. The two existing tests stand, and 24 new tests were added (`a1f9b2b`, `d9a865e`, by a Sonnet test writer, each committed before its implementation: `0d9910e`, then the review fixes in `57b84d6`).
   - Review (Sonnet, adversarial scripts): found that kept segments were copied whole (a JFIF thumbnail or bytes after the Adobe or JFIF fields survived) and that a DNL with a payload passed through. Both are fixed. Remaining by design: the ICC profile is kept whole as colour data (phone profiles hold names like "Display P3" and a copyright line), and bytes hidden inside the entropy-coded data of a crafted file cannot be removed by a lossless copy. Neither occurs in normal phone photos.
   - Cost: about 6–15 ms per 1568 px image (one extra decode to verify the copy), off the event loop.
   - Gate: ruff and mypy clean; `474 passed, 1 skipped, 4 deselected`.
3. ~~**The test arithmetic bug**~~ — approved and fixed (`588` → `600`, test-only commit). Suite: `450 passed, 1 skipped, 4 deselected`.
4. ~~**`backend/README.md`** still documents the torch install, `download_model.py` and Grad-CAM (Phase 1 review).~~ — approved and done on 2026-11-22 (docs-only commit).
   - README: the torch install, the opencv trap, the checkpoint and `download_model.py` notes and the Grad-CAM device rule are gone. It now covers running with the mock or Claude engine, `smoke_claude.sh`, both decision functions, the no-fallback and image-only rules, inline `/predict/async`, a Vercel section, the current layout, and the empty heatmap card for Android (8.3). The stale "rate limiting deferred" item is replaced: the limiter exists (30 per minute per IP, in memory, per process).
   - `.env.example` had the same leftovers (shadow "requires torch", Grad-CAM on cpu) and no Claude settings. Now it has `ANTHROPIC_API_KEY` (empty), the `CLAUDE_*` defaults, `PROMPT_VERSION`, `UNCERTAIN_REFERS` and `EYE_STORAGE`, and its compose DB path is corrected to `/app/data/eye.db`. Both env examples load into `Settings` with the stated values.
   - **Found: `.env.vercel.example` still set `CLAUDE_MAX_TOKENS=800`**, so copying it into Vercel would have overridden the new 4000 default (decision 1). Now 4000.
   - **Found: `.dockerignore` excludes `**/*.md`**, which includes the prompt `app/inference/prompts/fundus_v1.md`. The Docker image therefore cannot run the Claude engine (it stays the mock demo stack; the README says so). Vercel does not read `.dockerignore`. Not changed.
5. **`onnxruntime` on Vercel.**
   - It stays in `requirements.txt` per §12.2, but is useless on Vercel, because `skin.onnx` is not deployed there.
   - Measured installed sizes (macOS; Linux is smaller): cv2 152 MB, numpy 60, onnxruntime 59 plus its dependency **sympy 79 and mpmath 5**, anthropic 33, sqlalchemy 20, PIL 14. The whole production set is about 461 MB on macOS.
   - The Phase 3 reviewer estimates 350–400 MB on Linux. Vercel's FastAPI docs give a standard **500 MB** Python bundle limit (up to 5 GB on Fluid compute, in beta), so it should fit.
   - If a deploy fails on size, `onnxruntime` and sympy (about 150 MB) are the first thing to drop. For example, move it to a `requirements-analysis.txt` that only the Dockerfile installs.
6. ~~**Windows launchers (Phase 3 review).** `backend/run_backend_hidden.bat:5` still starts `celery -A app.worker.celery_app worker`, and `stop_backend.bat` kills Celery processes.~~ — approved and done on 2026-11-22: both Celery lines are removed, and the stop message no longer mentions Celery. Not changed: `stop_backend.bat` uses `wmic`, which is deprecated and missing from newer Windows 11 installs (24H2 and later) by default. If stopping silently does nothing there, that is why.

7. **Should the §8 pass bar count UNGRADABLE fundus images as misses? (Phase 4 review)** For you and the ophthalmologist.
   - Today the pass bar uses sensitivity and specificity **excluding** UNGRADABLE images, as the old torch eval did; the report also shows the strict figures that count them as misses.
   - Why it matters: an engine that calls every hard referable image UNGRADABLE scores well on the plain figure. Clinically an UNGRADABLE result asks for a retake or a referral, so it is not a silent miss, but a high ungradable rate makes the service less useful.
   - Options: keep it as is; make the pass bar use the strict figures; or keep the plain figures and add a cap on the ungradable rate (for example, at most 10% of referable images). No change is made without your decision.
8. **A definite referable lesion on a poor photo returns UNGRADABLE (manual check, finding A).** For you and the ophthalmologist; it is a decision-rule change (plan §3.5), so nothing is changed yet.
   - Today: rule 3 (`gradable: false` → UNGRADABLE, "retake") runs before the lesion rules, even when Claude marks a grade-2+ lesion as **present** (here: neovascularization, grade 4, p = 0.95).
   - Option, sensitivity-first: if `gradable` is false **but** any grade-2+ lesion is `present` (not `uncertain`), return REFER with a text that also asks for a retake. Otherwise keep UNGRADABLE. Implemented with tests first in `decide_from_assessment`, leaving the frozen `decide()` alone.
   - Or keep it as is: the operator retakes, and a second poor photo is referred by local protocol.
9. ~~**The per-call log line is never printed (manual check, finding B).**~~ — approved and fixed on 2026-11-22, before the Vercel deploy.
   - Cause: no `logging` configuration anywhere in `app/`; Python's default shows WARNING and above, so the INFO lines `claude_call ...` and `rate_limit new_bucket ...` were dropped. Tests read log records directly, so none caught it.
   - Tests first (Sonnet test writer, `d223e3e`, `tests/contract/test_logging.py`, 7 tests): a subprocess proves a line reaches real stdout exactly once; in-process checks of level, the single named handler across re-imports, emit-time stdout and an untouched root logger; and the `claude_call` line's fields with no patient id, API key or image data. 4 failed before the fix; 3 passed already and guard it.
   - Fix `f8936be` (`app/main.py` only): `configure_logging()`, called first in `create_app()`, sets the `eyedetect` logger to INFO and attaches one handler named `eyedetect-stdout` that writes to the current `sys.stdout` as `LEVEL logger message`. Root, uvicorn loggers and propagation are untouched.
   - Verified under real uvicorn (mock mode, no key): `INFO eyedetect.main started mode=demo ...` and `INFO eyedetect.rate_limit rate_limit new_bucket key=127.0.0.1 x_forwarded_for=None` each appear once.
   - Audit: every INFO line in `app/` logs ids, mode, tokens, decisions or byte counts; none carries a patient id, key or image data. The rate-limit line logs the client IP on purpose (issue 9).
   - If Vercel's runtime also installs a root handler, each line could appear twice in its logs; check after the first deploy. Checked: it does (decision 10).
10. ~~**Duplicate app log lines on Vercel (deploy).**~~ — approved and fixed on 2026-11-22; not yet redeployed.
    - Seen in production: each `eyedetect` line appeared twice, with and without the `INFO eyedetect.<name>` prefix, including the lifespan `started` line, so Vercel's root handler is active by startup. Every stdout line is tagged "info" by Vercel, so our prefix is the only place the real level shows.
    - Fix: `configure_logging()` sets `propagate = not VERCEL` on every call (Vercel sets `VERCEL=1` in its runtime). On Vercel only our prefixed line is printed, whenever Vercel configures its root logger; elsewhere (uvicorn, pytest's `caplog`) nothing changes. This replaces the first idea (skip our handler when root prints INFO), which depended on when Vercel sets up logging.
    - Tests first (`b269a6d`, 6 new cases in `tests/contract/test_logging.py`): subprocesses with `VERCEL=1` and root printing INFO configured before or after the app import print the probe once; a control without `VERCEL` prints it twice; in-process `propagate` follows `VERCEL` and is restored when it is unset or empty. 4 failed before the fix (fix `f5f15d3`), 13/13 pass after.
    - Gate: ruff and mypy clean; `583 passed, 1 skipped, 4 deselected`.
   - Gate: ruff and mypy clean; `577 passed, 1 skipped, 4 deselected`.

## Vercel deploy steps (done on 2026-11-22 with the CLI; see "Vercel deploy" above)

With the CLI, also set the project's **Framework Preset = FastAPI**; a project created empty gets "Other" and the build fails.


1. Merge or push `feature/claude-engine` as you prefer (the kit forbids me pushing).
2. Vercel → Add New → Project → import the repository. Set **Root Directory = `backend`**. Vercel finds the FastAPI `app` at `app/main.py` and reads `.python-version` (3.12) and `requirements.txt`.
3. Storage → **Blob** → create a store → connect it to the project. This adds `BLOB_READ_WRITE_TOKEN`.
4. Storage or Marketplace → **Postgres** (e.g. Neon) → connect it to the project. Copy its **pooled** URL into `DATABASE_URL`; `postgres://` is fine, the config rewrites it.
5. Settings → Environment Variables: every name in `backend/.env.vercel.example`.
   - `EYE_MODE=shadow`, `EYE_MODEL_SOURCE=claude`, `EYE_STORAGE=blob`, `QUALITY_BLUR_MIN_VAR=8`, `MAX_UPLOAD_MB=4`.
   - `EYE_API_KEY` from `openssl rand -hex 32`, the same value as the app's `API_KEY`.
   - `ANTHROPIC_API_KEY`, and `CLAUDE_MAX_TOKENS=4000` (decision 1).
6. Deploy. Then:
   - `bash scripts/smoke_claude.sh https://<project>.vercel.app <EYE_API_KEY> eval/manual`
   - Check the function logs for `claude_call` lines (and none for the blurred image), and for `rate_limit new_bucket key=... x_forwarded_for=...` (issue 9: is `key` the phone's IP or a proxy IP?).
7. Postgres round trip, run once by hand: `TEST_POSTGRES_URL=<pooled URL> EYE_MODE=demo pytest -q tests/integration/test_postgres_async.py`

## Manual Claude checks

<!-- Phase 2/3: per image — decision, icdr_grade, image_type, latency, tokens. -->

### 2026-11-22 — local run with the real key (closes Phase 2's manual check)

- Setup: `main` code (feature branch tip after PRs #9 and #10), `EYE_MODE=shadow EYE_MODEL_SOURCE=claude QUALITY_BLUR_MIN_VAR=8 MAX_UPLOAD_MB=4 CLAUDE_MODEL=claude-sonnet-5-5 CLAUDE_MAX_TOKENS=4000 PROMPT_VERSION=v1`, local storage and SQLite in a scratch folder. The key was read by the app from the main checkout's `backend/.env` through `EYE_ENV_FILE`; it never passed through the shell. `/health/ready` reported `model: true`.
- Images, all public from Wikimedia Commons, kept in `backend/eval/manual/` (git-ignored, not redistributed):
  - `referable.jpg`: "Fundus - diabetic retinopathy.png" (Hao et al., CC BY 4.0), its printed "A" panel label blacked out, saved as JPEG.
  - `normal.jpg`: "Fundus photograph of normal left eye.jpg" (Mikael Häggström, CC0).
  - `external_eye.jpg`: "Human eye close up, anterior view.jpg" (Rapidreflex, CC BY-SA 4.0).
  - `blurred.jpg`: the normal fundus with a Gaussian blur (radius 14), made here.
  - `referable_pdr_film_scan.jpg`: "Fundus Proliferative retinopathy EDA01.JPG" (National Eye Institute, public domain), kept for the finding below.
- Local quality gate first (free): blur variance 67.7 / 69.6 / 204.9 pass; `blurred.jpg` 1.65 fails.
- `scripts/smoke_claude.sh`: **all checks passed** — health 200, wrong key 401, 5 MB 413, then:

  | Image | Claude's assessment | Verdict |
  |---|---|---|
  | referable | fundus, gradable, grade 2, hard exudates present within about one disc diameter of the macula, macular edema signs present, p = 0.87 | **REFER** |
  | normal | fundus, gradable, grade 0, no lesions, p = 0.04 | **NO_REFER** |
  | external_eye | `external_eye`, "not a retinal fundus image" | **UNGRADABLE**, not-a-fundus text |
  | blurred | no Claude call (quality gate) | **UNGRADABLE** |

  The database stores NULL probability and grade for the UNGRADABLE rows (C3), and an `assessment_json` for every Claude answer, none for the blurred image.
- **Finding A (rule, see open decision 8):** the NEI proliferative-DR film scan, the first referable image tried, came back **UNGRADABLE**. Claude reported `neovascularization: present`, grade 4, p = 0.95, but `gradable: false` (blur, obstruction: "soft and hazy, the macula is not clearly identifiable"). Plan §3.5 rule 3 makes not-gradable win before the lesions are read, so a photo with sight-threatening disease visible gets "retake" instead of "refer".
- **Finding B (bug, see open decision 9):** no `claude_call` line (nor any other INFO line from the app) appeared in the server output. The app never configures logging, so its `eyedetect.*` INFO lines are dropped. Latency and tokens per call were therefore not captured here; the Phase 4 eval measures them itself.
- Billed calls: 4 (Sonnet 5.5), roughly $0.02–0.05 each.

## Eval results

<!-- Phase 4: link to eval/results/*.json and the summary against the pass bar. -->

*Pending.* To run, from `backend/`, with the key in `backend/.env`:
1. Put the images under `eval/data/` (git-ignored), with `eval/data/labels.csv` (`image_path,icdr_grade,patient_id,split`, paths relative to the CSV) and a folder of non-fundus phone eye photos, e.g. `eval/data/non_fundus/`.
2. Pilot, a few billed calls: `QUALITY_BLUR_MIN_VAR=8 python eval/run_claude_eval.py --labels eval/data/labels.csv --non-fundus eval/data/non_fundus --limit 5`
3. Full run with `CLAUDE_MODEL=claude-sonnet-5-5` (the default). It prints the upper-bound cost and stops above $10; add `--yes` once you accept it.
