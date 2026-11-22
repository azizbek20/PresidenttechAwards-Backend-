# CLAUDE.md — EYE DETECT AI backend (Claude migration)

This file guides Claude Code in `backend/`. It replaces the v4 multi-agent
version (still in git history).

**Precedence:** for anything inside the migration's scope (model inference,
decision rules, storage, deployment), `docs/MIGRATION_PLAN.md` wins. For
everything else, `SPEC.md` still wins. Where this file and the plan disagree,
stop and ask.

The migration replaces the PyTorch / ONNX / Grad-CAM inference layer with
Claude vision (Anthropic API) and makes the backend deployable on Vercel.
Everything that carries a safety rule stays.

---

## Hard rules

1. Work only on the current phase of `docs/MIGRATION_PLAN.md`. Do not start
   the next phase until asked.
2. Edit only the files the current phase lists. If an interface looks wrong,
   STOP and report — do not improvise a redesign.
3. **Tests are written before implementation, in their own commits.**
   Implementation commits must not touch `tests/`. If a test looks wrong
   during implementation, stop and explain why; do not edit it.
4. Your definition of done is the phase's command list exiting 0. Paste the
   final lines of each command's output. Never claim a test passed that was
   skipped or not run.
5. Commit small and often on `feature/claude-engine`. Never push, merge,
   rebase or touch other branches.
6. Record what you did, what you measured and anything surprising in
   `docs/NOTES.md` at the end of every session.

## Still frozen (read-only)

- `app/schemas.py` and `app/analysis/schemas.py` — the wire contract the
  deployed app reads. No key renamed, removed or made nullable.
- `app/core/errors.py` — the `{"error", "detail"}` envelope; `detail` is
  always one short Uzbek string.
- `app/inference/mock_engine.py` — the test double; the contract tests depend
  on its brightness bands.
- The existing `decide()` in `app/inference/decision.py` — add new functions
  next to it, do not change it.
- `tests/conftest.py`, `tests/test_frozen_kit.py`,
  `tests/fixtures/golden_predict.json`.

## Unfrozen for this migration (change as the plan says, additively where possible)

`app/config.py`, `app/inference/engine.py`, `app/inference/decision.py`
(additions only), `app/api/predict.py`, `app/main.py`, `app/storage/*`,
`app/db/base.py`, `app/db/models.py` (one new nullable column),
`requirements*.txt`, plus the new files the plan names.
Also, per the Phase 0 decisions (plan §12): `app/worker.py` (Phase 1: step 8
→ `heatmap_url = None`; deleted in Phase 3), `app/db/crud.py` (Phase 2: one
optional `assessment_json` kwarg on `create_exam_with_result`), and
`app/api/deps.py` (Phase 2: `engine_for()` return type only).

## Test files that may change (test-only commits, listed in the plan)

Delete: `tests/unit/test_torch_engine.py`, `tests/unit/test_gradcam.py`.
Change assertions only: `tests/contract/test_static_serving.py` (no heatmap
any more), `tests/integration/test_predict_async.py` (Celery → inline replay),
`tests/perf/test_latency.py` (torch-only cases, if any; Phase 0 found none),
`tests/integration/test_static_serving.py::test_heatmap_png_is_on_disk`
(Phase 1: assert no heatmap file is written).
New test files as each phase lists. **Any other test that starts failing is
an implementation bug, not a test to fix** — in particular
`test_frozen_kit.py`, `test_model_unavailable.py` and
`test_audit_regressions.py` must keep passing unchanged (the legacy `torch`
config value stays for exactly this reason; see the plan §3.2).

## Safety invariants — never break these

- Step order in `POST /api/v1/predict` stays: validate → capped read → decode
  → model gate (3c) → dedup (3b) → save original → quality gate → inference →
  decision → persist → respond.
- The quality gate and dedup replay run **before** any Claude call. A failed
  gate or a replay makes zero Claude calls.
- No error path returns `NO_REFER`. An API error, timeout or invalid model
  output is `500 inference_error`. There is no fallback verdict.
