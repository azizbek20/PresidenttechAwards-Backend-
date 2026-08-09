"""``POST /api/v1/predict`` — the whole screening flow (spec §5-C C4).

The step numbers in the code are the spec's step numbers; keeping them visible
is the cheapest way to prove at review time that no step was reordered. The
ordering carries real safety weight:

* the quality gate (step 5) runs on the FULL image and BEFORE the DR engine,
  so a blurry photo is UNGRADABLE without ``engine.predict`` ever being
  called (pinned by ``tests/contract/test_engine_spy.py``);
* the dedup lookup (step 3b) runs before inference, so a client retry of the
  same bytes replays the stored verdict instead of burning a second inference
  and creating a second exam (C14);
* persistence (step 10) is unconditional — a result the admin panel cannot
  corroborate never reaches the phone (C10).

Agent A (`preprocess`, `quality`, `gradcam`) and Agent B (`db.base`, the
`crud` bodies) supply the modules imported below; this file only orchestrates
them against the frozen signatures.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from starlette.concurrency import run_in_threadpool

# Agent A delivers `preprocess`/`quality`/`gradcam` and Agent B delivers
# `db.base` at the Phase 2 merge. They are imported as modules (not as loose
# functions) so tests can substitute them by dotted string, and aliased so the
# import form stays resolvable for the type checker on every branch.
import app.db.base as db_base
import app.inference.gradcam as heatmaps
import app.inference.preprocess as preprocessing
import app.inference.quality as quality_gate
from app.api.deps import engine_for, fill_additive_keys, semaphore_for
from app.config import Settings, get_settings
from app.core.errors import ApiError
from app.db import crud
from app.inference.decision import DecisionResult, decide
from app.inference.engine import ModelUnavailable
from app.schemas import DISCLAIMER, Decision, Eye, PredictResponse, Quality
from app.storage import local as storage

logger = logging.getLogger("eyedetect.predict")

router = APIRouter()

#: Upload is drained a megabyte at a time so the cap is enforced *while*
#: reading, never after buffering the whole body (C11).
READ_CHUNK = 1024 * 1024

_VALID_EYES: tuple[str | None, ...] = (None, "right", "left")

# --- C15: every one of these is shown verbatim to the user on the phone. ---
_D_EYE = "Ko'z noto'g'ri — 'right' yoki 'left' bo'lishi kerak"
_D_INVALID_IMAGE = "Rasm yaroqsiz yoki buzilgan — qayta suratga oling"
_D_INFERENCE = "Tahlil bajarilmadi — qayta urining"
_D_PERSISTENCE = "Natija saqlanmadi — qayta urining"
_D_MODEL = "Model tayyor emas — administratorga murojaat qiling"
_D_IDEMPOTENCY = "Bu kalit boshqa rasm uchun ishlatilgan"


def _clean(value: str | None) -> str | None:
    """Blank form fields arrive as ``""``; treat them as absent."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _too_large_detail(settings: Settings) -> str:
    return f"Rasm hajmi juda katta — {settings.max_upload_mb} MB dan oshmasin"


