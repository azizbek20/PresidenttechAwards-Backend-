"""The real ClaudeEngine (fake client) inside the running app (plan §3.6, §5)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.contract._appkit import build_client
from tests.contract.conftest import upload
from tests.fakes import FakeAnthropic, make_assessment

MODEL = "claude-wiring-test"
FUNDUS_TEXT = (
    "Bu ko'z tubi (fundus) rasmi emas — fundus kamera yoki adapter bilan oling"
)


class ClaudeApp:
    """A TestClient whose engine is the real ClaudeEngine on a fake client."""

    def __init__(self, client: Any) -> None:
        self.client = client
        self.fake = FakeAnthropic.returning(make_assessment())

    def use(self, fake: FakeAnthropic) -> FakeAnthropic:
        from app.config import get_settings
        from app.inference.claude_engine import ClaudeEngine

        settings = get_settings().model_copy(update={"anthropic_api_key": "test-key"})
        self.fake = fake
        self.client.app.state.engine = ClaudeEngine(settings, client=fake)
        return fake

    def post(self, raw: bytes, **form: Any) -> Any:
        data = {k: v for k, v in form.items() if v is not None}
        return self.client.post("/api/v1/predict", files=upload(raw), data=data)


@pytest.fixture
def claude_app(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[ClaudeApp]:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    gen = build_client(
        monkeypatch,
        tmp_path,
        EYE_MODE="demo",
        EYE_MODEL_SOURCE="claude",
        CLAUDE_MODEL=MODEL,
    )
    client = next(gen)
    app = ClaudeApp(client)
    app.use(FakeAnthropic.returning(make_assessment()))
    try:
        yield app
    finally:
        gen.close()


def result_rows() -> list[Any]:
    import app.db.base as db_base
    from app.db.models import Result

    with db_base.get_session() as session:
        rows = list(session.query(Result).all())
        session.expunge_all()
    return rows


# --------------------------------------------------------------------------
# zero Claude calls
# --------------------------------------------------------------------------
def test_quality_gate_failure_makes_no_claude_call(
    claude_app: ClaudeApp, blurry_jpeg_bytes: bytes
) -> None:
    response = claude_app.post(blurry_jpeg_bytes, eye="right")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "UNGRADABLE"
    assert body["quality"] == "poor"
    assert claude_app.fake.calls == []
    rows = result_rows()
    assert len(rows) == 1
    assert rows[0].assessment_json is None


def test_dark_image_makes_no_claude_call(
    claude_app: ClaudeApp, dark_jpeg_bytes: bytes
) -> None:
    response = claude_app.post(dark_jpeg_bytes)
    assert response.json()["decision"] == "UNGRADABLE"
    assert claude_app.fake.calls == []


def test_dedup_replay_makes_exactly_one_claude_call(
    claude_app: ClaudeApp, refer_jpeg_bytes: bytes
) -> None:
    claude_app.use(
        FakeAnthropic.returning(make_assessment(icdr_grade=3, referable_probability=0.9))
    )
    first = claude_app.post(refer_jpeg_bytes, patient_id="P-0001", eye="right")
    second = claude_app.post(refer_jpeg_bytes, patient_id="P-0001", eye="right")

    assert first.status_code == second.status_code == 200, second.text
    assert first.json()["exam_id"] == second.json()["exam_id"]
    assert len(claude_app.fake.calls) == 1
    assert len(claude_app.client.get("/api/v1/exams").json()) == 1


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "build",
    [
        lambda: FakeAnthropic.failing(RuntimeError("api down")),
        lambda: FakeAnthropic.failing(TimeoutError()),
        lambda: FakeAnthropic.returning(None),
        lambda: FakeAnthropic.returning(make_assessment(), stop_reason="refusal"),
    ],
    ids=["sdk-error", "timeout", "no-parsed-output", "refusal"],
)
def test_engine_failure_is_500_inference_error_and_nothing_is_stored(
    claude_app: ClaudeApp, refer_jpeg_bytes: bytes, build: Any
) -> None:
    fake = claude_app.use(build())
    response = claude_app.post(refer_jpeg_bytes, eye="right")

    assert response.status_code == 500, response.text
    body = response.json()
    assert body["error"] == "inference_error"
    assert isinstance(body["detail"], str) and body["detail"]
    assert "referable" not in body and "decision" not in body
    assert len(fake.calls) == 1
    assert claude_app.client.get("/api/v1/exams").json() == []
    assert result_rows() == []


# --------------------------------------------------------------------------
# verdicts
# --------------------------------------------------------------------------
def test_non_fundus_image_is_ungradable_with_the_fundus_text(
    claude_app: ClaudeApp, refer_jpeg_bytes: bytes
) -> None:
    claude_app.use(
        FakeAnthropic.returning(
            make_assessment(
                image_type="external_eye",
                gradable=False,
                rationale="A photograph of an eyelid.",
            )
        )
    )
    response = claude_app.post(refer_jpeg_bytes)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "UNGRADABLE"
    assert body["referable"] is False
    assert body["decision_text"] == FUNDUS_TEXT
    assert body["probability"] == 0.0
    assert body["icdr_grade"] == 0
    assert body["grade_label"] == "Baholab bo'lmadi"
    assert len(claude_app.fake.calls) == 1
    row = result_rows()[0]
    assert row.probability is None
    assert row.icdr_grade is None


def test_graded_refer_persists_the_assessment_and_the_model_version(
    claude_app: ClaudeApp, refer_jpeg_bytes: bytes
) -> None:
    assessment = make_assessment(
        lesions={"hard_exudates": "present", "microaneurysms": "present"},
        icdr_grade=3,
        referable_probability=0.93,
        rationale="Exudates near the macula.",
    )
    claude_app.use(FakeAnthropic.returning(assessment))

    response = claude_app.post(refer_jpeg_bytes, patient_id="P-0007", eye="left")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["decision"] == "REFER"
    assert body["referable"] is True
    assert body["icdr_grade"] == 3
    assert body["grade_label"] == "Og'ir NPDR"
    assert body["probability"] == 0.93
    assert body["heatmap_url"] is None
    assert body["model_version"] == f"{MODEL}/prompt-v2"

    rows = result_rows()
    assert len(rows) == 1
    assert rows[0].assessment_json == assessment.model_dump_json()
    assert rows[0].model_version == f"{MODEL}/prompt-v2"
    assert rows[0].icdr_grade == 3
    assert rows[0].probability == 0.93


def test_graded_no_refer(claude_app: ClaudeApp, refer_jpeg_bytes: bytes) -> None:
    claude_app.use(FakeAnthropic.returning(make_assessment()))
    body = claude_app.post(refer_jpeg_bytes).json()
    assert body["decision"] == "NO_REFER"
    assert body["quality"] == "good"
    assert body["icdr_grade"] == 0
    assert body["probability"] == 0.1


def test_response_keys_are_the_legacy_keys_plus_request_id_and_mode(
    claude_app: ClaudeApp, refer_jpeg_bytes: bytes
) -> None:
    from app.schemas import LEGACY_KEYS

    body = claude_app.post(refer_jpeg_bytes).json()
    assert set(body) == set(LEGACY_KEYS) | {"request_id", "mode"}
    assert body["mode"] == "demo"


# --------------------------------------------------------------------------
# privacy
# --------------------------------------------------------------------------
def test_patient_id_never_reaches_claude(
    claude_app: ClaudeApp, refer_jpeg_bytes: bytes
) -> None:
    secret = "P-SECRET-4242"
    response = claude_app.post(refer_jpeg_bytes, patient_id=secret, eye="right")

    assert response.status_code == 200, response.text
    assert response.json()["patient_id"] == secret
    assert len(claude_app.fake.calls) == 1
    for call in claude_app.fake.calls:
        assert secret not in repr(call)
