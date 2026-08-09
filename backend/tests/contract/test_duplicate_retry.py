"""C14 — a retry must not become a second patient exam.

Verified client behaviour at HEAD `f6e4a0c`: `retry()` resends the SAME
retained bytes (`ScreeningViewModel.kt:150`, pinned by
`ScreeningViewModelTest.kt:167`), and the source file is deleted only after a
successful request (`:195`). So "server succeeded, phone timed out, user taps
Qayta urinish" is a routine sequence, and without dedup it writes a duplicate
exam that the admin panel then shows twice.

The client sends no `Idempotency-Key` header (grep over `app/src/main` at
`f6e4a0c`: zero matches), which is why the primary key is the content
fingerprint. The header path is honoured too, for the future Android patch.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from tests.contract.conftest import upload


@pytest.fixture
def engine_calls(client: Any, monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Counts real invocations of the DR engine. Requested AFTER `client`."""
    calls: list[int] = []
    mock_engine = importlib.import_module("app.inference.mock_engine")
    original = mock_engine.MockEngine.predict

    def spy(self: Any, img: Any) -> Any:
        calls.append(1)
        return original(self, img)

    monkeypatch.setattr("app.inference.mock_engine.MockEngine.predict", spy)
    return calls


def post(client: Any, raw: bytes, **form: Any) -> Any:
    data = {k: v for k, v in form.items() if v is not None}
    return client.post("/api/v1/predict", files=upload(raw), data=data)


# --------------------------------------------------------------------------
# fingerprint dedup (the path today's APK actually takes)
# --------------------------------------------------------------------------
def test_same_bytes_patient_and_eye_replay_one_exam(
    client: Any, refer_jpeg_bytes: bytes, engine_calls: list[int]
) -> None:
    first = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right")
    second = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right")

    assert first.status_code == second.status_code == 200, second.text
    assert first.json()["exam_id"] == second.json()["exam_id"]
    assert len(engine_calls) == 1, "the retry re-ran inference"

    exams = client.get("/api/v1/exams").json()
    assert len(exams) == 1, exams


def test_replayed_body_matches_the_original_verdict(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    first = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right").json()
    second = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right").json()

    # `request_id` is per-request by definition and `crud.create_exam_with_result`
    # has no parameter to persist the original one, so it is excluded.
    volatile = {"request_id"}
    assert {k: v for k, v in first.items() if k not in volatile} == {
        k: v for k, v in second.items() if k not in volatile
    }


def test_the_other_eye_is_a_new_exam(
    client: Any, refer_jpeg_bytes: bytes, engine_calls: list[int]
) -> None:
    """Bilateral screening posts two images that may be byte-identical."""
    first = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right")
    second = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="left")

    assert first.json()["exam_id"] != second.json()["exam_id"]
    assert len(engine_calls) == 2
    assert len(client.get("/api/v1/exams").json()) == 2


def test_blank_patient_id_retry_replays_the_same_exam(
    client: Any, refer_jpeg_bytes: bytes, engine_calls: list[int]
) -> None:
    """The default demo flow: no patient ID typed, no Idempotency-Key sent.

    `crud.find_recent_duplicate(patient_code=None)` is UNCONSTRAINED on
    patient, not `patient_code IS NULL` — C2 has already replaced every blank
    ID with a fresh `P-XXXXXX`, so a NULL match could never hit and every
    ID-less retry would duplicate the exam. The effective key here is
    (fingerprint, eye), and this is the case the G6 phone gate checks.
    """
    first = post(client, refer_jpeg_bytes, eye="right")
    second = post(client, refer_jpeg_bytes, eye="right")

    assert first.status_code == second.status_code == 200, second.text
    assert first.json()["exam_id"] == second.json()["exam_id"]
    assert len(engine_calls) == 1, "the ID-less retry re-ran inference"
    assert len(client.get("/api/v1/exams").json()) == 1


