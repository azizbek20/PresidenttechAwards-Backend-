"""C2 — the server generates the patient code the UI promised.

The Uzbek UI says "ID kiritilmasa avtomatik raqam beriladi", but the app sends
nothing when the field is blank. The backend closes that gap and returns the
generated code, which the result screen then displays.
"""

from __future__ import annotations

from typing import Any

from tests.contract.conftest import PATIENT_CODE_RE, upload


def test_missing_patient_id_gets_a_server_code(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    response = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert response.status_code == 200, response.text
    patient_id = response.json()["patient_id"]
    assert patient_id is not None, "the result screen would show nothing"
    assert PATIENT_CODE_RE.match(patient_id), patient_id


def test_blank_patient_id_is_treated_as_missing(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """An empty form field must not become an empty patient code."""
    response = client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"patient_id": "   "}
    )
    assert response.status_code == 200, response.text
    assert PATIENT_CODE_RE.match(response.json()["patient_id"])


def test_provided_patient_id_is_echoed_verbatim(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    response = client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        data={"patient_id": "P-0001", "eye": "right"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["patient_id"] == "P-0001"


def test_generated_codes_are_distinct_per_exam(
    client: Any, refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    first = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    second = client.post("/api/v1/predict", files=upload(norefer_jpeg_bytes))
    assert first.status_code == second.status_code == 200
    assert first.json()["patient_id"] != second.json()["patient_id"]


def test_generated_code_is_persisted_not_just_returned(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """C10's corollary: the admin panel must show the same code as the phone."""
    created = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    stored = client.get(f"/api/v1/exams/{created['exam_id']}")
    assert stored.status_code == 200, stored.text
    assert stored.json()["patient_id"] == created["patient_id"]
