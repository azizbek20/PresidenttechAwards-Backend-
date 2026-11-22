"""ClaudeHTTPClient: raw HTTP to the Messages API, no Anthropic SDK. No network.

Every test uses ``httpx.MockTransport``; nothing leaves the process.
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

APP_DIR = Path(__file__).resolve().parents[2] / "app"
EVAL_DIR = Path(__file__).resolve().parents[2] / "eval"
REQUIREMENTS = Path(__file__).resolve().parents[2] / "requirements.txt"
KEY = "sk-test-not-a-real-key"


def make_client(handler: Any) -> Any:
    from app.inference.claude_http import ClaudeHTTPClient

    return ClaudeHTTPClient(api_key=KEY, transport=httpx.MockTransport(handler))


def call(client: Any, body: dict[str, Any], timeout: float = 7.0) -> Any:
    async def go() -> Any:
        try:
            return await client.create_message(body, timeout=timeout)
        finally:
            await client.close()

    return asyncio.run(go())


# --------------------------------------------------------------------------
# no SDK
# --------------------------------------------------------------------------
def test_no_anthropic_sdk_import_in_app_or_eval() -> None:
    pattern = re.compile(r"^\s*(import anthropic|from anthropic\b)", re.MULTILINE)
    for path in [*APP_DIR.rglob("*.py"), *EVAL_DIR.rglob("*.py")]:
        assert not pattern.search(path.read_text(encoding="utf-8")), path


def test_sdk_is_not_a_runtime_requirement() -> None:
    lines = REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    names = [ln.split("=")[0].split("[")[0].strip().lower() for ln in lines if ln and not ln.startswith("#")]
    assert "anthropic" not in names
    assert "httpx" in names


# --------------------------------------------------------------------------
# the request
# --------------------------------------------------------------------------
def test_posts_json_to_messages_with_key_and_version_headers() -> None:
    from app.inference.claude_http import ANTHROPIC_VERSION, MESSAGES_URL

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"content": [], "stop_reason": "end_turn"})

    body = {"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}
    result = call(make_client(handler), body)

    assert result == {"content": [], "stop_reason": "end_turn"}
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == MESSAGES_URL == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == KEY
    assert request.headers["anthropic-version"] == ANTHROPIC_VERSION
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == body


def test_per_call_timeout_is_applied() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={})

    call(make_client(handler), {}, timeout=3.5)
    assert seen[0]["read"] == 3.5
    assert seen[0]["connect"] == 3.5


def test_no_automatic_retry() -> None:
    hits: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        hits.append(1)
        return httpx.Response(529, json={"type": "error", "error": {"type": "overloaded_error", "message": "busy"}})

    with pytest.raises(Exception):  # noqa: B017
        call(make_client(handler), {})
    assert len(hits) == 1


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------
@pytest.mark.parametrize("status", [400, 401, 429, 500, 529])
def test_non_2xx_raises_with_status_and_error_type(status: int) -> None:
    from app.inference.claude_http import ClaudeAPIError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            headers={"request-id": "req_123"},
            json={"type": "error", "error": {"type": "some_error", "message": "nope"}},
        )

    with pytest.raises(ClaudeAPIError) as info:
        call(make_client(handler), {})
    err = info.value
    assert err.status_code == status
    assert err.error_type == "some_error"
    assert err.request_id == "req_123"
    assert KEY not in str(err)


def test_non_json_error_body_still_raises_cleanly() -> None:
    from app.inference.claude_http import ClaudeAPIError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    with pytest.raises(ClaudeAPIError) as info:
        call(make_client(handler), {})
    assert info.value.status_code == 502
    assert info.value.error_type is None


def test_transport_timeout_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(httpx.TimeoutException):
        call(make_client(handler), {})


def test_key_is_not_in_the_client_repr() -> None:
    client = make_client(lambda r: httpx.Response(200, json={}))
    assert KEY not in repr(client)
    asyncio.run(client.close())
