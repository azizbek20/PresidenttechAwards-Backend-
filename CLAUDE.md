# CLAUDE.md — EYE DETECT AI

Diabetic-retinopathy screening demo: the phone photographs the fundus, the backend grades it (ICDR 0–4), and the app shows a traffic light, confidence and a Grad-CAM heatmap. It also does skin and other analyses and eye-care exercises.

| Path | What | Rules |
|---|---|---|
| `backend/` | FastAPI + SQLAlchemy + PyTorch/ONNX inference, Streamlit admin | `backend/CLAUDE.md` (hard rules, frozen files), `backend/SPEC.md` wins on conflicts |
| `composeApp/` | Kotlin Multiplatform / Jetpack Compose Android app (CameraX, MediaPipe, TFLite, Room+SQLCipher, WorkManager) | README.md, PLAN.md |
| `training/` | DR and skin model training/eval (separate CUDA venv) | training/README.md |
| `docs/superpowers/` | past design specs and plans | |

User-visible strings (app UI and API error `detail`) are **Uzbek**. The app also ships `ru` and `en`.
Code style guide: `clean-code-solid-dry-kiss.md`.

## Project skills (`.claude/skills/`)

- `backend-verify`: CI-identical backend gate (ruff, mypy, pytest markers, smoke, docker) and how to run the API and admin locally.
- `android-build`: Gradle tasks, `local.properties` keys, debug vs release URL, Android pitfalls.
- `api-contract`: backend ⇄ Kotlin wire contract. Use it for **any** request/response field change.
- `model-training`: train/eval/export/deploy models, licence and quality-gate rules.

Global skills that fit this repo, if installed: `fastapi`, `async-python-patterns`, `python-resilience`, `python-background-jobs`, `security-audit`, `ml-training-recipes`, `superpowers:test-driven-development`, `superpowers:systematic-debugging`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- A committed graphify-out/graph.json is rewritten whole on every build, so a large diff to it in a pull request is expected. Do not flag it as churn or suggest skipping the graph rebuild or its hooks.
