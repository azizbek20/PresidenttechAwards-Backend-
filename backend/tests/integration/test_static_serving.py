"""Static media, checked against the real filesystem (Agent C).

`tests/contract/test_static_serving.py` pins what the HTTP surface promises;
this file checks that the promise is backed by actual files in the configured
storage root, with the extension C11 requires, and that nothing else lands
there.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.contract import _shim
from tests.contract.conftest import upload

_shim.install()


def storage_root() -> Path:
    from app.config import get_settings

    return get_settings().storage_dir


@pytest.fixture
def created(client: Any, refer_jpeg_bytes: bytes) -> dict[str, Any]:
    response = client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_startup_creates_both_media_subdirectories(client: Any) -> None:
    root = storage_root()
    assert (root / "images").is_dir()
    assert (root / "heatmaps").is_dir()


def test_original_bytes_are_on_disk_unmodified(
    created: dict[str, Any], refer_jpeg_bytes: bytes
) -> None:
    path = storage_root() / "images" / f"{created['exam_id']}.jpg"
    assert path.is_file()
    assert path.read_bytes() == refer_jpeg_bytes


def test_heatmap_png_is_on_disk(created: dict[str, Any]) -> None:
    path = storage_root() / "heatmaps" / f"{created['exam_id']}.png"
    assert path.is_file()
    assert path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_png_upload_is_stored_with_a_png_extension(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """C11 on disk: a PNG must never be written as `.jpg`."""
    import cv2
    import numpy as np

    from tests import synthetic

    rgb = synthetic.decode_rgb(refer_jpeg_bytes)
    ok, buf = cv2.imencode(".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    assert ok
    png_bytes = bytes(np.asarray(buf).tobytes())

    created = client.post(
        "/api/v1/predict",
        files=upload(png_bytes, name="x.png", content_type="image/png"),
    ).json()

    images = storage_root() / "images"
    assert (images / f"{created['exam_id']}.png").is_file()
    assert not (images / f"{created['exam_id']}.jpg").exists()


def test_a_rejected_upload_leaves_no_file_behind(
    client: Any, text_file_bytes: bytes
) -> None:
    """Nothing is written before the format is known to be servable."""
    before = set((storage_root() / "images").iterdir())
    assert client.post("/api/v1/predict", files=upload(text_file_bytes)).status_code == 400
    assert set((storage_root() / "images").iterdir()) == before


def test_an_ungradable_exam_writes_the_original_but_no_heatmap(
    client: Any, blurry_jpeg_bytes: bytes
) -> None:
    created = client.post("/api/v1/predict", files=upload(blurry_jpeg_bytes)).json()
    assert (storage_root() / "images" / f"{created['exam_id']}.jpg").is_file()
    assert not (storage_root() / "heatmaps" / f"{created['exam_id']}.png").exists()


def test_served_bytes_equal_the_bytes_on_disk(
    client: Any, created: dict[str, Any]
) -> None:
    path = storage_root() / "images" / f"{created['exam_id']}.jpg"
    assert client.get(created["image_url"]).content == path.read_bytes()
