"""App log lines must reach stdout (NOTES.md open decision 9, logging spec).

Nothing in ``app/`` used to configure logging, so every INFO line from the
``eyedetect.*`` loggers (the per-call ``claude_call`` line, ``rate_limit``)
was dropped under uvicorn and on Vercel. Tests that read records directly
(caplog) could not see it, so item 1 runs a real subprocess.
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

from tests.contract._appkit import purge_app_modules
from tests.contract.conftest import upload
from tests.contract.test_claude_wiring import ClaudeApp, claude_app  # noqa: F401
from tests.fakes import FakeAnthropic, make_assessment

BACKEND = Path(__file__).resolve().parents[2]
HANDLER_NAME = "eyedetect-stdout"


# --------------------------------------------------------------------------
# 1. a real process, real stdout, no pytest handlers
# --------------------------------------------------------------------------
def test_probe_reaches_stdout_exactly_once(tmp_path: Path) -> None:
    probe = f"probe-{uuid.uuid4().hex}"
    storage = tmp_path / "storage"
    storage.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env.update(
        {
            "EYE_ENV_FILE": "",
            "EYE_MODE": "demo",
            "EYE_MODEL_SOURCE": "mock",
            "EYE_STORAGE_DIR": str(storage),
            "DATABASE_URL": f"sqlite:///{tmp_path / 'sub.db'}",
        }
    )
    code = (
        "import logging\n"
        "from app.main import create_app\n"
        "create_app()\n"
        "create_app()\n"
        f"logging.getLogger('eyedetect.predict').info({probe!r})\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    lines = [line for line in proc.stdout.splitlines() if probe in line]
    assert len(lines) == 1, proc.stdout
    assert lines[0] == f"INFO eyedetect.predict {probe}"
    assert proc.stdout.count(probe) == 1


# --------------------------------------------------------------------------
# 2. in-process configuration
# --------------------------------------------------------------------------
def _named_handlers() -> list[logging.Handler]:
    return [h for h in logging.getLogger("eyedetect").handlers if h.name == HANDLER_NAME]


def _build_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """What the frozen fixtures do, but returning the snapshot around create_app."""
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EYE_MODE", "demo")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "mock")
    monkeypatch.setenv("EYE_STORAGE_DIR", str(storage))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'log.db'}")
    monkeypatch.delenv("EYE_API_KEY", raising=False)
    purge_app_modules()
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    return create_app


@pytest.fixture(autouse=False)
def _cleanup_app() -> Any:
    yield
    purge_app_modules()


def test_eyedetect_logger_is_configured(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _cleanup_app: Any
) -> None:
    create_app = _build_app(monkeypatch, tmp_path)
    create_app()
    predict_logger = logging.getLogger("eyedetect.predict")
    assert predict_logger.isEnabledFor(logging.INFO)
    assert logging.getLogger("eyedetect").level == logging.INFO
    assert logging.getLogger("eyedetect").propagate is True
    assert len(_named_handlers()) == 1


def test_one_handler_after_second_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _cleanup_app: Any
) -> None:
    _build_app(monkeypatch, tmp_path)()
    # purge + re-import, the way the frozen fixtures do per test
    create_app = _build_app(monkeypatch, tmp_path)
    create_app()
    create_app()
    assert len(_named_handlers()) == 1
    assert [h.name for h in logging.getLogger("eyedetect").handlers].count(HANDLER_NAME) == 1


def test_root_logger_is_untouched(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _cleanup_app: Any
) -> None:
    create_app = _build_app(monkeypatch, tmp_path)
    root = logging.getLogger()
    level_before = root.level
    handlers_before = list(root.handlers)
    uvicorn_before = {
        name: (logging.getLogger(name).level, list(logging.getLogger(name).handlers))
        for name in ("uvicorn", "uvicorn.error", "uvicorn.access")
    }
    create_app()
    assert root.level == level_before
    assert list(root.handlers) == handlers_before
    for name, (level, handlers) in uvicorn_before.items():
        assert logging.getLogger(name).level == level
        assert list(logging.getLogger(name).handlers) == handlers


def test_handler_format_and_stream_resolved_at_emit_time(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    _cleanup_app: Any,
) -> None:
    _build_app(monkeypatch, tmp_path)()
    logging.getLogger("eyedetect.predict").info("emit-time-check")
    out = capsys.readouterr().out
    assert "INFO eyedetect.predict emit-time-check" in out


# --------------------------------------------------------------------------
# 3. the per-call line
# --------------------------------------------------------------------------
PATIENT_ID = "PATIENT-SECRET-7731"
API_KEY_VALUE = "super-secret-api-key-4242"


def _call_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == "eyedetect.predict" and r.getMessage().startswith("claude_call")
    ]


def test_claude_call_line_fields_and_no_secrets(
    claude_app: ClaudeApp,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
    refer_jpeg_bytes: bytes,
) -> None:
    fake = claude_app.use(FakeAnthropic.returning(make_assessment(), input_tokens=4321, output_tokens=765))
    caplog.set_level(logging.INFO, logger="eyedetect")
    response = claude_app.client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        data={"patient_id": PATIENT_ID, "eye": "right"},
        headers={"X-API-Key": API_KEY_VALUE},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(fake.calls) == 1

    records = _call_records(caplog)
    assert len(records) == 1
    msg = records[0].getMessage()
    assert f"request_id={body['request_id']}" in msg
    assert f"exam_id={body['exam_id']}" in msg
    assert f"model_version={body['model_version']}" in msg
    assert "latency_ms=" in msg
    assert "input_tokens=4321" in msg
    assert "output_tokens=765" in msg
    assert "image_type=fundus" in msg
    assert f"decision={body['decision']}" in msg

    b64_prefix = base64.standard_b64encode(refer_jpeg_bytes).decode("ascii")[:40]
    for record in caplog.records:
        text = record.getMessage() + " " + str(record.args) + " " + str(record.exc_text)
        assert PATIENT_ID not in text
        assert API_KEY_VALUE not in text
        assert b64_prefix not in text


def test_quality_gate_failure_logs_no_claude_call(
    claude_app: ClaudeApp,  # noqa: F811
    caplog: pytest.LogCaptureFixture,
    blurry_jpeg_bytes: bytes,
) -> None:
    caplog.set_level(logging.INFO, logger="eyedetect")
    response = claude_app.post(blurry_jpeg_bytes, eye="right")
    assert response.status_code == 200, response.text
    assert response.json()["decision"] == "UNGRADABLE"
    assert claude_app.fake.calls == []
    assert _call_records(caplog) == []



# --------------------------------------------------------------------------
# 4. Vercel: one line per event (NOTES.md open decision 10)
#
# Vercel's runtime prints the root logger at INFO to stdout, so with
# propagation on every app line appeared twice: ours (prefixed) and raw.
# --------------------------------------------------------------------------
BASIC_CONFIG = (
    'logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(message)s")\n'
)


def _run_child(tmp_path: Path, body: str, *, vercel: str | None) -> subprocess.CompletedProcess[str]:
    storage = tmp_path / "storage"
    storage.mkdir(exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "VERCEL")}
    env.update(
        {
            "EYE_ENV_FILE": "",
            "EYE_MODE": "demo",
            "EYE_MODEL_SOURCE": "mock",
            "EYE_STORAGE_DIR": str(storage),
            "DATABASE_URL": f"sqlite:///{tmp_path / 'sub.db'}",
        }
    )
    if vercel is not None:
        env["VERCEL"] = vercel
    proc = subprocess.run(
        [sys.executable, "-c", "import logging, sys\n" + body],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    return proc


def _probe_lines(stdout: str, probe: str) -> tuple[list[str], list[str]]:
    hits = [line for line in stdout.splitlines() if probe in line]
    prefixed = [line for line in hits if line == f"INFO eyedetect.predict {probe}"]
    bare = [line for line in hits if line == probe]
    assert len(prefixed) + len(bare) == len(hits), stdout  # no other shapes
    return prefixed, bare


def _probe_code(*, root_first: bool) -> tuple[str, str]:
    probe = f"probe-{uuid.uuid4().hex}"
    log = f"logging.getLogger('eyedetect.predict').info({probe!r})\n"
    if root_first:
        body = BASIC_CONFIG + "from app.main import create_app\ncreate_app()\n" + log
    else:
        body = "from app.main import create_app\ncreate_app()\n" + BASIC_CONFIG + log
    return probe, body


@pytest.mark.parametrize("root_first", [True, False], ids=["root-before-app", "root-after-app"])
def test_vercel_prints_each_line_once(tmp_path: Path, root_first: bool) -> None:
    probe, body = _probe_code(root_first=root_first)
    proc = _run_child(tmp_path, body, vercel="1")
    prefixed, bare = _probe_lines(proc.stdout, probe)
    assert len(prefixed) == 1, proc.stdout
    assert bare == [], proc.stdout


def test_without_vercel_root_handler_doubles_the_line(tmp_path: Path) -> None:
    """Control: why the VERCEL switch exists. Must pass before and after the fix."""
    probe, body = _probe_code(root_first=True)
    proc = _run_child(tmp_path, body, vercel=None)
    prefixed, bare = _probe_lines(proc.stdout, probe)
    assert len(prefixed) == 1, proc.stdout
    assert len(bare) == 1, proc.stdout


def test_vercel_empty_value_counts_as_unset(tmp_path: Path) -> None:
    probe, body = _probe_code(root_first=True)
    proc = _run_child(tmp_path, body, vercel="")
    prefixed, bare = _probe_lines(proc.stdout, probe)
    assert (len(prefixed), len(bare)) == (1, 1), proc.stdout


@pytest.fixture
def _propagation_restored() -> Any:
    yield
    logging.getLogger("eyedetect").propagate = True
    purge_app_modules()


def test_propagate_follows_vercel_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _propagation_restored: Any
) -> None:
    monkeypatch.setenv("VERCEL", "1")
    _build_app(monkeypatch, tmp_path)()
    assert logging.getLogger("eyedetect").propagate is False
    assert len(_named_handlers()) == 1

    monkeypatch.delenv("VERCEL")
    _build_app(monkeypatch, tmp_path)()
    assert logging.getLogger("eyedetect").propagate is True
    assert len(_named_handlers()) == 1

    monkeypatch.setenv("VERCEL", "1")
    _build_app(monkeypatch, tmp_path)()
    assert logging.getLogger("eyedetect").propagate is False

    monkeypatch.setenv("VERCEL", "")
    _build_app(monkeypatch, tmp_path)()
    assert logging.getLogger("eyedetect").propagate is True
    assert len(_named_handlers()) == 1


def test_repeated_call_in_same_import_restores_propagation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, _propagation_restored: Any
) -> None:
    monkeypatch.setenv("VERCEL", "1")
    create_app = _build_app(monkeypatch, tmp_path)
    create_app()
    assert logging.getLogger("eyedetect").propagate is False
    monkeypatch.delenv("VERCEL")
    create_app()
    assert logging.getLogger("eyedetect").propagate is True
