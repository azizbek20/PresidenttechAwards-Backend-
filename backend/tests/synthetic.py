"""Frozen synthetic fundus generators (spec §4.8). DO NOT EDIT.

Shared deliberately between `tests/conftest.py` and `scripts/make_test_images.py`
(§5-D D2: "same generators as the frozen conftest fixtures, so smoke-test
colors are deterministic"). Agent D imports from here rather than
re-implementing — two generators that drift would make the smoke test disagree
with the suite about which image is REFER.

GEOMETRY, and why it matters
----------------------------
The retina circle is *inscribed* (radius = size/2), so it touches all four
edges. Its non-black bounding box is therefore the full frame, which makes
`retina_crop` a no-op on these fixtures. That is intentional: the frozen kit
feeds `MockEngine` the whole decoded image while `api/predict.py` feeds it the
cropped+normalised tensor, and only if crop is a no-op do those two paths land
in the *same* intensity band. A smaller disc would make `no_dr.jpg` grade 0 in
the unit test and grade 4 over HTTP.

CALIBRATION
-----------
JPEG is lossy, so the fill value is bisected until the *decoded* image's mean
gray hits the target. `mean_gray` is imported from the frozen mock so the
fixtures are calibrated against the exact function that grades them.
"""

from __future__ import annotations

import cv2
import numpy as np

from app.inference.mock_engine import mean_gray

SIZE = 640
JPEG_QUALITY = 95

#: Targets chosen against the frozen bands (grade = 4 if m>=140 else 2 if m>=120 else 0).
#: Both sit 20 gray levels clear of a boundary so JPEG noise cannot flip them.
REFER_MEAN = 160.0
NOREFER_MEAN = 100.0
DARK_MEAN = 8.0

REFER_SEED = 20260809
NOREFER_SEED = 19700101
DARK_SEED = 42


def render(fill: float, seed: int, size: int = SIZE) -> np.ndarray:
    """Fundus-like RGB uint8: inscribed disc + optic disc + speckle noise.

    Speckle noise is what gives the image a high Laplacian variance, so the
    sharp fixtures clear `quality_blur_min_var` by a wide margin instead of
    sitting on the knife edge.
    """
    rng = np.random.default_rng(seed)
    img = np.zeros((size, size, 3), dtype=np.float64)

    yy, xx = np.ogrid[:size, :size]
    c = (size - 1) / 2.0
    r = size / 2.0
    retina = (yy - c) ** 2 + (xx - c) ** 2 <= r * r

    img[retina] = fill

    # Optic disc: a brighter blob offset from centre, like a real fundus.
    disc = (yy - c * 0.72) ** 2 + (xx - c * 1.28) ** 2 <= (size * 0.085) ** 2
    img[disc & retina] = min(255.0, fill * 1.35)

    # Vessel-ish darker arcs, purely so the image is not a flat plate.
    for k in range(4):
        angle = np.pi / 2 * k + 0.3
        for t in np.linspace(0.15, 0.95, 220):
            y = int(c + np.sin(angle + t * 1.1) * r * t)
            x = int(c + np.cos(angle + t * 1.1) * r * t)
            if 1 <= y < size - 1 and 1 <= x < size - 1 and retina[y, x]:
                img[y - 1 : y + 2, x - 1 : x + 2] *= 0.72

    noise = rng.normal(0.0, 20.0, (size, size, 3))
    img[retina] += noise[retina]

    return np.clip(img, 0, 255).astype(np.uint8)


def encode_jpeg(img: np.ndarray, quality: int = JPEG_QUALITY) -> bytes:
    """Encode RGB uint8 -> JPEG bytes (cv2 wants BGR)."""
    ok, buf = cv2.imencode(
        ".jpg", cv2.cvtColor(img, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, quality]
    )
    if not ok:  # pragma: no cover - cv2 failure is not a normal path
        raise RuntimeError("JPEG encode failed")
    return bytes(buf.tobytes())


def decode_rgb(raw: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:  # pragma: no cover
        raise RuntimeError("JPEG decode failed")
    return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)


def calibrated_jpeg(
    target_mean: float,
    seed: int,
    *,
    blur_ksize: int | None = None,
    quality: int = JPEG_QUALITY,
    tol: float = 0.5,
) -> bytes:
    """Bisect the fill value until the *decoded* mean gray hits `target_mean`.

    Deterministic for a given (target, seed): bisection on a monotonic function
    with a fixed iteration count.
    """
    lo, hi = 0.0, 255.0
    best = b""
    for _ in range(24):
        mid = (lo + hi) / 2.0
        img = render(mid, seed)
        if blur_ksize:
            img = cv2.GaussianBlur(img, (blur_ksize, blur_ksize), 0)
        raw = encode_jpeg(img, quality)
        best = raw
        got = mean_gray(decode_rgb(raw))
        if abs(got - target_mean) <= tol:
            return raw
        if got < target_mean:
            lo = mid
        else:
            hi = mid
    return best


def refer_jpeg() -> bytes:
    """Sharp, mean ~160 -> mock grade 4 -> REFER."""
    return calibrated_jpeg(REFER_MEAN, REFER_SEED)


def norefer_jpeg() -> bytes:
    """Sharp, mean ~100 -> mock grade 0 -> NO_REFER."""
    return calibrated_jpeg(NOREFER_MEAN, NOREFER_SEED)


def blurry_jpeg() -> bytes:
    """The NO_REFER image through a 21px Gaussian -> quality gate fails first."""
    return calibrated_jpeg(NOREFER_MEAN, NOREFER_SEED, blur_ksize=21)


def dark_jpeg() -> bytes:
    """Mean well under 20 -> quality gate fails on brightness."""
    return calibrated_jpeg(DARK_MEAN, DARK_SEED)


def not_an_image() -> bytes:
    return b"EYE DETECT AI smoke test - this is deliberately not an image.\n"
