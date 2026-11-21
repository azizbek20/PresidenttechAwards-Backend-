"""A fake async Anthropic client: records every ``messages.parse`` call.

It never imports ``app.*`` and never touches the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeUsage:
    input_tokens: int = 1234
    output_tokens: int = 321


@dataclass
class FakeParseResponse:
    """The slice of the SDK's parsed message the engine reads."""

    parsed_output: Any = None
    stop_reason: str = "end_turn"
    usage: FakeUsage = field(default_factory=FakeUsage)


class _FakeMessages:
    def __init__(self, owner: FakeAnthropic) -> None:
        self._owner = owner

    async def parse(self, **kwargs: Any) -> Any:
        self._owner.calls.append(kwargs)
        if self._owner.error is not None:
            raise self._owner.error
        return self._owner.response


class FakeAnthropic:
    """``await client.messages.parse(**kw)`` returns ``response`` or raises ``error``."""

    def __init__(
        self,
        response: Any = None,
        error: BaseException | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.messages = _FakeMessages(self)

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
            response=FakeParseResponse(
                parsed_output=assessment,
                stop_reason=stop_reason,
                usage=FakeUsage(input_tokens, output_tokens),
            )
        )

    @classmethod
    def failing(cls, error: BaseException) -> FakeAnthropic:
        return cls(error=error)
