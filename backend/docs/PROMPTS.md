# Prompts for Claude Code — Claude engine migration

Paste these into Claude Code, opened at the **repo root**, one at a time.
Wait for each to finish and read its report before sending the next.

Order for every phase: **tests → implementation → review**.
Suggested models: tests = Sonnet (or Haiku for simple test edits),
implementation = Opus, review = your reviewer model.

Before Phase 2, put the Anthropic key in `backend/.env` (git-ignored) as
`ANTHROPIC_API_KEY=...`. Never paste the key into a prompt.

---

## START — Phase 0 (baseline, no code changes)

```
You are working on the EYE DETECT AI backend in backend/. Read
backend/CLAUDE.md and backend/docs/MIGRATION_PLAN.md completely before doing
anything else. This session is PHASE 0 ONLY. Do not modify any file under
backend/app or backend/tests (committing the kit files exactly as they are
is fine).

1. Create and switch to branch feature/claude-engine (from the current branch).
   Commit the kit files that are already in the working tree
   (backend/CLAUDE.md, backend/docs/*, backend/.env.vercel.example,
   backend/app/inference/prompts/fundus_v1.md) as
   "docs: Claude migration kit".
2. In backend/, create a Python 3.11 venv and install dependencies exactly as
   the "BEFORE Phase 1" commands in CLAUDE.md say (including the opencv fix).
3. Run, from backend/:
     ruff check app tests
     mypy app
     EYE_MODE=demo pytest -q -m "not model and not perf"
   Record the exact pass / fail / skip / error counts and every failure
   (test id + one-line reason) in backend/docs/NOTES.md under "## Baseline".
4. Confirm the lists in MIGRATION_PLAN.md §4 by grepping tests/ for torch,
   onnx, gradcam, heatmap, shadow, celery, worker, predict/async. Add any test
   the plan missed under "## Test impact" in NOTES.md, with the reason. Also
   confirm that test_frozen_kit.py, test_model_unavailable.py and
   test_audit_regressions.py will keep passing if the legacy `torch` config
   value stays (plan §3.2).
5. Read app/api/predict.py, app/api/deps.py, app/inference/engine.py,
   app/inference/decision.py, app/config.py, app/main.py, app/storage/local.py
   and app/db/models.py. Under "## Edit map" in NOTES.md, list for Phases 1–3
   every file and function you expect to change, and any place where the plan
   conflicts with the code.
6. Commit NOTES.md as "docs: phase 0 baseline". Stop.

Report back: baseline counts, failures, the confirmed test-impact list, and
every conflict between the plan and the code. Do not start Phase 1.
```

---

## Phase 1 — delete model code

### 1a. Tests (Sonnet / Haiku)

```
Read backend/CLAUDE.md and backend/docs/MIGRATION_PLAN.md (§4, §6 Phase 1).
You are the TEST WRITER for Phase 1. Change only test files.
- Delete tests/unit/test_torch_engine.py and tests/unit/test_gradcam.py.
- In tests/contract/test_static_serving.py, a REFER result no longer has a
  heatmap: assert heatmap_url is None; keep every image-serving assertion.
- In tests/perf/test_latency.py, remove torch-only cases if any.
Do not touch any other test. Commit as "tests(phase1): drop model-specific
tests". Report the files changed and which tests you expect to fail until
the implementation lands.
```

### 1b. Implementation (Opus)

```
Read backend/CLAUDE.md and backend/docs/MIGRATION_PLAN.md (§3.2 legacy torch
note, §3.10, §6 Phase 1). You are the IMPLEMENTER for Phase 1. Do not edit
anything under tests/.
- Delete app/inference/torch_engine.py, app/inference/onnx_engine.py,
  app/inference/gradcam.py, scripts/download_model.py, scripts/export_onnx.py,
  requirements-torch.txt.
- engine.get_engine: remove the onnx branch; keep the torch branch (it now
  always returns UnavailableEngine). config: remove "onnx" from
  eye_model_source; keep "torch" and its SHA-256 rule.
- predict.py and worker.py: remove step 8 (heatmap); heatmap_url = None.
  Keep app/worker.py otherwise (removed in Phase 3).
- Requirements as §3.10 (without anthropic/vercel yet). Update the Dockerfile
  and .github/workflows/backend-ci.yml install steps to match (no torch index,
  no opencv fix).
Then recreate the venv with the "AFTER Phase 1" commands and run:
  ruff check app tests && mypy app
  EYE_MODE=demo pytest -q -m "not model and not perf"
Compare the counts with the baseline in docs/NOTES.md; every difference must
be one of the deleted or changed tests. Paste the final output lines. Commit
as "phase1: remove torch/onnx/grad-cam", update NOTES.md, stop.
```

