"""Local filesystem media storage (spec §5-C C3, corrections C6 + C11).

Two rules are load-bearing here:

* **C11 — true extension.** ``save_original`` derives the suffix from the
  *magic bytes*, never from the client filename and never a hardcoded
  ``.jpg``. PNG bytes written as ``.jpg`` would be served with the wrong
  content type and would break Coil on the phone.
* **C6 — stable relative URLs.** The returned URL is always
  ``/static/<kind>/<exam_id><ext>``: unauthenticated, UUID4-named and stable
  forever, because the app persists it in Room.

Filenames come ONLY from the server-side ``exam_id``. The client filename is
never read, so a crafted ``../../etc/passwd`` upload name cannot escape the
storage root.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import get_settings

#: Magic-byte prefixes we accept. Anything else is not an image we will store.
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

#: uuid4 in canonical form. Anything else is refused before it reaches the
#: filesystem, so a caller mistake can never become a path traversal.
_SAFE_ID = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")


def sniff_ext(raw: bytes) -> str | None:
    """Return ``'.jpg'`` / ``'.png'`` from the magic bytes, else ``None``."""
    if raw.startswith(JPEG_MAGIC):
        return ".jpg"
    if raw.startswith(PNG_MAGIC):
        return ".png"
    return None


def ensure_dirs() -> None:
    """Create ``<storage>/images`` and ``<storage>/heatmaps`` if absent."""
    settings = get_settings()
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    settings.heatmaps_dir.mkdir(parents=True, exist_ok=True)


def _checked_id(exam_id: str) -> str:
    if not _SAFE_ID.fullmatch(exam_id):
        raise ValueError(f"unsafe exam_id for a filename: {exam_id!r}")
    return exam_id


def save_original(raw: bytes, exam_id: str) -> tuple[Path, str]:
    """Persist the upload under its TRUE extension.

    Returns ``(filesystem path, public "/static/images/..." URL)``.
    Raises ``ValueError`` when the bytes are not a format we serve — callers
    sniff first and answer 400 ``invalid_image``, so this is a guard, not a
    control-flow path.
    """
    ext = sniff_ext(raw)
    if ext is None:
        raise ValueError("unsupported image format (not JPEG or PNG)")

    settings = get_settings()
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    name = f"{_checked_id(exam_id)}{ext}"
    path = settings.images_dir / name
    path.write_bytes(raw)
    return path, f"/static/images/{name}"


def heatmap_target(exam_id: str) -> tuple[Path, str]:
    """Where the Grad-CAM overlay for ``exam_id`` goes, and its public URL.

    Nothing is written here; the renderer (Agent A) writes the PNG and the
    caller only publishes the URL when the render actually succeeded.
    """
    settings = get_settings()
    settings.heatmaps_dir.mkdir(parents=True, exist_ok=True)
    name = f"{_checked_id(exam_id)}.png"
    return settings.heatmaps_dir / name, f"/static/heatmaps/{name}"
