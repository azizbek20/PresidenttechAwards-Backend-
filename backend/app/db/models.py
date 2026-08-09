"""SQLAlchemy 2.0 typed ORM (spec §5-B B1). Portable SQLite <-> PostgreSQL.

Design notes that are load-bearing elsewhere:

* **C3 split truth.** ``results.probability`` and ``results.icdr_grade`` are
  NULLABLE and store ``NULL`` for UNGRADABLE so training exports stay clean,
  while ``referable`` and ``decision`` are ALWAYS stored. The non-null wire
  placeholders are rebuilt on read by :func:`exam_to_wire` — never persisted.
* **One timestamp per exam.** ``exams.created_at`` *is* the wire's
  ``processed_at``: the caller hands ``processed_at`` to
  ``crud.create_exam_with_result`` and it lands here. Keeping a second column
  would let the C14 dedup window (which orders and filters on ``created_at``)
  drift away from the timestamp the phone was shown.
* **``audit_log`` is append-only.** There is deliberately no update or delete
  path for it anywhere in this codebase; rows are only ever INSERTed by
  ``crud.create_exam_with_result``.
* **Portability.** Every type used here (TEXT/VARCHAR, REAL, INTEGER, BOOLEAN,
  TIMESTAMP) renders on both SQLite and PostgreSQL, and :class:`UtcDateTime`
  papers over the one real difference — SQLite cannot store an offset.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import PurePath
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.inference.decision import GRADE_LABELS, decide
from app.schemas import DISCLAIMER

#: The C3 placeholder label, derived from the frozen decision logic rather than
#: retyped, so the DB layer can never drift from ``decide()``.
UNGRADABLE_GRADE_LABEL: str = decide(None, False, 0.0).grade_label

DECISIONS: tuple[str, ...] = ("REFER", "NO_REFER", "UNGRADABLE")


# ---------------------------------------------------------------------------
# small helpers (shared with crud.py, whose module body is frozen)
# ---------------------------------------------------------------------------
def new_uuid() -> str:
    """A fresh uuid4 as TEXT — every primary key in this schema."""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Coerce to an aware UTC datetime; naive input is *assumed* UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def iso_z(value: datetime) -> str:
    """ISO-8601 UTC ending in ``Z``, second precision.

    Matches the frozen contract regex
    ``^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$``.
    """
    return as_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def static_url(stored: str | None, subdir: str) -> str | None:
    """Normalise a stored image/heatmap location to a ``/static/...`` URL.

    ``crud.create_exam_with_result`` takes ``image_path``/``heatmap_path`` as
    ``str`` while ``storage.local`` returns ``(Path, url)`` pairs, so callers
    may reasonably hand over either the relative URL or a filesystem path. Both
    are accepted and both read back as the stable relative URL the app persists
    in Room (C6).
    """
    if stored is None:
        return None
    if stored.startswith("/static/"):
        return stored
    return f"/static/{subdir}/{PurePath(stored).name}"


class UtcDateTime(TypeDecorator[datetime]):
    """TIMESTAMP that is always tz-aware UTC in Python.

    PostgreSQL keeps the offset (``TIMESTAMP WITH TIME ZONE``); SQLite cannot,
    so values are normalised to UTC and stored naive there, then re-tagged as
    UTC on the way out. Either way the ORM only ever hands back aware UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        value = as_utc(value)
        if dialect.name == "sqlite":
            return value.replace(tzinfo=None)
        return value

    def process_result_value(
        self, value: datetime | None, dialect: Dialect
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# tables
# ---------------------------------------------------------------------------
class Patient(Base):
    __tablename__ = "patients"
    __table_args__ = (
        UniqueConstraint("patient_code", name="uq_patients_patient_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    #: Client-supplied ID or the C2 server-generated ``P-XXXXXX``.
    patient_code: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )


class Exam(Base):
    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    patient_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("patients.id"), nullable=True
    )
    eye: Mapped[str | None] = mapped_column(String(8), nullable=True)
    image_path: Mapped[str] = mapped_column(Text, nullable=False)
    heatmap_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: C14 dedup fingerprint: sha256 of the uploaded bytes.
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    #: Optional ``Idempotency-Key`` header; takes precedence over the
    #: fingerprint when the client sends one.
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quality: Mapped[str] = mapped_column(String(8), nullable=False)
    blur_var: Mapped[float | None] = mapped_column(Float, nullable=True)
    mean_gray: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: The wire's ``processed_at`` — see the module docstring.
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )

    patient: Mapped[Patient | None] = relationship(lazy="joined")
    results: Mapped[list[Result]] = relationship(
        back_populates="exam",
        lazy="selectin",
        order_by="desc(Result.created_at)",
    )

    @property
    def latest_result(self) -> Result | None:
        return self.results[0] if self.results else None


