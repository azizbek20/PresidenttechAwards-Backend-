"""Frozen mock engine (spec §4.5). DO NOT EDIT.

Deterministic AND fixture-controllable: a hash-modulo mock cannot guarantee the
demo shows both a red (REFER) and a green (NO_REFER) card, so the verdict is
driven by image *intensity bands*:

    m = mean gray  ->  grade = 4 if m >= 140 else (2 if m >= 120 else 0)

Probability mass: 0.85 on the chosen grade, the remaining 0.15 spread evenly
over the other four (0.0375 each), so ``probs`` always sums to 1.0.

------------------------------------------------------------------------------
DUAL INPUT DOMAIN (orchestrator interface resolution, §0 rule 2 — additive)
------------------------------------------------------------------------------
``predict`` is called with two different array kinds in this codebase:

  * ``tests/`` and the frozen kit pass a **decoded RGB image** (HWC, uint8),
    which is what §4.5's "mean gray of the decoded RGB image" describes.
  * ``api/predict.py`` step 6 passes ``to_model_input(retina_crop(img))`` — a
    **normalised CHW float32 tensor** whose raw mean is ≈0.

Taking a naive ``.mean()`` of the second form would put every live request in
the ``m < 120`` band and the demo would show NO_REFER for everything. So the
mock detects a normalised CHW tensor and inverts the exact ImageNet transform
(``x * std + mean`` then ``* 255``) to recover the original mean gray. The
frozen signature is unchanged; only tolerance was added.

"Mean gray" here is the plain arithmetic mean over all pixels and channels.
``tests/conftest.py`` calibrates its fixtures against this same definition, so
the bands are exact on both paths.
"""

from __future__ import annotations

import numpy as np

from app.inference.engine import IMAGENET_MEAN, IMAGENET_STD, Prediction

MODEL_VERSION = "mock-v0"

_TOP_PROB = 0.85
_REST_PROB = (1.0 - _TOP_PROB) / 4.0  # 0.0375


def mean_gray(img: np.ndarray) -> float:
    """Mean gray in 0..255, accepting raw RGB or a normalised CHW tensor.

    Detection rule: a float array shaped (3, H, W) is treated as a normalised
    model input; anything else is treated as raw pixels. A raw RGB image is
    HWC, so (3, H, W) is unambiguous for any realistic image size.
    """
    arr = np.asarray(img)

    if arr.ndim == 3 and arr.shape[0] == 3 and np.issubdtype(arr.dtype, np.floating):
        mean = np.asarray(IMAGENET_MEAN, dtype=np.float64).reshape(3, 1, 1)
        std = np.asarray(IMAGENET_STD, dtype=np.float64).reshape(3, 1, 1)
        denorm = (arr.astype(np.float64) * std + mean) * 255.0
        return float(np.clip(denorm, 0.0, 255.0).mean())

    if np.issubdtype(arr.dtype, np.floating) and float(arr.max(initial=0.0)) <= 1.0:
        # float image already in 0..1
        return float(np.clip(arr.astype(np.float64) * 255.0, 0.0, 255.0).mean())

    return float(arr.astype(np.float64).mean())


def grade_for_mean(m: float) -> int:
    return 4 if m >= 140 else (2 if m >= 120 else 0)


class MockEngine:
    """Full chain, no model weights — the Doc 5 ``EYE_MODEL_SOURCE=mock`` path."""

    model_loaded: bool = True

    def predict(self, img: np.ndarray) -> Prediction:
        grade = grade_for_mean(mean_gray(img))
        probs = [_REST_PROB] * 5
        probs[grade] = _TOP_PROB
        return Prediction(grade=grade, probs=probs, model_version=MODEL_VERSION)
