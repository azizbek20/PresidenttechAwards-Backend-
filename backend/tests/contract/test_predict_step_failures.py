"""Steps 3b and 4 of `/predict` (app/api/predict.py) used to be unguarded.

`_lookup_replay` (the dedup/idempotency DB read) and `storage.save_original`
(writing the original image to disk) both ran with no `try/except`, so a
failure there fell through to the generic catch-all handler
(`app/core/errors.py::_unhandled`) — a `500 inference_error` with a log line
that names neither the request nor which step broke, indistinguishable from
an actual model crash. `test_db_failure.py` only covers the final
`create_exam_with_result` write (step 10); these two earlier steps had no
coverage at all.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.conftest import upload


def _explode(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("database is on fire")


def _explode_disk(*args: Any, **kwargs: Any) -> None:
    raise OSError("no space left on device")


# --------------------------------------------------------------------------
# 3b. dedup lookup, no Idempotency-Key header -> crud.find_recent_duplicate
# --------------------------------------------------------------------------
def test_dedup_lookup_failure_is_500_inference_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.db.crud.find_recent_duplicate", _explode)

    response = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert response.status_code == 500, response.text
    body = response.json()
    assert body == {"error": "inference_error", "detail": "Tahlil bajarilmadi — qayta urining"}


def test_dedup_lookup_failure_creates_no_exam(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.db.crud.find_recent_duplicate", _explode)
    client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert client.get("/api/v1/exams").json() == []


# --------------------------------------------------------------------------
# 3b. dedup lookup, WITH an Idempotency-Key header -> find_by_idempotency_key
# --------------------------------------------------------------------------
def test_idempotency_lookup_failure_is_500_inference_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.db.crud.find_by_idempotency_key", _explode)

    response = client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        headers={"Idempotency-Key": "retry-1"},
    )
    assert response.status_code == 500, response.text
    assert response.json()["error"] == "inference_error"


def test_dedup_failure_never_leaks_the_database_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.db.crud.find_recent_duplicate", _explode)
    body = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    assert "database is on fire" not in body["detail"]


# --------------------------------------------------------------------------
# 4. writing the original image to disk -> storage.save_original
# --------------------------------------------------------------------------
def test_save_original_failure_is_500_inference_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.storage.local.save_original", _explode_disk)

    response = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert response.status_code == 500, response.text
    body = response.json()
    assert body == {"error": "inference_error", "detail": "Tahlil bajarilmadi — qayta urining"}


def test_save_original_failure_creates_no_exam(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.storage.local.save_original", _explode_disk)
    client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert client.get("/api/v1/exams").json() == []


def test_save_original_failure_never_leaks_the_os_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.storage.local.save_original", _explode_disk)
    body = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    assert "no space left" not in body["detail"]


# --------------------------------------------------------------------------
# A recovered DB/disk still lets the retained bytes succeed on retry.
# --------------------------------------------------------------------------
def test_a_retry_after_a_recovered_dedup_lookup_succeeds(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    crud = importlib.import_module("app.db.crud")
    original = crud.find_recent_duplicate
    outage = {"active": True}

    def flaky(*args: Any, **kwargs: Any) -> Any:
        if outage["active"]:
            raise RuntimeError("database is on fire")
        return original(*args, **kwargs)

    monkeypatch.setattr("app.db.crud.find_recent_duplicate", flaky)

    first = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert first.status_code == 500

    outage["active"] = False
    second = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert second.status_code == 200, second.text
    assert client.get("/api/v1/exams").json()[0]["exam_id"] == second.json()["exam_id"]
