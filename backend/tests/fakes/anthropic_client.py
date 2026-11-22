"""A fake Claude Messages API client: records every ``create_message`` call.

It stands in for :class:`app.inference.claude_http.ClaudeHTTPClient` (raw
HTTP, no SDK). It never imports ``app.*`` and never touches the network.
``calls`` holds each JSON request body exactly as the engine built it, and
``timeouts`` the per-call timeout.
"""

from __future__ import annotations

import json
from typing import Any


def message_response(
    assessment: Any,
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 1234,
    output_tokens: int = 321,
) -> dict[str, Any]:
    """A Messages API response body (decoded JSON) carrying ``assessment``.

    ``assessment=None`` gives a response with no text block.
    """
    content: list[dict[str, Any]] = []
    if assessment is not None:
        data = assessment.model_dump(mode="json", warnings=False)
        content.append({"type": "text", "text": json.dumps(data)})
    return {
        "id": "msg_fake",
        "type": "message",
        "role": "assistant",
        "content": content,
        "stop_reason": stop_reason,
        "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
    }


class FakeAnthropic:
    """``await client.create_message(body, timeout=...)`` returns ``response`` or raises ``error``."""

    def __init__(
        self,
        response: dict[str, Any] | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.timeouts: list[float] = []

    async def create_message(self, body: dict[str, Any], *, timeout: float) -> dict[str, Any]:
        self.calls.append(body)
        self.timeouts.append(timeout)
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response

    @classmethod
    def returning(
        cls,
        assessment: Any,
        *,
        stop_reason: str = "end_turn",
        input_tokens: int = 1234,
        output_tokens: int = 321,
    ) -> FakeAnthropic:
        return cls(
            response=message_response(
                assessment,
                stop_reason=stop_reason,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        )

    @classmethod
    def failing(cls, error: BaseException) -> FakeAnthropic:
        return cls(error=error)
