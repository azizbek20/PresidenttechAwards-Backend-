"""Regressions for four defects the requirements audit found in the merged tree.

Each of these passed the original suite. They are pinned here so they cannot
come back silently.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.contract._appkit import build_client
from tests.contract.conftest import upload

SHADOW_DIGEST = "0" * 64

#: Framework wording that must never reach the phone. ScreeningViewModel.kt:332
#: prints `detail` verbatim, so an English string here is shown to a clinician.
_ENGLISH_LEAKS = (
    "boundary",
    "Content-Disposition",
    "Bad Request",
    "Unauthorized",
    "Not Found",
    "Internal Server Error",
    "Unprocessable",
    "Request Entity Too Large",
)


def _assert_uzbek_detail(body: dict) -> None:
    detail = body["detail"]
    assert isinstance(detail, str) and detail, f"detail must be a non-empty str: {body}"
    for leak in _ENGLISH_LEAKS:
        assert leak.lower() not in detail.lower(), f"English framework wording leaked: {detail!r}"


# --------------------------------------------------------------------------
# 1. A non-ASCII API key must be rejected, not crash the comparison.
# --------------------------------------------------------------------------
def test_non_ascii_api_key_comparison_does_not_raise() -> None:
    """`secrets.compare_digest` raises TypeError on non-ASCII *str*.

    Before the fix that TypeError escaped the dependency and the catch-all
    handler turned a wrong key into `500 inference_error` — telling an attacker
    the server broke rather than that the key was wrong.
    """
    from app.core.security import verify_api_key

    assert verify_api_key("аuditkey", "testkey") is False  # Cyrillic а
    assert verify_api_key("ключ", "testkey") is False
    assert verify_api_key("🔑", "testkey") is False
    assert verify_api_key("testkey", "testkey") is True


def test_non_ascii_api_key_is_401_not_500(authed_client: Any) -> None:
    """End-to-end version of the above.

    The header value is passed as BYTES: httpx refuses to encode a non-ASCII
    *str* header and raises UnicodeEncodeError client-side, so a str here would
    test the HTTP client rather than the server. Starlette decodes the raw
    bytes as latin-1, which still yields a non-ASCII str at the dependency —
    exactly the input that used to blow up.
    """
    response = authed_client.get(
        "/api/v1/exams", headers={"X-API-Key": "аuditkey".encode()}
    )
    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"] == "unauthorized"
    _assert_uzbek_detail(body)


def test_a_correct_key_still_works(authed_client: Any) -> None:
    assert authed_client.get("/api/v1/exams").status_code == 200


# --------------------------------------------------------------------------
# 2. Framework-raised HTTP errors must not leak English detail (C15).
# --------------------------------------------------------------------------
def test_malformed_multipart_detail_is_uzbek(authed_client: Any) -> None:
    """The multipart parser raises its own English HTTPException.

    Before the fix the phone showed "Missing boundary in multipart." verbatim.
    """
    response = authed_client.post(
        "/api/v1/predict",
        content=b"garbage-not-multipart",
        headers={"Content-Type": "multipart/form-data"},
    )
    assert response.status_code == 400, response.text
    _assert_uzbek_detail(response.json())


def test_unknown_exam_detail_is_uzbek(authed_client: Any) -> None:
    body = authed_client.get("/api/v1/exams/does-not-exist").json()
    assert body["error"] == "not_found"
    _assert_uzbek_detail(body)


# --------------------------------------------------------------------------
# 3. An oversized declared Content-Length is refused before body parsing (C11).
# --------------------------------------------------------------------------
@pytest.fixture
def small_cap_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Any]:
    yield from build_client(monkeypatch, tmp_path, MAX_UPLOAD_MB="1")


def test_declared_oversize_is_413(small_cap_client: Any) -> None:
    """`UploadFile = File(...)` spools the whole body before the endpoint runs,
    so the cap has to be enforced in middleware to mean anything at the HTTP
    layer.
    """
    payload = b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024)  # 2 MB, cap is 1 MB
    response = small_cap_client.post(
        "/api/v1/predict",
        content=payload,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 413, response.status_code
    body = response.json()
    assert body["error"] == "payload_too_large"
    _assert_uzbek_detail(body)


def test_a_normal_upload_is_unaffected(
    small_cap_client: Any, refer_jpeg_bytes: bytes
) -> None:
    response = small_cap_client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "REFER"


# --------------------------------------------------------------------------
# 4. Shadow mode refuses EVERY predict, including quality-gate failures (C9).
# --------------------------------------------------------------------------
@pytest.fixture
def shadow_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Any]:
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


def test_shadow_refuses_even_an_ungradable_image(
    shadow_client: Any, blurry_jpeg_bytes: bytes
) -> None:
    """The 503 used to live INSIDE the `if report.ok:` branch.

    A blurry image therefore skipped it and came back 200 UNGRADABLE carrying
    model_version="mock-v0" and mode="shadow" — a model-less deployment
    answering as though a model were loaded. §4.9 says predict returns 503.
    """
    response = shadow_client.post(
        "/api/v1/predict", files=upload(blurry_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "model_unavailable"
    assert "mock" not in response.text.lower(), "shadow must never mention a mock model"


def test_shadow_refuses_a_dark_image_too(
    shadow_client: Any, dark_jpeg_bytes: bytes
) -> None:
    response = shadow_client.post(
        "/api/v1/predict", files=upload(dark_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 503, response.text
