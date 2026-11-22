"""Phase 2 config rules (plan §3.2, §5) and the model-less shadow boot."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.contract._appkit import build_client
from tests.contract.conftest import upload

ENV_NAMES = (
    "EYE_MODE",
    "EYE_MODEL_SOURCE",
    "EYE_MODEL_SHA256",
    "EYE_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_MODEL",
    "CLAUDE_TIMEOUT_S",
    "CLAUDE_MAX_TOKENS",
    "PROMPT_VERSION",
    "UNCERTAIN_REFERS",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def settings_cls() -> Any:
    from app.config import Settings

    return Settings


# --------------------------------------------------------------------------
# defaults and accepted values
# --------------------------------------------------------------------------
def test_claude_defaults() -> None:
    s = settings_cls()()
    assert s.anthropic_api_key is None
    assert s.claude_model == "claude-sonnet-5-5"
    assert s.claude_timeout_s == 25.0
    assert s.claude_max_tokens == 4000
    assert s.prompt_version == "v2"
    assert s.uncertain_refers is True


def test_claude_fields_read_their_env_names(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("CLAUDE_MODEL", "claude-opus-5-5")
    monkeypatch.setenv("CLAUDE_TIMEOUT_S", "9.5")
    monkeypatch.setenv("CLAUDE_MAX_TOKENS", "1200")
    monkeypatch.setenv("PROMPT_VERSION", "v1")
    monkeypatch.setenv("UNCERTAIN_REFERS", "false")
    s = settings_cls()()
    assert s.anthropic_api_key == "test-key"
    assert s.claude_model == "claude-opus-5-5"
    assert s.claude_timeout_s == 9.5
    assert s.claude_max_tokens == 1200
    assert s.prompt_version == "v1"
    assert s.uncertain_refers is False


def test_claude_is_an_accepted_model_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EYE_MODEL_SOURCE", "claude")
    assert settings_cls()().eye_model_source == "claude"


def test_onnx_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EYE_MODEL_SOURCE", "onnx")
    with pytest.raises(ValueError):
        settings_cls()()


# --------------------------------------------------------------------------
# mode validator
# --------------------------------------------------------------------------
def test_shadow_claude_without_eye_api_key_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EYE_MODE", "shadow")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "claude")
    with pytest.raises(ValueError, match="EYE_API_KEY"):
        settings_cls()()


def test_shadow_claude_with_an_empty_eye_api_key_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EYE_MODE", "shadow")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "claude")
    monkeypatch.setenv("EYE_API_KEY", "")
    with pytest.raises(ValueError, match="EYE_API_KEY"):
        settings_cls()()


def test_shadow_claude_needs_no_sha256_and_no_anthropic_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EYE_MODE", "shadow")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "claude")
    monkeypatch.setenv("EYE_API_KEY", "demo123")
    s = settings_cls()()
    assert s.eye_mode == "shadow"
    assert s.anthropic_api_key is None
    assert s.eye_model_sha256 is None


@pytest.mark.parametrize("with_key", [True, False])
def test_demo_claude_is_allowed(
    monkeypatch: pytest.MonkeyPatch, with_key: bool
) -> None:
    monkeypatch.setenv("EYE_MODE", "demo")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "claude")
    if with_key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    s = settings_cls()()
    assert (s.eye_mode, s.eye_model_source) == ("demo", "claude")


def test_the_legacy_shadow_rules_still_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EYE_MODE", "shadow")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "mock")
    with pytest.raises(ValueError, match="shadow"):
        settings_cls()()

    monkeypatch.setenv("EYE_MODEL_SOURCE", "torch")
    with pytest.raises(ValueError, match="SHA256"):
        settings_cls()()


# --------------------------------------------------------------------------
# shadow + claude without an Anthropic key: boots, answers 503
# --------------------------------------------------------------------------
@pytest.fixture
def keyless_shadow_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[Any]:
    yield from build_client(
        monkeypatch,
        tmp_path,
        api_key="demo123",
        EYE_MODE="shadow",
        EYE_MODEL_SOURCE="claude",
    )


def test_keyless_shadow_claude_is_alive_but_not_ready(
    keyless_shadow_client: Any,
) -> None:
    assert keyless_shadow_client.get("/health/live").status_code == 200
    ready = keyless_shadow_client.get("/health/ready")
    assert ready.status_code == 503, ready.text
    assert ready.json()["checks"]["model"] is False


def test_keyless_shadow_claude_predict_is_503_model_unavailable(
    keyless_shadow_client: Any, refer_jpeg_bytes: bytes
) -> None:
    response = keyless_shadow_client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        headers={"X-API-Key": "demo123"},
    )
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["error"] == "model_unavailable"
    assert set(body) == {"error", "detail"}


# --------------------------------------------------------------------------
# Phase 3: Postgres URL rewrite, pool settings, EYE_STORAGE (plan §3.2, §3.8, §3.9)
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgres://u:p@host.example:5432/db?sslmode=require",
            "postgresql+psycopg://u:p@host.example:5432/db?sslmode=require",
        ),
        (
            "postgresql://u:p@host.example/db",
            "postgresql+psycopg://u:p@host.example/db",
        ),
        (
            "postgresql+psycopg://u:p@host.example/db",
            "postgresql+psycopg://u:p@host.example/db",
        ),
        ("sqlite:///./eye.db", "sqlite:///./eye.db"),
        ("sqlite:////tmp/x/test.db", "sqlite:////tmp/x/test.db"),
    ],
    ids=["postgres", "postgresql", "psycopg-kept", "sqlite", "sqlite-abs"],
)
def test_database_url_is_rewritten_for_psycopg(
    monkeypatch: pytest.MonkeyPatch, given: str, expected: str
) -> None:
    monkeypatch.setenv("DATABASE_URL", given)
    assert settings_cls()().database_url == expected


def test_eye_storage_defaults_to_local(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EYE_STORAGE", raising=False)
    assert settings_cls()().eye_storage == "local"


def test_eye_storage_accepts_blob(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EYE_STORAGE", "blob")
    assert settings_cls()().eye_storage == "blob"


@pytest.mark.parametrize("bad", ["s3", "", "LOCAL "])
def test_eye_storage_rejects_other_values(
    monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    monkeypatch.setenv("EYE_STORAGE", bad)
    with pytest.raises(ValueError):
        settings_cls()()


def test_postgres_engine_uses_the_small_serverless_pool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.contract._appkit import purge_app_modules

    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@localhost:5432/eye")
    monkeypatch.setenv("EYE_STORAGE_DIR", str(tmp_path / "storage"))
    purge_app_modules()
    from app.config import get_settings

    get_settings.cache_clear()
    import app.db.base as db_base

    try:
        engine = db_base.get_engine()  # creating an engine never connects
        assert engine.url.drivername == "postgresql+psycopg"
        assert engine.pool.size() == 2  # type: ignore[attr-defined]
        assert engine.pool._max_overflow == 2  # type: ignore[attr-defined]
        assert engine.pool._pre_ping is True  # type: ignore[attr-defined]
    finally:
        db_base.dispose_engine()
        purge_app_modules()


def test_sqlite_engine_keeps_its_setup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from tests.contract._appkit import purge_app_modules

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'x.db'}")
    purge_app_modules()
    from app.config import get_settings

    get_settings.cache_clear()
    import app.db.base as db_base

    try:
        engine = db_base.get_engine()
        assert engine.url.get_backend_name() == "sqlite"
        assert engine.pool._pre_ping is True  # type: ignore[attr-defined]
        with db_base.get_session() as session:
            from sqlalchemy import text

            assert session.execute(text("SELECT 1")).scalar() == 1
    finally:
        db_base.dispose_engine()
        purge_app_modules()
