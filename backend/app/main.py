"""ASGI application factory (spec §5-C C1).

``create_app()`` is the name the frozen ``tests/conftest.py`` imports, and
``app`` is the module-level instance ``uvicorn app.main:app`` serves.

Everything reads configuration through ``get_settings()`` **at call time**.
Binding settings at import would break the test harness, which rebuilds the
whole ``app.*`` module tree per test against a fresh environment.

Route authentication map (C2/C6/C16):

    /api/v1/*     require_api_key
    /health*      open  — probes and compose healthchecks
    /static/*     open  — Coil sends no API key (C6)
    HEAD /        open  — ApiClient.ping() counts ANY response as online (C16)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

import app.db.base as db_base  # Agent B; arrives at the Phase 2 merge.
from app.api import exams as exams_api
from app.api import predict as predict_api
from app.api.deps import engine_for, require_api_key
from app.config import get_settings
from app.core.errors import register_handlers
from app.core.limits import MaxBodySizeMiddleware
from app.core.security import warn_if_unprotected
from app.inference.engine import get_engine
from app.storage import local as storage

logger = logging.getLogger("eyedetect.main")

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: storage dirs, DB schema, engine, inference admission gate."""
    settings = get_settings()

    warn_if_unprotected(settings.eye_api_key)
    storage.ensure_dirs()
    await run_in_threadpool(db_base.init_db)

    app.state.engine = get_engine(settings)
    # Built inside the running loop so the semaphore binds to it.
    app.state.infer_sem = asyncio.Semaphore(settings.inference_concurrency)
    logger.info(
        "started mode=%s source=%s model_loaded=%s concurrency=%s",
        settings.eye_mode,
        settings.eye_model_source,
        getattr(app.state.engine, "model_loaded", False),
        settings.inference_concurrency,
    )
    yield


def _db_ok() -> bool:
    try:
        from sqlalchemy import text

        with db_base.get_session() as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception:  # a probe reports, it never raises
        logger.warning("readiness: database ping failed", exc_info=True)
        return False


def _storage_ok() -> bool:
    try:
        storage.ensure_dirs()
        probe = get_settings().storage_dir / ".readiness"
        probe.write_bytes(b"ok")
        probe.unlink()
        return True
    except Exception:  # a probe reports, it never raises
        logger.warning("readiness: storage is not writable", exc_info=True)
        return False


def _model_ok(app: FastAPI) -> bool:
    """Demo mode is ready without a checkpoint; shadow mode is not (C9)."""
    if get_settings().eye_mode != "shadow":
        return True
    return bool(getattr(engine_for(app), "model_loaded", False))


def create_app() -> FastAPI:
    settings = get_settings()

    # StaticFiles validates its directory at construction, and the storage
    # root may not exist yet on a fresh container.
    storage.ensure_dirs()

    app = FastAPI(
        title="EYE DETECT AI",
        version="4.0",
        summary="Diabetic retinopathy screening/triage API (demo phase).",
        lifespan=lifespan,
    )

    # C4: these override FastAPI's defaults, including the {"detail": [...]}
    # validation shape the phone cannot read.
    register_handlers(app)

    # ORDER MATTERS. `add_middleware` inserts at index 0, so the LAST one
    # registered ends up OUTERMOST. The body cap is registered first precisely
    # so CORS wraps it: registered the other way round, the 413 was emitted
    # outside CORSMiddleware and carried no access-control-allow-origin, so a
    # browser client saw a network failure instead of the Uzbek `detail`.
    #
    # C11: cap the RAW ASGI body stream, not the parsed form. `UploadFile`
    # spools the whole upload to disk before the endpoint runs, so an
    # in-handler cap never bounds intake. See app/core/limits.py.
    app.add_middleware(
        MaxBodySizeMiddleware,
        max_bytes=settings.max_upload_bytes,
        detail=f"Rasm hajmi juda katta — {settings.max_upload_mb} MB dan oshmasin",
    )

    # Starlette's CORS middleware is app-scoped; /api/v1/* is the surface that
    # needs it and the open /static + /health probes are unharmed by it.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    api = APIRouter(prefix=API_PREFIX, dependencies=[Depends(require_api_key)])
    api.include_router(predict_api.router, tags=["predict"])
    api.include_router(exams_api.router, tags=["exams"])
    app.include_router(api)

    @app.head("/", status_code=204, include_in_schema=False)
    async def ping() -> Response:
        """C16: ``ApiClient.ping()`` HEADs the base URL to decide "online".

        Unauthenticated on purpose — the client's ping *does* carry the
        X-API-Key header (pingClient inherits the auth interceptor), so this
        must answer with or without a key, and with a wrong one.
        """
        return Response(status_code=204)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "model_loaded": bool(getattr(engine_for(app), "model_loaded", False)),
        }

    @app.get("/health/live", include_in_schema=False)
    async def live() -> dict[str, str]:
        """Liveness: the process is up. Never depends on the DB or the model."""
        return {"status": "ok"}

    @app.get("/health/ready", include_in_schema=False)
    async def ready() -> JSONResponse:
        """Readiness: what compose's healthcheck gates traffic on."""
        checks = {
            "database": await run_in_threadpool(_db_ok),
            "storage": await run_in_threadpool(_storage_ok),
            "model": _model_ok(app),
        }
        ok = all(checks.values())
        return JSONResponse(
            status_code=200 if ok else 503,
            content={"status": "ready" if ok else "not_ready", "checks": checks},
        )

    # Mounted last so these can never shadow an API route. Unauthenticated by
    # design (C6: Coil sends no API key).
    #
    # The two MEDIA SUBDIRS are mounted individually rather than mounting
    # `storage_dir` itself. The URLs are identical (/static/images/... and
    # /static/heatmaps/...), but serving the parent handed out *anything* that
    # landed in the storage directory — and once the compose file put the
    # SQLite database on the storage volume, `GET /static/eye.db` returned the
    # entire patient database to an unauthenticated caller while
    # `GET /api/v1/exams` correctly answered 401. Serving only the media dirs
    # makes that class of exposure structurally impossible.
    app.mount(
        "/static/images",
        StaticFiles(directory=settings.images_dir),
        name="static-images",
    )
    app.mount(
        "/static/heatmaps",
        StaticFiles(directory=settings.heatmaps_dir),
        name="static-heatmaps",
    )
    return app


#: The instance ``uvicorn app.main:app`` serves. Tests never use it — the
#: frozen conftest calls ``create_app()`` per test instead.
app = create_app()
