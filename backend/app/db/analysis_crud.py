"""Persistence for :class:`app.db.models.Analysis` (non-fundus analyses).

Kept out of the frozen ``crud.py``; reuses its patient helpers so a patient
code means the same patient across DR exams and these analyses.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.analysis.catalog import ANALYSIS_DISCLAIMER, get_type, recommendation
from app.analysis.analyzer import MOCK_VERSION
from app.db import crud, models


def create_analysis(
    session: Any,
    *,
    analysis_id: str,
    patient_code: str,
    analysis_type: str,
    body_site: str | None,
    image_path: str,
    content_sha256: str,
    quality: str,
    risk_level: str,
    top_finding: str | None,
    probability: float | None,
    findings: list[dict[str, Any]],
    model_version: str,
    processed_at: datetime,
) -> models.Analysis:
    patient = crud.get_or_create_patient(session, patient_code)
    row = models.Analysis(
        id=analysis_id,
        patient_id=patient.id,
        analysis_type=analysis_type,
        body_site=body_site,
        image_path=image_path,
        content_sha256=content_sha256,
        quality=quality,
        risk_level=risk_level,
        top_finding=top_finding,
        probability=probability,
        findings_json=json.dumps(findings, ensure_ascii=False),
        model_version=model_version,
        created_at=processed_at,
    )
    session.add(row)
    session.add(
        models.AuditLog(
            action="analysis_created",
            exam_id=analysis_id,
            detail=f"{analysis_type}:{risk_level}",
        )
    )
    session.flush()
    return row


def analysis_to_wire(row: models.Analysis, *, mode: str) -> dict[str, Any]:
    atype = get_type(row.analysis_type)
    findings = json.loads(row.findings_json or "[]")
    top = findings[0] if findings else None
    return {
        "analysis_id": row.id,
        "analysis_type": row.analysis_type,
        "analysis_label": atype.label if atype else row.analysis_type,
        "patient_id": row.patient.patient_code if row.patient is not None else "",
        "body_site": row.body_site or "",
        "risk_level": row.risk_level,
        "top_finding": row.top_finding or "",
        "top_label": top["label"] if top else "Baholab bo'lmadi",
        "probability": float(row.probability or 0.0),
        "findings": findings,
        "recommendation": recommendation(atype, row.risk_level) if atype else "",
        "quality": row.quality,
        "image_url": models.static_url(row.image_path, "images") or "",
        "model_version": row.model_version,
        "processed_at": models.iso_z(row.created_at),
        "disclaimer": ANALYSIS_DISCLAIMER,
        "is_demo": row.model_version.startswith("mock") or row.model_version == MOCK_VERSION,
        "request_id": models.new_uuid(),
        "mode": mode,
    }


def list_analyses(
    session: Any,
    *,
    patient_code: str | None = None,
    analysis_type: str | None = None,
    limit: int = 50,
) -> list[models.Analysis]:
    stmt = select(models.Analysis).order_by(models.Analysis.created_at.desc())
    if patient_code:
        stmt = stmt.join(models.Patient, models.Analysis.patient_id == models.Patient.id).where(
            models.Patient.patient_code == patient_code
        )
    if analysis_type:
        stmt = stmt.where(models.Analysis.analysis_type == analysis_type)
    return list(session.execute(stmt.limit(limit)).scalars().unique())


def get_analysis(session: Any, analysis_id: str) -> models.Analysis | None:
    return session.get(models.Analysis, analysis_id)