def test_blank_patient_id_retry_keeps_the_generated_code(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """The result screen must not show a different P-XXXXXX after a retry."""
    first = post(client, refer_jpeg_bytes, eye="right").json()
    second = post(client, refer_jpeg_bytes, eye="right").json()

    assert first["patient_id"] == second["patient_id"]
    assert second["patient_id"].startswith("P-")


def test_blank_patient_id_retry_with_no_eye_also_replays(
    client: Any, refer_jpeg_bytes: bytes, engine_calls: list[int]
) -> None:
    """Nothing but the bytes: still one exam."""
    first = post(client, refer_jpeg_bytes)
    second = post(client, refer_jpeg_bytes)

    assert first.json()["exam_id"] == second.json()["exam_id"]
    assert len(engine_calls) == 1


def test_blank_patient_id_still_separates_the_two_eyes(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """Unconstrained on patient must not collapse a bilateral screening."""
    right = post(client, refer_jpeg_bytes, eye="right")
    left = post(client, refer_jpeg_bytes, eye="left")

    assert right.json()["exam_id"] != left.json()["exam_id"]
    assert len(client.get("/api/v1/exams").json()) == 2


def test_a_different_patient_is_a_new_exam(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    first = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right")
    second = post(client, refer_jpeg_bytes, patient_id="P-0002", eye="right")
    assert first.json()["exam_id"] != second.json()["exam_id"]


def test_different_bytes_are_a_new_exam(
    client: Any, refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    first = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right")
    second = post(client, norefer_jpeg_bytes, patient_id="P-0001", eye="right")
    assert first.json()["exam_id"] != second.json()["exam_id"]


def test_lookup_uses_the_configured_window_and_an_expired_one_creates_a_new_exam(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Window expiry, without sleeping for DEDUP_WINDOW_MIN.

    Whether a stored row is "inside the window" is `crud`'s judgement (Agent
    B). What Agent C owns is passing the configured window and honouring a
    miss, so the lookup is replaced by a spy that reports the arguments it got
    and answers "expired".
    """
    from app.config import get_settings

    seen: list[dict[str, Any]] = []

    def expired(session: Any, **kwargs: Any) -> None:
        seen.append(kwargs)

    first = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right")
    monkeypatch.setattr("app.db.crud.find_recent_duplicate", expired)
    second = post(client, refer_jpeg_bytes, patient_id="P-0001", eye="right")

    assert first.json()["exam_id"] != second.json()["exam_id"]
    assert seen[-1]["window_min"] == get_settings().dedup_window_min
    assert seen[-1]["patient_code"] == "P-0001"
    assert seen[-1]["eye"] == "right"
    assert len(seen[-1]["content_sha256"]) == 64


# --------------------------------------------------------------------------
# Idempotency-Key (accepted now, for the future Android patch)
# --------------------------------------------------------------------------
def test_same_key_and_same_bytes_replay(
    client: Any, refer_jpeg_bytes: bytes, engine_calls: list[int]
) -> None:
    headers = {"Idempotency-Key": "capture-42"}
    first = client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        data={"patient_id": "P-0001", "eye": "right"},
        headers=headers,
    )
    second = client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        data={"patient_id": "P-0001", "eye": "right"},
        headers=headers,
    )

    assert first.status_code == second.status_code == 200, second.text
    assert first.json()["exam_id"] == second.json()["exam_id"]
    assert len(engine_calls) == 1
    assert len(client.get("/api/v1/exams").json()) == 1


def test_same_key_with_different_bytes_is_409(
    client: Any, refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    """Replaying the old verdict for a new photo would be a clinical error."""
    headers = {"Idempotency-Key": "capture-42"}
    first = client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), headers=headers
    )
    assert first.status_code == 200, first.text

    second = client.post(
        "/api/v1/predict", files=upload(norefer_jpeg_bytes), headers=headers
    )
    assert second.status_code == 409, second.text
    body = second.json()
    assert body["error"] == "idempotency_conflict"
    assert isinstance(body["detail"], str) and body["detail"]


def test_a_key_takes_precedence_over_the_fingerprint(
    client: Any, refer_jpeg_bytes: bytes, engine_calls: list[int]
) -> None:
    """Different keys mean two deliberate captures, even of identical bytes."""
    for key in ("capture-1", "capture-2"):
        response = client.post(
            "/api/v1/predict",
            files=upload(refer_jpeg_bytes),
            data={"patient_id": "P-0001", "eye": "right"},
            headers={"Idempotency-Key": key},
        )
        assert response.status_code == 200, response.text

    assert len(engine_calls) == 2
    assert len(client.get("/api/v1/exams").json()) == 2
