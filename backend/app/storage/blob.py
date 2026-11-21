"""Vercel Blob media storage (MIGRATION_PLAN.md §3.8).

Used when ``EYE_STORAGE=blob`` (Vercel's filesystem is read-only). The same two
guards as :mod:`app.storage.local` apply: the extension comes from the magic
bytes (C11), and the object name comes only from the server-side ``exam_id``
— never from the client filename.

Objects are public, as ``/static/images`` is today (C6: the phone's image
loader sends no API key), and get a random suffix so their URLs cannot be
guessed from an exam id. ``put_blob`` reads ``BLOB_READ_WRITE_TOKEN`` from the
environment; it is a module attribute so tests can replace it.
"""

from __future__ import annotations

from vercel.blob.sync import put_blob

from app.storage.local import _checked_id, sniff_ext

_CONTENT_TYPES = {".jpg": "image/jpeg", ".png": "image/png"}

__all__ = ["put_blob", "save_original", "sniff_ext"]


def save_original(raw: bytes, exam_id: str) -> tuple[str, str]:
    """Upload the original under ``images/<exam_id><ext>``.

    Returns ``(blob pathname, absolute public URL)``. Raises ``ValueError``
    for bytes that are not a format we serve, or an unsafe ``exam_id`` —
    callers sniff first, so this is a guard, not a control-flow path.
    """
    ext = sniff_ext(raw)
    if ext is None:
        raise ValueError("unsupported image format (not JPEG or PNG)")
    pathname = f"images/{_checked_id(exam_id)}{ext}"
    result = put_blob(
        pathname,
        raw,
        access="public",
        content_type=_CONTENT_TYPES[ext],
        add_random_suffix=True,
    )
    return str(result.pathname), str(result.url)
