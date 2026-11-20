"""``/api/v1/analyze`` — non-fundus analyses (external eye, skin, oral, nail)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from tests.contract._appkit import build_client
from tests.contract.conftest import PROCESSED_AT_RE, upload

TYPES = ("external_eye", "skin", "oral", "nail")


def _photo(rgb: tuple[int, int, int], *, seed: int = 7, size: int = 480) -> bytes:
    """Sharp JPEG of a flat colour plus speckle (clears the blur gate)."""
    rng = np.random.default_rng(seed)
    img = np.empty((size, size, 3), dtype=np.float64)
    img[:] = rgb
    img += rng.normal(0.0, 12.0, img.shape)
    arr = np.clip(img, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(arr, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 95])
    assert ok
    return buf.tobytes()


RED = (200, 80, 80)
DARK = (40, 35, 30)
NEUTRAL = (150, 130, 120)


def _post(client: Any, raw: bytes, **form: Any) -> Any:
    data = {k: v for k, v in form.items() if v is not None}
    return client.post("/api/v1/analyze", files=upload(raw), data=data)


def test_types_catalogue(authed_client: Any) -> None:
    r = authed_client.get("/api/v1/analysis/types")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [t["code"] for t in body] == list(TYPES)
    for t in body:
        assert t["label"] and t["conditions"]
        assert t["model_ready"] is False  # no model files in tmp


@pytest.mark.parametrize("atype", TYPES)
def test_every_type_returns_a_full_result(authed_client: Any, atype: str) -> None:
    r = _post(authed_client, _photo(NEUTRAL, seed=hash(atype) % 1000), analysis_type=atype, patient_id="PT-1")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["analysis_type"] == atype
    assert b["patient_id"] == "PT-1"
    assert b["quality"] == "good"
    assert b["risk_level"] in ("low", "medium", "high")
    assert b["findings"] and b["findings"][0]["code"] == b["top_finding"]
    assert abs(sum(f["probability"] for f in b["findings"]) - 1.0) < 1e-3
    probs = [f["probability"] for f in b["findings"]]
    assert probs == sorted(probs, reverse=True)
    assert b["is_demo"] is True and b["model_version"].startswith("mock")
    assert b["image_url"].startswith("/static/images/")
    assert PROCESSED_AT_RE.match(b["processed_at"])
    assert b["recommendation"] and b["disclaimer"]
    assert None not in b.values()


def test_red_eye_is_conjunctivitis_dark_skin_lesion_is_high_risk(authed_client: Any) -> None:
    eye = _post(authed_client, _photo(RED), analysis_type="external_eye").json()
    assert eye["top_finding"] == "conjunctivitis"
    assert eye["risk_level"] == "medium"

    skin = _post(authed_client, _photo(DARK), analysis_type="skin", body_site="chap bilak").json()
    assert skin["top_finding"] == "melanoma_suspect"
    assert skin["risk_level"] == "high"
    assert skin["body_site"] == "chap bilak"
    assert "tezroq" in skin["recommendation"]


def test_patient_code_is_generated_when_absent(authed_client: Any) -> None:
    b = _post(authed_client, _photo(NEUTRAL), analysis_type="nail").json()
    assert b["patient_id"].startswith("P-")


def test_unknown_type_is_422(authed_client: Any) -> None:
    r = _post(authed_client, _photo(NEUTRAL), analysis_type="liver")
    assert r.status_code == 422
    assert r.json()["error"] == "validation_error"
    assert isinstance(r.json()["detail"], str)


def test_not_an_image_is_400(authed_client: Any) -> None:
    r = _post(authed_client, b"hello, not an image", analysis_type="skin")
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_image"


def test_blurry_photo_is_ungradable(authed_client: Any, blurry_jpeg_bytes: bytes) -> None:
    b = _post(authed_client, blurry_jpeg_bytes, analysis_type="skin").json()
    assert b["risk_level"] == "ungradable"
    assert b["quality"] == "poor"
    assert b["findings"] == [] and b["top_finding"] == ""


def test_duplicate_upload_replays_instead_of_creating(authed_client: Any) -> None:
    raw = _photo(RED, seed=99)
    first = _post(authed_client, raw, analysis_type="oral", patient_id="DUP").json()
    second = _post(authed_client, raw, analysis_type="oral", patient_id="DUP").json()
    assert first["analysis_id"] == second["analysis_id"]
    listed = authed_client.get("/api/v1/analyses", params={"patient_id": "DUP"}).json()
    assert len(listed) == 1


def test_list_and_get(authed_client: Any) -> None:
    a = _post(authed_client, _photo(RED, seed=1), analysis_type="skin", patient_id="L1").json()
    _post(authed_client, _photo(DARK, seed=2), analysis_type="nail", patient_id="L1")
    listed = authed_client.get("/api/v1/analyses", params={"patient_id": "L1"}).json()
    assert len(listed) == 2
    only_skin = authed_client.get(
        "/api/v1/analyses", params={"patient_id": "L1", "analysis_type": "skin"}
    ).json()
    assert [x["analysis_id"] for x in only_skin] == [a["analysis_id"]]
    got = authed_client.get(f"/api/v1/analyses/{a['analysis_id']}")
    assert got.status_code == 200 and got.json()["top_finding"] == a["top_finding"]
    assert authed_client.get("/api/v1/analyses/nope").status_code == 404


def test_analyze_requires_api_key(authed_client: Any) -> None:
    from fastapi.testclient import TestClient

    anon = TestClient(authed_client.app)
    assert _post(anon, _photo(NEUTRAL), analysis_type="skin").status_code == 401
    assert anon.get("/api/v1/analysis/types").status_code == 401


def test_dr_predict_contract_is_untouched(authed_client: Any, refer_jpeg_bytes: bytes) -> None:
    r = authed_client.post("/api/v1/predict", files=upload(refer_jpeg_bytes))
    assert r.status_code == 200
    assert "analysis_type" not in r.json()


# ---------------------------------------------------------------------------
# shadow mode: never a mock analysis
# ---------------------------------------------------------------------------
@pytest.fixture
def shadow_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Any]:
    empty_models = tmp_path / "models"
    empty_models.mkdir(parents=True, exist_ok=True)
    yield from build_client(
        monkeypatch,
        tmp_path,
        EYE_MODE="shadow",
        EYE_MODEL_SOURCE="torch",
        EYE_MODEL_SHA256="0" * 64,
        EYE_MODEL_DIR=str(empty_models),
    )


def test_shadow_without_model_is_503(shadow_client: Any) -> None:
    r = _post(shadow_client, _photo(NEUTRAL), analysis_type="skin")
    assert r.status_code == 503
    assert r.json()["error"] == "model_unavailable"
    assert shadow_client.get("/api/v1/analyses").json() == []


# ---------------------------------------------------------------------------
# unit: risk escalation
# ---------------------------------------------------------------------------
def test_high_risk_condition_escalates_even_when_not_top() -> None:
    from app.analysis.catalog import get_type
    from app.api.analyze import overall_risk

    skin = get_type("skin")
    assert skin is not None
    codes = [c.code for c in skin.conditions]
    probs = [0.0] * len(codes)
    probs[codes.index("benign_nevus")] = 0.6
    probs[codes.index("melanoma_suspect")] = 0.35
    probs[codes.index("normal")] = 0.05
    assert overall_risk(skin, probs) == "high"
    probs[codes.index("melanoma_suspect")] = 0.1
    probs[codes.index("normal")] = 0.3
    assert overall_risk(skin, probs) == "low"
