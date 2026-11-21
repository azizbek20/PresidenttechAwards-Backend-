"""``EYE_STORAGE`` switch (plan §3.8): Vercel Blob with a fake client."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from tests.contract._appkit import build_client
from tests.contract.conftest import upload
from tests.fakes.blob import HOST, FakeBlob

UUID = "123e4567-e89b-42d3-a456-426614174000"


class BlobApp:
    def __init__(self, client: Any, fake: FakeBlob, never: Path) -> None:
        self.client = client
        self.fake = fake
        self.never = never

    def post(self, raw: bytes, **form: str) -> Any:
        return self.client.post("/api/v1/predict", files=upload(raw), data=form)


@pytest.fixture
def blob_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[BlobApp]:
    never = tmp_path / "never-created"
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "test-token")
    gen = build_client(
        monkeypatch,
        tmp_path,
        EYE_STORAGE="blob",
        EYE_STORAGE_DIR=str(never),
    )
    client = next(gen)
    fake = FakeBlob()
    monkeypatch.setattr("app.storage.blob.put_blob", fake)
    try:
        yield BlobApp(client, fake, never)
    finally:
        gen.close()


def png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 120, 40)).save(buf, format="PNG")
    return buf.getvalue()


# --------------------------------------------------------------------------
# predict with blob storage
# --------------------------------------------------------------------------
def test_predict_returns_the_absolute_blob_url(
    blob_app: BlobApp, refer_jpeg_bytes: bytes
) -> None:
    response = blob_app.post(refer_jpeg_bytes, eye="right")

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(blob_app.fake.calls) == 1
    assert body["image_url"] == blob_app.fake.results[0].url
    assert body["image_url"].startswith("https://")
    assert body["heatmap_url"] is None

    call = blob_app.fake.calls[0]
    assert call["pathname"] == f"images/{body['exam_id']}.jpg"
    assert call["access"] == "public"
    assert call["add_random_suffix"] is True
    assert call["content_type"] == "image/jpeg"
    assert call["body"] == refer_jpeg_bytes


def test_the_stored_exam_keeps_the_blob_url(
    blob_app: BlobApp, refer_jpeg_bytes: bytes
) -> None:
    body = blob_app.post(refer_jpeg_bytes).json()
    exam = blob_app.client.get(f"/api/v1/exams/{body['exam_id']}").json()
    assert exam["image_url"] == body["image_url"]
    assert exam["heatmap_url"] is None


def test_async_flow_also_stores_in_blob(
    blob_app: BlobApp, refer_jpeg_bytes: bytes
) -> None:
    task = blob_app.client.post(
        "/api/v1/predict/async", files=upload(refer_jpeg_bytes)
    ).json()
    result = blob_app.client.get(f"/api/v1/predict/status/{task['task_id']}").json()
    assert result["status"] == "SUCCESS"
    assert result["result"]["image_url"] == blob_app.fake.results[0].url


def test_a_blob_failure_is_500_inference_error_and_nothing_is_stored(
    blob_app: BlobApp, refer_jpeg_bytes: bytes
) -> None:
    blob_app.fake.error = RuntimeError("blob is down")
    response = blob_app.post(refer_jpeg_bytes)

    assert response.status_code == 500, response.text
    assert response.json()["error"] == "inference_error"
    assert blob_app.client.get("/api/v1/exams").json() == []


def test_a_replay_does_not_upload_again(
    blob_app: BlobApp, refer_jpeg_bytes: bytes
) -> None:
    first = blob_app.post(refer_jpeg_bytes, patient_id="P-9").json()
    second = blob_app.post(refer_jpeg_bytes, patient_id="P-9").json()
    assert second["exam_id"] == first["exam_id"]
    assert second["image_url"] == first["image_url"]
    assert len(blob_app.fake.calls) == 1


# --------------------------------------------------------------------------
# no local filesystem, no static mounts
# --------------------------------------------------------------------------
def test_the_storage_dir_is_never_created(
    blob_app: BlobApp, refer_jpeg_bytes: bytes
) -> None:
    assert not blob_app.never.exists()  # import + create_app + lifespan startup
    assert blob_app.post(refer_jpeg_bytes).status_code == 200
    assert blob_app.client.get("/health/ready").status_code == 200
    assert not blob_app.never.exists()


def test_static_media_is_not_mounted(blob_app: BlobApp) -> None:
    paths = [getattr(route, "path", "") for route in blob_app.client.app.routes]
    assert not [p for p in paths if p.startswith("/static")]
    assert blob_app.client.get("/static/images/x.jpg").status_code == 404
    assert blob_app.client.get("/static/heatmaps/x.png").status_code == 404


# --------------------------------------------------------------------------
# readiness
# --------------------------------------------------------------------------
def test_ready_with_a_token_reports_storage_ok(blob_app: BlobApp) -> None:
    response = blob_app.client.get("/health/ready")
    assert response.status_code == 200, response.text
    assert response.json()["checks"]["storage"] is True
    assert blob_app.fake.calls == []
    assert not blob_app.never.exists()


def test_ready_without_a_token_is_not_ready(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    never = tmp_path / "never-created"
    monkeypatch.delenv("BLOB_READ_WRITE_TOKEN", raising=False)
    gen = build_client(
        monkeypatch, tmp_path, EYE_STORAGE="blob", EYE_STORAGE_DIR=str(never)
    )
    client = next(gen)
    try:
        response = client.get("/health/ready")
        assert response.status_code == 503, response.text
        assert response.json()["checks"]["storage"] is False
        assert not never.exists()
    finally:
        gen.close()


# --------------------------------------------------------------------------
# app.storage.blob.save_original and the selector
# --------------------------------------------------------------------------
def test_save_original_uploads_a_png_with_its_content_type(blob_app: BlobApp) -> None:
    from app.storage import blob

    pathname, url = blob.save_original(png_bytes(), UUID)

    call = blob_app.fake.calls[0]
    assert call["pathname"] == f"images/{UUID}.png"
    assert call["content_type"] == "image/png"
    assert call["access"] == "public"
    assert call["add_random_suffix"] is True
    assert (pathname, url) == (
        blob_app.fake.results[0].pathname,
        blob_app.fake.results[0].url,
    )
    assert url.startswith(HOST)


def test_save_original_refuses_a_non_image(blob_app: BlobApp) -> None:
    from app.storage import blob

    with pytest.raises(ValueError):
        blob.save_original(b"just some text", UUID)
    assert blob_app.fake.calls == []


@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "not-a-uuid", "", "a/b"])
def test_save_original_refuses_an_unsafe_exam_id(
    blob_app: BlobApp, refer_jpeg_bytes: bytes, bad_id: str
) -> None:
    from app.storage import blob

    with pytest.raises(ValueError):
        blob.save_original(refer_jpeg_bytes, bad_id)
    assert blob_app.fake.calls == []


def test_the_package_selector_routes_to_blob(
    blob_app: BlobApp, refer_jpeg_bytes: bytes
) -> None:
    import app.storage as storage

    assert storage.sniff_ext(refer_jpeg_bytes) == ".jpg"
    assert storage.sniff_ext(png_bytes()) == ".png"
    assert storage.sniff_ext(b"nope") is None
    _, url = storage.save_original(refer_jpeg_bytes, UUID)
    assert url.startswith("https://")
    assert len(blob_app.fake.calls) == 1


# --------------------------------------------------------------------------
# default (local) behaviour is unchanged
# --------------------------------------------------------------------------
def test_local_storage_is_still_the_default(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    body = client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).json()
    assert body["image_url"] == f"/static/images/{body['exam_id']}.jpg"
    assert client.get(body["image_url"]).status_code == 200
    assert body["heatmap_url"] is None
