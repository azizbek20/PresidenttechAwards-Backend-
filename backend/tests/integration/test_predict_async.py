"""``POST /predict/async`` + ``GET /predict/status/{id}`` (the mobile client's flow).

Celery runs eagerly against an in-memory result backend, so the task executes
inside the request and its result is visible to the status endpoint without a
broker or a worker process.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.schemas import LEGACY_KEYS

PREDICT_ASYNC = "/api/v1/predict/async"
STATUS = "/api/v1/predict/status/{}"


@pytest.fixture
def eager(client: Any) -> Any:
    from app.worker import celery_app

    celery_app.conf.update(
        broker_url="memory://",
        result_backend="cache+memory://",
        task_always_eager=True,
        task_store_eager_result=True,
    )
    return client


def _submit(c: Any, data: bytes, **form: str) -> Any:
    return c.post(PREDICT_ASYNC, files={"file": ("eye.jpg", data, "image/jpeg")}, data=form)


def test_async_flow_returns_the_same_wire_shape_as_sync(
    eager: Any, refer_jpeg_bytes: bytes
) -> None:
    queued = _submit(eager, refer_jpeg_bytes, patient_id="P-1", eye="left")
    assert queued.status_code == 200, queued.text
    task = queued.json()
    assert task["status"] == "PENDING"

    status = eager.get(STATUS.format(task["task_id"]))
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["status"] == "SUCCESS"
    result = body["result"]
    assert set(LEGACY_KEYS) <= set(result)
    assert result["patient_id"] == "P-1"
    assert result["eye"] == "left"
    assert result["decision"] == "REFER"

    exam = eager.get(f"/api/v1/exams/{result['exam_id']}")
    assert exam.status_code == 200, exam.text


def test_missing_eye_stays_null_instead_of_defaulting_to_right(
    eager: Any, norefer_jpeg_bytes: bytes
) -> None:
    task_id = _submit(eager, norefer_jpeg_bytes).json()["task_id"]
    result = eager.get(STATUS.format(task_id)).json()["result"]
    assert result["eye"] is None


def test_a_resent_payload_replays_the_stored_exam(
    eager: Any, refer_jpeg_bytes: bytes
) -> None:
    first_id = _submit(eager, refer_jpeg_bytes, patient_id="P-2").json()["task_id"]
    first = eager.get(STATUS.format(first_id)).json()["result"]

    again = _submit(eager, refer_jpeg_bytes, patient_id="P-2").json()
    assert again["task_id"] == f"replay:{first['exam_id']}"
    replay = eager.get(STATUS.format(again["task_id"])).json()
    assert replay["status"] == "SUCCESS"
    assert replay["result"]["exam_id"] == first["exam_id"]


def test_bad_input_is_rejected_synchronously(eager: Any, text_file_bytes: bytes) -> None:
    assert _submit(eager, text_file_bytes).status_code == 400
    assert _submit(eager, b"", eye="right").status_code == 400


def test_invalid_eye_is_rejected_synchronously(
    eager: Any, refer_jpeg_bytes: bytes
) -> None:
    assert _submit(eager, refer_jpeg_bytes, eye="middle").status_code == 422


def test_unknown_replay_id_reports_failure(eager: Any) -> None:
    body = eager.get(STATUS.format("replay:does-not-exist")).json()
    assert body["status"] == "FAILURE"
    assert isinstance(body["error"], str)
