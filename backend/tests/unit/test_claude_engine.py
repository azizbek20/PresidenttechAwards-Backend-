"""ClaudeEngine against a fake async client (plan §3.3, §5). No network."""

from __future__ import annotations

import asyncio
import base64
import inspect
import io
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from tests.fakes import FakeAnthropic, make_assessment

PROMPT_FILE = Path(__file__).resolve().parents[2] / "app/inference/prompts/fundus_v1.md"
TEST_MODEL = "claude-test-model-9"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def make_settings(**env: Any) -> Any:
    from app.config import Settings

    values: dict[str, Any] = {
        "ANTHROPIC_API_KEY": "test-key",
        "CLAUDE_MODEL": TEST_MODEL,
        "CLAUDE_MAX_TOKENS": 777,
        "CLAUDE_TIMEOUT_S": 12.5,
    }
    values.update(env)
    return Settings(**{k: v for k, v in values.items() if v is not None})


def make_engine(client: Any, **env: Any) -> Any:
    from app.inference.claude_engine import ClaudeEngine

    return ClaudeEngine(make_settings(**env), client=client)


def run_assess(engine: Any, jpeg: bytes) -> Any:
    return asyncio.run(engine.assess(jpeg))


def jpeg_bytes(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height))
    px = img.load()
    for x in range(0, width, 7):
        for y in range(0, height, 7):
            px[x, y] = ((x * 3) % 256, (y * 5) % 256, 120)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def png_bytes(width: int, height: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), (200, 80, 40)).save(buf, format="PNG")
    return buf.getvalue()


