"""Per-client request rate limiting for the authenticated API surface.

Audit finding: `require_api_key` (app/api/deps.py) has no throttle, so wrong
API-key guesses and upload floods against `/api/v1/*` are unbounded aside from
the per-request byte cap in `app/core/limits.py`. `app/core/errors.py`
(frozen) already reserves the `429 too_many_requests` error code and Uzbek
detail string for exactly this — nothing ever raised it.

Pure ASGI (not `BaseHTTPMiddleware`), matching `MaxBodySizeMiddleware`'s style:
a 429 here needs no cooperation from downstream routing or exception handling,
and this must sit where CORSMiddleware wraps it so a rejected browser client
still sees the Uzbek `detail` instead of an opaque network error (see
`test_oversize_413_still_carries_cors_headers` for the same reasoning applied
to 413).

Single-process, in-memory sliding window, keyed by client IP. This deployment
is a single SQLite-backed instance (app/db/base.py, app/storage/local.py) with
no shared cache between workers, so a distributed limiter (Redis, etc.) would
add infrastructure this project doesn't otherwise run; if this service is ever
scaled to multiple processes/workers, the limiter must move to shared storage
or every worker will apply its own independent quota.
"""

from __future__ import annotations

import json
import time
from collections import deque
from typing import Any

_JSON = b"application/json"


class RateLimitMiddleware:
    """Reject a client's requests beyond ``max_requests`` per ``window_seconds``.

    Scoped to ``path_prefix`` — the authenticated API surface an attacker
    would flood or brute-force an API key against. ``/health*`` and
    ``/static/*`` stay unthrottled (compose healthchecks, unauthenticated Coil
    image loads — C6).
    """

    def __init__(
        self,
        app: Any,
        *,
        path_prefix: str,
        max_requests: int,
        window_seconds: float,
        detail: str,
    ) -> None:
        self.app = app
        self.path_prefix = path_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.detail = detail
        # Pruned to empty-and-removed on every hit that finds a stale window,
        # so this does not grow without bound over the life of the process —
        # only genuinely recent clients are held.
        self._hits: dict[str, deque[float]] = {}

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not scope.get("path", "").startswith(
            self.path_prefix
        ):
            await self.app(scope, receive, send)
            return

        client_id = self._client_id(scope)
        now = time.monotonic()
        hits = self._hits.get(client_id)
        if hits is not None:
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()
            if not hits:
                del self._hits[client_id]
                hits = None

        if hits is not None and len(hits) >= self.max_requests:
            await self._reject(send)
            return

        if hits is None:
            hits = deque()
            self._hits[client_id] = hits
        hits.append(now)

        await self.app(scope, receive, send)

    @staticmethod
    def _client_id(scope: Any) -> str:
        client = scope.get("client")
        return client[0] if client else "unknown"

    async def _reject(self, send: Any) -> None:
        body = json.dumps(
            {"error": "too_many_requests", "detail": self.detail},
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"content-type", _JSON),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
