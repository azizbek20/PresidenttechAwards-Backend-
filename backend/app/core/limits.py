"""Raw-stream upload cap (C11).

Why this exists at the ASGI layer rather than in the route:

``file: UploadFile = File(...)`` makes FastAPI parse the multipart body — and
spool it to a temporary file — BEFORE the endpoint function runs. So a cap
enforced inside the handler bounds how much the handler copies, not how much
the server ingests: an audit probe pushed a 100 MB body that was fully written
to disk before the 413 came back, with no ceiling other than free space. The
handler's 1 MB chunk loop was reading from an already-complete spool file and
bought nothing.

C11 says "Stream with a byte cap — never buffer-then-check". Only middleware
that wraps the raw ASGI ``receive`` channel can honour that, because it sees
body chunks as they arrive and can abort mid-stream. Content-Length is checked
first as a cheap fast path, but it is only a *claim* — a chunked request omits
it entirely, which is exactly the case the counting path covers.
"""

from __future__ import annotations

import json
from typing import Any

_JSON = b"application/json"


class BodyTooLarge(Exception):
    """Raised inside the wrapped ``receive`` once the cap is crossed."""


class MaxBodySizeMiddleware:
    """Reject a request body larger than ``max_bytes`` before it is parsed.

    Pure ASGI (not ``BaseHTTPMiddleware``) so it can wrap ``receive`` itself.
    It sits OUTSIDE Starlette's ``ExceptionMiddleware``, so ``BodyTooLarge``
    reaches the ``except`` below instead of being converted into a 500 by the
    catch-all handler.
    """

    def __init__(self, app: Any, *, max_bytes: int, detail: str) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.detail = detail

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        # Fast path: an honestly declared oversize is refused without reading
        # a single body byte.
        for key, value in scope.get("headers", ()):
            if key.lower() == b"content-length":
                try:
                    if int(value) > self.max_bytes:
                        await self._reject(send)
                        return
                except ValueError:
                    pass
                break

        total = 0
        exceeded = False
        forwarded = False

        async def counting_receive() -> Any:
            nonlocal total, exceeded
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    exceeded = True
                    # Abort now: the point of C11 is to stop reading, not to
                    # drain the body politely and complain afterwards.
                    raise BodyTooLarge
            return message

        async def guarded_send(message: Any) -> None:
            nonlocal forwarded
            if exceeded:
                # FastAPI wraps `await request.form()` in a broad
                # `except Exception` and re-raises it as HTTPException(400), so
                # BodyTooLarge usually never reaches our `except` below — the
                # app just answers 400. Swallow that response: nothing has
                # reached the client yet, so we are still free to send 413.
                return
            forwarded = True
            await send(message)

        try:
            await self.app(scope, counting_receive, guarded_send)
        except BodyTooLarge:
            pass  # propagated cleanly; fall through to the 413 below

        if exceeded and not forwarded:
            await self._reject(send)

    async def _reject(self, send: Any) -> None:
        body = json.dumps(
            {"error": "payload_too_large", "detail": self.detail},
            ensure_ascii=False,
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", _JSON),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
