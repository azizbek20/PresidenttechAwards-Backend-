"""Exam history endpoints (spec §5-C C5).

The list feeds the Streamlit admin panel (step 5 of the demo script, C5) and
the phone's History screen; the detail endpoint returns the *same* shape as
``POST /predict`` so the client can reuse one parser.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from starlette.concurrency import run_in_threadpool

import app.db.base as db_base  # Agent B; arrives at the Phase 2 merge.
from app.api.deps import fill_additive_keys
from app.config import get_settings
from app.core.errors import ApiError
from app.db import crud
from app.schemas import ExamSummary, PredictResponse

router = APIRouter()

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
