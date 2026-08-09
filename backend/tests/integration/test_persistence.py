"""Persistence integration tests (spec §5-B B4). Tmp sqlite, no HTTP.

These exercise ``app.db`` directly so a failure points at the DB layer and not
at Agent C's routing. The only shared state involved is the ``get_settings``
lru_cache and the lazily built engine, and the ``db`` fixture resets both on
the way in *and* on the way out — the same discipline ``tests/conftest.py``
applies to the app fixtures.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError

from app.inference.decision import GRADE_LABELS, decide
from app.schemas import DISCLAIMER, LEGACY_KEYS, PredictResponse

PROCESSED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

REFER = decide(
    {"grade": 4, "probs": [0.05, 0.05, 0.05, 0.05, 0.80], "model_version": "mock-v0"},
    True,
    0.5,
)
NO_REFER = decide(
    {"grade": 0, "probs": [0.80, 0.10, 0.05, 0.03, 0.02], "model_version": "mock-v0"},
    True,
    0.5,
)
UNGRADABLE = decide(None, False, 0.5)


# --------------------------------------------------------------------------
# fixture
# --------------------------------------------------------------------------
@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """A freshly created tmp sqlite schema, torn down cleanly."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'persistence.db'}")

    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import base

    base.dispose_engine()
    base.init_db()
    try:
        yield base
    finally:
        base.dispose_engine()
        get_settings.cache_clear()


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _create(db, exam_id: str, **overrides: Any) -> None:
    from app.db import crud

    kwargs: dict[str, Any] = {
        "exam_id": exam_id,
        "patient_code": "P-0001",
        "eye": "right",
        "image_path": f"/static/images/{exam_id}.jpg",
        "content_sha256": "a" * 64,
        "quality": "good",
        "blur_var": 180.5,
        "mean_gray": 160.25,
        "result": REFER,
        "model_version": "mock-v0",
        "heatmap_path": f"/static/heatmaps/{exam_id}.png",
        "processed_at": datetime.now(timezone.utc),
    }
    kwargs.update(overrides)
    with db.get_session() as session:
        crud.create_exam_with_result(session, **kwargs)


def _count(db, table: str) -> int:
    with db.get_session() as session:
        return session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()


