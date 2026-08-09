"""C15 — `detail` is user-visible text, so it is always a non-empty string.

`ScreeningViewModel.kt:323-329` does `JSONObject(body).optString("detail")` and
shows the result to the user. `optString` on a JSON *array* silently returns
"", so a FastAPI-style `{"detail": [...]}` would degrade every error on the
phone to a generic message — the failure mode is invisible from the server
side, which is exactly why it needs a dedicated regression test.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.conftest import upload


def _explode(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("boom")


def error_responses(
    client: Any, text_file_bytes: bytes, refer_jpeg_bytes: bytes
) -> list[tuple[str, Any]]:
    """Every error path Agent C owns, in one place."""
    from app.config import get_settings

    oversized = b"\xff\xd8\xff" + b"\x00" * get_settings().max_upload_bytes
    return [
        ("missing file part", client.post("/api/v1/predict", data={"eye": "right"})),
        ("not an image", client.post("/api/v1/predict", files=upload(text_file_bytes))),
        ("empty upload", client.post("/api/v1/predict", files=upload(b""))),
        (
            "undecodable image",
            client.post("/api/v1/predict", files=upload(refer_jpeg_bytes[:32])),
        ),
        (
            "bad eye",
            client.post(
                "/api/v1/predict",
                files=upload(refer_jpeg_bytes),
                data={"eye": "sideways"},
            ),
        ),
        ("oversized", client.post("/api/v1/predict", files=upload(oversized))),
        ("unknown exam", client.get("/api/v1/exams/nope")),
        ("bad limit", client.get("/api/v1/exams", params={"limit": 500})),
        ("unknown route", client.get("/api/v1/does-not-exist")),
        ("wrong method", client.get("/api/v1/predict")),
        ("missing static", client.get("/static/images/missing.jpg")),
    ]


def test_every_error_path_returns_a_non_empty_string_detail(
    client: Any, text_file_bytes: bytes, refer_jpeg_bytes: bytes
) -> None:
    for label, response in error_responses(client, text_file_bytes, refer_jpeg_bytes):
        assert response.status_code >= 400, label
        body = response.json()
        assert isinstance(body, dict), label
        assert set(body) == {"error", "detail"}, (label, body)
        assert isinstance(body["detail"], str), (label, type(body["detail"]))
        assert body["detail"].strip(), label
        assert isinstance(body["error"], str) and body["error"], label


def test_unauthorized_detail_is_a_string(
    authed_client: Any, refer_jpeg_bytes: bytes
) -> None:
    response = authed_client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        headers={"X-API-Key": "wrong"},
    )
    assert response.status_code == 401
    assert isinstance(response.json()["detail"], str)


def test_persistence_error_detail_is_a_string(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)
    body = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    assert body["error"] == "persistence_error"
    assert isinstance(body["detail"], str) and body["detail"].strip()


def test_inference_error_detail_is_a_string(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.inference.mock_engine.MockEngine.predict", _explode)
    body = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    assert body["error"] == "inference_error"
    assert isinstance(body["detail"], str) and body["detail"].strip()
