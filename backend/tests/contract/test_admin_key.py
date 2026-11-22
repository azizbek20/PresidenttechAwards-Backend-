"""Admin key for the exam list endpoints (owner-approved, admin_key_spec.md).

The app key ships inside the APK, so anyone with the APK can extract it. The
two exam endpoints, which only the admin panel uses, get a second key
(``EYE_ADMIN_API_KEY``, header ``X-Admin-Key``) that never leaves the server
and the panel. Spec items 1-6; the dashboard (7) and docs (8) are not tested
here.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.contract._appkit import build_client, purge_app_modules
from tests.contract.conftest import upload

APP_KEY = "APPKEY-abc-7733"
ADMIN_KEY = "ADMINKEY-xyz-9911"
APP = {"X-API-Key": APP_KEY}
BOTH = {"X-API-Key": APP_KEY, "X-Admin-Key": ADMIN_KEY}

FORBIDDEN_DETAIL = "Kirish rad etildi — API kalit noto'g'ri"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("EYE_ADMIN_API_KEY", "EYE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def open_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Callable[..., TestClient]]:
    """``open_app(admin=..., **env)`` -> a TestClient (lifespan entered)."""
    gens: list[Iterator[Any]] = []

    def _open(*, admin: str | None, app_key: str = APP_KEY, **env: str) -> TestClient:
        if admin is not None:
            env["EYE_ADMIN_API_KEY"] = admin
        gen = build_client(monkeypatch, tmp_path, api_key=app_key, **env)
        gens.append(gen)
        return next(gen)  # type: ignore[no-any-return]

    yield _open
    for gen in gens:
        gen.close()


def make_exam(client: TestClient, raw: bytes) -> dict[str, Any]:
    response = client.post("/api/v1/predict", files=upload(raw), headers=APP)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


# --------------------------------------------------------------------------
# 1. unset or empty: nothing changes
# --------------------------------------------------------------------------
@pytest.mark.parametrize("admin", [None, ""], ids=["unset", "empty"])
def test_without_admin_key_the_app_key_is_enough(
    open_app: Callable[..., TestClient], refer_jpeg_bytes: bytes, admin: str | None
) -> None:
    client = open_app(admin=admin)
    exam = make_exam(client, refer_jpeg_bytes)
    listing = client.get("/api/v1/exams", headers=APP)
    assert listing.status_code == 200, listing.text
    assert [e["exam_id"] for e in listing.json()] == [exam["exam_id"]]
    one = client.get(f"/api/v1/exams/{exam['exam_id']}", headers=APP)
    assert one.status_code == 200, one.text
    assert one.json()["exam_id"] == exam["exam_id"]


# --------------------------------------------------------------------------
# 2. set: both keys required on both endpoints
# --------------------------------------------------------------------------
@pytest.fixture
def secured(open_app: Callable[..., TestClient], refer_jpeg_bytes: bytes) -> tuple[TestClient, dict[str, Any]]:
    client = open_app(admin=ADMIN_KEY)
    return client, make_exam(client, refer_jpeg_bytes)


def paths(exam: dict[str, Any]) -> list[str]:
    return ["/api/v1/exams", f"/api/v1/exams/{exam['exam_id']}"]


def assert_forbidden(response: Any) -> None:
    assert response.status_code == 403, response.text
    body = response.json()
    assert body["error"] == "unauthorized"
    assert isinstance(body["detail"], str) and body["detail"]
    assert body["detail"] == FORBIDDEN_DETAIL


@pytest.mark.parametrize("which", [0, 1], ids=["list", "by-id"])
def test_app_key_alone_is_403(secured: Any, which: int) -> None:
    client, exam = secured
    assert_forbidden(client.get(paths(exam)[which], headers=APP))


@pytest.mark.parametrize("which", [0, 1], ids=["list", "by-id"])
def test_wrong_admin_key_is_403(secured: Any, which: int) -> None:
    client, exam = secured
    for wrong in ("definitely-not-it", ADMIN_KEY[:-1], APP_KEY):
        assert_forbidden(
            client.get(paths(exam)[which], headers={**APP, "X-Admin-Key": wrong})
        )


@pytest.mark.parametrize("which", [0, 1], ids=["list", "by-id"])
def test_non_ascii_admin_key_is_403_not_500(secured: Any, which: int) -> None:
    client, exam = secured
    # Bytes, as in test_audit_regressions: httpx refuses a non-ASCII str header.
    headers = {"X-API-Key": APP_KEY, "X-Admin-Key": "аdmin-key".encode()}
    assert_forbidden(client.get(paths(exam)[which], headers=headers))


@pytest.mark.parametrize("which", [0, 1], ids=["list", "by-id"])
def test_both_keys_work_and_body_shape_is_unchanged(secured: Any, which: int) -> None:
    client, exam = secured
    response = client.get(paths(exam)[which], headers=BOTH)
    assert response.status_code == 200, response.text
    body = response.json()
    if which == 0:
        assert isinstance(body, list) and len(body) == 1
        row = body[0]
        assert row["exam_id"] == exam["exam_id"]
        assert set(row) >= {"exam_id", "decision", "model_version"}
    else:
        assert set(body) == set(exam)
        assert body["exam_id"] == exam["exam_id"]
        assert body["decision"] == exam["decision"]


@pytest.mark.parametrize("which", [0, 1], ids=["list", "by-id"])
@pytest.mark.parametrize("app_header", [None, "wrong-app-key"], ids=["missing", "wrong"])
def test_app_key_is_checked_first(secured: Any, which: int, app_header: str | None) -> None:
    client, exam = secured
    headers = {"X-Admin-Key": ADMIN_KEY}
    if app_header is not None:
        headers["X-API-Key"] = app_header
    response = client.get(paths(exam)[which], headers=headers)
    assert response.status_code == 401, response.text
    body = response.json()
    assert body["error"] == "unauthorized"
    assert isinstance(body["detail"], str) and body["detail"]


# --------------------------------------------------------------------------
# 3. every other route is unchanged with the app key alone
# --------------------------------------------------------------------------
def test_other_routes_need_only_the_app_key(
    open_app: Callable[..., TestClient], refer_jpeg_bytes: bytes
) -> None:
    client = open_app(admin=ADMIN_KEY)

    predicted = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes), headers=APP)
    assert predicted.status_code == 200, predicted.text

    task = client.post("/api/v1/predict/async", files=upload(refer_jpeg_bytes), headers=APP)
    assert task.status_code == 200, task.text
    status = client.get(f"/api/v1/predict/status/{task.json()['task_id']}", headers=APP)
    assert status.status_code == 200, status.text
    assert status.json()["status"] == "SUCCESS"

    analysis = client.post(
        "/api/v1/analyze",
        files=upload(refer_jpeg_bytes),
        data={"analysis_type": "external_eye"},
        headers=APP,
    )
    assert analysis.status_code == 200, analysis.text
    analysis_id = analysis.json()["analysis_id"]

    assert client.get("/api/v1/analyses", headers=APP).status_code == 200
    assert client.get(f"/api/v1/analyses/{analysis_id}", headers=APP).status_code == 200
    assert client.get("/api/v1/analysis/types", headers=APP).status_code == 200

    assert client.get("/health").status_code == 200
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code in (200, 503)
    assert client.head("/").status_code == 204


# --------------------------------------------------------------------------
# 4. config validation
# --------------------------------------------------------------------------
def settings(**env: str) -> Any:
    purge_app_modules()
    from app.config import Settings

    return Settings(**{"EYE_MODE": "demo", "EYE_MODEL_SOURCE": "mock", **env})


def test_equal_keys_are_rejected() -> None:
    with pytest.raises(ValueError, match="EYE_ADMIN_API_KEY"):
        settings(EYE_API_KEY="same-key", EYE_ADMIN_API_KEY="same-key")


def test_different_keys_are_fine() -> None:
    s = settings(EYE_API_KEY="one", EYE_ADMIN_API_KEY="two")
    assert s.eye_admin_api_key == "two"


@pytest.mark.parametrize("app_key", ["one", "", None])
def test_empty_admin_key_is_fine_with_any_app_key(app_key: str | None) -> None:
    env = {"EYE_ADMIN_API_KEY": ""}
    if app_key is not None:
        env["EYE_API_KEY"] = app_key
    assert settings(**env).eye_admin_api_key in ("", None)


def test_two_empty_keys_are_not_equal_keys() -> None:
    settings(EYE_API_KEY="", EYE_ADMIN_API_KEY="")


# --------------------------------------------------------------------------
# 5. startup warning
# --------------------------------------------------------------------------
def admin_warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.name == "eyedetect.security"
        and r.levelno == logging.WARNING
        and "EYE_ADMIN_API_KEY" in r.getMessage()
    ]


SHADOW = {"EYE_MODE": "shadow", "EYE_MODEL_SOURCE": "claude"}


@pytest.mark.parametrize("admin", [None, ""], ids=["unset", "empty"])
def test_shadow_mode_without_admin_key_warns_once(
    open_app: Callable[..., TestClient], caplog: pytest.LogCaptureFixture, admin: str | None
) -> None:
    caplog.set_level(logging.WARNING, logger="eyedetect")
    open_app(admin=admin, **SHADOW)
    assert len(admin_warnings(caplog)) == 1


def test_shadow_mode_with_admin_key_does_not_warn(
    open_app: Callable[..., TestClient], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="eyedetect")
    open_app(admin=ADMIN_KEY, **SHADOW)
    assert admin_warnings(caplog) == []


def test_demo_mode_without_admin_key_does_not_warn(
    open_app: Callable[..., TestClient], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="eyedetect")
    open_app(admin=None)
    assert admin_warnings(caplog) == []


# --------------------------------------------------------------------------
# 6. keys never reach the logs
# --------------------------------------------------------------------------
def test_neither_key_appears_in_any_log_record(
    open_app: Callable[..., TestClient], caplog: pytest.LogCaptureFixture, refer_jpeg_bytes: bytes
) -> None:
    caplog.set_level(logging.DEBUG, logger="eyedetect")
    client = open_app(admin=ADMIN_KEY)
    exam = make_exam(client, refer_jpeg_bytes)
    assert_forbidden(client.get("/api/v1/exams", headers=APP))
    assert_forbidden(
        client.get("/api/v1/exams", headers={**APP, "X-Admin-Key": "wrong-admin-value-5521"})
    )
    assert client.get("/api/v1/exams", headers=BOTH).status_code == 200
    assert client.get(f"/api/v1/exams/{exam['exam_id']}", headers=BOTH).status_code == 200
    assert caplog.records, "expected some log records"
    for record in caplog.records:
        text = f"{record.getMessage()} {record.args} {record.exc_text}"
        for secret in (APP_KEY, ADMIN_KEY, "wrong-admin-value-5521"):
            assert secret not in text
