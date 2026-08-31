import os
import logging
from celery import Celery
from celery.signals import worker_process_init
from datetime import datetime, timezone
import hashlib
from uuid import uuid4

from app.config import get_settings
from app.inference.engine import get_engine, ModelUnavailable
from app.storage import local as storage
from app.inference import preprocess as preprocessing
from app.inference import quality as quality_gate
from app.inference.decision import decide
from app.db import crud
import app.db.base as db_base
import app.inference.gradcam as heatmaps
from app.schemas import DISCLAIMER

logger = logging.getLogger("eyedetect.worker")

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "sqla+sqlite:///celery_broker.db")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "db+sqlite:///celery_results.db")

celery_app = Celery("eyedetect_worker", broker=CELERY_BROKER_URL, backend=CELERY_RESULT_BACKEND)

engine = None

@worker_process_init.connect
def init_worker(**kwargs):
    global engine
    settings = get_settings()
    engine = get_engine(settings)
    logger.info("Celery Worker initialized inference engine.")

def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)

def _wire_time(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

@celery_app.task(bind=True, name="process_exam_task")
def process_exam_task(self, exam_id: str, raw_bytes: bytes, patient_id: str, eye: str, idempotency_key: str, content_sha256: str):
    """
    Synchronous Celery task that processes an exam.
    Returns the JSON-serializable PredictResponse dictionary.
    """
    global engine
    settings = get_settings()

    # 3. Decode
    img = preprocessing.load_rgb(raw_bytes)
    if img is None:
        raise ValueError("Invalid image bytes")

    # 4. Identity + save original
    _, image_url = storage.save_original(raw_bytes, exam_id)

    # 5. Quality Gate
    report = quality_gate.assess(img, settings)

    # 6. Inference
    pred = None
    tensor = None
    if report.ok:
        try:
            tensor = preprocessing.to_model_input(preprocessing.retina_crop(img), settings.engine_input_size)
            pred = engine.predict(tensor)
        except Exception as exc:
            logger.exception("inference failed for exam %s", exam_id)
            raise RuntimeError("Inference error") from exc

    # 7. Decision
    result = decide(pred, report.ok, settings.referable_threshold)

    # 8. Heatmap
    heatmap_url = None
    if report.ok:
        heatmap_path, candidate_url = storage.heatmap_target(exam_id)
        model = getattr(engine, "model", None)
        try:
            display = preprocessing.display_copy(img)
            if model is not None and tensor is not None and heatmaps.render_heatmap(model, tensor, display, heatmap_path):
                heatmap_url = candidate_url
            elif heatmaps.mock_heatmap(display, heatmap_path):
                heatmap_url = candidate_url
        except Exception:
            logger.warning("heatmap rendering failed", exc_info=True)

    # 9. Patient code
    patient_code = patient_id or crud.generate_patient_code()
    processed_at = _utc_now()
    model_version = pred["model_version"] if pred else settings.eye_model_version

    # 10. Persistence
    with db_base.get_session() as session:
        crud.create_exam_with_result(
            session,
            exam_id=exam_id,
            patient_code=patient_code,
            eye=eye,
            image_path=image_url,
            content_sha256=content_sha256,
            quality=result.quality,
            blur_var=report.blur_var,
            mean_gray=report.mean_gray,
            result=result,
            model_version=model_version,
            heatmap_path=heatmap_url,
            processed_at=processed_at,
            idempotency_key=idempotency_key,
        )

    return {
        "exam_id": exam_id,
        "patient_id": patient_code,
        "eye": eye,
        "referable": result.referable,
        "probability": result.probability,
        "icdr_grade": result.icdr_grade,
        "grade_label": result.grade_label,
        "decision": result.decision,
        "decision_text": result.decision_text,
        "quality": result.quality,
        "heatmap_url": heatmap_url,
        "image_url": image_url,
        "model_version": model_version,
        "processed_at": _wire_time(processed_at),
        "disclaimer": DISCLAIMER,
        "request_id": str(uuid4()),
        "mode": settings.eye_mode,
    }
