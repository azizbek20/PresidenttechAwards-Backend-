"""Safety regression: the quality gate runs BEFORE the DR engine, always.

If the order ever flips, a blurry photo would be graded by a model that was
never given a gradable image — and the demo-grade quality heuristic is the
only thing standing between "unreadable photo" and "confident 6% NO_REFER".
The engine is therefore replaced with a landmine: any call fails the test.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.conftest import upload


def _landmine(self: Any, img: Any) -> Any:
    raise AssertionError("the DR engine was invoked after a quality-gate failure")


def test_blurry_image_never_reaches_the_engine(
    client: Any, blurry_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.inference.mock_engine.MockEngine.predict", _landmine)

    response = client.post(
        "/api/v1/predict", files=upload(blurry_jpeg_bytes), data={"eye": "right"}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["decision"] == "UNGRADABLE"
    assert payload["quality"] == "poor"


def test_dark_image_never_reaches_the_engine(
    client: Any, dark_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.inference.mock_engine.MockEngine.predict", _landmine)

    response = client.post("/api/v1/predict", files=upload(dark_jpeg_bytes))

    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "UNGRADABLE"


def test_the_landmine_really_does_fire_on_a_gradable_image(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control: proves the two tests above pass for the right reason."""
    monkeypatch.setattr("app.inference.mock_engine.MockEngine.predict", _landmine)

    response = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))

    assert response.status_code == 500
    assert response.json()["error"] == "inference_error"


def test_the_quality_gate_sees_the_full_image_not_the_crop(
    client: Any, blurry_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Step 5 runs before step 6's `retina_crop`, so cropping cannot rescue
    an image the gate already rejected."""
    cropped: list[int] = []
    import importlib

    preprocess = importlib.import_module("app.inference.preprocess")
    original = preprocess.retina_crop

    def spy(img: Any) -> Any:
        cropped.append(1)
        return original(img)

    monkeypatch.setattr("app.inference.preprocess.retina_crop", spy)

    response = client.post("/api/v1/predict", files=upload(blurry_jpeg_bytes))
    assert response.status_code == 200
    assert response.json()["decision"] == "UNGRADABLE"
    assert cropped == [], "the image was cropped despite failing the gate"