### 1c. Review (reviewer model)

```
Review branch feature/claude-engine, Phase 1 commits only, against
backend/docs/MIGRATION_PLAN.md §6 Phase 1 and §9. Report, do not fix:
1. Implementation commits touch nothing under tests/.
2. Frozen files unchanged (§9 last bullet command).
3. No remaining import of torch, onnxruntime, timm, pytorch_grad_cam,
   huggingface_hub, or app.inference.gradcam anywhere in app/.
4. The torch config value and its SHA-256 validator are still present.
5. Requirements, Dockerfile and CI agree with each other.
6. The test count change matches the deleted/changed tests exactly.
List each problem with file:line and severity.
```

---

## Phase 2 — Claude engine

### 2a. Tests (Sonnet)

```
Read backend/CLAUDE.md and backend/docs/MIGRATION_PLAN.md (§3.2–§3.6, §5
Phase 2 rows). You are the TEST WRITER for Phase 2. Change only tests.
Write, using fakes in tests/fakes/ (a fake Anthropic client and a fake
ClaudeEngine; never the real API):
- tests/unit/test_decision_claude.py — table-driven, one case per rule in
  §3.5 (including both probability clamps, C3 split, every Uzbek text,
  edema/uncertain refer clauses, final grade = max(claude, rule)).
- tests/unit/test_claude_engine.py — the cases in §5.
- tests/contract/test_claude_wiring.py — the cases in §5 (zero Claude calls
  on quality-gate failure and on dedup replay; engine error -> 500
  inference_error with nothing persisted; non-fundus -> UNGRADABLE with the
  fundus text; assessment_json stored; response keys == LEGACY_KEYS +
  request_id, mode).
- tests/unit/test_config_claude.py — the Phase 2 cases in §5.
Import the new modules by the names in the plan (app.inference.claude_engine,
app.inference.assessment, decision.decide_from_assessment); they do not exist
yet, so these tests fail now — that is expected. No skip/xfail markers.
Commit as "tests(phase2): claude engine and decision". Report files, test
counts, and anything in the plan that was ambiguous.
```

### 2b. Implementation (Opus)

```
Read backend/CLAUDE.md and backend/docs/MIGRATION_PLAN.md (§3.2–§3.6, §6
Phase 2). You are the IMPLEMENTER for Phase 2. Do not edit tests/.
- Add anthropic to requirements.txt; reinstall. Add eval/manual/,
  eval/data/ and eval/results/*.jpg to backend/.gitignore (patient-like
  images never go into git).
- app/config.py: new fields and validator rules from §3.2.
- app/inference/assessment.py (schema), app/inference/claude_engine.py,
  ClaudePrediction in engine.py, get_engine branch for "claude".
  Check the installed anthropic SDK's docs for the async messages.parse call.
- decision.decide_from_assessment exactly as §3.5; leave decide() untouched.
- predict.py steps 6, 7, 10 as §3.6 (run_screening comes in Phase 3).
- db/models.py: nullable Text column assessment_json; crud persists it.
- Per-call log line as CLAUDE.md "Claude API usage" says.
Run: ruff check app tests && mypy app && EYE_MODE=demo pytest -q -m "not model and not perf"
Paste the final lines. Commit as "phase2: claude engine".

Then a MANUAL check with the real key from backend/.env (the only real API
use in this phase): start the server in shadow+claude mode (CLAUDE.md
commands) and POST, with X-API-Key, the images I put in
backend/eval/manual/ (I will tell you which are referable, normal, a phone
eye photo, and blurred). Record in docs/NOTES.md, per image: decision,
icdr_grade, image_type, latency, input/output tokens. Do not commit the
images. Stop and report.
```

### 2c. Review (reviewer model)

```
Review Phase 2 commits on feature/claude-engine against
backend/docs/MIGRATION_PLAN.md §3.2–§3.6 and the §9 checklist. Report, do not
fix. Check especially:
- No code path returns NO_REFER after any exception; no fallback verdict.
- The Claude request contains only the image and fixed text: grep for
  patient_id/eye/patient_code reaching claude_engine.
- Zero Claude calls before the quality gate and on dedup replay.
- Enums lower-cased and ranges validated locally; invalid output -> 500.
- decide() unchanged; decide_from_assessment matches §3.5 rule by rule.
- model_version = "<CLAUDE_MODEL>/prompt-<PROMPT_VERSION>".
- No key, image bytes or patient ID in any log call.
- Implementation commits do not touch tests/; frozen files unchanged.
List each problem with file:line and severity.
```

---

## Phase 3 — Vercel

### 3a. Tests (Sonnet)