def _utc_now() -> datetime:
    """Whole-second UTC: the wire format has no sub-second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0)


def _wire_time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


async def _read_capped(request: Request, file: UploadFile, cap: int) -> bytes:
    """Step 2: reject on Content-Length, then stream with a hard byte cap."""
    settings = get_settings()

    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > cap:
                raise ApiError(413, "payload_too_large", _too_large_detail(settings))
        except ValueError:
            # An unparsable Content-Length is not a reason to reject; the
            # chunked read below is the authoritative limit either way.
            logger.warning("ignoring unparsable Content-Length %r", declared)

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(READ_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > cap:
            # Abort the moment the cap is crossed — never buffer-then-check.
            raise ApiError(413, "payload_too_large", _too_large_detail(settings))
        chunks.append(chunk)

    if total == 0:
        raise ApiError(400, "invalid_image", _D_INVALID_IMAGE)
    return b"".join(chunks)


def _lookup_replay(
    *,
    content_sha256: str,
    idempotency_key: str | None,
    patient_code: str | None,
    eye: str | None,
    window_min: int,
) -> tuple[str, dict[str, Any] | None]:
    """Step 3b (C14). Returns ``("replay", row)``, ``("conflict", None)`` or
    ``("miss", None)``.

    KNOWN DEMO LIMITATION, deliberately not hidden: this is a check-then-insert,
    so two *truly concurrent* uploads of identical bytes can both miss the
    lookup and both insert. The window is milliseconds wide and the real-world
    trigger (a phone retry after a timeout) is strictly sequential, so the
    pilot phase adds row locking / a unique constraint rather than this phase
    paying for it.
    """
    with db_base.get_session() as session:
        if idempotency_key:
            found = crud.find_by_idempotency_key(
                session, idempotency_key=idempotency_key, window_min=window_min
            )
            if found is None:
                return "miss", None
            stored_row, stored_sha = found
            if stored_sha != content_sha256:
                # Same key, different bytes: the client reused a key it must
                # not have. Answering 200 with the old result would show the
                # wrong eye's verdict for the new photo.
                return "conflict", None
            return "replay", dict(stored_row)

        prior = crud.find_recent_duplicate(
            session,
            content_sha256=content_sha256,
            patient_code=patient_code,
            eye=eye,
            window_min=window_min,
        )
        if prior is None:
            return "miss", None
        return "replay", dict(prior)


def _render_heatmap(
    engine: Any, img: Any, tensor: Any, out_path: Path
) -> bool:
    """Step 8, best effort: a missing heatmap is never a failed screening."""
    try:
        display = preprocessing.display_copy(img)
        model = getattr(engine, "model", None)
        # A real torch model gets Grad-CAM; the mock path gets the stand-in
        # overlay, and a failed render just means no heatmap.
        if model is not None and tensor is not None and heatmaps.render_heatmap(
            model, tensor, display, out_path
        ):
            return True
        return bool(heatmaps.mock_heatmap(display, out_path))
    except Exception:
        logger.warning("heatmap rendering failed", exc_info=True)
        return False


def _persist(
    *,
    exam_id: str,
    patient_code: str,
    eye: str | None,
    image_url: str,
    content_sha256: str,
    result: DecisionResult,
    blur_var: float | None,
    mean_gray: float | None,
    model_version: str,
    heatmap_url: str | None,
    processed_at: datetime,
    idempotency_key: str | None,
) -> None:
    """Step 10. One transaction, owned by Agent B's ``crud``.

    ``image_path``/``heatmap_path`` are stored as the PUBLIC ``/static/...``
    URLs, because ``crud.get_exam`` has to reconstruct ``image_url`` and
    ``heatmap_url`` for the wire and the filesystem location is derivable from
    the exam id anyway.
    """
    with db_base.get_session() as session:
        crud.create_exam_with_result(
            session,
            exam_id=exam_id,
            patient_code=patient_code,
            eye=eye,
            image_path=image_url,
            content_sha256=content_sha256,
            quality=result.quality,
            blur_var=blur_var,
            mean_gray=mean_gray,
            result=result,
            model_version=model_version,
            heatmap_path=heatmap_url,
            processed_at=processed_at,
            idempotency_key=idempotency_key,
        )


@router.post("/predict", response_model=PredictResponse)
async def predict(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI's declaration style
    patient_id: str | None = Form(default=None),
    eye: str | None = Form(default=None),
) -> PredictResponse:
    settings = get_settings()

    # ---- 1. eye validation ------------------------------------------------
    eye = _clean(eye)
    if eye not in _VALID_EYES:
        raise ApiError(422, "validation_error", _D_EYE)
    patient_id = _clean(patient_id)

    # ---- 2. capped streaming read ----------------------------------------
    raw = await _read_capped(request, file, settings.max_upload_bytes)

    # ---- 3. format sniff + decode ----------------------------------------
    if storage.sniff_ext(raw) is None:
        raise ApiError(400, "invalid_image", _D_INVALID_IMAGE)
    img = preprocessing.load_rgb(raw)
    if img is None:
        raise ApiError(400, "invalid_image", _D_INVALID_IMAGE)

    # ---- 3b. dedup / idempotency (C14) -----------------------------------
    content_sha256 = hashlib.sha256(raw).hexdigest()
    idempotency_key = request.headers.get("Idempotency-Key")
    outcome, stored = await run_in_threadpool(
        _lookup_replay,
        content_sha256=content_sha256,
        idempotency_key=idempotency_key,
        patient_code=patient_id,
        eye=eye,
        window_min=settings.dedup_window_min,
    )
    if outcome == "conflict":
        raise ApiError(409, "idempotency_conflict", _D_IDEMPOTENCY)
    if outcome == "replay" and stored is not None:
        logger.info("replaying exam %s for a duplicate upload", stored.get("exam_id"))
        return PredictResponse.model_validate(fill_additive_keys(stored, settings))

    # ---- 4. identity + original bytes on disk ----------------------------
    exam_id = str(uuid4())
    _, image_url = await run_in_threadpool(storage.save_original, raw, exam_id)

    # ---- 5. quality gate, on the FULL image, before any crop -------------
    report = await run_in_threadpool(quality_gate.assess, img, settings)

    # ---- 6. inference, only when the gate passed -------------------------
    pred = None
    tensor = None
    engine = engine_for(request.app)
    if report.ok:
        if not getattr(engine, "model_loaded", False):
            # C9: shadow mode without a verified artifact refuses to answer.
            # It never falls back to a mock prediction.
            raise ApiError(503, "model_unavailable", _D_MODEL)
        try:
            tensor = await run_in_threadpool(
                _to_tensor, img, settings.engine_input_size
            )
            # `async with` (not acquire/release): a client that navigates away
            # mid-request is cancelled here, and the permit must still come
            # back or the server dies of slow permit exhaustion (C16).
            async with semaphore_for(request.app):
                pred = await run_in_threadpool(engine.predict, tensor)
        except ModelUnavailable as exc:
            raise ApiError(503, "model_unavailable", _D_MODEL) from exc
        except ApiError:
            raise
        except Exception as exc:
            logger.exception("inference failed for exam %s", exam_id)
            raise ApiError(500, "inference_error", _D_INFERENCE) from exc

    # ---- 7. verdict (threshold lives server-side, only here) -------------
    result = decide(pred, report.ok, settings.referable_threshold)

    # ---- 8. heatmap, best effort ------------------------------------------
    heatmap_url: str | None = None
    if report.ok:
        heatmap_path, candidate_url = storage.heatmap_target(exam_id)
        if await run_in_threadpool(
            _render_heatmap, engine, img, tensor, heatmap_path
        ):
            heatmap_url = candidate_url

    # ---- 9. C2: the patient code is non-null from here on ----------------
    patient_code = patient_id or crud.generate_patient_code()

    # ---- 10. unconditional persistence (C10) -----------------------------
    processed_at = _utc_now()
    model_version = pred["model_version"] if pred else settings.eye_model_version
    try:
        await run_in_threadpool(
            _persist,
            exam_id=exam_id,
            patient_code=patient_code,
            eye=eye,
            image_url=image_url,
            content_sha256=content_sha256,
            result=result,
            blur_var=report.blur_var,
            mean_gray=report.mean_gray,
            model_version=model_version,
            heatmap_url=heatmap_url,
            processed_at=processed_at,
            idempotency_key=idempotency_key,
        )
    except Exception as exc:  # C10 is unconditional: ANY failure is a 500.
        logger.exception("persistence failed for exam %s", exam_id)
        raise ApiError(500, "persistence_error", _D_PERSISTENCE) from exc

    # ---- 11. the frozen wire shape ---------------------------------------
    return PredictResponse(
        exam_id=exam_id,
        patient_id=patient_code,
        eye=cast("Eye | None", eye),
        referable=result.referable,
        probability=result.probability,
        icdr_grade=result.icdr_grade,
        grade_label=result.grade_label,
        decision=cast("Decision", result.decision),
        decision_text=result.decision_text,
        quality=cast("Quality", result.quality),
        heatmap_url=heatmap_url,
        image_url=image_url,
        model_version=model_version,
        processed_at=_wire_time(processed_at),
        disclaimer=DISCLAIMER,
        request_id=str(uuid4()),
        mode=settings.eye_mode,
    )


def _to_tensor(img: Any, size: int) -> Any:
    """Crop to the retina, then normalise to the engine's input tensor.

    Runs in the threadpool: both steps are OpenCV/NumPy work that would
    otherwise block the event loop for every concurrent request.
    """
    return preprocessing.to_model_input(preprocessing.retina_crop(img), size)
