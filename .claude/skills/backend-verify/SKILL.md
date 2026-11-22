---
name: backend-verify
description: Run, lint, type-check and test the FastAPI backend in backend/ exactly the way CI does (ruff, mypy, pytest with the right markers, smoke test, docker compose). Use before claiming any backend change is done, when CI's backend-ci workflow fails, when setting up the backend venv, or when asked to start the API / admin panel locally.
---

# Backend verify & run (backend/)

`backend/SPEC.md` is the source of truth and `backend/CLAUDE.md` holds the hard rules.
Read the frozen-file list there before editing anything under `backend/app/`.

## One-time environment (Python 3.11)

```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements-torch.txt && pip install -r requirements-dev.txt
# MANDATORY: grad-cam pulls in GUI opencv, which breaks `import cv2` in containers/CI.
pip uninstall -y opencv-python && \
  pip install --force-reinstall --no-deps opencv-python-headless==4.10.0.84
```

If `import cv2` fails with `libGL.so.1`, the opencv step above was skipped.

## The gate (same order as .github/workflows/backend-ci.yml)

Run from `backend/` with `EYE_DEVICE=cpu EYE_MODE=demo EYE_MODEL_SOURCE=mock`:

```bash
ruff check                              # lint (CI runs it with no path)
mypy app                                # types
pytest -q -m "not model and not perf"   # default suite: what every gate runs
```

- `model` tests need a licensed checkpoint in `backend/models/`; `perf` is the latency guard. Neither runs by default. Never report them as passing if they were skipped.
- Single test: `pytest tests/contract/test_predict_contract.py::test_all_legacy_keys_present -q`
- Contract tests (`tests/contract/`) pin the wire format the deployed APK depends on. If one fails, the change is wrong, not the test. See the `api-contract` skill.

## Run locally

```bash
EYE_API_KEY=demo123 uvicorn app.main:app --port 8000          # demo mode, mock engine
API_URL=http://localhost:8000 EYE_API_KEY=demo123 streamlit run admin/dashboard.py
python scripts/make_test_images.py                             # writes scripts/out/ fixtures
bash scripts/smoke_test.sh http://localhost:8000 demo123       # needs curl + jq
```

Readiness probe: `GET /health/ready`. Real models: see the `model-training` skill (the env vars include `EYE_MODEL_SOURCE=torch` and `QUALITY_BLUR_MIN_VAR=8.0`).

## Docker parity (CI job 3)

```bash
docker build -t eye-backend:dev . && docker compose config -q
mkdir -p models && EYE_API_KEY=ci-not-a-secret docker compose up -d api
```

Use the same `EYE_API_KEY` for compose and for the smoke test, because a mismatch fails auth.

## Non-negotiables (from CLAUDE.md §7)

- `EYE_DEVICE=cpu` for every test, CI and Docker run. MPS is for dev only. Grad-CAM always runs on CPU.
- The quality gate runs before `engine.predict`. UNGRADABLE never calls the engine.
- Any DB write failure is `500 persistence_error`, in every mode.
- Never `torch.load(weights_only=False)`, never download models at runtime, and never return mock predictions outside `EYE_MODE=demo`.
