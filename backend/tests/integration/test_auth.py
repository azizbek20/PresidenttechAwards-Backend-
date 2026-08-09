"""Auth wiring end to end (Agent C).

The contract suite proves 401/200 on `/api/v1/*`. This file proves the wiring
itself: that the dependency is attached to the API router and to nothing else,
that the comparison is the constant-time one, and that an unset key produces
the single startup WARNING C2 requires rather than silent open access.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.contract import _shim
from tests.contract._appkit import build_client
from tests.contract.conftest import upload

_shim.install()

OPEN_PATHS = ("/health", "/health/live", "/health/ready")


@pytest.fixture
def keyed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Any]:
    yield from build_client(monkeypatch, tmp_path, api_key="s3cr3t-lan-key")


def test_only_the_api_router_carries_the_dependency(authed_client: Any) -> None:
    """Read the route table rather than trusting a handful of examples."""
    from app.api.deps import require_api_key

    guarded, open_routes = [], []
    for route in authed_client.app.routes:
        path = getattr(route, "path", None)
        if path is None:
            continue
        deps = [
            d.call for d in getattr(getattr(route, "dependant", None), "dependencies", [])
        ]
        (guarded if require_api_key in deps else open_routes).append(path)

    assert guarded, "no route is protected at all"
    assert all(p.startswith("/api/v1") for p in guarded), guarded
    assert all(not p.startswith("/api/v1") for p in open_routes), open_routes


def test_every_open_path_answers_without_a_key(keyed_client: Any) -> None:
    for path in OPEN_PATHS:
        assert keyed_client.get(path).status_code in (200, 503), path
    assert keyed_client.head("/").status_code == 204


def test_api_paths_are_all_guarded(keyed_client: Any, refer_jpeg_bytes: bytes) -> None:
    assert keyed_client.get("/api/v1/exams").status_code == 401
    assert keyed_client.get("/api/v1/exams/whatever").status_code == 401
    assert (
        keyed_client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).status_code
        == 401
    )


def test_the_configured_key_unlocks_everything(
    keyed_client: Any, refer_jpeg_bytes: bytes
) -> None:
    headers = {"X-API-Key": "s3cr3t-lan-key"}
    created = keyed_client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), headers=headers
    )
    assert created.status_code == 200, created.text
    assert keyed_client.get("/api/v1/exams", headers=headers).status_code == 200
    # ...and the media it produced is still fetchable with no key at all (C6).
    assert keyed_client.get(created.json()["image_url"]).status_code == 200


def test_auth_rejection_never_reaches_the_database(
    keyed_client: Any, refer_jpeg_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 401 must be decided before any work is done."""

    def _explode(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("an unauthenticated request performed a write")

    monkeypatch.setattr("app.db.crud.create_exam_with_result", _explode)
    assert (
        keyed_client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).status_code
        == 401
    )


def test_unset_key_logs_one_startup_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """C2: open access is allowed, but never quietly."""
    with caplog.at_level(logging.WARNING, logger="eyedetect.security"):
        for _ in build_client(monkeypatch, tmp_path, api_key=None):
            break

    warnings = [r for r in caplog.records if r.name == "eyedetect.security"]
    assert len(warnings) == 1, [r.getMessage() for r in warnings]
    assert "UNAUTHENTICATED" in warnings[0].getMessage()


def test_a_configured_key_logs_no_such_warning(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="eyedetect.security"):
        for _ in build_client(monkeypatch, tmp_path, api_key="a-key"):
            break

    assert [r for r in caplog.records if r.name == "eyedetect.security"] == []


def test_comparison_is_constant_time() -> None:
    """Unit-level: `==` on a secret leaks its prefix through timing."""
    import inspect

    from app.core import security

    source = inspect.getsource(security.verify_api_key)
    assert "compare_digest" in source
    assert security.verify_api_key("k", "k") is True
    assert security.verify_api_key("k", "K") is False
    assert security.verify_api_key(None, "k") is False
    assert security.verify_api_key("", "k") is False
    # An unset key means the API is open by configuration, not by accident.
    assert security.verify_api_key(None, None) is True
    assert security.verify_api_key(None, "") is True


def test_a_second_client_without_default_headers_is_anonymous(
    authed_client: Any,
) -> None:
    """Guards the technique the rest of the auth tests rely on."""
    assert TestClient(authed_client.app).get("/api/v1/exams").status_code == 401
