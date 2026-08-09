"""Unit tests for `app.inference.preprocess` (spec §5-A A5).

Covers the three behaviours the brief names — determinism, EXIF handling,
non-square input — plus the cross-module contract that actually breaks the demo
when it drifts: `to_model_input` must use the frozen ImageNet constants in the
frozen order, so `mock_engine.mean_gray` can invert it and land in the same
intensity band as the raw image.
"""

from __future__ import annotations

import io

import cv2
import numpy as np
import pytest
from PIL import Image

from app.inference.engine import IMAGENET_MEAN, IMAGENET_STD
from app.inference.mock_engine import MockEngine, mean_gray
from app.inference.preprocess import (
    BORDER_GRAY_THRESHOLD,
    DISPLAY_SIZE,
    display_copy,
    load_rgb,
    retina_crop,
    to_model_input,
)
from tests import synthetic

EXIF_ORIENTATION_TAG = 0x0112
#: EXIF orientation 6 = "rotate 90° CW to display", so H and W swap on transpose.
EXIF_ROTATE_90 = 6

INPUT_SIZE = 224


def _jpeg(img_rgb: np.ndarray, *, orientation: int | None = None) -> bytes:
    """Encode RGB uint8 to JPEG, optionally tagging an EXIF orientation."""
    buffer = io.BytesIO()
    pil = Image.fromarray(img_rgb, mode="RGB")
    if orientation is None:
        pil.save(buffer, format="JPEG", quality=95)
    else:
        exif = Image.Exif()
        exif[EXIF_ORIENTATION_TAG] = orientation
        pil.save(buffer, format="JPEG", quality=95, exif=exif)
    return buffer.getvalue()


def _framed(
    disc: np.ndarray, height: int, width: int, top: int, left: int
) -> np.ndarray:
    """Paste `disc` onto a black canvas — a synthetic letterboxed fundus."""
    canvas = np.zeros((height, width, 3), dtype=np.uint8)
    canvas[top : top + disc.shape[0], left : left + disc.shape[1]] = disc
    return canvas


# ---------------------------------------------------------------------------
# load_rgb
# ---------------------------------------------------------------------------
def test_load_rgb_returns_hwc_uint8_rgb(refer_jpeg_bytes: bytes) -> None:
    img = load_rgb(refer_jpeg_bytes)

    assert img is not None
    assert img.shape == (640, 640, 3)
    assert img.dtype == np.uint8


def test_load_rgb_returns_none_for_non_image_bytes(text_file_bytes: bytes) -> None:
    assert load_rgb(text_file_bytes) is None


def test_load_rgb_returns_none_for_empty_or_truncated(refer_jpeg_bytes: bytes) -> None:
    assert load_rgb(b"") is None
    assert load_rgb(refer_jpeg_bytes[:20]) is None


def test_load_rgb_matches_the_frozen_decoder(refer_jpeg_bytes: bytes) -> None:
    """Pillow and the frozen cv2-based fixture decoder must agree on the pixels.

    They are different JPEG implementations, so exact equality is not promised;
    the intensity band is what the mock grades on, and it must not shift.
    """
    pillow = load_rgb(refer_jpeg_bytes)
    frozen = synthetic.decode_rgb(refer_jpeg_bytes)

    assert pillow is not None
    assert pillow.shape == frozen.shape
    assert mean_gray(pillow) == pytest.approx(mean_gray(frozen), abs=0.5)


# ---------------------------------------------------------------------------
# determinism
# ---------------------------------------------------------------------------
def test_load_rgb_is_bit_identical_twice(refer_jpeg_bytes: bytes) -> None:
    first = load_rgb(refer_jpeg_bytes)
    second = load_rgb(refer_jpeg_bytes)

    assert first is not None
    assert second is not None
    assert first.tobytes() == second.tobytes()


