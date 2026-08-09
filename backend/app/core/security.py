"""API-key primitives (spec §5-C C2).

Deliberately free of FastAPI imports so it stays unit-testable and so the
comparison rule lives in exactly one place:

* No ``EYE_API_KEY`` configured  -> the API is OPEN. That is a legitimate
  LAN-demo posture, but it is announced once with a WARNING at startup so it
  can never be an accident nobody noticed.
* A key configured -> ``secrets.compare_digest`` only. A plain ``==`` on a
  secret leaks its prefix through timing, and this key is typed into
  ``local.properties`` on every demo phone.
"""

from __future__ import annotations

import logging
from secrets import compare_digest

logger = logging.getLogger("eyedetect.security")

#: The header the Android client sends (``ApiClient.kt`` auth interceptor).
API_KEY_HEADER = "X-API-Key"

#: C15: user-visible on the phone, so it is a short Uzbek string.
UNAUTHORIZED_DETAIL = "Kirish rad etildi — API kalit noto'g'ri"

_OPEN_API_WARNING = (
    "EYE_API_KEY is not set: /api/v1/* is UNAUTHENTICATED. "
    "Acceptable only for a local demo on a trusted LAN (C13: synthetic data only)."
)


def auth_disabled(expected: str | None) -> bool:
    """True when no key is configured, i.e. every request is allowed."""
    return expected is None or expected == ""


def verify_api_key(provided: str | None, expected: str | None) -> bool:
    """Constant-time check of the ``X-API-Key`` header against the config."""
    if expected is None or expected == "":
        return True
    if not provided:
        return False
    return compare_digest(provided, expected)


def warn_if_unprotected(expected: str | None) -> None:
    """Emit the single startup WARNING required by C2 when auth is off."""
    if auth_disabled(expected):
        logger.warning(_OPEN_API_WARNING)
