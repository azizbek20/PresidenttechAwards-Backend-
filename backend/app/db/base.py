"""Engine / session plumbing (spec §5-B B2).

**Everything here is lazy, and that is a contract, not a style choice.**
``tests/conftest.py`` purges ``app.*`` from ``sys.modules`` and rebuilds the app
per test with a per-test tmp sqlite ``DATABASE_URL``. A module-level
``engine = create_engine(get_settings().database_url)`` would bind at import
time and silently pin every later test to the first test's database. So:

* ``get_settings()`` is read *inside* the function that needs it;
* the engine is built on first use and cached against the URL it was built
  from, so a settings change (a new test, a reconfigured process) transparently
  swaps it instead of quietly reusing the stale one.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

_LOCK = threading.Lock()
_engine: Engine | None = None
_engine_url: str | None = None
_session_factory: sessionmaker[Session] | None = None


def _connect_args(url: str) -> dict[str, Any]:
    """SQLite is reached from FastAPI's threadpool and from test threads."""
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


def _build(url: str) -> None:
    """Caller must hold ``_LOCK``."""
    global _engine, _engine_url, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(url, connect_args=_connect_args(url), pool_pre_ping=True)
    _engine_url = url
    _session_factory = sessionmaker(
        bind=_engine, expire_on_commit=False, autoflush=False
    )


def get_engine() -> Engine:
    """The process engine for the *current* ``settings.database_url``."""
    url = get_settings().database_url
    with _LOCK:
        if _engine is None or _engine_url != url:
            _build(url)
        if _engine is None:  # pragma: no cover - _build always assigns
            raise RuntimeError("engine was not built")
        return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()  # ensures the factory matches the current URL
    with _LOCK:
        if _session_factory is None:  # pragma: no cover - built alongside _engine
            raise RuntimeError("session factory was not built")
        return _session_factory


def dispose_engine() -> None:
    """Drop the cached engine. Used by tests that swap ``DATABASE_URL``."""
    global _engine, _engine_url, _session_factory
    with _LOCK:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _engine_url = None
        _session_factory = None


def init_db() -> None:
    """``create_all`` for every table in :mod:`app.db.models`."""
    Base.metadata.create_all(get_engine())


@contextmanager
def get_session() -> Iterator[Session]:
    """Session scope: commit on clean exit, roll back on any exception."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
