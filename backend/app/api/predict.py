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
from app.schemas import DISCLAIMER, Decision, Eye, PredictResponse, Quality, TaskResponse
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


@router.post("/predict", response_model=TaskResponse)
async def predict(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008 - FastAPI's declaration style
    patient_id: str | None = Form(default=None),
    eye: str | None = Form(default=None),
) -> TaskResponse:
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

    # ---- 3c. C9 gate: refuse before ANY state is read or written ---------
    # §4.9: "predict returns 503 model_unavailable — it never serves mock
    # output." This must sit ABOVE the replay in 3b, not merely outside the
    # `report.ok` branch below. A model-less shadow deployment sharing a
    # database with an earlier demo run would otherwise REPLAY a stored
    # mock-v0 exam: verified reachable end-to-end, returning
    # 200 {"model_version": "mock-v0", "mode": "shadow"} — precisely the
    # "answering as though a model were loaded" that C9 forbids. It is a
    # realistic configuration because the compose volume survives `down`,
    # EYE_MODE is a .env flip, and DEDUP_WINDOW_MIN reaches 1440 minutes.
    #
    # Placing it here (after decode, before dedup and before step 4's write)
    # also means a refused request stores no orphan original on disk.
    # A payload that is not an image at all still gets 400 from step 3: that
    # needs no model to reject and produces no verdict, so C9's harm cannot
    # occur.
    engine = engine_for(request.app)
    if not getattr(engine, "model_loaded", False):
        raise ApiError(503, "model_unavailable", _D_MODEL)

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
        return TaskResponse(
            task_id=f"replay:{stored.get('exam_id')}",
            status="PROCESSING",
            message="Natija topildi, tayyorlanmoqda..."
        )

    # ---- 4. Celery Task Dispatch -----------------------------------------
    exam_id = str(uuid4())
    
    # Send task to celery worker
    from app.worker import process_exam_task
    task = process_exam_task.delay(
        exam_id, raw, patient_id or "", eye or "right", idempotency_key or "", content_sha256
    )

    from app.schemas import TaskResponse
    return TaskResponse(
        task_id=task.id,
        status="PENDING",
        message="Rasm qabul qilindi, ishlov berilmoqda..."
    )


from app.schemas import TaskStatusResponse
from celery.result import AsyncResult

@router.get("/predict/status/{task_id}", response_model=TaskStatusResponse)
async def get_predict_status(task_id: str) -> TaskStatusResponse:
    if task_id.startswith("replay:"):
        exam_id = task_id.split(":", 1)[1]
        with db_base.get_session() as session:
            exam = crud.get_exam(session, exam_id)
            if exam:
                from app.api.deps import fill_additive_keys
                settings = get_settings()
                result = PredictResponse.model_validate(fill_additive_keys(dict(exam), settings))
                return TaskStatusResponse(task_id=task_id, status="SUCCESS", result=result)
            return TaskStatusResponse(task_id=task_id, status="FAILURE", error="Replay not found")

    from app.worker import celery_app
    task_result = AsyncResult(task_id, app=celery_app)
    
    if task_result.state == "PENDING" or task_result.state == "STARTED":
        return TaskStatusResponse(task_id=task_id, status="PROCESSING")
    elif task_result.state == "SUCCESS":
        return TaskStatusResponse(
            task_id=task_id, 
            status="SUCCESS", 
            result=task_result.result
        )
    else:
        return TaskStatusResponse(
            task_id=task_id, 
            status="FAILURE", 
            error=str(task_result.info)
        )


def _to_tensor(img: Any, size: int) -> Any:
    """Crop to the retina, then normalise to the engine's input tensor.

    Runs in the threadpool: both steps are OpenCV/NumPy work that would
    otherwise block the event loop for every concurrent request.
    """
    return preprocessing.to_model_input(preprocessing.retina_crop(img), size)
