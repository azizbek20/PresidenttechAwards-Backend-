"""C9 — shadow mode without a verified model refuses to answer.

The failure this prevents is the quiet one: a deployment believed to be
running a real model, silently serving mock verdicts to clinicians. So
`EYE_MODE=shadow` with no loadable checkpoint returns `503 model_unavailable`
and `/health/ready` stays 503 — it never degrades to the mock engine.

`EYE_MODEL_DIR` points at an empty tmp directory, so this test behaves the same
before and after Agent A's `torch_engine.py` merges (missing module -> import
error -> `UnavailableEngine`; present module -> missing checkpoint -> same).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.contract._appkit import build_client
from tests.contract.conftest import upload

SHADOW_DIGEST = "0" * 64


@pytest.fixture
def shadow_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Any]:
    empty_models = tmp_path / "models"
    empty_models.mkdir(parents=True, exist_ok=True)
    yield from build_client(
        monkeypatch,
        tmp_path,
        EYE_MODE="shadow",
        EYE_MODEL_SOURCE="torch",
        EYE_MODEL_SHA256=SHADOW_DIGEST,
        EYE_MODEL_DIR=str(empty_models),
    )


def test_predict_is_503_model_unavailable(
    shadow_client: Any, refer_jpeg_bytes: bytes
) -> None:
    response = shadow_client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "model_unavailable"
    assert isinstance(body["detail"], str) and body["detail"]


def test_no_mock_prediction_is_ever_served(
    shadow_client: Any, refer_jpeg_bytes: bytes
) -> None:
    """The whole point of C9: no verdict, no grade, no `mock-v0`."""
    body = shadow_client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes)
    ).json()
    assert set(body) == {"error", "detail"}
    assert "mock" not in body["detail"].lower()


def test_health_reports_the_model_as_not_loaded(shadow_client: Any) -> None:
    response = shadow_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_loaded": False}


def test_readiness_is_503_without_a_verified_artifact(shadow_client: Any) -> None:
    response = shadow_client.get("/health/ready")
    assert response.status_code == 503, response.text
    assert response.json()["checks"]["model"] is False


def test_liveness_and_ping_still_answer(shadow_client: Any) -> None:
    """A model-less shadow deployment is unhealthy, not dead."""
    assert shadow_client.get("/health/live").status_code == 200
    assert shadow_client.head("/").status_code == 204


def test_demo_mode_readiness_is_200(client: Any) -> None:
    """Control: demo mode is ready with the mock engine, by design."""
    response = client.get("/health/ready")
    assert response.status_code == 200, response.text
    assert response.json()["checks"] == {
        "database": True,
        "storage": True,
        "model": True,
    }
