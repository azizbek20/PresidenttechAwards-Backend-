"""Raw HTTP client for the Claude Messages API (no Anthropic SDK).

One method, :meth:`ClaudeHTTPClient.create_message`: POST a JSON body to
``/v1/messages`` and return the decoded JSON response. Rules carried here:

* No automatic retries: one attempt per call (the phone has its own retry).
* A hard per-call timeout, applied to connect, read, write and pool.
* A non-2xx answer raises :class:`ClaudeAPIError` with the status, the API's
  error type and the ``request-id`` header; never the key or the request body.
"""

from __future__ import annotations

from typing import Any

import httpx

MESSAGES_URL = "https://api.anthropic.com/v1/messages"
#: API version header. 2026-10-21 rejects sampling parameters, which this
#: backend never sends.
ANTHROPIC_VERSION = "2026-10-21"


class ClaudeAPIError(RuntimeError):
    """The Messages API answered with a non-2xx status."""

    def __init__(
        self,
        status_code: int,
        error_type: str | None,
        message: str,
        request_id: str | None,
    ) -> None:
        self.status_code = status_code
        self.error_type = error_type
        self.request_id = request_id
        super().__init__(
            f"Claude API {status_code} {error_type or 'unknown_error'}: {message} "
            f"(request_id={request_id})"
        )


def _error_from(response: httpx.Response) -> ClaudeAPIError:
    error_type: str | None = None
    message = ""
    try:
        data = response.json()
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            error_type = error.get("type")
            message = str(error.get("message", ""))[:300]
    except ValueError:  # not JSON (a proxy's HTML page, for example)
        message = ""
    return ClaudeAPIError(
        response.status_code, error_type, message, response.headers.get("request-id")
    )


class ClaudeHTTPClient:
    """``await create_message(body, timeout=...)`` → the response JSON as a dict."""

    def __init__(
        self,
        api_key: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._headers = {
            "x-api-key": api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }
        # transport=None: httpx's default, which never retries a request.
        self._http = httpx.AsyncClient(transport=transport)

    def __repr__(self) -> str:  # never show the key
        return f"ClaudeHTTPClient(url={MESSAGES_URL!r})"

    async def create_message(self, body: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        response = await self._http.post(
            MESSAGES_URL,
            json=body,
            headers=self._headers,
            timeout=httpx.Timeout(timeout),
        )
        if response.status_code // 100 != 2:
            raise _error_from(response)
        data = response.json()
        if not isinstance(data, dict):
            raise ClaudeAPIError(response.status_code, None, "response is not an object", None)
        return data

    async def close(self) -> None:
        await self._http.aclose()
