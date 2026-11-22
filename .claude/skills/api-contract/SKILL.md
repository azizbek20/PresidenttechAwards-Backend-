---
name: api-contract
description: Keep the HTTP/JSON contract between the FastAPI backend (backend/app/schemas.py, analysis/schemas.py) and the Kotlin app (composeApp commonMain PredictResponse.kt, AnalysisApi.kt, ApiService.kt) in sync. Use whenever adding, renaming, removing or changing the type or nullability of any request/response field, error code, endpoint or header, or when a contract test or the app's JSON parsing fails.
---

# Backend ⇄ app wire contract

The deployed APK cannot be hot-fixed, so the wire format is **append-only**. A change that is safe in Python can still crash the phone.

## Where the contract lives

| Side | File | What |
|---|---|---|
| Backend (FROZEN) | `backend/app/schemas.py` | `PredictResponse` (15 legacy fields + `request_id`, `mode`), `TaskResponse`, `TaskStatusResponse`, `ExamSummary`, `ErrorEnvelope` |
| Backend | `backend/app/analysis/schemas.py` | `/analyze`, `/analyses`, `/analysis/types` |
| Backend (FROZEN) | `backend/app/core/errors.py` | error codes → HTTP status, envelope shape |
| Backend (FROZEN) | `backend/tests/fixtures/golden_predict.json` | golden response |
| App | `composeApp/src/commonMain/kotlin/com/eyedetect/ai/data/PredictResponse.kt` | `@Serializable` mirrors (snake_case via `@SerialName`) |
| App | `.../data/AnalysisApi.kt`, `.../data/ApiService.kt` | endpoints, multipart, headers |
| Pinning tests | `backend/tests/contract/test_predict_contract.py`, `test_error_envelope.py`, `test_error_detail_is_string.py`, `test_ungradable_wire.py` | |

Endpoints: `POST /predict`, `POST /predict/async`, `GET /predict/status/{task_id}`, `GET /exams`, `GET /exams/{id}`, `GET /analysis/types`, `POST /analyze`, `GET /analyses`, `GET /analyses/{id}`, `GET /health[/live|/ready]`. `/static` media has **no auth** on purpose.

## Rules

1. **Never rename or remove a JSON key.** Add new fields only, and only through an orchestrator-level change to the frozen `schemas.py` (backend/CLAUDE.md rule 2: stop and report rather than editing frozen files).
2. **No nullable wire fields that used to be non-null.** UNGRADABLE sends placeholders (`probability=0.0`, `icdr_grade=0`) because the APK crashes on null. The DB stores `NULL`, so wire and DB differ on purpose (C3).
3. **Error `detail` is always a short, human-readable Uzbek string**, never a list or object (the phone shows it). Error shape: `{"error": "<code>", "detail": "<text>"}`. No problem+json.
4. New Kotlin fields must have a default (`= null` or a value) so an older backend still parses. `ApiClient.kt` sets `ignoreUnknownKeys = true`, so the backend can add fields before the app knows them. That setting is what makes append-only safe, so don't remove it.
5. `decision` is a string enum on the app side (`REFER | NO_REFER | UNGRADABLE`). Adding a value means updating every branch over it: `ui/components/EyeComponents.kt`, `ui/theme/Color.kt`, `vision/OfflineDrClassifier.kt` (the offline verdict), plus `ResultScreenTest.kt` / `ScreeningViewModelTest.kt`.

## Checklist for any contract change

- [ ] Backend schema plus the pinning contract test updated (and the golden fixture, if frozen-kit rules allow)
- [ ] Kotlin `@Serializable` class updated with `@SerialName` and a default
- [ ] `ApiServiceTest.kt` covers parsing the new and the old payload
- [ ] `pytest -q -m "not model and not perf"` and `./gradlew :composeApp:testDebugUnitTest` both pass (skills `backend-verify` and `android-build`)