def test_full_pipeline_is_bit_identical_twice(refer_jpeg_bytes: bytes) -> None:
    """Same bytes -> bit-identical model input, twice (§5-A A1)."""

    def run() -> tuple[bytes, bytes]:
        img = load_rgb(refer_jpeg_bytes)
        assert img is not None
        tensor = to_model_input(retina_crop(img), INPUT_SIZE)
        return tensor.tobytes(), display_copy(img).tobytes()

    assert run() == run()


# ---------------------------------------------------------------------------
# EXIF
# ---------------------------------------------------------------------------
def test_exif_orientation_is_applied() -> None:
    """A phone writes orientation in EXIF instead of rotating pixels."""
    portrait = synthetic.render(140.0, seed=7, size=320)[:200, :]  # 200x320, H != W
    assert portrait.shape[:2] == (200, 320)

    plain = load_rgb(_jpeg(portrait))
    rotated = load_rgb(_jpeg(portrait, orientation=EXIF_ROTATE_90))

    assert plain is not None
    assert rotated is not None
    assert plain.shape[:2] == (200, 320), "no EXIF tag must leave the frame alone"
    assert rotated.shape[:2] == (320, 200), "orientation 6 must swap H and W"


def test_exif_orientation_1_is_a_no_op() -> None:
    upright = synthetic.render(140.0, seed=11, size=320)[:200, :]

    plain = load_rgb(_jpeg(upright))
    tagged = load_rgb(_jpeg(upright, orientation=1))

    assert plain is not None
    assert tagged is not None
    assert plain.tobytes() == tagged.tobytes()


# ---------------------------------------------------------------------------
# retina_crop
# ---------------------------------------------------------------------------
def test_retina_crop_is_a_no_op_on_the_frozen_fixtures(refer_jpeg_bytes: bytes) -> None:
    """The frozen fixtures inscribe the disc, so their bbox is the whole frame.

    `tests/synthetic.py` depends on this: only a no-op crop keeps the unit-test
    path and the HTTP path in the same mock intensity band.
    """
    img = load_rgb(refer_jpeg_bytes)
    assert img is not None

    cropped = retina_crop(img)

    assert cropped.shape == img.shape
    assert np.array_equal(cropped, img)


def test_retina_crop_trims_the_black_border() -> None:
    disc = synthetic.render(150.0, seed=3, size=400)
    framed = _framed(disc, height=700, width=900, top=120, left=250)

    cropped = retina_crop(framed)

    assert cropped.shape == (400, 400, 3)
    assert np.array_equal(cropped, disc)


def test_retina_crop_squares_a_non_square_input() -> None:
    """Non-square content is reduced to its largest centred square."""
    wide = np.full((300, 500, 3), 180, dtype=np.uint8)

    cropped = retina_crop(wide)

    assert cropped.shape == (300, 300, 3)
    assert np.array_equal(cropped, wide[:, 100:400])


def test_retina_crop_returns_an_all_dark_image_unchanged() -> None:
    """Empty bbox must not raise and must not return an empty array."""
    black = np.zeros((64, 80, 3), dtype=np.uint8)

    cropped = retina_crop(black)

    assert cropped.shape == black.shape
    assert np.array_equal(cropped, black)


def test_retina_crop_handles_the_dark_fixture(dark_jpeg_bytes: bytes) -> None:
    """The dark fixture must survive the crop so the quality gate can measure it."""
    img = load_rgb(dark_jpeg_bytes)
    assert img is not None

    cropped = retina_crop(img)

    assert cropped.size > 0
    assert cropped.ndim == 3
    assert cropped.dtype == np.uint8


def test_retina_crop_threshold_is_the_specified_one() -> None:
    """Pixels at the threshold are content; below it they are border."""
    assert BORDER_GRAY_THRESHOLD == 10

    img = np.zeros((40, 40, 3), dtype=np.uint8)
    img[10:30, 10:30] = BORDER_GRAY_THRESHOLD - 1
    assert retina_crop(img).shape == (40, 40, 3), "sub-threshold content is border"

    img[10:30, 10:30] = BORDER_GRAY_THRESHOLD + 1
    assert retina_crop(img).shape == (20, 20, 3)


