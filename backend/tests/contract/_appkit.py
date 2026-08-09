"""Build an app under an environment the frozen `client` fixture cannot give.

The frozen `tests/conftest.py` pins `EYE_MODE=demo` / `EYE_MODEL_SOURCE=mock`,
which is right for almost everything — but C9 (`503 model_unavailable`) and the
dedup-window behaviour are *about* other configurations. This builder mirrors
the frozen `_build_app` exactly, including the `app.*` purge and the settings
cache clear, and only adds an env override hook.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.contract import _shim

_shim.install()


def purge_app_modules() -> None:
    for name in [n for n in sys.modules if n == "app" or n.startswith("app.")]:
        del sys.modules[name]


def build_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    api_key: str | None = None,
    **env: str,
) -> Iterator[Any]:
    """Yield a `TestClient` (lifespan entered) for a custom environment."""
    from fastapi.testclient import TestClient

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
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    purge_app_modules()

    from app.config import get_settings

    get_settings.cache_clear()

    from app.main import create_app

    with TestClient(create_app()) as client:
        yield client

    purge_app_modules()
