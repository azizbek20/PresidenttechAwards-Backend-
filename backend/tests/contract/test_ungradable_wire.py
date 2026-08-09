"""C3 — UNGRADABLE on the wire is non-null placeholders, never nulls.

The deployed APK dereferences `probability` and `icdr_grade` unconditionally,
so an honest `null` would crash the phone. The truth is kept in the database
(NULL columns) instead; this file pins the wire half of that split.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.schemas import PredictResponse
from tests.contract.conftest import upload


@pytest.fixture
def blurry_body(client: Any, blurry_jpeg_bytes: bytes) -> dict[str, Any]:
    response = client.post(
        "/api/v1/predict", files=upload(blurry_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_blurry_image_is_ungradable(blurry_body: dict[str, Any]) -> None:
    assert blurry_body["decision"] == "UNGRADABLE"
    assert blurry_body["quality"] == "poor"


def test_placeholders_are_non_null(blurry_body: dict[str, Any]) -> None:
    assert blurry_body["referable"] is False
    assert blurry_body["probability"] == 0.0
    assert blurry_body["icdr_grade"] == 0
    assert blurry_body["grade_label"] == "Baholab bo'lmadi"


def test_no_heatmap_for_an_ungradable_image(blurry_body: dict[str, Any]) -> None:
    """Nothing was analysed, so there is nothing to overlay."""
    assert blurry_body["heatmap_url"] is None


def test_ungradable_body_still_validates(blurry_body: dict[str, Any]) -> None:
    PredictResponse.model_validate(blurry_body)


def test_dark_image_is_also_ungradable(client: Any, dark_jpeg_bytes: bytes) -> None:
    response = client.post("/api/v1/predict", files=upload(dark_jpeg_bytes))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["decision"] == "UNGRADABLE"
    assert payload["quality"] == "poor"
    assert payload["probability"] == 0.0


def test_ungradable_exam_reads_back_with_the_same_placeholders(
    client: Any, blurry_body: dict[str, Any]
) -> None:
    """History and the admin panel must agree with the result screen."""
    stored = client.get(f"/api/v1/exams/{blurry_body['exam_id']}")
    assert stored.status_code == 200, stored.text
    payload = stored.json()
    assert payload["decision"] == "UNGRADABLE"
    assert payload["probability"] == 0.0
    assert payload["icdr_grade"] == 0
    assert payload["grade_label"] == "Baholab bo'lmadi"
