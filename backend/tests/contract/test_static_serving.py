"""C6 — the media URLs the phone stores in Room actually resolve.

The originals and the heatmaps are served from `/static`, named by the
server-side exam id, with the extension the magic bytes dictated (C11).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.conftest import upload

JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


@pytest.fixture
def created(client: Any, refer_jpeg_bytes: bytes) -> dict[str, Any]:
    response = client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes), data={"eye": "right"}
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def test_image_url_serves_the_original_jpeg(
    client: Any, created: dict[str, Any]
) -> None:
    response = client.get(created["image_url"])
    assert response.status_code == 200
    assert response.content.startswith(JPEG_MAGIC)


def test_image_url_round_trips_the_exact_bytes(
    client: Any, created: dict[str, Any], refer_jpeg_bytes: bytes
) -> None:
    assert client.get(created["image_url"]).content == refer_jpeg_bytes


def test_heatmap_url_serves_a_png(client: Any, created: dict[str, Any]) -> None:
    assert created["heatmap_url"], "the demo shows a heatmap for a REFER card"
    response = client.get(created["heatmap_url"])
    assert response.status_code == 200
    assert response.content.startswith(PNG_MAGIC)


def test_media_is_named_from_the_server_exam_id(created: dict[str, Any]) -> None:
    """Never from the client filename — that is the path-traversal guard."""
    exam_id = created["exam_id"]
    assert created["image_url"] == f"/static/images/{exam_id}.jpg"
    assert created["heatmap_url"] == f"/static/heatmaps/{exam_id}.png"


def test_client_filename_is_ignored(client: Any, refer_jpeg_bytes: bytes) -> None:
    response = client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes, name="../../../etc/passwd"),
    )
    assert response.status_code == 200, response.text
    assert response.json()["image_url"].startswith("/static/images/")
    assert ".." not in response.json()["image_url"]


def test_unknown_media_path_is_404(client: Any) -> None:
    assert client.get("/static/images/nope.jpg").status_code == 404


def test_static_mount_does_not_escape_the_storage_root(client: Any) -> None:
    response = client.get("/static/../app/config.py")
    assert response.status_code in (404, 400), response.text