- Persistence before response: a result that was not saved never reaches the
  phone (`500 persistence_error`).
- No mock result outside `EYE_MODE=demo`.
- Only the image and the fixed instructions go to Claude — never
  `patient_id`, never any other patient data.
- Secrets only from environment variables. Never in code, tests, logs,
  commits or chat output. The Anthropic key lives in `backend/.env`
  (git-ignored) or the shell environment.
- The verdict is computed only on the server, in `decision.py`.

## Claude API usage

- Model from `CLAUDE_MODEL` (default `claude-sonnet-5-5`; `claude-opus-5-5`
  for comparison runs). Never hard-code a model ID elsewhere.
- Structured output with the SDK's `messages.parse(...)` and the
  `FundusAssessment` Pydantic model from the plan. Check the installed SDK
  version's docs for the exact async call before writing it.
- Timeout `CLAUDE_TIMEOUT_S` (25 s), no automatic retries on the request
  path. The phone has its own retry button and a 30 s request timeout.
- Numeric ranges and enum casing are not enforced by the API: validate
  locally (lower-case enums, reject out-of-range numbers → 500).
- **Tests never call the real API.** Use a fake client. The only real calls
  are the manual check at the end of Phase 2 and the Phase 4 eval.
- Log per call: `request_id`, `exam_id`, `model_version`, latency, input and
  output tokens, `image_type`, decision. Never log image bytes or the key.

## Commands

```bash
# environment — Python 3.11 locally (CI), 3.12 on Vercel from Phase 3
cd backend
python3.11 -m venv venv && source venv/bin/activate

# BEFORE Phase 1 (current requirements, torch still present):
pip install -r requirements-torch.txt && pip install -r requirements-dev.txt
pip uninstall -y opencv-python && \
  pip install --force-reinstall --no-deps opencv-python-headless==4.10.0.84

# AFTER Phase 1 (torch and grad-cam gone, no opencv trap):
pip install -r requirements-dev.txt

# the default suite (every phase gate)
EYE_MODE=demo pytest -q -m "not model and not perf"

# lint / types
ruff check app tests && mypy app

# run locally, mock engine (no key needed)
EYE_MODE=demo EYE_MODEL_SOURCE=mock EYE_API_KEY=demo123 uvicorn app.main:app --port 8000

# run locally with Claude (key from backend/.env or the shell)
EYE_MODE=shadow EYE_MODEL_SOURCE=claude EYE_API_KEY=demo123 \
  QUALITY_BLUR_MIN_VAR=8 uvicorn app.main:app --port 8000
```

## Architecture notes that span files

- **Two engine input kinds.** The mock receives a normalised CHW tensor from
  `preprocess.to_model_input(retina_crop(img))`. The Claude engine declares
  `wants_jpeg = True` and receives the uploaded JPEG bytes (re-encoded only
  if the long side is over 1568 px). `predict.py` step 6 branches on that flag.
- **Two decision functions.** `decide()` (frozen) for the mock's 5-class
  probabilities; `decide_from_assessment()` (new) for Claude's structured
  assessment. Both return the same `DecisionResult`.
- **C3 split truth.** The wire carries `probability=0.0, icdr_grade=0` for
  UNGRADABLE because the app cannot take nulls; the database stores NULL.
- **Model gate (3c).** `engine.model_loaded == False` → 503
  `model_unavailable`. For Claude that means `ANTHROPIC_API_KEY` is missing:
  the app still starts, `/health/ready` is 503. Same behaviour the shadow-mode
  tests already pin for a missing model.

## Roles (multi-model workflow)

- **Test writer** (Sonnet or Haiku): writes and changes tests only, from the
  plan, before implementation. New-behaviour tests are expected to fail.
- **Implementer** (Opus): makes the tests pass without touching `tests/`.
- **Reviewer** (any model): checks the diff against the plan and the
  checklist in `docs/MIGRATION_PLAN.md`; reports, does not fix.