```
Read backend/CLAUDE.md and backend/docs/MIGRATION_PLAN.md (§3.6–§3.11, §4
and §5 Phase 3 rows). You are the TEST WRITER for Phase 3. Change only tests.
- Rewrite tests/integration/test_predict_async.py for the inline flow:
  POST /api/v1/predict/async returns task_id "replay:<exam_id>" with status
  PROCESSING; GET /api/v1/predict/status/<task_id> returns SUCCESS with the
  same exam_id and verdict; a bad image still gets 400 synchronously.
- tests/integration/test_storage_switch.py with a fake Blob client.
- Postgres URL rewrite cases in tests/unit/test_config_claude.py.
- tests/integration/test_postgres_async.py marked `postgres` (run manually
  against a local Postgres container; excluded from the default run).
Commit as "tests(phase3): inline async, storage, postgres". Report.
```

### 3b. Implementation (Opus)

```
Read backend/CLAUDE.md and backend/docs/MIGRATION_PLAN.md (§3.6–§3.11, §6
Phase 3, issues 7, 9, 10, 11). You are the IMPLEMENTER for Phase 3. Do not
edit tests/.
- Extract run_screening(); /predict/async runs it inline and returns the
  replay task; delete app/worker.py and the Celery branch of the status
  endpoint; remove celery/pika/redis.
- Give /predict/async's dedup lookup the same try/except as /predict.
- Postgres scheme rewrite and small pool (§3.9).
- app/storage/blob.py + EYE_STORAGE switch; ensure_dirs, /static mounts and
  the readiness storage probe only for local (§3.8). Add vercel to
  requirements.
- backend/.python-version = 3.12; backend/vercel.json (§3.11).
- scripts/smoke_claude.sh: the live smoke in §7 layer 6, taking BASE_URL,
  API key and an images folder as arguments.
- Rate limiter: log the client IP it keys on, so we can check it behind
  Vercel's proxy (issue 9). Do not change the keying yet.
Run lint, types and the default suite; also run the postgres-marked test
against a local Postgres container. Paste the final lines. Commit as
"phase3: vercel-ready". Then give me the exact Vercel steps (project root,
env vars from .env.vercel.example, Blob and Postgres connection) and stop —
I will create the project and connect the stores myself.
```

### 3c. Review (reviewer model)

```
Review Phase 3 commits against backend/docs/MIGRATION_PLAN.md §3.6–§3.11 and
§9. Report, do not fix. Check: the first async status is PROCESSING, never
SUCCESS; /predict and /predict/async share run_screening with identical
errors; nothing writes to the local filesystem when EYE_STORAGE=blob
(including at import time); /static is not mounted in blob mode; Blob URLs
are absolute and unguessable; DATABASE_URL rewrite covers postgres:// and
postgresql://; no Celery import remains; requirements.txt has no dev or ML
packages; .python-version is 3.12. List problems with file:line.
```

### 3d. After you deploy (Opus or Sonnet)

```
The backend is deployed at <URL>. Run scripts/smoke_claude.sh against it
with the key from backend/.env and the images in backend/eval/manual/.
Then check the Vercel function logs I paste below for the client IP the rate
limiter keyed on (issue 9) and tell me whether it is the phone's IP or a
proxy IP. Record results in docs/NOTES.md and stop.
```

---

## Phase 4 — accuracy eval (Opus)

```
Read backend/docs/MIGRATION_PLAN.md §6 Phase 4 and §8. Write
backend/eval/run_claude_eval.py, adapted from training/eval_backend_dr.py,
that runs the backend's own path (load_rgb -> quality gate -> ClaudeEngine
-> decide_from_assessment) over a labelled CSV
(image_path, icdr_grade, patient_id, split) plus a folder of non-fundus phone
eye photos. Report: sensitivity and specificity for referable DR (grade >= 2)
with Wilson 95% CIs, confusion matrix, ungradable rate, non-fundus rejection
rate, p50/p95 latency, tokens and cost per scan. Write JSON to
eval/results/<date>-<model>-<prompt>.json and a short Markdown summary.
Limit concurrency to 2 and print the estimated cost before starting; ask me
to confirm if it exceeds $10. Do not change any threshold, rule or prompt.
Run it on the CSV I give you with CLAUDE_MODEL=claude-sonnet-5-5, then stop
and report against the §8 pass bar.
```

---

## Utility prompts

**Resume a session**
```
Read backend/CLAUDE.md, backend/docs/MIGRATION_PLAN.md and
backend/docs/NOTES.md. Tell me which phase we are in, what is done, what is
left, and whether the last recorded test run was green. Do not change
anything yet.
```

**When something fails and you are tempted to edit a test**
```
Stop. Explain why <test id> fails, quoting the assertion and the code path.
Say whether the test or the implementation contradicts MIGRATION_PLAN.md.
Do not edit either until I decide.
```
