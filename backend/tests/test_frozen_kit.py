"""Frozen kit gate (spec §4.8). DO NOT EDIT.

Phase 0 does not continue until this file passes. It pins the interfaces every
parallel agent codes against.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from app.config import Settings
from app.inference.decision import GRADE_LABELS, decide
from app.inference.engine import IMAGENET_MEAN, IMAGENET_STD
from app.inference.mock_engine import MockEngine, mean_gray
from app.schemas import DISCLAIMER, LEGACY_KEYS, PredictResponse
from tests import synthetic

GOLDEN = Path(__file__).parent / "fixtures" / "golden_predict.json"

#: Blur convention shared with Agent A's `quality.assess` (§5-A A2, "grayscale
#: at 512 px"). Pinned here so the frozen fixtures and the quality gate cannot
#: disagree about what "blur_var" means.
BLUR_SIZE = 512


def blur_var(img_rgb: np.ndarray) -> float:
    small = cv2.resize(img_rgb, (BLUR_SIZE, BLUR_SIZE), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


# --------------------------------------------------------------------------
# wire contract
# --------------------------------------------------------------------------
def test_golden_validates_against_frozen_schema() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    parsed = PredictResponse.model_validate(golden)
    assert parsed.decision == "REFER"
    assert parsed.mode == "demo"
    assert parsed.disclaimer == DISCLAIMER


def test_all_fifteen_legacy_keys_present() -> None:
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert len(LEGACY_KEYS) == 15
    missing = [k for k in LEGACY_KEYS if k not in golden]
    assert missing == [], f"golden lost legacy keys: {missing}"
    # C12: the two additive keys, and nothing else beyond them.
    assert set(golden) == set(LEGACY_KEYS) | {"request_id", "mode"}


def test_schema_has_exactly_seventeen_fields() -> None:
    assert set(PredictResponse.model_fields) == set(LEGACY_KEYS) | {
        "request_id",
        "mode",
    }


# --------------------------------------------------------------------------
# mock engine: determinism + band contract
# --------------------------------------------------------------------------
def test_mock_is_deterministic(refer_jpeg_bytes: bytes) -> None:
    img = synthetic.decode_rgb(refer_jpeg_bytes)
    a = MockEngine().predict(img)
    b = MockEngine().predict(img)
    assert a == b


def test_mock_band_contract(refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes) -> None:
    refer = synthetic.decode_rgb(refer_jpeg_bytes)
    norefer = synthetic.decode_rgb(norefer_jpeg_bytes)

    assert MockEngine().predict(refer)["grade"] == 4
    assert MockEngine().predict(norefer)["grade"] == 0


def test_fixture_means_sit_clear_of_band_edges(
    refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    """Bands are 140 and 120; a fixture landing on an edge would flake."""
    refer_m = mean_gray(synthetic.decode_rgb(refer_jpeg_bytes))
    norefer_m = mean_gray(synthetic.decode_rgb(norefer_jpeg_bytes))
    assert refer_m >= 155.0, refer_m
    assert norefer_m <= 105.0, norefer_m


def test_mock_probs_are_a_distribution(refer_jpeg_bytes: bytes) -> None:
    pred = MockEngine().predict(synthetic.decode_rgb(refer_jpeg_bytes))
    assert len(pred["probs"]) == 5
    assert pred["probs"][pred["grade"]] == pytest.approx(0.85)
    assert sum(pred["probs"]) == pytest.approx(1.0)
    assert pred["model_version"] == "mock-v0"


def test_mock_reads_raw_and_normalised_input_identically(
    refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    """The API hands the mock a normalised CHW tensor, tests hand it raw pixels.

    Both must land in the same band, or the demo would show one verdict in the
    suite and a different one over HTTP.
    """
    mean = np.asarray(IMAGENET_MEAN, dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray(IMAGENET_STD, dtype=np.float32).reshape(3, 1, 1)

    for raw in (refer_jpeg_bytes, norefer_jpeg_bytes):
        img = synthetic.decode_rgb(raw)
        resized = cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA)
        chw = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
        tensor = (chw - mean) / std

        assert MockEngine().predict(tensor)["grade"] == MockEngine().predict(img)["grade"]


# --------------------------------------------------------------------------
# quality fixtures (convention pinned for Agent A)
# --------------------------------------------------------------------------
def test_sharp_fixtures_clear_the_blur_threshold_by_3x(
    refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    default_min = Settings().quality_blur_min_var
    for raw in (refer_jpeg_bytes, norefer_jpeg_bytes):
        assert blur_var(synthetic.decode_rgb(raw)) >= 3 * default_min


def test_blurry_and_dark_fixtures_fail_their_gates(
    blurry_jpeg_bytes: bytes, dark_jpeg_bytes: bytes
) -> None:
    default_min = Settings().quality_blur_min_var
    assert blur_var(synthetic.decode_rgb(blurry_jpeg_bytes)) < default_min
    assert mean_gray(synthetic.decode_rgb(dark_jpeg_bytes)) < 20.0


# --------------------------------------------------------------------------
# decision logic
# --------------------------------------------------------------------------
def test_decide_worked_example() -> None:
    pred = {"grade": 3, "probs": [0.05, 0.10, 0.25, 0.45, 0.15], "model_version": "x"}
    d = decide(pred, quality_ok=True, threshold=0.5)

    assert d.decision == "REFER"
    assert d.referable is True
    assert d.probability == pytest.approx(0.85)
    assert d.icdr_grade == 3
    assert d.grade_label == GRADE_LABELS[3] == "Og'ir NPDR"
    assert d.quality == "good"
    assert d.db_probability == pytest.approx(0.85)
    assert d.db_icdr_grade == 3


def test_decide_ungradable_override_keeps_db_truth_null() -> None:
    pred = {"grade": 4, "probs": [0.0, 0.0, 0.0, 0.0, 1.0], "model_version": "x"}
    d = decide(pred, quality_ok=False, threshold=0.5)

    # C3: non-null placeholders on the wire...
    assert d.decision == "UNGRADABLE"
    assert d.referable is False
    assert d.probability == 0.0
    assert d.icdr_grade == 0
    assert d.grade_label == "Baholab bo'lmadi"
    assert d.quality == "poor"
    # ...NULL in the database, so training exports stay clean.
    assert d.db_probability is None
    assert d.db_icdr_grade is None


def test_decide_threshold_is_inclusive() -> None:
    pred = {"grade": 2, "probs": [0.3, 0.2, 0.5, 0.0, 0.0], "model_version": "x"}
    assert decide(pred, True, 0.5).decision == "REFER"
    assert decide(pred, True, 0.51).decision == "NO_REFER"


def test_decide_handles_none_prediction() -> None:
    assert decide(None, quality_ok=True, threshold=0.5).decision == "UNGRADABLE"


# --------------------------------------------------------------------------
# config enforcement (C9)
# --------------------------------------------------------------------------
def test_shadow_mode_refuses_the_mock_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EYE_MODE", "shadow")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "mock")
    with pytest.raises(ValueError, match="shadow"):
        Settings()


def test_shadow_mode_requires_a_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EYE_MODE", "shadow")
    monkeypatch.setenv("EYE_MODEL_SOURCE", "torch")
    monkeypatch.delenv("EYE_MODEL_SHA256", raising=False)
    with pytest.raises(ValueError, match="SHA256"):
        Settings()


def test_demo_defaults_are_safe() -> None:
    s = Settings()
    assert s.eye_mode == "demo"
    assert s.eye_model_source == "mock"
    assert s.eye_device == "cpu", "gates must never depend on MPS"


def test_patient_code_matches_the_wire_contract() -> None:
    import re

    from app.db.crud import generate_patient_code

    for _ in range(50):
        assert re.fullmatch(r"P-[0-9A-F]{6}", generate_patient_code())
