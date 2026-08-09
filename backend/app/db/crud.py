"""Frozen CRUD signatures (spec §4.7). Agent B implements the bodies.

Agents C and D code AGAINST these signatures and must not change them.

Two orchestrator-level notes (§0 rule 2 permits ADDING at this level, never
renaming):

1. ``generate_patient_code`` is implemented here rather than left to Agent B.
   Its body *is* the C2 contract (``^P-[0-9A-F]{6}$``, asserted by
   ``test_patient_autogen.py`` and by ``smoke_test.sh`` step 4), it touches no
   database, and a divergent implementation would break the wire contract.

2. ``find_by_idempotency_key`` is ADDED. §4.7 only lets callers look up by
   content fingerprint, but §5-C's ``test_duplicate_retry.py`` also requires
   "same ``Idempotency-Key`` + different bytes -> 409 ``idempotency_conflict``",
   which is undetectable unless the stored content hash for that key can be
   read back. Returning ``(response, content_sha256)`` keeps the predict-shaped
   dict clean instead of smuggling private keys into it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import models

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.db.models import Patient
    from app.inference.decision import DecisionResult

#: How many times a *generated* patient code may collide before we give up.
#: uuid4-derived codes have ~16.7M values, so two collisions in a row already
#: means something is badly wrong.
_CODE_COLLISION_ATTEMPTS = 8


def _wire(exam: models.Exam) -> dict:
    """Predict-shaped dict for one exam. ``mode`` is the server's current mode."""
    return models.exam_to_wire(exam, mode=get_settings().eye_mode)


def _select_by_patient_code(stmt: Select[Any], patient_code: str | None) -> Select[Any]:
    """Filter an ``exams`` select on the owning patient's code.

    ``patient_code=None`` deliberately means *unconstrained*, not "patient IS
    NULL". Every stored exam has a patient: C2 says a blank ``patient_id``
    gets a freshly generated ``P-XXXXXX``, and a *different* one per request.
    So the dedup key for a client that sends no patient ID can only be
    (fingerprint, eye) — matching on NULL would never hit and every retry of a
    blank-ID capture would create a second exam, which is exactly the C14
    duplicate the phone gate (§6 G6) checks for.
    """
    if patient_code is None:
        return stmt
    return stmt.join(
        models.Patient, models.Exam.patient_id == models.Patient.id
    ).where(models.Patient.patient_code == patient_code)


def _newest_exam_within(
    session: Any, stmt: Select[Any], window_min: int
) -> models.Exam | None:
    """Newest exam matching ``stmt`` whose ``created_at`` is inside the window."""
    cutoff = models.utcnow() - timedelta(minutes=window_min)
    stmt = (
        stmt.where(models.Exam.created_at >= cutoff)
        .order_by(models.Exam.created_at.desc(), models.Exam.id.desc())
        .limit(1)
    )
    return session.execute(stmt).unique().scalars().first()


def _create_patient_with_generated_code(session: Any) -> Patient:
    """Insert a patient under a fresh C2 code, regenerating on collision."""
    for _ in range(_CODE_COLLISION_ATTEMPTS):
        patient = models.Patient(
            id=models.new_uuid(),
            patient_code=generate_patient_code(),
            created_at=models.utcnow(),
        )
        try:
            with session.begin_nested():
                session.add(patient)
                session.flush()
        except IntegrityError:
            continue  # regenerate and retry
        return patient
    raise RuntimeError(
        "could not generate a free patient code in "
        f"{_CODE_COLLISION_ATTEMPTS} attempts"
    )


def generate_patient_code() -> str:
    """'P-' + uuid4().hex[:6].upper()  (C2). FROZEN BODY — do not modify."""
    return "P-" + uuid.uuid4().hex[:6].upper()


def get_or_create_patient(session: Any, patient_code: str) -> "Patient":
    stmt = select(models.Patient).where(models.Patient.patient_code == patient_code)
    existing = session.execute(stmt).scalars().first()
    if existing is not None:
        return existing

    patient = models.Patient(
        id=models.new_uuid(), patient_code=patient_code, created_at=models.utcnow()
    )
    try:
        # A savepoint, so losing the race costs us the INSERT and not the
        # caller's whole transaction.
        with session.begin_nested():
            session.add(patient)
            session.flush()
    except IntegrityError:
        # Someone else inserted this code between our SELECT and our INSERT.
        # The unique constraint is the arbiter; adopt the winner's row.
        winner = session.execute(stmt).scalars().first()
        if winner is None:  # pragma: no cover - not a uniqueness violation then
            raise
        return winner
    return patient


