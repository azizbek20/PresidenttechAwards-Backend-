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

**Watch-out.** `tests/contract/_shim.py` installs a stub `app.inference.gradcam` whenever the real file is absent. Once Phase 1 deletes `gradcam.py`, a forgotten `import app.inference.gradcam` in `predict.py` would still pass the **contract** suite on the stub. Only the integration suite, which has no shim, would catch it.

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

## Phase log

<!-- One entry per phase: date, commits, commands run, counts, surprises. -->

### 2026-11-21 — Phase 0 (baseline, no code changes)

- Commits: `d339fc5` "docs: Claude migration kit", then "docs: phase 0 baseline" (this file only).
- No file under `app/` or `tests/` was modified.
- Commands and counts: see Baseline (ruff 0, mypy 0, `277 passed, 7 deselected`).
- Surprises: plan §1 test counts are off (contract 133 / unit 80, not 130 / 78); six plan-vs-code conflicts are listed under Edit map and need decisions before Phases 1–3; two integration tests are missing from §4.
- `eye-detect-claude-kit.zip` sits untracked at the repo root and was deliberately not committed.

## Manual Claude checks

<!-- Phase 2/3: per image — decision, icdr_grade, image_type, latency, tokens. -->

## Eval results

<!-- Phase 4: link to eval/results/*.json and the summary against the pass bar. -->
