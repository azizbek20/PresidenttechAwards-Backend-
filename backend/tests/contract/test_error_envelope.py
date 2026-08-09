"""C4 — one error envelope, on every path, with no FastAPI defaults leaking.

The shape is exactly `{"error": ..., "detail": ...}`. FastAPI's stock
validation body is `{"detail": [ ... ]}`, which fails BOTH halves of the
contract: it drops `error` and it makes `detail` a list the phone renders as
an empty string.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.contract.conftest import upload


def assert_envelope(response: Any, status: int, error: str) -> dict[str, Any]:
    assert response.status_code == status, response.text
    body = response.json()
    assert set(body) == {"error", "detail"}, body
    assert body["error"] == error
    assert isinstance(body["detail"], str) and body["detail"]
    return dict(body)


def test_text_file_is_rejected_as_invalid_image(
    client: Any, text_file_bytes: bytes
) -> None:
    response = client.post(
        "/api/v1/predict",
        files=upload(text_file_bytes, name="notes.txt", content_type="text/plain"),
    )
    assert_envelope(response, 400, "invalid_image")


def test_empty_upload_is_invalid_image(client: Any) -> None:
    response = client.post("/api/v1/predict", files=upload(b""))
    assert_envelope(response, 400, "invalid_image")


def test_truncated_jpeg_that_cannot_decode_is_invalid_image(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """Right magic bytes, unusable payload — the decoder must be the judge."""
    response = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes[:64]))
    assert_envelope(response, 400, "invalid_image")


def test_missing_file_part_is_a_string_detail_422(client: Any) -> None:
    """The exact case that would otherwise emit `{"detail": [...]}`."""
    response = client.post("/api/v1/predict", data={"eye": "right"})
    body = assert_envelope(response, 422, "validation_error")
    assert not isinstance(body["detail"], list)


def test_bad_eye_value_is_422(client: Any, refer_jpeg_bytes: bytes) -> None:
    response = client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "middle"}
    )
    assert_envelope(response, 422, "validation_error")


def test_unknown_exam_is_404_not_found(client: Any) -> None:
    response = client.get("/api/v1/exams/6f0f1d1e-0000-4000-8000-000000000000")
    assert_envelope(response, 404, "not_found")


def test_oversized_upload_is_413(client: Any) -> None:
    """MAX_UPLOAD_MB defaults to 10; this body is over it by construction."""
    from app.config import get_settings

    cap = get_settings().max_upload_bytes
    payload = b"\xff\xd8\xff" + b"\x00" * cap
    response = client.post("/api/v1/predict", files=upload(payload))
    assert_envelope(response, 413, "payload_too_large")


def test_engine_failure_is_500_inference_error(
    client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(self: Any, img: Any) -> Any:
        raise RuntimeError("engine exploded")

    monkeypatch.setattr("app.inference.mock_engine.MockEngine.predict", boom)

    response = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    body = assert_envelope(response, 500, "inference_error")
    assert "engine exploded" not in body["detail"], "internals must not leak"


def test_method_not_allowed_still_uses_the_envelope(client: Any) -> None:
    response = client.get("/api/v1/predict")
    assert response.status_code == 405
    body = response.json()
    assert set(body) == {"error", "detail"}
    assert isinstance(body["detail"], str) and body["detail"]


def test_no_error_response_ever_has_a_list_detail(
    client: Any, text_file_bytes: bytes, refer_jpeg_bytes: bytes
) -> None:
    responses = [
        client.post("/api/v1/predict", data={"eye": "right"}),
        client.post("/api/v1/predict", files=upload(text_file_bytes)),
        client.post(
            "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "up"}
        ),
        client.get("/api/v1/exams/does-not-exist"),
        client.get("/api/v1/exams", params={"limit": 1000}),
        client.get("/api/v1/nope"),
    ]
    for response in responses:
        assert response.status_code >= 400, response.url
        body = response.json()
        assert set(body) == {"error", "detail"}, (response.url, body)
        assert isinstance(body["detail"], str), (response.url, body)


def test_read_aborts_the_moment_the_cap_is_crossed(client: Any) -> None:
    """C11 directly: the cap is enforced *while* streaming, not afterwards.

    Going through HTTP would only exercise the Content-Length shortcut, so the
    chunked branch is driven here with a body that never reports its length.
    """
    # Imported here, not at module scope: the frozen conftest rebuilt the
    # `app.*` tree for this test, so an earlier `ApiError` would be a
    # different class object and `pytest.raises` would not match it.
    from app.api import predict as predict_api
    from app.core.errors import ApiError

    cap = 3 * predict_api.READ_CHUNK

    class _Upload:
        """Yields chunks forever; a buffer-then-check reader would hang."""

        def __init__(self) -> None:
            self.reads = 0

        async def read(self, size: int) -> bytes:
            self.reads += 1
            return b"\x00" * size

    class _Request:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

    upload_file = _Upload()
    with pytest.raises(ApiError) as caught:
        asyncio.run(predict_api._read_capped(_Request(), upload_file, cap))

    assert caught.value.status == 413
    assert caught.value.error == "payload_too_large"
    # cap/READ_CHUNK reads fit, the next one crosses it and aborts.
    assert upload_file.reads == 4
