"""Claude vision engine for ``POST /api/v1/predict`` (MIGRATION_PLAN.md §3.3).

One request per screening: the (possibly downsized) JPEG plus a fixed
instruction, with the versioned fundus prompt as the system prompt and the
:class:`~app.inference.assessment.FundusAssessment` schema as structured
output. Safety rules carried here:

* Only the image and fixed text are sent — :meth:`ClaudeEngine.assess` takes
  image bytes and nothing else, so no patient id, eye or request metadata can
  reach the API.
* No fallback verdict. An SDK error, a timeout, a refusal, a truncated answer
  or output that fails local validation all raise; ``predict.py`` maps that to
  ``500 inference_error``.
* No automatic retries on the request path (``max_retries=0``) and a hard
  per-request timeout (``CLAUDE_TIMEOUT_S``): the phone has its own retry.
"""

from __future__ import annotations

import asyncio
import base64
import io
import math
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageOps

from app.inference.assessment import FundusAssessment
from app.inference.engine import ClaudePrediction

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.config import Settings

#: Claude's vision models downscale anything larger; sending more only costs
#: upload time and latency.
MAX_LONG_SIDE = 1568
JPEG_QUALITY = 90

#: The fixed user text sent with every image. Never interpolate request data.
USER_INSTRUCTION = (
    "Assess this photograph following the system instructions and fill in "
    "every field of the required output."
)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
_HEADER_COMMENT = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)
_SAFE_VERSION = re.compile(r"[A-Za-z0-9_-]+")
_JPEG_MAGIC = b"\xff\xd8\xff"


class ClaudeOutputError(RuntimeError):
    """Claude answered, but not with an assessment we may turn into a verdict."""


def load_system_prompt(prompt_version: str) -> str:
    """Read ``prompts/fundus_<version>.md`` with its leading ``<!-- -->`` header removed.

    A missing file raises :class:`FileNotFoundError`: it is a boot error
    (plan §3.3), never a reason to fall back to another prompt.
    """
    if not _SAFE_VERSION.fullmatch(prompt_version):
        raise ValueError(f"unsafe PROMPT_VERSION={prompt_version!r}")
    path = _PROMPT_DIR / f"fundus_{prompt_version}.md"
    text = path.read_text(encoding="utf-8")
    return _HEADER_COMMENT.sub("", text, count=1).strip()


def prepare_jpeg(raw: bytes) -> bytes:
    """The bytes to send: unchanged for a JPEG within ``MAX_LONG_SIDE``.

    Anything larger is downsized keeping its aspect ratio; any non-JPEG (PNG)
    is re-encoded as JPEG. EXIF orientation is applied when re-encoding so
    the pixels Claude sees match what the uploader saw.
    """
    with Image.open(io.BytesIO(raw)) as opened:
        is_jpeg = opened.format == "JPEG" and raw.startswith(_JPEG_MAGIC)
        if is_jpeg and max(opened.size) <= MAX_LONG_SIDE:
            return raw
        img = ImageOps.exif_transpose(opened) or opened
        img = img.convert("RGB")
    if max(img.size) > MAX_LONG_SIDE:
        img.thumbnail((MAX_LONG_SIDE, MAX_LONG_SIDE), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=JPEG_QUALITY)
    return out.getvalue()


def _secret(value: Any) -> str:
    """The key as text, whether ``Settings`` holds a str or a ``SecretStr``."""
    if value is None:
        return ""
    getter = getattr(value, "get_secret_value", None)
    return str(getter() if callable(getter) else value)


def validate_assessment(parsed: Any) -> FundusAssessment:
    """Re-validate the model's answer locally; raise on anything off-schema.

    The API enforces the JSON shape but not numeric ranges, and an object
    built without validation (``model_construct``) must not slip through
    either — so the answer is always rebuilt through Pydantic, enum strings
    must be exactly lower-case, and ranges are checked here.
    """
    if isinstance(parsed, FundusAssessment):
        data = parsed.model_dump(mode="python", warnings=False)
    elif hasattr(parsed, "model_dump"):
        data = parsed.model_dump(mode="python", warnings=False)
    else:
        data = parsed
    assessment = FundusAssessment.model_validate(data, strict=False)
    if isinstance(assessment.icdr_grade, bool) or not 0 <= assessment.icdr_grade <= 4:
        raise ClaudeOutputError(f"icdr_grade out of range: {assessment.icdr_grade!r}")
    p = assessment.referable_probability
    if not math.isfinite(p) or not 0.0 <= p <= 1.0:
        raise ClaudeOutputError(f"referable_probability out of range: {p!r}")
    return assessment


class ClaudeEngine:
    """Engine for ``EYE_MODEL_SOURCE=claude``. Receives JPEG bytes, not a tensor."""

    wants_jpeg = True

    def __init__(self, settings: "Settings", client: Any = None) -> None:
        self._settings = settings
        # Boot error, not a runtime fallback (plan §3.3).
        self._system_prompt = load_system_prompt(settings.prompt_version)
        if client is None and self.model_loaded:
            from anthropic import AsyncAnthropic

            client = AsyncAnthropic(
                api_key=_secret(settings.anthropic_api_key),
                timeout=settings.claude_timeout_s,
                max_retries=0,
            )
        self._client = client

    @property
    def model_loaded(self) -> bool:
        return bool(_secret(self._settings.anthropic_api_key))

    @property
    def model_version(self) -> str:
        return f"{self._settings.claude_model}/prompt-{self._settings.prompt_version}"

    async def assess(self, jpeg: bytes) -> ClaudePrediction:
        """One Claude call for one image. Raises on every failure."""
        if self._client is None:  # predict.py's 3c gate normally stops this first
            raise ClaudeOutputError("ANTHROPIC_API_KEY is not configured")
        # Pillow decode/resize/re-encode is CPU work: keep it off the event loop.
        prepared = await asyncio.to_thread(prepare_jpeg, jpeg)
        image = base64.standard_b64encode(prepared).decode("ascii")
        settings = self._settings
        started = time.perf_counter()
        response = await self._client.messages.parse(
            model=settings.claude_model,
            max_tokens=settings.claude_max_tokens,
            system=self._system_prompt,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image,
                            },
                        },
                        {"type": "text", "text": USER_INSTRUCTION},
                    ],
                }
            ],
            output_format=FundusAssessment,
            timeout=settings.claude_timeout_s,
        )
        latency_ms = (time.perf_counter() - started) * 1000.0

        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason in ("refusal", "max_tokens"):
            raise ClaudeOutputError(f"unusable answer: stop_reason={stop_reason}")
        parsed = getattr(response, "parsed_output", None)
        if parsed is None:
            raise ClaudeOutputError("no structured output in the response")
        assessment = validate_assessment(parsed)

        usage = getattr(response, "usage", None)
        return ClaudePrediction(
            assessment=assessment,
            model_version=self.model_version,
            latency_ms=latency_ms,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
        )
