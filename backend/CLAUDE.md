# CLAUDE.md — EYE DETECT AI backend

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository. `SPEC.md` in this directory is the single source of
truth; where this file and `SPEC.md` disagree, `SPEC.md` wins.

## Hard rules for every agent (SPEC.md §0, verbatim)

1. You may create/modify **only the paths listed in your worktree brief** (§5).
2. Frozen files (§4.2 list) are read-only. If an interface looks wrong, **STOP
   and report in your final message — do not change it** (Doc 5 §6.3 rule:
   interfaces change only at the orchestrator level, by adding, never renaming).
3. Every function you implement must match the exact signature in this spec.
4. Your definition of done is the exact command list in your brief exiting 0.
   Never claim a test passed that was skipped or not run.
5. Commit small and often on your own branch. Never merge, rebase, or touch
   other branches. Never push.

## Frozen files (§4.2) — read-only

`SPEC.md`, `CLAUDE.md`, `requirements*.txt`, `app/config.py`, `app/schemas.py`,
`app/core/errors.py`, `app/inference/engine.py`, `app/inference/mock_engine.py`,
`app/inference/decision.py`, `app/db/crud.py` (signatures — bodies are Agent
B's), `tests/conftest.py`, `tests/test_frozen_kit.py`,
`tests/fixtures/golden_predict.json`.

## What agents must NOT do (§7, recap)

No response fields beyond frozen `schemas.py` (15 legacy + `request_id`,
`mode`), no renamed JSON keys, no problem+json, no nullable wire fields, no
auth on `/static`, no mock predictions outside `EYE_MODE=demo`, no duplicate
exams from a resent payload, no non-string error `detail`, no runtime model
downloads, no `torch.load(weights_only=False)`, no CC-BY-NC model artifacts, no
editing frozen files, no cross-branch operations, no pushes, no claims of
untested success. When blocked → finish what is unblocked, report the blocker.

## Commands

```bash
# environment (Python 3.11)
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements-torch.txt && pip install -r requirements-dev.txt
# MANDATORY: grad-cam depends on opencv-python (the GUI build), which overwrites
# opencv-python-headless's cv2 directory. In a container the GUI build dies on
# `import cv2` with libGL.so.1 not found. Restore the pinned headless build:
pip uninstall -y opencv-python && \
  pip install --force-reinstall --no-deps opencv-python-headless==4.10.0.84

# the default suite (what every gate runs)
pytest -q -m "not model and not perf"

# a single test
pytest tests/contract/test_predict_contract.py::test_all_legacy_keys_present -q

# lint / types
ruff check app tests && mypy app

# run the API (demo mode, mock engine)
EYE_API_KEY=demo123 uvicorn app.main:app --port 8000

# admin panel (step 5 of the demo script)
API_URL=http://localhost:8000 EYE_API_KEY=demo123 streamlit run admin/dashboard.py
```

## Device policy

The delivered `SPEC.md` ends at §9 and contains **no §10 macOS/MPS addendum**,
so the device contract is pinned in `app/config.py`:

* `EYE_DEVICE=cpu` is the default and is **mandatory** for tests, CI, Docker
  and every gate assertion. MPS never gates anything.
* `EYE_DEVICE=mps` is for Apple-silicon dev runs only; `auto` picks mps when
  genuinely available and otherwise falls back to cpu with a WARNING.
* Grad-CAM always runs on cpu.

## Architecture notes that span files

* **Two input domains reach `engine.predict`.** Tests pass a decoded RGB image
  (HWC uint8); `api/predict.py` passes `to_model_input(retina_crop(img))`, a
  normalised CHW float32 tensor. `mock_engine.mean_gray` inverts the ImageNet
  transform to recover the intensity band. `IMAGENET_MEAN`/`IMAGENET_STD` live
  in `app/inference/engine.py` and **both** `preprocess.to_model_input` and the
  mock must use them, or every demo verdict shifts.
* **The quality gate runs before the DR engine, always.** A blurry or dark
  image is UNGRADABLE and `engine.predict` is never called — pinned by
  `tests/contract/test_engine_spy.py`.
* **C3 split truth:** the wire carries non-null placeholders for UNGRADABLE
  (`probability=0.0, icdr_grade=0`) because the deployed APK crashes on nulls,
  while the DB stores `NULL` so training exports stay clean.
* **Persistence is unconditional (C10):** any DB write failure is
  `500 persistence_error`, in every mode. A result the admin panel cannot
  corroborate must never reach the phone.
