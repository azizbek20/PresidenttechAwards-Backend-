"""Unit tests for `app.inference.quality` (spec §5-A A5).

Each failure test isolates ONE rule: it asserts that the other two rules still
pass, so a test named "fails on brightness" cannot quietly start passing
because the blur rule fired instead.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass

import numpy as np
import pytest

from app.config import Settings
from app.inference.mock_engine import mean_gray as frozen_mean_gray
from app.inference.preprocess import load_rgb
from app.inference.quality import (
    MEAN_GRAY_MAX,
    MEAN_GRAY_MIN,
    MIN_SIDE_PX,
    QualityReport,
    assess,
    blur_variance,
    mean_gray,
)
from tests import synthetic
from tests.test_frozen_kit import blur_var as frozen_blur_var

DEFAULT_BLUR_MIN = 50.0
SHARP_MARGIN = 3  # the sharp fixtures must clear the threshold by this factor


@dataclass(frozen=True)
class StubSettings:
    """Minimal structural stand-in for `app.config.Settings`."""

    quality_blur_min_var: float = DEFAULT_BLUR_MIN


def _decode(raw: bytes) -> np.ndarray:
    img = load_rgb(raw)
    assert img is not None
    return img


# ---------------------------------------------------------------------------
# conventions are pinned to the frozen implementations
# ---------------------------------------------------------------------------
def test_default_threshold_is_fifty() -> None:
    """§5-A A2 pins the default; the stub below is calibrated against it."""
    assert Settings.model_fields["quality_blur_min_var"].default == DEFAULT_BLUR_MIN


def test_blur_variance_matches_the_frozen_convention(
    refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes, blurry_jpeg_bytes: bytes
) -> None:
    """`tests/test_frozen_kit.blur_var` is the definition; we must reproduce it."""
    for raw in (refer_jpeg_bytes, norefer_jpeg_bytes, blurry_jpeg_bytes):
        img = synthetic.decode_rgb(raw)
        assert blur_variance(img) == pytest.approx(frozen_blur_var(img), rel=1e-12)


def test_mean_gray_matches_the_frozen_mock(
    refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes, dark_jpeg_bytes: bytes
) -> None:
    """The gate and the mock must never disagree about how bright an image is."""
    for raw in (refer_jpeg_bytes, norefer_jpeg_bytes, dark_jpeg_bytes):
        img = synthetic.decode_rgb(raw)
        assert mean_gray(img) == pytest.approx(frozen_mean_gray(img), rel=1e-12)


# ---------------------------------------------------------------------------
# the pass case
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fixture", ["refer_jpeg_bytes", "norefer_jpeg_bytes"])
def test_sharp_fixture_passes(fixture: str, request: pytest.FixtureRequest) -> None:
    img = _decode(request.getfixturevalue(fixture))

    report = assess(img, StubSettings())

    assert report.ok is True
    assert report.quality == "good"
    assert MEAN_GRAY_MIN <= report.mean_gray <= MEAN_GRAY_MAX


@pytest.mark.parametrize("fixture", ["refer_jpeg_bytes", "norefer_jpeg_bytes"])
def test_sharp_fixture_clears_the_threshold_by_3x(
    fixture: str, request: pytest.FixtureRequest
) -> None:
    """Not knife-edge: a fixture sitting just above 50.0 would flake (§5-A A5)."""
    img = _decode(request.getfixturevalue(fixture))

    report = assess(img, StubSettings())

    assert report.blur_var >= SHARP_MARGIN * DEFAULT_BLUR_MIN, report.blur_var


# ---------------------------------------------------------------------------
# blur rule
# ---------------------------------------------------------------------------
def test_blurry_fixture_fails_on_blur_only(blurry_jpeg_bytes: bytes) -> None:
    img = _decode(blurry_jpeg_bytes)

    report = assess(img, StubSettings())

    assert report.ok is False
    assert report.quality == "poor"
    assert report.blur_var < DEFAULT_BLUR_MIN, "must fail the blur rule"
    # ...and specifically NOT the other two rules:
    assert MEAN_GRAY_MIN <= report.mean_gray <= MEAN_GRAY_MAX
    assert min(img.shape[:2]) >= MIN_SIDE_PX


def test_blur_threshold_comes_from_settings(blurry_jpeg_bytes: bytes) -> None:
    """QUALITY_BLUR_MIN_VAR is the knob; the gate must honour it, inclusively."""
    img = _decode(blurry_jpeg_bytes)
    measured = blur_variance(img)

    assert assess(img, StubSettings(quality_blur_min_var=measured)).ok is True
    assert assess(img, StubSettings(quality_blur_min_var=measured + 0.1)).ok is False


def test_a_sharp_image_fails_under_an_absurd_threshold(refer_jpeg_bytes: bytes) -> None:
    img = _decode(refer_jpeg_bytes)

    assert assess(img, StubSettings(quality_blur_min_var=1e9)).ok is False


# ---------------------------------------------------------------------------
# brightness rule
# ---------------------------------------------------------------------------
def test_dark_fixture_fails_on_brightness_only(dark_jpeg_bytes: bytes) -> None:
    img = _decode(dark_jpeg_bytes)

    report = assess(img, StubSettings())

    assert report.ok is False
    assert report.quality == "poor"
    assert report.mean_gray < MEAN_GRAY_MIN, "must fail the brightness rule"
    # ...and specifically NOT the other two rules:
    assert report.blur_var >= DEFAULT_BLUR_MIN
    assert min(img.shape[:2]) >= MIN_SIDE_PX


def test_blown_out_image_fails_on_brightness() -> None:
    """The other end of the exposure band: a flash-blown frame."""
    blown = np.full((640, 640, 3), 245, dtype=np.uint8)
    rng = np.random.default_rng(1234)
    noise = rng.normal(0.0, 6.0, blown.shape)
    blown = np.clip(blown.astype(np.float64) + noise, 236, 255).astype(np.uint8)

    report = assess(blown, StubSettings(quality_blur_min_var=0.0))

    assert report.mean_gray > MEAN_GRAY_MAX
    assert report.ok is False


def test_brightness_band_is_inclusive() -> None:
    for value in (MEAN_GRAY_MIN, MEAN_GRAY_MAX):
        flat = np.full((640, 640, 3), int(value), dtype=np.uint8)
        report = assess(flat, StubSettings(quality_blur_min_var=0.0))
        assert report.mean_gray == pytest.approx(value)
        assert report.ok is True, f"mean_gray={value} sits on the band edge"


# ---------------------------------------------------------------------------
# resolution rule
# ---------------------------------------------------------------------------
def test_small_image_fails_on_resolution_only(refer_jpeg_bytes: bytes) -> None:
    """A sharp, well-exposed crop that is simply too small to grade."""
    img = _decode(refer_jpeg_bytes)
    side = MIN_SIDE_PX - 1
    top = (img.shape[0] - side) // 2
    left = (img.shape[1] - side) // 2
    small = np.ascontiguousarray(img[top : top + side, left : left + side])

    report = assess(small, StubSettings())

    assert min(small.shape[:2]) < MIN_SIDE_PX
    assert report.ok is False
    assert report.quality == "poor"
    # ...and specifically NOT the other two rules:
    assert report.blur_var >= DEFAULT_BLUR_MIN
    assert MEAN_GRAY_MIN <= report.mean_gray <= MEAN_GRAY_MAX


def test_resolution_rule_is_inclusive(refer_jpeg_bytes: bytes) -> None:
    img = _decode(refer_jpeg_bytes)
    top = (img.shape[0] - MIN_SIDE_PX) // 2
    left = (img.shape[1] - MIN_SIDE_PX) // 2
    exactly_min = np.ascontiguousarray(
        img[top : top + MIN_SIDE_PX, left : left + MIN_SIDE_PX]
    )

    assert assess(exactly_min, StubSettings()).ok is True


# ---------------------------------------------------------------------------
# report shape
# ---------------------------------------------------------------------------
def test_quality_report_is_a_frozen_dataclass(refer_jpeg_bytes: bytes) -> None:
    report = assess(_decode(refer_jpeg_bytes), StubSettings())

    assert isinstance(report, QualityReport)
    assert [f.name for f in dataclasses.fields(report)] == [
        "ok",
        "quality",
        "blur_var",
        "mean_gray",
    ]
    assert isinstance(report.blur_var, float)
    assert isinstance(report.mean_gray, float)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.ok = False  # type: ignore[misc]


def test_quality_string_is_derived_from_ok(
    refer_jpeg_bytes: bytes, blurry_jpeg_bytes: bytes
) -> None:
    good = assess(_decode(refer_jpeg_bytes), StubSettings())
    poor = assess(_decode(blurry_jpeg_bytes), StubSettings())

    assert (good.ok, good.quality) == (True, "good")
    assert (poor.ok, poor.quality) == (False, "poor")


def test_assess_accepts_the_real_settings_object(refer_jpeg_bytes: bytes) -> None:
    """The production call site passes `app.config.Settings` (§5-C step 5)."""
    report = assess(_decode(refer_jpeg_bytes), Settings())

    assert isinstance(report, QualityReport)
