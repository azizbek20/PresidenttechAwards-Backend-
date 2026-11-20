"""Non-fundus analyses: external eye, skin, oral cavity, nails.

    GET  /api/v1/analysis/types       catalogue for the phone's picker
    POST /api/v1/analyze              multipart: file, analysis_type, patient_id?, body_site?
    GET  /api/v1/analyses             newest first (?patient_id=&analysis_type=&limit=)
    GET  /api/v1/analyses/{id}

Same safety order as ``/predict``: decode → model gate (no mock outside demo)
→ dedup replay → save original → quality gate → inference → persist. A failed
DB write is ``500 persistence_error``; the phone never sees an unsaved result.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, File, Form, Query, Request, UploadFile
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

import app.db.base as db_base
import app.inference.preprocess as preprocessing
import app.inference.quality as quality_gate
from app.analysis import analyzer as analyzers
from app.analysis.catalog import ANALYSIS_TYPES, TYPE_CODES, AnalysisType, get_type
from app.analysis.schemas import AnalysisTypeOut, AnalyzeResponse
from app.api.deps import semaphore_for
from app.api.predict import _clean, _read_capped
from app.config import get_settings
from app.core.errors import ApiError
from app.db import analysis_crud, crud, models
from app.inference.engine import ModelUnavailable
from app.storage import local as storage

logger = logging.getLogger("eyedetect.analyze")

router = APIRouter()

#: A high-risk condition at or above this probability escalates the overall
#: risk to "high" even when it is not the top class — missing a melanoma is
#: worse than an unnecessary referral.
HIGH_RISK_ESCALATION = 0.30

_D_TYPE = "Tahlil turi noto'g'ri — " + ", ".join(TYPE_CODES) + " dan birini tanlang"
_D_INVALID_IMAGE = "Rasm yaroqsiz yoki buzilgan — qayta suratga oling"
_D_INFERENCE = "Tahlil bajarilmadi — qayta urining"
_D_PERSISTENCE = "Natija saqlanmadi — qayta urining"
_D_MODEL = "Bu tahlil turi uchun model tayyor emas — administratorga murojaat qiling"
_D_NOT_FOUND = "So'ralgan yozuv topilmadi"
_D_BODY_SITE = "Tana qismi nomi juda uzun (64 belgidan oshmasin)"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def overall_risk(atype: AnalysisType, probs: list[float]) -> str:
    top, _ = analyzers.top_condition(atype, probs)
    if top.risk == "high":
        return "high"
    for cond, p in zip(atype.conditions, probs):
        if cond.risk == "high" and p >= HIGH_RISK_ESCALATION:
            return "high"
    return top.risk


def _findings(atype: AnalysisType, probs: list[float]) -> list[dict[str, Any]]:
    ranked = sorted(zip(atype.conditions, probs), key=lambda cp: float(cp[1]), reverse=True)
    return [
        {"code": c.code, "label": c.label, "probability": round(float(p), 4), "risk": c.risk}
        for c, p in ranked
    ]


def _find_duplicate(
    *, content_sha256: str, analysis_type: str, patient_code: str | None, window_min: int
) -> dict[str, Any] | None:
    if window_min <= 0:
        return None
    since = _utc_now() - timedelta(minutes=window_min)
    with db_base.get_session() as session:
        stmt = (
            select(models.Analysis)
            .where(models.Analysis.content_sha256 == content_sha256)
            .where(models.Analysis.analysis_type == analysis_type)
            .where(models.Analysis.created_at >= since)
            .order_by(models.Analysis.created_at.desc())
        )
        if patient_code:
            stmt = stmt.join(
                models.Patient, models.Analysis.patient_id == models.Patient.id
            ).where(models.Patient.patient_code == patient_code)
        row = session.execute(stmt.limit(1)).scalars().first()
        if row is None:
            return None
        return analysis_crud.analysis_to_wire(row, mode=get_settings().eye_mode)


def _persist(**kwargs: Any) -> dict[str, Any]:
    with db_base.get_session() as session:
        row = analysis_crud.create_analysis(session, **kwargs)
        return analysis_crud.analysis_to_wire(row, mode=get_settings().eye_mode)


@router.get("/analysis/types", response_model=list[AnalysisTypeOut])
async def list_types() -> list[AnalysisTypeOut]:
    model_dir = get_settings().eye_model_dir
    return [
        AnalysisTypeOut(
            code=t.code,
            label=t.label,
            description=t.description,
            asks_body_site=t.asks_body_site,
            model_ready=analyzers.is_real_model_available(t, model_dir),
            conditions=[c.label for c in t.conditions],
        )
        for t in ANALYSIS_TYPES
    ]


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    file: UploadFile = File(...),  # noqa: B008
    analysis_type: str = Form(...),
    patient_id: str | None = Form(default=None),
    body_site: str | None = Form(default=None),
) -> AnalyzeResponse:
    settings = get_settings()

    atype = get_type((analysis_type or "").strip())
    if atype is None:
        raise ApiError(422, "validation_error", _D_TYPE)
    patient_id = _clean(patient_id)
    body_site = _clean(body_site)
    if body_site is not None and len(body_site) > 64:
        raise ApiError(422, "validation_error", _D_BODY_SITE)

    raw = await _read_capped(request, file, settings.max_upload_bytes)
    if storage.sniff_ext(raw) is None:
        raise ApiError(400, "invalid_image", _D_INVALID_IMAGE)
    img = preprocessing.load_rgb(raw)
    if img is None:
        raise ApiError(400, "invalid_image", _D_INVALID_IMAGE)

    # Model gate before any state is read or written (same reasoning as C9 in
    # predict.py: a shadow deployment must never replay a stored mock result).
    try:
        model = analyzers.get_analyzer(
            atype, model_dir=settings.eye_model_dir, mode=settings.eye_mode
        )
    except ModelUnavailable as exc:
        logger.warning("analysis model unavailable for %s: %s", atype.code, exc)
        raise ApiError(503, "model_unavailable", _D_MODEL) from exc

    content_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        stored = await run_in_threadpool(
            _find_duplicate,
            content_sha256=content_sha256,
            analysis_type=atype.code,
            patient_code=patient_id,
            window_min=settings.dedup_window_min,
        )
    except Exception as exc:
        logger.exception("analysis dedup lookup failed")
        raise ApiError(500, "inference_error", _D_INFERENCE) from exc
    if stored is not None:
        logger.info("replaying analysis %s for a duplicate upload", stored["analysis_id"])
        return AnalyzeResponse.model_validate(stored)

    analysis_id = str(uuid4())
    try:
        _, image_url = await run_in_threadpool(storage.save_original, raw, analysis_id)
    except Exception as exc:
        logger.exception("failed to write the original image for analysis %s", analysis_id)
        raise ApiError(500, "inference_error", _D_INFERENCE) from exc

    report = await run_in_threadpool(quality_gate.assess, img, settings)

    findings: list[dict[str, Any]] = []
    risk_level = "ungradable"
    top_code: str | None = None
    probability: float | None = None
    if report.ok:
        try:
            async with semaphore_for(request.app):
                probs = await run_in_threadpool(model.predict, img)
        except Exception as exc:
            logger.exception("analysis inference failed (%s)", atype.code)
            raise ApiError(500, "inference_error", _D_INFERENCE) from exc
        top, probability = analyzers.top_condition(atype, probs)
        top_code = top.code
        risk_level = overall_risk(atype, probs)
        findings = _findings(atype, probs)

    patient_code = patient_id or crud.generate_patient_code()
    try:
        wire = await run_in_threadpool(
            _persist,
            analysis_id=analysis_id,
            patient_code=patient_code,
            analysis_type=atype.code,
            body_site=body_site,
            image_path=image_url,
            content_sha256=content_sha256,
            quality=report.quality,
            risk_level=risk_level,
            top_finding=top_code,
            probability=probability,
            findings=findings,
            model_version=model.model_version,
            processed_at=_utc_now(),
        )
    except Exception as exc:
        logger.exception("failed to persist analysis %s", analysis_id)
        raise ApiError(500, "persistence_error", _D_PERSISTENCE) from exc

    logger.info(
        "analysis %s type=%s risk=%s model=%s",
        analysis_id, atype.code, risk_level, model.model_version,
    )
    return AnalyzeResponse.model_validate(wire)


@router.get("/analyses", response_model=list[AnalyzeResponse])
async def list_analyses(
    patient_id: str | None = Query(default=None),
    analysis_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[AnalyzeResponse]:
    mode = get_settings().eye_mode

    def _read() -> list[dict[str, Any]]:
        with db_base.get_session() as session:
            rows = analysis_crud.list_analyses(
                session,
                patient_code=_clean(patient_id),
                analysis_type=_clean(analysis_type),
                limit=limit,
            )
            return [analysis_crud.analysis_to_wire(r, mode=mode) for r in rows]

    return [AnalyzeResponse.model_validate(r) for r in await run_in_threadpool(_read)]


@router.get("/analyses/{analysis_id}", response_model=AnalyzeResponse)
async def get_analysis(analysis_id: str) -> AnalyzeResponse:
    mode = get_settings().eye_mode

    def _read() -> dict[str, Any] | None:
        with db_base.get_session() as session:
            row = analysis_crud.get_analysis(session, analysis_id)
            return None if row is None else analysis_crud.analysis_to_wire(row, mode=mode)

    wire = await run_in_threadpool(_read)
    if wire is None:
        raise ApiError(404, "not_found", _D_NOT_FOUND)
    return AnalyzeResponse.model_validate(wire)
