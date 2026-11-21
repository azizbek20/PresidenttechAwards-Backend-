"""Celery worker for ``POST /api/v1/predict/async`` (steps 4-11).

Steps 1-3b (validation, decode, C9 gate, dedup) already ran in the API
process; this task runs the rest of the screening flow with the SAME helpers
as the synchronous ``/predict`` endpoint, so both paths produce identical
verdicts, files and database rows.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from celery import Celery
from celery.signals import worker_process_init

import app.api.predict as predict_flow
import app.inference.preprocess as preprocessing
import app.inference.quality as quality_gate
from app.config import get_settings
from app.db import crud
from app.inference.decision import decide
from app.inference.engine import InferenceEngine, get_engine
from app.storage import local as storage

logger = logging.getLogger("eyedetect.worker")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "sqla+sqlite:///celery_broker.db")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "db+sqlite:///celery_results.db")

celery_app = Celery("eyedetect_worker", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

_engine: InferenceEngine | None = None


def _get_engine() -> InferenceEngine:
    """Load the engine once per worker process (lazily if the signal did not fire)."""
    global _engine
    if _engine is None:
        _engine = get_engine(get_settings())
    return _engine


@worker_process_init.connect
def init_worker(**_kwargs: Any) -> None:
    _get_engine()
    logger.info("Celery worker initialised the inference engine.")


@celery_app.task(bind=True, name="process_exam_task")
def process_exam_task(
    self: Any,  # noqa: ARG001 - bound task signature
    exam_id: str,
    raw_bytes: bytes,
    patient_id: str | None,
    eye: str | None,
    idempotency_key: str | None,
    content_sha256: str,
) -> dict[str, Any]:
    """Run steps 4-11 and return the JSON-ready ``PredictResponse`` dict."""
    settings = get_settings()
    engine = _get_engine()

    img = preprocessing.load_rgb(raw_bytes)
    if img is None:
        raise ValueError(predict_flow._D_INVALID_IMAGE)

    # 4. original bytes on disk
    _, image_url = storage.save_original(raw_bytes, exam_id)

    # 5. quality gate on the full image
    report = quality_gate.assess(img, settings)

    # 6. inference only when the gate passed
    pred = None
    if report.ok:
        if not getattr(engine, "model_loaded", False):
            raise RuntimeError(predict_flow._D_MODEL)
        try:
            tensor = predict_flow._to_tensor(img, settings.engine_input_size)
            pred = engine.predict(tensor)
        except Exception as exc:
            logger.exception("inference failed for exam %s", exam_id)
            raise RuntimeError(predict_flow._D_INFERENCE) from exc

    # 7. verdict
    result = decide(pred, report.ok, settings.referable_threshold)

    # 8. heatmap: removed in the Claude migration (plan §3.1, §12.1)
    heatmap_url: str | None = None

    # 9. patient code is non-null from here on
    patient_code = patient_id or crud.generate_patient_code()

    # 10. unconditional persistence
    processed_at = predict_flow._utc_now()
    model_version = pred["model_version"] if pred else settings.eye_model_version
    predict_flow._persist(
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

    # 11. the frozen wire shape
    return predict_flow.wire_response(
        exam_id=exam_id,
        patient_code=patient_code,
        eye=eye,
        result=result,
        heatmap_url=heatmap_url,
        image_url=image_url,
        model_version=model_version,
        processed_at=processed_at,
        settings=settings,
    ).model_dump()
