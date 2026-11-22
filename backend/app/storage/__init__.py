"""Media storage, selected by ``EYE_STORAGE`` (MIGRATION_PLAN.md §3.8).

* ``local`` (default) — :mod:`app.storage.local`: files under
  ``EYE_STORAGE_DIR``, served by the app at ``/static/...`` (C6/C7).
* ``blob`` — :mod:`app.storage.blob`: Vercel Blob, absolute public URLs; the
  app writes nothing to the local filesystem and mounts no ``/static``.

Callers use ``storage.save_original`` and ``storage.sniff_ext`` and never
branch on the backend themselves.
"""

from __future__ import annotations

from pathlib import Path

from app.config import get_settings
from app.storage.local import sniff_ext

__all__ = ["is_local", "save_original", "sniff_ext"]


def is_local() -> bool:
    return get_settings().eye_storage == "local"


def save_original(raw: bytes, exam_id: str) -> tuple[Path | str, str]:
    """Persist the upload; returns ``(location, public URL)`` (plan §12.6)."""
    if is_local():
        from app.storage import local

        return local.save_original(raw, exam_id)
    # Imported lazily so a local deployment never loads the Blob client.
    from app.storage import blob

    return blob.save_original(raw, exam_id)