class Result(Base):
    __tablename__ = "results"
    __table_args__ = (
        UniqueConstraint("exam_id", "model_version", name="uq_results_exam_model"),
        # NULL passes a CHECK by SQL three-valued logic, which is exactly the
        # C3 behaviour: UNGRADABLE stores NULL, everything else stores 0..4.
        CheckConstraint("icdr_grade BETWEEN 0 AND 4", name="ck_results_icdr_grade"),
        CheckConstraint(
            "decision IN ('REFER', 'NO_REFER', 'UNGRADABLE')",
            name="ck_results_decision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    exam_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("exams.id"), nullable=False
    )
    #: C3: NULL for UNGRADABLE.
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    #: C3: NULL for UNGRADABLE.
    icdr_grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: Always stored, including for UNGRADABLE.
    referable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Stored rather than re-derived so a C14 replay is byte-identical to the
    #: response the phone originally received.
    decision_text: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime, nullable=False, default=utcnow
    )

    exam: Mapped[Exam] = relationship(back_populates="results")


class AuditLog(Base):
    """Append-only (Doc 3 §4.2). Nothing in this codebase updates or deletes it."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    ts: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False, default=utcnow)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    exam_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


# ---------------------------------------------------------------------------
# indexes (DESC where the reads are newest-first)
# ---------------------------------------------------------------------------
Index("ix_exams_created_at", Exam.created_at.desc())
Index("ix_exams_patient_created_at", Exam.patient_id, Exam.created_at.desc())
#: C14 dedup lookup.
Index("ix_exams_sha256_created_at", Exam.content_sha256, Exam.created_at.desc())
#: C14 ``Idempotency-Key`` lookup.
Index("ix_exams_idem_key_created_at", Exam.idempotency_key, Exam.created_at.desc())
Index("ix_audit_log_ts", AuditLog.ts.desc())


# ---------------------------------------------------------------------------
# wire projection
# ---------------------------------------------------------------------------
def exam_to_wire(exam: Exam, *, mode: str) -> dict[str, Any]:
    """Rebuild the predict-shaped dict (§4.3) from stored rows.

    C3 in one place: DB NULLs become the non-null wire placeholders
    (``probability=0.0``, ``icdr_grade=0``, ``grade_label="Baholab bo'lmadi"``)
    because the deployed APK crashes on nulls.
    """
    result = exam.latest_result
    if result is None:
        # Unreachable through create_exam_with_result, which writes exam +
        # result in one transaction. Loud rather than silently half-shaped.
        raise ValueError(f"exam {exam.id} has no result row")

    grade = result.icdr_grade
    probability = result.probability
    return {
        "exam_id": exam.id,
        "patient_id": exam.patient.patient_code if exam.patient is not None else None,
        "eye": exam.eye,
        "referable": result.referable,
        "probability": 0.0 if probability is None else float(probability),
        "icdr_grade": 0 if grade is None else int(grade),
        "grade_label": (
            UNGRADABLE_GRADE_LABEL if grade is None else GRADE_LABELS[int(grade)]
        ),
        "decision": result.decision,
        "decision_text": result.decision_text,
        "quality": exam.quality,
        "heatmap_url": static_url(exam.heatmap_path, "heatmaps"),
        "image_url": static_url(exam.image_path, "images"),
        "model_version": result.model_version,
        "processed_at": iso_z(exam.created_at),
        "disclaimer": DISCLAIMER,
        # Per-request, by definition — a replayed exam gets a fresh one.
        "request_id": new_uuid(),
        "mode": mode,
    }
