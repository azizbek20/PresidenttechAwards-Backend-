"""RateLimitMiddleware (app/core/rate_limit.py) — audit finding C2 follow-up.

`require_api_key` (app/api/deps.py) had no throttle: wrong-key guesses and
upload floods against `/api/v1/*` were unbounded, even though
`app/core/errors.py` (frozen) already reserved the `429 too_many_requests`
error code and Uzbek detail string for exactly this. Nothing ever raised it.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

_ENGLISH_LEAKS = ("Too Many Requests", "Rate limit")


def _assert_uzbek_429(body: dict) -> None:
    assert body["error"] == "too_many_requests"
    detail = body["detail"]
    assert isinstance(detail, str) and detail
    for leak in _ENGLISH_LEAKS:
        assert leak.lower() not in detail.lower(), f"English wording leaked: {detail!r}"


# --------------------------------------------------------------------------
# Unit-level: drive the ASGI middleware directly, the same way
# test_audit_regressions.py exercises MaxBodySizeMiddleware.
# --------------------------------------------------------------------------
def _scope(path: str, client_ip: str = "203.0.113.9") -> dict[str, Any]:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "client": (client_ip, 51000),
    }


@pytest.mark.asyncio
async def test_nth_plus_one_request_from_the_same_client_is_429() -> None:
    from app.core.rate_limit import RateLimitMiddleware

    async def inner(scope, receive, send):  # noqa: ANN001
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RateLimitMiddleware(
        inner,
        path_prefix="/api/v1",
        max_requests=3,
        window_seconds=60.0,
        detail="So'rovlar juda ko'p — biroz kuting",
    )

    async def receive():  # noqa: ANN202
        return {"type": "http.request", "body": b"", "more_body": False}

    for _ in range(3):
        sent: list[dict[str, Any]] = []

        async def send(message, _sent=sent):  # noqa: ANN001
            _sent.append(message)

        await middleware(_scope("/api/v1/exams"), receive, send)
        assert sent[0]["status"] == 200, sent

    sent = []

    async def send_4th(message):  # noqa: ANN001
        sent.append(message)

    await middleware(_scope("/api/v1/exams"), receive, send_4th)
    assert sent[0]["status"] == 429, sent
    body = json.loads(sent[1]["body"])
    _assert_uzbek_429(body)


@pytest.mark.asyncio
async def test_a_different_client_ip_has_its_own_quota() -> None:
    from app.core.rate_limit import RateLimitMiddleware

    async def inner(scope, receive, send):  # noqa: ANN001
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RateLimitMiddleware(
        inner, path_prefix="/api/v1", max_requests=1, window_seconds=60.0, detail="x"
    )

    async def receive():  # noqa: ANN202
        return {"type": "http.request", "body": b"", "more_body": False}

    sent_a: list[dict[str, Any]] = []

    async def send_a(message):  # noqa: ANN001
        sent_a.append(message)

    await middleware(_scope("/api/v1/exams", "10.0.0.1"), receive, send_a)
    assert sent_a[0]["status"] == 200

    sent_b: list[dict[str, Any]] = []

    async def send_b(message):  # noqa: ANN001
        sent_b.append(message)

    await middleware(_scope("/api/v1/exams", "10.0.0.2"), receive, send_b)
    assert sent_b[0]["status"] == 200, "a different client must not inherit the first quota"


@pytest.mark.asyncio
async def test_a_path_outside_the_prefix_is_never_limited() -> None:
    from app.core.rate_limit import RateLimitMiddleware

    async def inner(scope, receive, send):  # noqa: ANN001
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = RateLimitMiddleware(
        inner, path_prefix="/api/v1", max_requests=1, window_seconds=60.0, detail="x"
    )

    async def receive():  # noqa: ANN202
        return {"type": "http.request", "body": b"", "more_body": False}

    for _ in range(5):
        sent: list[dict[str, Any]] = []

        async def send(message, _sent=sent):  # noqa: ANN001
            _sent.append(message)

        await middleware(_scope("/health"), receive, send)
        assert sent[0]["status"] == 200, sent


# --------------------------------------------------------------------------
# End-to-end: through the real app, with its actual configured quota.
# --------------------------------------------------------------------------
def test_exceeding_the_quota_end_to_end_is_429(authed_client: Any) -> None:
    responses = [authed_client.get("/api/v1/exams") for _ in range(31)]
    assert [r.status_code for r in responses[:30]] == [200] * 30, [
        r.status_code for r in responses[:30]
    ]
    assert responses[30].status_code == 429, responses[30].text
    _assert_uzbek_429(responses[30].json())


def test_429_still_carries_cors_headers(authed_client: Any) -> None:
    for _ in range(30):
        authed_client.get("/api/v1/exams")
    limited = authed_client.get(
        "/api/v1/exams", headers={"Origin": "https://example.com"}
    )
    assert limited.status_code == 429, limited.text
    assert limited.headers.get("access-control-allow-origin") == "*", dict(
        limited.headers
    )


def test_health_is_unaffected_once_the_api_quota_is_exhausted(authed_client: Any) -> None:
    for _ in range(30):
        authed_client.get("/api/v1/exams")
    assert authed_client.get("/api/v1/exams").status_code == 429

    assert authed_client.get("/health").status_code == 200
    assert authed_client.get("/health/live").status_code == 200
