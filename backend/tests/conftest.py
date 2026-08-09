"""Frozen test fixtures (spec §4.8). DO NOT EDIT.

Image fixtures are session-scoped because each one bisects ~24 JPEG
encode/decode rounds to land exactly on its intensity band.

APP FIXTURES ARE LAZY BY DESIGN. `app.main` does not exist until Agent C's
branch lands, so it is imported *inside* the fixture body — importing it at
module scope would make `test_frozen_kit.py` (the Phase 0 gate) fail to
collect.

Each app fixture purges `app.*` from `sys.modules` before importing, so a test
gets a module tree bound to *its* environment no matter how an agent chose to
read settings. Consequence for agents: monkeypatch by dotted string
(`monkeypatch.setattr("app.db.crud.create_exam_with_result", ...)`) AFTER
requesting the client fixture — a module object captured earlier belongs to a
discarded import.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests import synthetic

TEST_API_KEY = "testkey"


# --------------------------------------------------------------------------
# image fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="session")
def refer_jpeg_bytes() -> bytes:
    """Sharp synthetic fundus, mean gray ~160 -> mock grade 4 -> REFER."""
    return synthetic.refer_jpeg()


@pytest.fixture(scope="session")
def norefer_jpeg_bytes() -> bytes:
    """Sharp synthetic fundus, mean gray ~100 -> mock grade 0 -> NO_REFER."""
    return synthetic.norefer_jpeg()


@pytest.fixture(scope="session")
def blurry_jpeg_bytes() -> bytes:
    """NO_REFER geometry through a 21px Gaussian -> quality gate fails."""
    return synthetic.blurry_jpeg()


@pytest.fixture(scope="session")
def dark_jpeg_bytes() -> bytes:
    """Mean gray < 15 -> quality gate fails on brightness."""
    return synthetic.dark_jpeg()


@pytest.fixture(scope="session")
def text_file_bytes() -> bytes:
    return synthetic.not_an_image()


# --------------------------------------------------------------------------
# app fixtures
# --------------------------------------------------------------------------
def _purge_app_modules() -> None:
    for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
        del sys.modules[name]


def _build_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, api_key: str | None):
    storage = tmp_path / "storage"
    storage.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("EYE_MODE", "demo")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "mock")
    monkeypatch.setenv("EYE_DEVICE", "cpu")
    monkeypatch.setenv("EYE_STORAGE_DIR", str(storage))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'test.db'}")
    if api_key is None:
        monkeypatch.delenv("EYE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("EYE_API_KEY", api_key)

    _purge_app_modules()

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    return create_app()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """TestClient with the mock engine, tmp storage and a tmp sqlite DB, no auth."""
    from fastapi.testclient import TestClient

    app = _build_app(monkeypatch, tmp_path, api_key=None)
    with TestClient(app) as c:
        yield c
    _purge_app_modules()


@pytest.fixture
def authed_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Same, plus EYE_API_KEY=testkey. The key header is sent by default.

    `c.api_key` is the header helper: send `{"X-API-Key": c.api_key}` explicitly
    to override, or `headers={"X-API-Key": "wrong"}` to test rejection.
    """
    from fastapi.testclient import TestClient

    app = _build_app(monkeypatch, tmp_path, api_key=TEST_API_KEY)
    with TestClient(app, headers={"X-API-Key": TEST_API_KEY}) as c:
        c.api_key = TEST_API_KEY  # type: ignore[attr-defined]
        yield c
    _purge_app_modules()
