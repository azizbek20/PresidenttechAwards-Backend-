"""Exam history endpoints (spec §5-C C5).

The list feeds the Streamlit admin panel (step 5 of the demo script, C5); the
detail endpoint returns the *same* shape as ``POST /predict`` so a client can
reuse one parser. Neither Android app calls them (phone history is local).

Admin key: together they expose every exam of every phone and its photo URL,
while the app key (``X-API-Key``) ships inside the APK and can be extracted.
With ``EYE_ADMIN_API_KEY`` set they also require ``X-Admin-Key``; the app key
is still checked first by the ``/api/v1`` router (401), then this one (403).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, Query
from starlette.concurrency import run_in_threadpool

import app.db.base as db_base  # Agent B; arrives at the Phase 2 merge.
from app.api.deps import fill_additive_keys
from app.config import get_settings
from app.core.errors import ApiError
from app.core.security import UNAUTHORIZED_DETAIL, verify_api_key
from app.db import crud
from app.schemas import ExamSummary, PredictResponse


async def require_admin_key(
    x_admin_key: str | None = Header(default=None, alias="X-Admin-Key"),
) -> None:
    """403 unless the configured admin key was presented (no-op when unset)."""
    if not verify_api_key(x_admin_key, get_settings().eye_admin_api_key):
        raise ApiError(403, "unauthorized", UNAUTHORIZED_DETAIL)


router = APIRouter(dependencies=[Depends(require_admin_key)])

_D_NOT_FOUND = "So'ralgan yozuv topilmadi"

#: Hard ceiling from the spec: a page bigger than this is a scrape, not a UI.
MAX_LIMIT = 100


def _list(limit: int, offset: int, patient_code: str | None) -> list[dict[str, Any]]:
    with db_base.get_session() as session:
        return crud.list_exams(
            session, limit=limit, offset=offset, patient_code=patient_code
        )


def _detail(exam_id: str) -> dict[str, Any] | None:
    with db_base.get_session() as session:
        return crud.get_exam(session, exam_id)


@router.get("/exams", response_model=list[ExamSummary])
async def list_exams(
    limit: int = Query(default=50, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    patient_id: str | None = Query(default=None),
) -> list[ExamSummary]:
    rows = await run_in_threadpool(_list, limit, offset, patient_id)
    # Rows are predict-shaped; ExamSummary keeps the subset the list views need.
    return [ExamSummary.model_validate(row) for row in rows]


@router.get("/exams/{exam_id}", response_model=PredictResponse)
async def get_exam(exam_id: str) -> PredictResponse:
    row = await run_in_threadpool(_detail, exam_id)
    if row is None:
        raise ApiError(404, "not_found", _D_NOT_FOUND)
    return PredictResponse.model_validate(fill_additive_keys(dict(row), get_settings()))
