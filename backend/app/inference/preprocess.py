"""Image decoding and model-input preparation (spec §5-A A1).

Four pure functions, no I/O beyond decoding the bytes the API already read:

``load_rgb``       bytes -> HWC uint8 RGB (EXIF-corrected), ``None`` on failure
``retina_crop``    trim the black fundus border, then centre-square
``to_model_input`` HWC uint8 -> normalised CHW float32 model tensor
``display_copy``   512 px RGB uint8 base image for the Grad-CAM overlay

DETERMINISM
-----------
Every step is a fixed-parameter OpenCV/Pillow call with no RNG, so the same
input bytes produce bit-identical arrays on every invocation. This is asserted
directly in ``tests/unit/test_preprocess.py``.

CROSS-MODULE CONTRACT — DO NOT LOCALISE THESE CONSTANTS
-------------------------------------------------------
``to_model_input`` imports ``IMAGENET_MEAN``/``IMAGENET_STD`` from the frozen
``app.inference.engine``. The frozen ``mock_engine.mean_gray`` inverts exactly
this transform (``x * std + mean`` then ``* 255``) to recover an image's
intensity band from the normalised tensor the API hands it. Hard-coding a
private copy here — or reordering the ``/255`` and the ``(x - mean) / std``
steps — would silently shift every demo verdict.

The transform is, in order:
    RGB uint8 -> resize(size, size) -> float32 / 255 -> (x - mean) / std -> CHW
"""

from __future__ import annotations

import io
import logging

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.inference.engine import IMAGENET_MEAN, IMAGENET_STD

logger = logging.getLogger("eyedetect.preprocess")

#: Pixels whose gray value is below this are treated as fundus border (§5-A A1).
BORDER_GRAY_THRESHOLD = 10

#: Longest-side length of the Grad-CAM display copy.
DISPLAY_SIZE = 512


def _as_rgb_uint8(img: np.ndarray) -> np.ndarray:
    """Coerce an array to contiguous HWC uint8 RGB.

    ``load_rgb`` already returns that shape; this guards the other entry points
    against grayscale, RGBA and float arrays reaching OpenCV, which raises
    rather than converting.
    """
    arr = np.asarray(img)

    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    elif arr.ndim != 3:
        msg = f"expected a 2-D or 3-D image array, got shape {arr.shape}"
        raise ValueError(msg)
    elif arr.shape[2] == 1:
        arr = np.repeat(arr, 3, axis=2)
    elif arr.shape[2] == 4:
        arr = arr[:, :, :3]
    elif arr.shape[2] != 3:
        msg = f"expected 1, 3 or 4 channels, got {arr.shape[2]}"
        raise ValueError(msg)

    if arr.dtype != np.uint8:
        scaled = arr.astype(np.float64)
        if float(np.nanmax(scaled, initial=0.0)) <= 1.0:
            scaled = scaled * 255.0
        arr = np.clip(scaled, 0.0, 255.0).astype(np.uint8)

    return np.ascontiguousarray(arr)


def load_rgb(raw: bytes) -> np.ndarray | None:
    """Decode upload bytes to an HWC uint8 RGB array, or ``None`` on failure.

    Pillow decode + ``ImageOps.exif_transpose`` (phone cameras write the
    orientation in EXIF rather than rotating the pixels) + RGB conversion.
    Every decode failure is a *client* error the API turns into
    ``400 invalid_image``, so nothing is raised here.
    """
    if not raw:
        return None
    try:
        with Image.open(io.BytesIO(raw)) as im:
            im.load()
            # exif_transpose may return the same object when there is no EXIF,
            # so the conversion has to happen before the context manager closes it.
            oriented = ImageOps.exif_transpose(im) or im
            rgb = oriented.convert("RGB")
            return np.array(rgb, dtype=np.uint8, copy=True)
    # Broad by contract: Pillow signals a bad image with OSError, ValueError,
    # SyntaxError or DecompressionBombError depending on the codec, and the
    # caller's only vocabulary is "decoded" vs "did not decode".
    except Exception:
        logger.info("image decode failed (%d bytes)", len(raw), exc_info=True)
        return None


def retina_crop(img: np.ndarray) -> np.ndarray:
    """Trim the black border around the fundus, then take a centred square.

    Pixels with gray < :data:`BORDER_GRAY_THRESHOLD` are border. The bounding
    box of everything brighter is cropped out and reduced to its largest
    centred square, so the model always sees a square field of view.

    An **all-dark image** (empty bounding box — the ``dark_jpeg_bytes`` family)
    returns the input unchanged rather than raising or returning an empty
    array: the quality gate is what rejects such an image, and it must be able
    to measure it first.
    """
    arr = _as_rgb_uint8(img)

    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    mask = gray >= BORDER_GRAY_THRESHOLD
    if not bool(mask.any()):
        return arr

    rows = np.flatnonzero(mask.any(axis=1))
    cols = np.flatnonzero(mask.any(axis=0))
    box = arr[int(rows[0]) : int(rows[-1]) + 1, int(cols[0]) : int(cols[-1]) + 1]

    height, width = box.shape[:2]
    side = min(height, width)
    top = (height - side) // 2
    left = (width - side) // 2
    return np.ascontiguousarray(box[top : top + side, left : left + side])


def to_model_input(img: np.ndarray, size: int) -> np.ndarray:
    """Resize to ``size``², scale to 0..1, ImageNet-normalise, return CHW float32.

    See the module docstring: the constants and the ordering are a frozen
    cross-module contract with ``mock_engine.mean_gray``.
    """
    if size <= 0:
        msg = f"model input size must be positive, got {size}"
        raise ValueError(msg)

    arr = _as_rgb_uint8(img)
    resized = cv2.resize(arr, (size, size), interpolation=cv2.INTER_AREA)

    chw = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
    mean = np.asarray(IMAGENET_MEAN, dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray(IMAGENET_STD, dtype=np.float32).reshape(3, 1, 1)
    return np.ascontiguousarray((chw - mean) / std, dtype=np.float32)


def display_copy(img: np.ndarray) -> np.ndarray:
    """Return a 512 px (longest side) RGB uint8 copy for the heatmap overlay.

    The aspect ratio is preserved so the overlay lines up with what the
    clinician photographed; Grad-CAM output is resized onto this canvas.
    """
    arr = _as_rgb_uint8(img)
    height, width = arr.shape[:2]
    longest = max(height, width)
    if longest == 0:
        msg = "cannot build a display copy of an empty image"
        raise ValueError(msg)
    if longest == DISPLAY_SIZE:
        return arr

    scale = DISPLAY_SIZE / float(longest)
    new_w = max(1, round(width * scale))
    new_h = max(1, round(height * scale))
    interpolation = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR
    resized = cv2.resize(arr, (new_w, new_h), interpolation=interpolation)
    return np.ascontiguousarray(resized)
