"""``POST /predict/async`` + ``GET /predict/status/{id}`` — inline flow (plan §3.7).

The screening runs inside the POST (the same ``run_screening`` as ``/predict``);
the task id is ``replay:<exam_id>`` and the status endpoint reads the stored
exam. No worker, no broker.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.schemas import LEGACY_KEYS

PREDICT_ASYNC = "/api/v1/predict/async"
STATUS = "/api/v1/predict/status/{}"
BACKEND = Path(__file__).resolve().parents[2]


def _submit(c: Any, data: bytes, **form: str) -> Any:
    return c.post(PREDICT_ASYNC, files={"file": ("eye.jpg", data, "image/jpeg")}, data=form)


def test_async_flow_returns_the_same_wire_shape_as_sync(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    queued = _submit(client, refer_jpeg_bytes, patient_id="P-1", eye="left")
    assert queued.status_code == 200, queued.text
    task = queued.json()
    assert task["status"] == "PROCESSING"
    assert task["message"] == "Rasm tahlil qilindi, natija tayyorlanmoqda..."
    assert task["task_id"].startswith("replay:")

    status = client.get(STATUS.format(task["task_id"]))
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["status"] == "SUCCESS"
    result = body["result"]
    assert set(LEGACY_KEYS) <= set(result)
    assert result["patient_id"] == "P-1"
    assert result["eye"] == "left"
    assert result["decision"] == "REFER"
    assert task["task_id"] == f"replay:{result['exam_id']}"

    exam = client.get(f"/api/v1/exams/{result['exam_id']}")
    assert exam.status_code == 200, exam.text
    stored = exam.json()
    for key in ("exam_id", "decision", "probability", "icdr_grade", "quality"):
        assert result[key] == stored[key]


def test_the_first_status_is_never_success(client: Any, refer_jpeg_bytes: bytes) -> None:
    first = _submit(client, refer_jpeg_bytes).json()
    assert first["status"] in ("PENDING", "PROCESSING")
    assert first["status"] != "SUCCESS"


def test_missing_eye_stays_null_instead_of_defaulting_to_right(
    client: Any, norefer_jpeg_bytes: bytes
) -> None:
    task_id = _submit(client, norefer_jpeg_bytes).json()["task_id"]
    result = client.get(STATUS.format(task_id)).json()["result"]
    assert result["eye"] is None


def test_a_resent_payload_replays_the_stored_exam(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    first_task = _submit(client, refer_jpeg_bytes, patient_id="P-2").json()
    first = client.get(STATUS.format(first_task["task_id"])).json()["result"]

    again = _submit(client, refer_jpeg_bytes, patient_id="P-2")
    assert again.status_code == 200, again.text
    again_body = again.json()
    assert again_body["task_id"] == f"replay:{first['exam_id']}"
    assert again_body["status"] == "PROCESSING"
    replay = client.get(STATUS.format(again_body["task_id"])).json()
    assert replay["status"] == "SUCCESS"
    assert replay["result"]["exam_id"] == first["exam_id"]
    assert len(client.get("/api/v1/exams").json()) == 1


def test_bad_input_is_rejected_synchronously(client: Any, text_file_bytes: bytes) -> None:
    bad = _submit(client, text_file_bytes)
    assert bad.status_code == 400
    assert bad.json()["error"] == "invalid_image"
    empty = _submit(client, b"", eye="right")
    assert empty.status_code == 400
    assert empty.json()["error"] == "invalid_image"
    assert client.get("/api/v1/exams").json() == []


def test_invalid_eye_is_rejected_synchronously(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    response = _submit(client, refer_jpeg_bytes, eye="middle")
    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


def test_engine_failure_is_an_immediate_500_and_nothing_is_stored(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    class Boom:
        model_loaded = True
        wants_jpeg = False
        model_version = "boom"

        def predict(self, tensor: Any) -> Any:
            raise RuntimeError("engine exploded")

    client.app.state.engine = Boom()
    response = _submit(client, refer_jpeg_bytes, eye="right")

    assert response.status_code == 500, response.text
    body = response.json()
    assert body["error"] == "inference_error"
    assert isinstance(body["detail"], str) and body["detail"]
    assert "task_id" not in body
    assert client.get("/api/v1/exams").json() == []


def test_a_failing_dedup_lookup_is_500_inference_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(**_: Any) -> Any:
        raise RuntimeError("database is down")

    monkeypatch.setattr("app.api.predict._lookup_replay", broken)
    response = _submit(client, refer_jpeg_bytes)

    assert response.status_code == 500, response.text
    assert response.json()["error"] == "inference_error"


def test_unknown_replay_id_reports_failure(client: Any) -> None:
    body = client.get(STATUS.format("replay:does-not-exist")).json()
    assert body["status"] == "FAILURE"
    assert isinstance(body["error"], str)


def test_the_worker_module_is_gone() -> None:
    assert importlib.util.find_spec("app.worker") is None


def test_importing_the_app_does_not_import_celery(tmp_path: Path) -> None:
    code = "import sys, app.main; sys.exit(1 if 'celery' in sys.modules else 0)"
    env = {
        "PATH": "/usr/bin:/bin",
        "EYE_ENV_FILE": "",
        "EYE_MODE": "demo",
        "EYE_MODEL_SOURCE": "mock",
        "EYE_STORAGE_DIR": str(tmp_path / "storage"),
        "DATABASE_URL": f"sqlite:///{tmp_path / 't.db'}",
    }
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    assert done.returncode == 0, done.stderr