def _minutes_ago(minutes: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(minutes=minutes)


# --------------------------------------------------------------------------
# create -> read roundtrip
# --------------------------------------------------------------------------
def test_create_read_roundtrip_returns_what_went_in(db) -> None:
    from app.db import crud

    processed_at = datetime(2026, 8, 9, 6, 30, 0, tzinfo=timezone.utc)
    _create(db, "exam-roundtrip", processed_at=processed_at)

    with db.get_session() as session:
        wire = crud.get_exam(session, "exam-roundtrip")

    assert wire is not None
    assert wire["exam_id"] == "exam-roundtrip"
    assert wire["patient_id"] == "P-0001"
    assert wire["eye"] == "right"
    assert wire["referable"] is True
    assert wire["probability"] == pytest.approx(REFER.probability)
    assert wire["icdr_grade"] == 4
    assert wire["grade_label"] == GRADE_LABELS[4]
    assert wire["decision"] == "REFER"
    assert wire["decision_text"] == REFER.decision_text
    assert wire["quality"] == "good"
    assert wire["image_url"] == "/static/images/exam-roundtrip.jpg"
    assert wire["heatmap_url"] == "/static/heatmaps/exam-roundtrip.png"
    assert wire["model_version"] == "mock-v0"
    assert wire["processed_at"] == "2026-08-09T06:30:00Z"
    assert wire["disclaimer"] == DISCLAIMER
    assert wire["mode"] == "demo"


def test_wire_shape_has_every_frozen_key_and_validates(db) -> None:
    from app.db import crud

    _create(db, "exam-shape")
    with db.get_session() as session:
        wire = crud.get_exam(session, "exam-shape")

    assert wire is not None
    assert set(wire) == set(LEGACY_KEYS) | {"request_id", "mode"}
    assert PROCESSED_AT_RE.fullmatch(wire["processed_at"]), wire["processed_at"]
    # The DB layer must produce something the frozen response model accepts.
    PredictResponse.model_validate(wire)


def test_get_exam_returns_none_for_an_unknown_id(db) -> None:
    from app.db import crud

    with db.get_session() as session:
        assert crud.get_exam(session, "does-not-exist") is None


def test_quality_metrics_are_persisted(db) -> None:
    from app.db import models

    _create(db, "exam-metrics", blur_var=12.5, mean_gray=88.0)
    with db.get_session() as session:
        exam = session.get(models.Exam, "exam-metrics")
        assert exam is not None
        assert exam.blur_var == pytest.approx(12.5)
        assert exam.mean_gray == pytest.approx(88.0)
        assert exam.content_sha256 == "a" * 64
        # TZ-aware UTC out of the DB, not a naive datetime.
        assert exam.created_at.tzinfo is not None
        assert exam.created_at.utcoffset() == timedelta(0)


def test_predict_writes_exactly_one_audit_row_per_exam(db) -> None:
    from app.db import models

    _create(db, "exam-audit-1")
    _create(db, "exam-audit-2")

    with db.get_session() as session:
        rows = session.execute(select(models.AuditLog)).scalars().all()

    assert len(rows) == 2
    assert {r.action for r in rows} == {"predict"}
    assert {r.exam_id for r in rows} == {"exam-audit-1", "exam-audit-2"}


# --------------------------------------------------------------------------
# patients
# --------------------------------------------------------------------------
def test_same_patient_code_twice_yields_one_patient_and_two_exams(db) -> None:
    from app.db import crud

    _create(db, "exam-p1", patient_code="P-SHARED")
    _create(db, "exam-p2", patient_code="P-SHARED", content_sha256="b" * 64)

    assert _count(db, "patients") == 1
    assert _count(db, "exams") == 2

    with db.get_session() as session:
        both = crud.list_exams(session, patient_code="P-SHARED")
    assert {e["exam_id"] for e in both} == {"exam-p1", "exam-p2"}
    assert {e["patient_id"] for e in both} == {"P-SHARED"}


def test_absent_patient_code_is_generated_and_persisted(db) -> None:
    """C2: crud must not leave an exam patient-less if the caller sent none."""
    from app.db import crud

    _create(db, "exam-autogen", patient_code=None)
    with db.get_session() as session:
        wire = crud.get_exam(session, "exam-autogen")

    assert wire is not None
    assert re.fullmatch(r"P-[0-9A-F]{6}", wire["patient_id"]), wire["patient_id"]
    assert _count(db, "patients") == 1


# --------------------------------------------------------------------------
# C3 — NULL in the DB, placeholders on the wire
# --------------------------------------------------------------------------
def test_ungradable_stores_null_and_reads_back_placeholders(db) -> None:
    from app.db import crud, models

    _create(db, "exam-ungradable", quality="poor", result=UNGRADABLE, heatmap_path=None)

    with db.get_session() as session:
        stored = session.execute(select(models.Result)).scalars().one()
        # DB truth: NULL, so training exports stay clean...
        assert stored.probability is None
        assert stored.icdr_grade is None
        # ...while the verdict itself is always stored.
        assert stored.referable is False
        assert stored.decision == "UNGRADABLE"

        wire = crud.get_exam(session, "exam-ungradable")

    # Wire truth: non-null placeholders, because the deployed APK crashes on nulls.
    assert wire is not None
    assert wire["probability"] == 0.0
    assert wire["icdr_grade"] == 0
    assert wire["grade_label"] == "Baholab bo'lmadi"
    assert wire["referable"] is False
    assert wire["decision"] == "UNGRADABLE"
    assert wire["quality"] == "poor"
    assert wire["heatmap_url"] is None
    PredictResponse.model_validate(wire)


def test_null_columns_are_visible_to_raw_sql(db) -> None:
    """Proves the NULLs are really in the table, not a Python-side illusion."""
    _create(db, "exam-null-sql", quality="poor", result=UNGRADABLE, heatmap_path=None)
    with db.get_session() as session:
        row = session.execute(
            text("SELECT probability, icdr_grade FROM results WHERE exam_id = :e"),
            {"e": "exam-null-sql"},
        ).one()
    assert row == (None, None)


# --------------------------------------------------------------------------
# list_exams
# --------------------------------------------------------------------------
def test_list_exams_orders_newest_first_and_paginates(db) -> None:
    from app.db import crud

    for i in range(5):
        _create(
            db,
            f"exam-list-{i}",
            content_sha256=f"{i}" * 64,
            processed_at=_minutes_ago(10 - i),  # exam-list-4 is the newest
        )

    with db.get_session() as session:
        page1 = crud.list_exams(session, limit=2, offset=0)
        page2 = crud.list_exams(session, limit=2, offset=2)
        page3 = crud.list_exams(session, limit=2, offset=4)
        everything = crud.list_exams(session, limit=50, offset=0)

    assert [e["exam_id"] for e in page1] == ["exam-list-4", "exam-list-3"]
    assert [e["exam_id"] for e in page2] == ["exam-list-2", "exam-list-1"]
    assert [e["exam_id"] for e in page3] == ["exam-list-0"]
    assert [e["exam_id"] for e in everything] == [
        f"exam-list-{i}" for i in (4, 3, 2, 1, 0)
    ]


def test_list_exams_filters_by_patient(db) -> None:
    from app.db import crud

    _create(db, "exam-a", patient_code="P-AAA")
    _create(db, "exam-b", patient_code="P-BBB", content_sha256="b" * 64)

    with db.get_session() as session:
        only_a = crud.list_exams(session, patient_code="P-AAA")
        unfiltered = crud.list_exams(session)
        nobody = crud.list_exams(session, patient_code="P-NOPE")

    assert [e["exam_id"] for e in only_a] == ["exam-a"]
    assert len(unfiltered) == 2
    assert nobody == []


# --------------------------------------------------------------------------
# C14 — content-fingerprint dedup
# --------------------------------------------------------------------------
def test_find_recent_duplicate_hits_inside_the_window(db) -> None:
    from app.db import crud

    _create(db, "exam-dup", content_sha256="f" * 64, processed_at=_minutes_ago(3))

    with db.get_session() as session:
        hit = crud.find_recent_duplicate(
            session,
            content_sha256="f" * 64,
            patient_code="P-0001",
            eye="right",
            window_min=10,
        )

    assert hit is not None
    assert hit["exam_id"] == "exam-dup"
    # The replay must be a complete response, not a stub.
    PredictResponse.model_validate(hit)


def test_find_recent_duplicate_returns_the_newest_match(db) -> None:
    from app.db import crud

    _create(db, "exam-old", content_sha256="f" * 64, processed_at=_minutes_ago(5))
    _create(db, "exam-new", content_sha256="f" * 64, processed_at=_minutes_ago(1))

    with db.get_session() as session:
        hit = crud.find_recent_duplicate(
            session,
            content_sha256="f" * 64,
            patient_code="P-0001",
            eye="right",
            window_min=10,
        )

    assert hit is not None and hit["exam_id"] == "exam-new"


def test_find_recent_duplicate_misses_outside_the_window(db) -> None:
    from app.db import crud

    _create(db, "exam-stale", content_sha256="f" * 64, processed_at=_minutes_ago(11))

    with db.get_session() as session:
        assert (
            crud.find_recent_duplicate(
                session,
                content_sha256="f" * 64,
                patient_code="P-0001",
                eye="right",
                window_min=10,
            )
            is None
        )
        # ...and hits again once the window is widened past it.
        assert (
            crud.find_recent_duplicate(
                session,
                content_sha256="f" * 64,
                patient_code="P-0001",
                eye="right",
                window_min=60,
            )
            is not None
        )


def test_find_recent_duplicate_misses_on_a_different_eye(db) -> None:
    from app.db import crud

    _create(db, "exam-right", content_sha256="f" * 64, eye="right")

    with db.get_session() as session:
        assert (
            crud.find_recent_duplicate(
                session,
                content_sha256="f" * 64,
                patient_code="P-0001",
                eye="left",
                window_min=10,
            )
            is None
        )


def test_find_recent_duplicate_misses_on_a_different_patient(db) -> None:
    from app.db import crud

    _create(db, "exam-mine", content_sha256="f" * 64, patient_code="P-MINE")

    with db.get_session() as session:
        assert (
            crud.find_recent_duplicate(
                session,
                content_sha256="f" * 64,
                patient_code="P-YOURS",
                eye="right",
                window_min=10,
            )
            is None
        )


def test_find_recent_duplicate_misses_on_a_different_fingerprint(db) -> None:
    from app.db import crud

    _create(db, "exam-fp", content_sha256="f" * 64)

    with db.get_session() as session:
        assert (
            crud.find_recent_duplicate(
                session,
                content_sha256="0" * 64,
                patient_code="P-0001",
                eye="right",
                window_min=10,
            )
            is None
        )


def test_blank_patient_id_still_dedups(db) -> None:
    """C2 + C14 together: the demo's blank-ID retry must not create a 2nd exam.

    Every stored exam has a *generated* code, so a caller that sends no
    patient_id can only be matched on (fingerprint, eye).
    """
    from app.db import crud

    _create(db, "exam-blank", patient_code=None, content_sha256="f" * 64)

    with db.get_session() as session:
        hit = crud.find_recent_duplicate(
            session,
            content_sha256="f" * 64,
            patient_code=None,
            eye="right",
            window_min=10,
        )

    assert hit is not None and hit["exam_id"] == "exam-blank"


# --------------------------------------------------------------------------
# C14 — Idempotency-Key
# --------------------------------------------------------------------------
def test_find_by_idempotency_key_roundtrip(db) -> None:
    from app.db import crud

    _create(db, "exam-idem", content_sha256="c" * 64, idempotency_key="key-123")

    with db.get_session() as session:
        found = crud.find_by_idempotency_key(
            session, idempotency_key="key-123", window_min=10
        )

    assert found is not None
    wire, sha = found
    assert wire["exam_id"] == "exam-idem"
    # The hash is what lets the caller tell a replay from a 409 conflict.
    assert sha == "c" * 64
    PredictResponse.model_validate(wire)


def test_find_by_idempotency_key_misses_on_unknown_key_and_outside_window(db) -> None:
    from app.db import crud

    _create(
        db,
        "exam-idem-stale",
        idempotency_key="key-stale",
        processed_at=_minutes_ago(11),
    )

    with db.get_session() as session:
        assert (
            crud.find_by_idempotency_key(
                session, idempotency_key="key-unknown", window_min=10
            )
            is None
        )
        assert (
            crud.find_by_idempotency_key(
                session, idempotency_key="key-stale", window_min=10
            )
            is None
        )
        assert (
            crud.find_by_idempotency_key(
                session, idempotency_key="key-stale", window_min=60
            )
            is not None
        )


def test_find_by_idempotency_key_ignores_exams_stored_without_one(db) -> None:
    from app.db import crud

    _create(db, "exam-no-key")  # idempotency_key defaults to None

    with db.get_session() as session:
        assert (
            crud.find_by_idempotency_key(
                session, idempotency_key="key-anything", window_min=10
            )
            is None
        )


# --------------------------------------------------------------------------
# concurrency
# --------------------------------------------------------------------------
def test_lost_race_adopts_the_winning_patient_row(db, monkeypatch) -> None:
    """The unique-constraint branch, pinned deterministically.

    A threaded test proves the *outcome* but cannot guarantee the interleaving
    actually happened. So the competing INSERT is injected at the one point
    ``get_or_create_patient`` reaches between its SELECT (which misses) and its
    flush (which must then violate the constraint).
    """
    from app.db import crud, models

    code = "P-LOSER"
    real_utcnow = models.utcnow
    injected: list[str] = []

    def inject_competitor() -> datetime:
        if not injected:
            injected.append(code)
            with db.get_session() as rival:
                rival.add(
                    models.Patient(
                        id="winner-id", patient_code=code, created_at=real_utcnow()
                    )
                )
        return real_utcnow()

    monkeypatch.setattr(crud.models, "utcnow", inject_competitor)

    with db.get_session() as session:
        adopted = crud.get_or_create_patient(session, code)
        assert adopted.id == "winner-id"
        assert adopted.patient_code == code

    assert injected == [code]
    assert _count(db, "patients") == 1


def test_concurrent_get_or_create_patient_leaves_exactly_one_row(db) -> None:
    """Two threads, one unique constraint, one patient row.

    The ``OperationalError`` retry is a SQLite artefact, not part of the
    contract: SQLite has a single writer, so one of the two transactions can be
    refused the write lock outright. What is under test is that a *unique
    constraint* violation resolves into the winner's row instead of an error.
    """
    from app.db import crud

    code = "P-RACE01"
    barrier = threading.Barrier(2, timeout=10)
    seen: list[str] = []
    failures: list[BaseException] = []
    lock = threading.Lock()

    def worker() -> None:
        try:
            barrier.wait()
            for attempt in range(20):
                try:
                    with db.get_session() as session:
                        patient = crud.get_or_create_patient(session, code)
                        with lock:
                            seen.append(patient.patient_code)
                    return
                except OperationalError:  # "database is locked" — retry
                    time.sleep(0.02 * (attempt + 1))
            raise AssertionError("never won the sqlite write lock")
        except BaseException as exc:  # noqa: BLE001 - re-raised in the main thread
            with lock:
                failures.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert failures == []
    assert seen == [code, code]

    with db.get_session() as session:
        from app.db import models

        total = session.execute(
            select(func.count()).select_from(models.Patient)
        ).scalar_one()
    assert total == 1