# ---------------------------------------------------------------------------
# to_model_input
# ---------------------------------------------------------------------------
def test_to_model_input_shape_and_dtype(refer_jpeg_bytes: bytes) -> None:
    img = load_rgb(refer_jpeg_bytes)
    assert img is not None

    tensor = to_model_input(img, INPUT_SIZE)

    assert tensor.shape == (3, INPUT_SIZE, INPUT_SIZE)
    assert tensor.dtype == np.float32
    assert tensor.flags["C_CONTIGUOUS"]


def test_to_model_input_uses_frozen_imagenet_constants(refer_jpeg_bytes: bytes) -> None:
    """Denormalising with the frozen constants must recover the resized pixels."""
    img = load_rgb(refer_jpeg_bytes)
    assert img is not None

    tensor = to_model_input(img, INPUT_SIZE)

    mean = np.asarray(IMAGENET_MEAN, dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray(IMAGENET_STD, dtype=np.float32).reshape(3, 1, 1)
    recovered = (tensor * std + mean) * 255.0

    expected = cv2.resize(img, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_AREA)
    expected_chw = expected.astype(np.float32).transpose(2, 0, 1)

    assert np.allclose(recovered, expected_chw, atol=1e-2)


def test_to_model_input_preserves_the_mock_intensity_band(
    refer_jpeg_bytes: bytes, norefer_jpeg_bytes: bytes
) -> None:
    """THE cross-agent contract: the API path and the raw path must agree.

    `api/predict.py` hands `MockEngine` a normalised tensor from this function
    while the frozen kit hands it raw pixels. If the constants or the ordering
    here drifted, the demo would show a different verdict over HTTP than in the
    suite — silently.
    """
    for raw, expected_grade in ((refer_jpeg_bytes, 4), (norefer_jpeg_bytes, 0)):
        img = load_rgb(raw)
        assert img is not None
        tensor = to_model_input(retina_crop(img), INPUT_SIZE)

        assert mean_gray(tensor) == pytest.approx(mean_gray(img), abs=2.0)
        assert MockEngine().predict(tensor)["grade"] == expected_grade
        assert MockEngine().predict(img)["grade"] == expected_grade


def test_to_model_input_accepts_a_non_square_image() -> None:
    wide = synthetic.render(150.0, seed=5, size=400)[:200, :]

    tensor = to_model_input(wide, INPUT_SIZE)

    assert tensor.shape == (3, INPUT_SIZE, INPUT_SIZE)


def test_to_model_input_rejects_a_non_positive_size(refer_jpeg_bytes: bytes) -> None:
    img = load_rgb(refer_jpeg_bytes)
    assert img is not None

    with pytest.raises(ValueError, match="positive"):
        to_model_input(img, 0)


# ---------------------------------------------------------------------------
# display_copy
# ---------------------------------------------------------------------------
def test_display_copy_is_512px_rgb_uint8(refer_jpeg_bytes: bytes) -> None:
    img = load_rgb(refer_jpeg_bytes)
    assert img is not None

    display = display_copy(img)

    assert display.shape == (DISPLAY_SIZE, DISPLAY_SIZE, 3)
    assert display.dtype == np.uint8


def test_display_copy_preserves_aspect_ratio_on_non_square_input() -> None:
    wide = synthetic.render(150.0, seed=9, size=800)[:400, :]  # 400x800

    display = display_copy(wide)

    assert max(display.shape[:2]) == DISPLAY_SIZE
    assert display.shape[:2] == (256, DISPLAY_SIZE)


def test_display_copy_upscales_a_small_image() -> None:
    small = synthetic.render(150.0, seed=13, size=128)

    display = display_copy(small)

    assert display.shape == (DISPLAY_SIZE, DISPLAY_SIZE, 3)
    assert display.dtype == np.uint8
