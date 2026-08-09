"""Regressions for four defects the requirements audit found in the merged tree.

Each of these passed the original suite. They are pinned here so they cannot
come back silently.
"""

from __future__ import annotations

import contextlib
import json
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


# --------------------------------------------------------------------------
# 5. C11: the cap must bite on a body that declares NO Content-Length.
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_raw_stream_cap_aborts_a_chunked_body() -> None:
    """Drives the ASGI middleware directly.

    A chunked request carries no Content-Length, so the cheap header check
    cannot help and only the counting path can stop it. Exercising the ASGI
    contract here (rather than through TestClient) keeps the test independent
    of whether httpx chooses to stream or to buffer.
    """
    from app.core.limits import MaxBodySizeMiddleware

    async def never_called(scope, receive, send):  # noqa: ANN001
        # Drain the stream the way the multipart parser would.
        while True:
            message = await receive()
            if not message.get("more_body"):
                return

    sent: list[dict] = []

    async def send(message):  # noqa: ANN001
        sent.append(message)

    chunks = [b"\x00" * 4096] * 40  # 160 KB against a 64 KB cap
    index = 0

    async def receive():
        nonlocal index
        if index < len(chunks):
            body = chunks[index]
            index += 1
            return {"type": "http.request", "body": body, "more_body": True}
        return {"type": "http.request", "body": b"", "more_body": False}

    middleware = MaxBodySizeMiddleware(
        never_called, max_bytes=64 * 1024, detail="Rasm hajmi juda katta"
    )
    scope = {"type": "http", "method": "POST", "path": "/api/v1/predict", "headers": []}
    await middleware(scope, receive, send)

    assert sent[0]["status"] == 413, sent
    body = json.loads(sent[1]["body"])
    assert body["error"] == "payload_too_large"
    _assert_uzbek_detail(body)
    assert index < len(chunks), "the stream must abort early, not drain fully"


@pytest.mark.asyncio
async def test_raw_stream_cap_lets_a_small_body_through() -> None:
    from app.core.limits import MaxBodySizeMiddleware

    seen = []

    async def inner(scope, receive, send):  # noqa: ANN001
        while True:
            message = await receive()
            seen.append(len(message.get("body", b"")))
            if not message.get("more_body"):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    sent: list[dict] = []
    done = False

    async def receive():
        nonlocal done
        if not done:
            done = True
            return {"type": "http.request", "body": b"x" * 1024, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):  # noqa: ANN001
        sent.append(message)

    middleware = MaxBodySizeMiddleware(inner, max_bytes=64 * 1024, detail="x")
    await middleware(
        {"type": "http", "method": "POST", "path": "/p", "headers": []},
        receive,
        send,
    )
    assert sent[0]["status"] == 200
    assert sum(seen) == 1024


# --------------------------------------------------------------------------
# 6. D4: the admin exams table needs model_version from the LIST endpoint.
# --------------------------------------------------------------------------
def test_exams_list_carries_model_version(
    authed_client: Any, refer_jpeg_bytes: bytes
) -> None:
    """`response_model=list[ExamSummary]` used to strip it, so the admin
    panel's `Model` column rendered "—" for every row (§5-D D4)."""
    created = authed_client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
    )
    assert created.status_code == 200, created.text

    rows = authed_client.get("/api/v1/exams").json()
    assert rows, "expected at least one exam"
    for row in rows:
        assert row.get("model_version"), f"model_version missing/blank: {row}"
    assert rows[0]["model_version"] == created.json()["model_version"]


# --------------------------------------------------------------------------
# 7. C10: persistence failure is 500 in BOTH modes — varying EYE_MODE, not auth.
# --------------------------------------------------------------------------
class _LoadedEngine:
    """A shadow-mode engine that reports itself loaded, so the request gets
    past the C9 gate and reaches persistence."""

    model_loaded = True

    def predict(self, img):  # noqa: ANN001
        return {"grade": 4, "probs": [0.0, 0.0, 0.0, 0.0, 1.0], "model_version": "shadow-test"}


def _boom(*args: object, **kwargs: object) -> None:
    raise RuntimeError("database is on fire")


def test_persistence_failure_is_500_in_demo_mode(
    authed_client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _boom)
    response = authed_client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 500, response.text
    assert response.json()["error"] == "persistence_error"


def test_shadow_never_replays_a_stored_mock_exam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, refer_jpeg_bytes: bytes
) -> None:
    """C9 hole found by the closure audit: the gate sat BELOW the C14 replay.

    A model-less shadow deployment sharing a database with an earlier demo run
    replayed the stored exam and answered
    200 {"model_version": "mock-v0", "mode": "shadow"} — a deployment with no
    model answering as though one were loaded. Realistic because the compose
    volume survives `down`, EYE_MODE is a .env flip, and DEDUP_WINDOW_MIN
    reaches 1440 minutes.
    """
    shared = tmp_path / "shared"
    shared.mkdir()

    with contextlib.closing(build_client(monkeypatch, shared)) as gen:
        demo = next(gen)
        created = demo.post(
            "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
        )
        assert created.status_code == 200, created.text
        assert created.json()["model_version"] == "mock-v0"

    empty_models = tmp_path / "models"
    empty_models.mkdir()
    shadow_gen = build_client(
        monkeypatch,
        shared,
        EYE_MODE="shadow",
        EYE_MODEL_SOURCE="torch",
        EYE_MODEL_SHA256=SHADOW_DIGEST,
        EYE_MODEL_DIR=str(empty_models),
    )
    with contextlib.closing(shadow_gen) as gen:
        shadow = next(gen)
        replay = shadow.post(
            "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
        )
        assert replay.status_code == 503, replay.text
        assert replay.json()["error"] == "model_unavailable"
        assert "mock" not in replay.text.lower()


def test_oversize_413_still_carries_cors_headers(small_cap_client: Any) -> None:
    """The cap middleware must sit INSIDE CORSMiddleware.

    Registered outermost, its 413 bypassed CORS entirely and a browser client
    saw a network error instead of the Uzbek `detail`.
    """
    payload = b"\xff\xd8\xff" + b"\x00" * (2 * 1024 * 1024)
    response = small_cap_client.post(
        "/api/v1/predict",
        content=payload,
        headers={
            "Content-Type": "application/octet-stream",
            "Origin": "https://example.com",
        },
    )
    assert response.status_code == 413, response.status_code
    assert response.headers.get("access-control-allow-origin") == "*", dict(
        response.headers
    )


def test_persistence_failure_is_500_in_shadow_mode(
    shadow_client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C10 is UNCONDITIONAL. The existing suite only varied AUTH, which its own
    docstring admits "changes nothing about C10" — the mode axis was untested.
    """
    shadow_client.app.state.engine = _LoadedEngine()
    monkeypatch.setattr("app.db.crud.create_exam_with_result", _boom)

    response = shadow_client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 500, response.text
    body = response.json()
    assert body["error"] == "persistence_error"
    _assert_uzbek_detail(body)
