"""Demo-grade image quality gate (spec §5-A A2).

This runs **before** the DR engine on every request (``api/predict.py`` step 5),
on the FULL uncropped image — ``retina_crop`` happens later, in step 6, only
once the image has been judged gradable. A failing report makes the request
UNGRADABLE and ``engine.predict`` is never called; that ordering is pinned by
``tests/contract/test_engine_spy.py``.

Scope, stated honestly: this is the Doc 4 heuristic, not a validated quality
model. It catches the two failure modes a phone camera actually produces in the
field — motion/defocus blur and an unlit or blown-out frame — plus images too
small to grade. A validated multi-property quality model is roadmap work.

BLUR CONVENTION IS PINNED
-------------------------
``blur_variance`` reproduces ``tests/test_frozen_kit.blur_var`` exactly:

    cv2.resize(img, (512, 512), INTER_AREA)
        -> cv2.cvtColor(..., COLOR_RGB2GRAY)
        -> cv2.Laplacian(gray, cv2.CV_64F).var()

Resizing first is what makes the threshold resolution-independent: Laplacian
variance otherwise scales with the sensor's pixel count, so a 12 MP phone and a
640 px fixture would need different thresholds.

``mean_gray`` is the plain arithmetic mean over all pixels and channels — the
same definition the frozen ``mock_engine.mean_gray`` uses for its intensity
bands, so the gate and the mock can never disagree about how bright an image
is. Both conventions are asserted against the frozen implementations in
``tests/unit/test_quality.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import cv2
import numpy as np

#: Working resolution for the blur measurement (frozen kit: ``BLUR_SIZE``).
BLUR_SIZE = 512

#: Acceptable exposure band for the mean gray value (§5-A A2).
MEAN_GRAY_MIN = 20.0
MEAN_GRAY_MAX = 235.0

#: An image whose shorter side is below this cannot be graded (§5-A A2).
MIN_SIDE_PX = 300


class QualitySettings(Protocol):
    """Structural view of the settings fields this module reads.

    Declared read-only so any object exposing a ``quality_blur_min_var`` float
    — ``app.config.Settings`` in production, a stub in tests — satisfies it.
    """

    @property
    def quality_blur_min_var(self) -> float: ...


@dataclass(frozen=True)
class QualityReport:
    ok: bool
    quality: str
    blur_var: float
    mean_gray: float


def _as_rgb_uint8(img_rgb: np.ndarray) -> np.ndarray:
    arr = np.asarray(img_rgb)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    if arr.ndim != 3 or arr.shape[2] not in (1, 3, 4):
        msg = f"expected an RGB image array, got shape {arr.shape}"
        raise ValueError(msg)
    if arr.shape[2] == 1:
        arr = np.repeat(arr, 3, axis=2)
    elif arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.dtype != np.uint8:
        arr = np.clip(arr.astype(np.float64), 0.0, 255.0).astype(np.uint8)
    return np.ascontiguousarray(arr)


def blur_variance(img_rgb: np.ndarray) -> float:
    """Laplacian variance at 512 px grayscale — higher is sharper."""
    arr = _as_rgb_uint8(img_rgb)
    small = cv2.resize(arr, (BLUR_SIZE, BLUR_SIZE), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def mean_gray(img_rgb: np.ndarray) -> float:
    """Arithmetic mean over all pixels and channels, 0..255.

    Deliberately identical to the frozen ``mock_engine.mean_gray`` for raw RGB
    input; ``tests/unit/test_quality.py`` asserts the two agree exactly.
    """
    return float(np.asarray(img_rgb).astype(np.float64).mean())


def assess(img_rgb: np.ndarray, settings: QualitySettings) -> QualityReport:
    """Judge whether ``img_rgb`` (full, uncropped, HWC RGB) can be graded."""
    arr = _as_rgb_uint8(img_rgb)
    height, width = arr.shape[:2]

    measured_blur = blur_variance(arr)
    measured_mean = mean_gray(arr)

    ok = (
        measured_blur >= float(settings.quality_blur_min_var)
        and MEAN_GRAY_MIN <= measured_mean <= MEAN_GRAY_MAX
        and min(height, width) >= MIN_SIDE_PX
    )
    return QualityReport(
        ok=ok,
        quality="good" if ok else "poor",
        blur_var=measured_blur,
        mean_gray=measured_mean,
    )
