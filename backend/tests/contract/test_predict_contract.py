"""The wire contract of `POST /api/v1/predict` (spec §5-C C6).

This is the test the deployed APK depends on: 15 legacy keys, never renamed,
never null where the client dereferences them, plus the two additive C12 keys.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.schemas import DISCLAIMER, LEGACY_KEYS, PredictResponse
from tests.contract.conftest import PROCESSED_AT_RE, upload


@pytest.fixture
def body(client: Any, refer_jpeg_bytes: bytes) -> dict[str, Any]:
    response = client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        data={"patient_id": "P-0001", "eye": "right"},
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_all_fifteen_legacy_keys_present(body: dict[str, Any]) -> None:
    missing = [key for key in LEGACY_KEYS if key not in body]
    assert missing == [], f"the APK would crash on missing keys: {missing}"


def test_exactly_seventeen_keys_and_nothing_invented(body: dict[str, Any]) -> None:
    assert set(body) == set(LEGACY_KEYS) | {"request_id", "mode"}


def test_body_validates_against_the_frozen_schema(body: dict[str, Any]) -> None:
    PredictResponse.model_validate(body)


def test_field_types(body: dict[str, Any]) -> None:
    assert isinstance(body["exam_id"], str) and body["exam_id"]
    assert isinstance(body["patient_id"], str)
    assert isinstance(body["referable"], bool)
    assert isinstance(body["probability"], float)
    assert isinstance(body["icdr_grade"], int)
    assert isinstance(body["grade_label"], str)
    assert isinstance(body["decision_text"], str)
    assert isinstance(body["model_version"], str)
    assert isinstance(body["request_id"], str)


def test_decision_and_quality_are_in_the_frozen_enums(body: dict[str, Any]) -> None:
    assert body["decision"] in ("REFER", "NO_REFER", "UNGRADABLE")
    assert body["quality"] in ("good", "poor")
    assert body["eye"] in ("right", "left", None)
    assert body["mode"] in ("demo", "shadow")


def test_probability_and_grade_stay_in_range(body: dict[str, Any]) -> None:
    assert 0.0 <= body["probability"] <= 1.0
    assert 0 <= body["icdr_grade"] <= 4


def test_processed_at_is_second_precision_utc(body: dict[str, Any]) -> None:
    assert PROCESSED_AT_RE.match(body["processed_at"]), body["processed_at"]


def test_media_urls_are_stable_relative_paths(body: dict[str, Any]) -> None:
    # C6: the app persists these in Room, so they are relative and stable.
    assert body["image_url"].startswith("/static/images/")
    assert body["heatmap_url"] is None or body["heatmap_url"].startswith(
        "/static/heatmaps/"
    )


def test_disclaimer_is_the_frozen_string(body: dict[str, Any]) -> None:
    assert body["disclaimer"] == DISCLAIMER


def test_refer_fixture_produces_the_red_card(body: dict[str, Any]) -> None:
    """The demo must be able to show 🔴; the mock's band contract guarantees it."""
    assert body["decision"] == "REFER"
    assert body["referable"] is True
    assert body["quality"] == "good"


def test_norefer_fixture_produces_the_green_card(
    client: Any, norefer_jpeg_bytes: bytes
) -> None:
    response = client.post(
        "/api/v1/predict", files=upload(norefer_jpeg_bytes), data={"eye": "left"}
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["decision"] == "NO_REFER"
    assert payload["referable"] is False
    assert payload["quality"] == "good"
    PredictResponse.model_validate(payload)


def test_eye_is_optional_and_echoed_as_null(
    client: Any, norefer_jpeg_bytes: bytes
) -> None:
    response = client.post("/api/v1/predict", files=upload(norefer_jpeg_bytes))
    assert response.status_code == 200, response.text
    assert response.json()["eye"] is None


def test_png_upload_is_accepted_and_stored_as_png(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """C11: the stored extension follows the magic bytes, not a hardcoded .jpg."""
    import cv2
    import numpy as np

    from tests import synthetic

    rgb = synthetic.decode_rgb(refer_jpeg_bytes)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    png = bytes(np.asarray(buf).tobytes())

    response = client.post(
        "/api/v1/predict", files=upload(png, name="eye.png", content_type="image/png")
    )
    assert response.status_code == 200, response.text
    assert response.json()["image_url"].endswith(".png")