def sent_image(call: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    block = call["messages"][0]["content"][0]
    return block, base64.b64decode(block["source"]["data"])


@pytest.fixture(autouse=True)
def _no_real_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("CLAUDE_MODEL", raising=False)


@pytest.fixture
def fake() -> FakeAnthropic:
    return FakeAnthropic.returning(make_assessment())


# --------------------------------------------------------------------------
# the request
# --------------------------------------------------------------------------
def test_one_call_with_image_block_then_instruction_text(
    fake: FakeAnthropic,
) -> None:
    from app.inference.claude_engine import USER_INSTRUCTION

    raw = jpeg_bytes(640, 480)
    run_assess(make_engine(fake), raw)

    assert len(fake.calls) == 1
    messages = fake.calls[0]["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    content = messages[0]["content"]
    assert len(content) == 2
    assert content[0] == {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": base64.b64encode(raw).decode("ascii"),
        },
    }
    assert content[1] == {"type": "text", "text": USER_INSTRUCTION}


def test_schema_model_and_limits_come_from_settings(fake: FakeAnthropic) -> None:
    from app.inference.assessment import FundusAssessment

    run_assess(make_engine(fake), jpeg_bytes(320, 240))

    call = fake.calls[0]
    assert call["output_format"] is FundusAssessment
    assert call["model"] == TEST_MODEL
    assert call["max_tokens"] == 777
    assert call["timeout"] == 12.5


def test_system_prompt_is_the_file_body_without_its_header_comment(
    fake: FakeAnthropic,
) -> None:
    run_assess(make_engine(fake), jpeg_bytes(320, 240))

    system = fake.calls[0]["system"]
    assert isinstance(system, str)
    assert not system.lstrip().startswith("<!--")
    assert "fundus_v1 — system prompt for ClaudeEngine" not in system
    body = PROMPT_FILE.read_text(encoding="utf-8").split("-->", 1)[1].strip()
    assert body[:120] in system
    assert body[-120:] in system


def test_assess_takes_only_image_bytes() -> None:
    from app.inference.claude_engine import ClaudeEngine

    params = list(inspect.signature(ClaudeEngine.assess).parameters)
    assert params == ["self", "jpeg"]


# --------------------------------------------------------------------------
# image preparation
# --------------------------------------------------------------------------
def test_small_jpeg_is_sent_byte_identical(fake: FakeAnthropic) -> None:
    raw = jpeg_bytes(1000, 700)
    run_assess(make_engine(fake), raw)
    block, data = sent_image(fake.calls[0])
    assert data == raw
    assert block["source"]["media_type"] == "image/jpeg"


def test_jpeg_exactly_at_the_limit_is_unchanged(fake: FakeAnthropic) -> None:
    from app.inference.claude_engine import MAX_LONG_SIDE

    assert MAX_LONG_SIDE == 1568
    raw = jpeg_bytes(MAX_LONG_SIDE, 900)
    run_assess(make_engine(fake), raw)
    assert sent_image(fake.calls[0])[1] == raw


@pytest.mark.parametrize(
    ("size", "expected"),
    [((2000, 1500), (1568, 1176)), ((1200, 3136), (588, 1568))],
    ids=["landscape", "portrait"],
)
def test_large_jpeg_is_resized_to_the_long_side_limit(
    fake: FakeAnthropic, size: tuple[int, int], expected: tuple[int, int]
) -> None:
    raw = jpeg_bytes(*size)
    run_assess(make_engine(fake), raw)

    block, data = sent_image(fake.calls[0])
    assert block["source"]["media_type"] == "image/jpeg"
    with Image.open(io.BytesIO(data)) as sent:
        assert sent.format == "JPEG"
        assert max(sent.size) == 1568
        assert abs(sent.size[0] - expected[0]) <= 1
        assert abs(sent.size[1] - expected[1]) <= 1


def test_png_is_reencoded_as_jpeg(fake: FakeAnthropic) -> None:
    raw = png_bytes(800, 600)
    run_assess(make_engine(fake), raw)

    block, data = sent_image(fake.calls[0])
    assert block["source"]["media_type"] == "image/jpeg"
    assert data != raw
    with Image.open(io.BytesIO(data)) as sent:
        assert sent.format == "JPEG"
        assert sent.size == (800, 600)


def test_large_png_is_resized_and_jpeg(fake: FakeAnthropic) -> None:
    run_assess(make_engine(fake), png_bytes(2400, 1000))
    _, data = sent_image(fake.calls[0])
    with Image.open(io.BytesIO(data)) as sent:
        assert sent.format == "JPEG"
        assert max(sent.size) == 1568


# --------------------------------------------------------------------------
# the result
# --------------------------------------------------------------------------
def test_returns_the_assessment_version_latency_and_tokens() -> None:
    a = make_assessment(icdr_grade=2, referable_probability=0.8)
    fake = FakeAnthropic.returning(a, input_tokens=4000, output_tokens=250)
    pred = run_assess(make_engine(fake), jpeg_bytes(320, 240))

    assert set(pred) == {
        "assessment",
        "model_version",
        "latency_ms",
        "input_tokens",
        "output_tokens",
    }
    assert pred["assessment"] == a
    assert pred["model_version"] == f"{TEST_MODEL}/prompt-v1"
    assert isinstance(pred["latency_ms"], float)
    assert pred["latency_ms"] >= 0
    assert pred["input_tokens"] == 4000
    assert pred["output_tokens"] == 250


# --------------------------------------------------------------------------
# failures raise; there is no fallback verdict
# --------------------------------------------------------------------------
def test_sdk_error_propagates() -> None:
    fake = FakeAnthropic.failing(RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        run_assess(make_engine(fake), jpeg_bytes(320, 240))


def test_builtin_timeout_propagates() -> None:
    fake = FakeAnthropic.failing(TimeoutError())
    with pytest.raises(TimeoutError):
        run_assess(make_engine(fake), jpeg_bytes(320, 240))


def test_sdk_timeout_propagates() -> None:
    import anthropic
    import httpx

    err = anthropic.APITimeoutError(request=httpx.Request("POST", "https://x.invalid"))
    fake = FakeAnthropic.failing(err)
    with pytest.raises(anthropic.APITimeoutError):
        run_assess(make_engine(fake), jpeg_bytes(320, 240))


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_bad_stop_reason_raises(stop_reason: str) -> None:
    fake = FakeAnthropic.returning(make_assessment(), stop_reason=stop_reason)
    with pytest.raises(Exception):  # noqa: B017 - the exception type is not pinned
        run_assess(make_engine(fake), jpeg_bytes(320, 240))


def test_missing_parsed_output_raises() -> None:
    fake = FakeAnthropic.returning(None)
    with pytest.raises(Exception):  # noqa: B017
        run_assess(make_engine(fake), jpeg_bytes(320, 240))


def _bad_enum_case() -> Any:
    a = make_assessment()
    return a.model_copy(update={"image_type": "Fundus"})


def _bad_presence_case() -> Any:
    a = make_assessment()
    return a.model_copy(
        update={"lesions": a.lesions.model_copy(update={"irma": "Present"})}
    )


def _bad_edema_case() -> Any:
    return make_assessment().model_copy(update={"macular_edema_signs": "PRESENT"})


def _bad_issue_case() -> Any:
    return make_assessment().model_copy(update={"quality_issues": ["Blur"]})


BAD_ASSESSMENTS: list[tuple[str, Callable[[], Any]]] = [
    ("image-type-case", _bad_enum_case),
    ("presence-case", _bad_presence_case),
    ("edema-case", _bad_edema_case),
    ("issue-case", _bad_issue_case),
    ("grade-5", lambda: make_assessment().model_copy(update={"icdr_grade": 5})),
    ("grade-neg", lambda: make_assessment().model_copy(update={"icdr_grade": -1})),
    (
        "prob-high",
        lambda: make_assessment().model_copy(update={"referable_probability": 1.2}),
    ),
    (
        "prob-neg",
        lambda: make_assessment().model_copy(update={"referable_probability": -0.1}),
    ),
]


@pytest.mark.parametrize(
    "build", [b for _, b in BAD_ASSESSMENTS], ids=[n for n, _ in BAD_ASSESSMENTS]
)
def test_locally_invalid_output_raises(build: Callable[[], Any]) -> None:
    fake = FakeAnthropic.returning(build())
    with pytest.raises(Exception):  # noqa: B017
        run_assess(make_engine(fake), jpeg_bytes(320, 240))


def test_boundary_values_are_accepted() -> None:
    for grade, p in [(0, 0.0), (4, 1.0)]:
        a = make_assessment(icdr_grade=grade, referable_probability=p)
        fake = FakeAnthropic.returning(a)
        pred = run_assess(make_engine(fake), jpeg_bytes(320, 240))
        assert pred["assessment"].icdr_grade == grade


# --------------------------------------------------------------------------
# properties, boot errors, factory
# --------------------------------------------------------------------------
def test_model_loaded_false_without_a_key(fake: FakeAnthropic) -> None:
    assert make_engine(fake, ANTHROPIC_API_KEY=None).model_loaded is False


def test_model_loaded_false_with_an_empty_key(fake: FakeAnthropic) -> None:
    assert make_engine(fake, ANTHROPIC_API_KEY="").model_loaded is False


def test_model_loaded_true_with_a_key(fake: FakeAnthropic) -> None:
    assert make_engine(fake).model_loaded is True


def test_class_declares_wants_jpeg() -> None:
    from app.inference.claude_engine import ClaudeEngine

    assert ClaudeEngine.wants_jpeg is True


def test_model_version_format(fake: FakeAnthropic) -> None:
    engine = make_engine(fake, CLAUDE_MODEL="claude-x", PROMPT_VERSION="v1")
    assert engine.model_version == "claude-x/prompt-v1"


def test_missing_prompt_file_is_a_boot_error(fake: FakeAnthropic) -> None:
    with pytest.raises((FileNotFoundError, OSError, ValueError, RuntimeError)):
        make_engine(fake, PROMPT_VERSION="v999-does-not-exist")


def test_get_engine_returns_a_claude_engine_for_the_claude_source() -> None:
    from app.inference.claude_engine import ClaudeEngine
    from app.inference.engine import get_engine

    settings = make_settings(EYE_MODEL_SOURCE="claude")
    engine = get_engine(settings)
    assert isinstance(engine, ClaudeEngine)
    assert engine.model_loaded is True