def create_exam_with_result(
    session: Any,
    *,
    exam_id: str,
    patient_code: str | None,
    eye: str | None,
    image_path: str,
    content_sha256: str,
    quality: str,
    blur_var: float | None,
    mean_gray: float | None,
    result: "DecisionResult",
    model_version: str,
    heatmap_path: str | None,
    processed_at: datetime,
    idempotency_key: str | None = None,
) -> None:
    """One transaction. patient_code may already be server-generated by caller.

    Writes ``result.db_probability`` / ``result.db_icdr_grade`` (NULL for
    UNGRADABLE, C3) while ``referable``/``decision`` are always stored, and
    appends one ``audit_log`` row (``action='predict'``) in the same
    transaction.
    """
    # "may already be server-generated by caller" — if it was not, generate it
    # here, retrying on the (astronomically rare) code collision.
    if patient_code is None:
        patient = _create_patient_with_generated_code(session)
    else:
        patient = get_or_create_patient(session, patient_code)

    stamped = models.as_utc(processed_at)
    session.add(
        models.Exam(
            id=exam_id,
            patient_id=patient.id,
            eye=eye,
            image_path=image_path,
            heatmap_path=heatmap_path,
            content_sha256=content_sha256,
            idempotency_key=idempotency_key,
            quality=quality,
            blur_var=blur_var,
            mean_gray=mean_gray,
            created_at=stamped,
        )
    )
    session.add(
        models.Result(
            id=models.new_uuid(),
            exam_id=exam_id,
            # C3: NULL for UNGRADABLE, so training exports stay clean...
            probability=result.db_probability,
            icdr_grade=result.db_icdr_grade,
            # ...while the verdict itself is always stored.
            referable=result.referable,
            decision=result.decision,
            decision_text=result.decision_text,
            model_version=model_version,
            created_at=stamped,
        )
    )
    session.add(
        models.AuditLog(
            id=models.new_uuid(),
            ts=models.utcnow(),
            action="predict",
            exam_id=exam_id,
            detail=(
                f"decision={result.decision} quality={quality} "
                f"model={model_version}"
            ),
        )
    )
    session.flush()
    # C10: the phone must never see a result the admin panel cannot corroborate,
    # so the row is durable before this returns rather than at some later
    # unwind. Committing here is idempotent w.r.t. an outer ``get_session()``.
    session.commit()


def find_recent_duplicate(
    session: Any,
    *,
    content_sha256: str,
    patient_code: str | None,
    eye: str | None,
    window_min: int,
) -> dict | None:
    """C14: predict-shaped dict of the newest matching exam inside the window, else None."""
    stmt = select(models.Exam).where(models.Exam.content_sha256 == content_sha256)
    if eye is None:
        stmt = stmt.where(models.Exam.eye.is_(None))
    else:
        stmt = stmt.where(models.Exam.eye == eye)
    stmt = _select_by_patient_code(stmt, patient_code)

    exam = _newest_exam_within(session, stmt, window_min)
    return None if exam is None else _wire(exam)


def find_by_idempotency_key(
    session: Any,
    *,
    idempotency_key: str,
    window_min: int,
) -> tuple[dict, str] | None:
    """ADDED (see module docstring). Newest exam stored under this key inside
    the window, as ``(predict_shaped_dict, content_sha256)``; ``None`` if absent.
    """
    stmt = select(models.Exam).where(
        models.Exam.idempotency_key == idempotency_key
    )
    exam = _newest_exam_within(session, stmt, window_min)
    if exam is None:
        return None
    # The caller compares this hash against the bytes it just received: equal
    # means replay, different means 409 idempotency_conflict.
    return _wire(exam), exam.content_sha256


def list_exams(
    session: Any,
    limit: int = 50,
    offset: int = 0,
    patient_code: str | None = None,
) -> list[dict]:
    stmt: Select[Any] = select(models.Exam)
    if patient_code is not None:
        stmt = stmt.join(
            models.Patient, models.Exam.patient_id == models.Patient.id
        ).where(models.Patient.patient_code == patient_code)
    stmt = (
        # id breaks ties so pagination is stable when two exams share a second.
        stmt.order_by(models.Exam.created_at.desc(), models.Exam.id.desc())
        .limit(limit)
        .offset(offset)
    )
    exams = session.execute(stmt).unique().scalars().all()
    return [_wire(exam) for exam in exams]


def get_exam(session: Any, exam_id: str) -> dict | None:
    """Returns predict-shaped dict (§4.3 keys) or None."""
    exam = session.get(models.Exam, exam_id)
    return None if exam is None else _wire(exam)
