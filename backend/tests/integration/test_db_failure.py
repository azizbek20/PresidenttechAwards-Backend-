"""C10 end to end: no result outlives a failed write (Agent C).

The contract suite pins the status code and envelope. This file pins the
consequence that actually matters for the demo script: after a persistence
failure the exam must not appear in the history the admin panel reads, and the
client's retry must produce exactly one row.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract import _shim
from tests.contract.conftest import upload

_shim.install()


def _explode(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("commit failed")


def test_failed_write_leaves_no_exam_in_the_history(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)

    assert (
        client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).status_code == 500
    )
    assert client.get("/api/v1/exams").json() == []


def test_retry_after_recovery_yields_exactly_one_row(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The phone kept the bytes, so the retry is byte-identical (C14 + C10)."""
    import importlib

    crud = importlib.import_module("app.db.crud")
    original = crud.create_exam_with_result
    outage = {"active": True}

    def flaky(*args: Any, **kwargs: Any) -> None:
        if outage["active"]:
            raise RuntimeError("commit failed")
        return original(*args, **kwargs)

    monkeypatch.setattr("app.db.crud.create_exam_with_result", flaky)

    form = {"patient_id": "P-0001", "eye": "right"}
    first = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes), data=form)
    assert first.status_code == 500

    outage["active"] = False
    second = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes), data=form)
    assert second.status_code == 200, second.text

    third = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes), data=form)
    assert third.status_code == 200
    assert third.json()["exam_id"] == second.json()["exam_id"]

    exams = client.get("/api/v1/exams").json()
    assert len(exams) == 1, exams
    assert exams[0]["exam_id"] == second.json()["exam_id"]


def test_a_read_failure_does_not_masquerade_as_persistence_error(
    client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`persistence_error` means "your result was not saved" to the user, so a
    failing history read must not borrow that wording."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr("app.db.crud.list_exams", _explode)

    # An unhandled error is re-raised by ServerErrorMiddleware after the
    # response is sent, so the envelope is only observable on a client that
    # does not re-raise it.
    quiet = TestClient(client.app, raise_server_exceptions=False)
    response = quiet.get("/api/v1/exams")
    assert response.status_code == 500
    body = response.json()
    assert set(body) == {"error", "detail"}
    assert body["error"] != "persistence_error"


def test_media_written_before_a_failed_write_is_not_advertised(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The original is on disk by then, but no URL for it ever reaches the
    client, so nothing dangling is referenced from Room."""
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)
    body = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    assert "image_url" not in body
    assert "exam_id" not in body
