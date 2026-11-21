"""C6 — the media URLs the phone stores in Room actually resolve.

The originals are served from `/static`, named by the server-side exam id,
with the extension the magic bytes dictated (C11). Grad-CAM heatmaps were
removed in the Claude migration (MIGRATION_PLAN.md §3.1 step 8), so
`heatmap_url` is always null.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.contract.conftest import upload

JPEG_MAGIC = b"\xff\xd8\xff"


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


def test_refer_has_no_heatmap_url(created: dict[str, Any]) -> None:
    assert created["decision"] == "REFER"
    assert created["heatmap_url"] is None


def test_media_is_named_from_the_server_exam_id(created: dict[str, Any]) -> None:
    """Never from the client filename — that is the path-traversal guard."""
    exam_id = created["exam_id"]
    assert created["image_url"] == f"/static/images/{exam_id}.jpg"


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
