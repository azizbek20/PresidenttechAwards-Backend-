"""C2/C6/C16 — where the API key is required, and where it must never be.

`/api/v1/*` is guarded. `/health*`, `/static/*` and `HEAD /` are not, and that
is a contract, not an oversight: Coil fetches heatmaps with no key at all, and
`ApiClient.ping()` treats *any* HTTP response to `HEAD /` as "backend online".
"""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from tests.contract.conftest import upload


def anonymous(authed_client: Any) -> TestClient:
    """A second client over the same app, with no default headers."""
    return TestClient(authed_client.app)


def test_correct_key_is_accepted(authed_client: Any, refer_jpeg_bytes: bytes) -> None:
    response = authed_client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert response.status_code == 200, response.text


def test_missing_key_is_401(authed_client: Any, refer_jpeg_bytes: bytes) -> None:
    response = anonymous(authed_client).post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes)
    )
    assert response.status_code == 401
    body = response.json()
    assert body["error"] == "unauthorized"
    assert isinstance(body["detail"], str) and body["detail"]


def test_wrong_key_is_401(authed_client: Any, refer_jpeg_bytes: bytes) -> None:
    response = authed_client.post(
        "/api/v1/predict",
        files=upload(refer_jpeg_bytes),
        headers={"X-API-Key": "definitely-not-the-key"},
    )
    assert response.status_code == 401
    assert response.json()["error"] == "unauthorized"


def test_key_prefix_is_not_enough(authed_client: Any) -> None:
    """A prefix match would mean the comparison was not constant-time."""
    response = authed_client.get(
        "/api/v1/exams", headers={"X-API-Key": authed_client.api_key[:-1]}
    )
    assert response.status_code == 401


def test_exams_list_is_guarded_too(authed_client: Any) -> None:
    assert anonymous(authed_client).get("/api/v1/exams").status_code == 401
    assert authed_client.get("/api/v1/exams").status_code == 200


def test_health_is_open(authed_client: Any) -> None:
    open_client = anonymous(authed_client)
    assert open_client.get("/health").status_code == 200
    assert open_client.get("/health/live").status_code == 200
    assert open_client.get("/health/ready").status_code in (200, 503)


def test_head_root_answers_without_a_key(authed_client: Any) -> None:
    """C16: this is how the phone decides it is online."""
    assert anonymous(authed_client).head("/").status_code == 204


def test_head_root_answers_with_a_wrong_key(authed_client: Any) -> None:
    """`pingClient` inherits the auth interceptor, so a key WILL be sent."""
    assert authed_client.head("/", headers={"X-API-Key": "wrong"}).status_code == 204


def test_static_media_needs_no_key(authed_client: Any, refer_jpeg_bytes: bytes) -> None:
    created = authed_client.post(
        "/api/v1/predict", files=upload(refer_jpeg_bytes)
    ).json()

    open_client = anonymous(authed_client)
    assert open_client.get(created["image_url"]).status_code == 200
    if created["heatmap_url"]:
        assert open_client.get(created["heatmap_url"]).status_code == 200


def test_no_key_configured_means_the_api_is_open(
    client: Any, refer_jpeg_bytes: bytes
) -> None:
    """The `client` fixture has EYE_API_KEY unset (a LAN demo posture)."""
    assert client.post("/api/v1/predict", files=upload(refer_jpeg_bytes)).status_code == 200
    assert client.get("/api/v1/exams").status_code == 200
