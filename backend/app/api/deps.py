"""Shared route dependencies (spec §5-C C2).

``require_api_key`` is attached to the ``/api/v1`` router and to nothing else.
``/health*``, ``/static/*`` and ``HEAD /`` stay open on purpose:

* Coil (the phone's image loader) sends no API key, so authenticating
  ``/static`` would blank every heatmap (C6).
* ``ApiClient.ping()`` sends ``HEAD /`` *with* the auth interceptor attached
  and counts any HTTP response as "online" (C16), so the route must answer
  whether or not a key is present — including a wrong one.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from fastapi import Header

from app.config import Settings, get_settings
from app.core.errors import ApiError
from app.core.security import UNAUTHORIZED_DETAIL, verify_api_key
from app.inference.engine import InferenceEngine, get_engine
from app.schemas import DISCLAIMER


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Reject the request unless the configured key was presented."""
    # Settings are read per call, never bound at import: the test harness
    # rebuilds the app against a fresh environment for every test.
    if not verify_api_key(x_api_key, get_settings().eye_api_key):
        raise ApiError(401, "unauthorized", UNAUTHORIZED_DETAIL)


def engine_for(app: Any) -> InferenceEngine:
    """The process-wide engine, built once during startup.

    The lazy fallback exists for an app object used without its lifespan (a
    bare ``TestClient(app)`` without the context manager); the normal path
    finds it already on ``app.state``.
    """
    engine = getattr(app.state, "engine", None)
    if engine is None:
        engine = get_engine(get_settings())
        app.state.engine = engine
    return engine  # type: ignore[no-any-return]


def semaphore_for(app: Any) -> asyncio.Semaphore:
    """The inference admission gate, ``Semaphore(INFERENCE_CONCURRENCY)``.

    Created inside the running loop by the lifespan; the fallback keeps a
    lifespan-less app usable.
    """
    sem = getattr(app.state, "infer_sem", None)
    if sem is None:
        sem = asyncio.Semaphore(get_settings().inference_concurrency)
        app.state.infer_sem = sem
    return sem  # type: ignore[no-any-return]


def fill_additive_keys(row: dict[str, Any], settings: Settings) -> dict[str, Any]:
    """Backfill the C12 keys on a row read back from the database.

    ``crud.create_exam_with_result`` has no ``request_id``/``mode`` parameter,
    so a stored exam cannot carry the values its original request had. A
    replayed or listed exam is still the same exam — same ``exam_id``, same
    verdict — but these two observability keys are regenerated. Without the
    backfill a row from a ``crud`` implementation that omits them would fail
    ``PredictResponse`` validation and turn a successful read into a 500.
    """
    row.setdefault("request_id", str(uuid4()))
    row.setdefault("mode", settings.eye_mode)
    row.setdefault("disclaimer", DISCLAIMER)
    return row
