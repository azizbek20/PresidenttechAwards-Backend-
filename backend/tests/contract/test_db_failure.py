"""C10 — a result the admin panel cannot corroborate never reaches the phone.

Doc 4's lenient "return the result anyway in demo mode" rule is retired. Any
persistence failure, in any mode, is `500 persistence_error`. The client keeps
the source file after a failure (`ScreeningViewModel.kt:195`), so "Qayta
urinish" is a safe and complete recovery.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.conftest import upload


def _explode(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("database is on fire")


def test_write_failure_is_500_persistence_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Patched by dotted string AFTER the client fixture built the app: the
    # frozen conftest purges `app.*`, so an earlier module object is stale.
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)

    response = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert response.status_code == 500, response.text
    body = response.json()
    assert body == {"error": "persistence_error", "detail": "Natija saqlanmadi — qayta urining"}


def test_failure_detail_never_leaks_the_database_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)
    body = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    assert "database is on fire" not in body["detail"]


def test_no_verdict_is_returned_alongside_the_failure(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The envelope has exactly two keys — no smuggled `decision`."""
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)
    body = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    assert set(body) == {"error", "detail"}


def test_ungradable_persistence_failure_also_fails_the_request(
    client: Any, blurry_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C10 is unconditional — it is not limited to the inference path."""
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)
    response = client.post("/api/v1/predict", files=upload(blurry_jpeg_bytes))
    assert response.status_code == 500
    assert response.json()["error"] == "persistence_error"


def test_authenticated_mode_behaves_identically(
    authed_client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One code path, one behaviour — auth changes nothing about C10."""
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)
    response = authed_client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert response.status_code == 500
    assert response.json()["error"] == "persistence_error"


def test_a_retry_after_a_recovered_database_succeeds(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The client resends the retained bytes; once the DB is back it works."""
    import importlib

    crud = importlib.import_module("app.db.crud")
    original = crud.create_exam_with_result
    outage = {"active": True}

    def flaky(*args: Any, **kwargs: Any) -> None:
        if outage["active"]:
            raise RuntimeError("database is on fire")
        return original(*args, **kwargs)

    # `monkeypatch.undo()` would also revert the env vars the frozen client
    # fixture set through this same monkeypatch object, so the outage is
    # toggled explicitly instead.
    monkeypatch.setattr("app.db.crud.create_exam_with_result", flaky)

    first = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert first.status_code == 500

    outage["active"] = False
    second = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert second.status_code == 200, second.text
    assert client.get("/api/v1/exams").json()[0]["exam_id"] == second.json()["exam_id"]
