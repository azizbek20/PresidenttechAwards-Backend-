"""Frozen error envelope (spec §4.4, C4, C15). DO NOT EDIT.

Every error body on every path is exactly ``{"error": ..., "detail": ...}``.
No RFC 9457, no ``problem+json``, and — critically — no FastAPI default shape.

C15 (verified at HEAD f6e4a0c, ScreeningViewModel.kt:327-332): the phone parses
``JSONObject(body).optString("detail")`` and shows it to the user verbatim.
``optString`` on a JSON *array* silently yields "", so FastAPI's default
``{"detail": [...]}`` would degrade to a generic message. Therefore ``detail``
is ALWAYS a short, human-readable Uzbek string.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("eyedetect.errors")

#: Stable error *codes* by HTTP status. ``error`` is the machine-readable code
#: (it is the contract); ``detail`` is the human string shown on the phone.
_ERROR_NAMES: dict[int, str] = {
    400: "invalid_image",
    401: "unauthorized",
    403: "unauthorized",
    404: "not_found",
    413: "payload_too_large",
    415: "invalid_image",
    422: "validation_error",
    429: "too_many_requests",
    500: "inference_error",
    503: "model_unavailable",
}

_UZBEK_DETAIL: dict[int, str] = {
    400: "Rasm yaroqsiz yoki buzilgan — qayta suratga oling",
    401: "Kirish rad etildi — API kalit noto'g'ri",
    403: "Kirish rad etildi — API kalit noto'g'ri",
    404: "So'ralgan yozuv topilmadi",
    413: "Rasm hajmi juda katta",
    415: "Rasm formati qo'llab-quvvatlanmaydi",
    422: "So'rov ma'lumotlari noto'g'ri",
    429: "So'rovlar juda ko'p — biroz kuting",
    500: "Server xatosi — qayta urining",
    503: "Model tayyor emas — administratorga murojaat qiling",
}


def _name_for(status: int) -> str:
    return _ERROR_NAMES.get(status, "http_error")


def _detail_for(status: int) -> str:
    return _UZBEK_DETAIL.get(status, "Kutilmagan xato — qayta urining")


class ApiError(Exception):
    """Raise this anywhere to emit the frozen envelope with an exact status."""

    def __init__(self, status: int, error: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.error = error
        self.detail = detail


def _envelope(status: int, error: str, detail: str) -> JSONResponse:
    # `detail` is coerced to str defensively: a non-string here would silently
    # blank the user-facing message on the phone (C15).
    return JSONResponse(
        status_code=status, content={"error": str(error), "detail": str(detail)}
    )


def _summarise_validation(exc: RequestValidationError) -> str:
    """Collapse FastAPI's error *list* into one short Uzbek string (C15)."""
    try:
        first = exc.errors()[0]
    except (IndexError, TypeError, AttributeError):
        return _detail_for(422)

    loc = [str(p) for p in first.get("loc", ()) if p not in ("body", "query", "path")]
    field = loc[-1] if loc else ""
    kind = str(first.get("type", ""))

    if kind.startswith("missing") and field:
        return f"Majburiy maydon yuborilmadi: {field}"
    if field:
        return f"Maydon qiymati noto'g'ri: {field}"
    return _detail_for(422)


def register_handlers(app: FastAPI) -> None:
    """Install the handlers that override FastAPI's defaults.

    Order matters only in that every one of these must exist: the default
    ``RequestValidationError`` handler emits ``{"detail": [...]}``, which
    violates both C4 (envelope shape) and C15 (detail must be a string).
    """

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _envelope(exc.status, exc.error, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(422, "validation_error", _summarise_validation(exc))

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        status = int(exc.status_code)
        # ALWAYS use the Uzbek table here — never `exc.detail`. Starlette and the
        # multipart parser set English detail strings ("Not Found",
        # "Missing boundary in multipart.", "The Content-Disposition header field
        # \"name\" must be provided."), and ScreeningViewModel.kt:332 prints
        # `detail` to the user verbatim, so any framework wording that survives
        # is shown on the phone in English. That breaks C15.
        #
        # Blanket-replacing is safe because application code raises ApiError,
        # never HTTPException — the ApiError handler above is what carries a
        # deliberate, localized message.
        return _envelope(status, _name_for(status), _detail_for(status))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Log the traceback server-side; NEVER leak it to the client.
        logger.exception(
            "unhandled error on %s %s", request.method, request.url.path, exc_info=exc
        )
        return _envelope(500, "inference_error", _detail_for(500))
