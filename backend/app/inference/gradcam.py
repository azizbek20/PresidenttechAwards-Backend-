"""Grad-CAM heatmap rendering (spec §5-A A4).

Two renderers, one contract: **never raise**. A heatmap is a nice-to-have
overlay on the result screen, so a rendering failure must degrade to
``heatmap_url = null`` and a served prediction — not to a 500. Both functions
wrap their whole body and return ``False`` on any failure.

``render_heatmap``  real Grad-CAM on the last conv block of a torch model
``mock_heatmap``    radial-gradient stand-in used by the demo/mock path

Both composite at 40% heatmap alpha over the display copy and write PNG.

DEVICE: Grad-CAM always runs on **cpu**, whatever ``EYE_DEVICE`` says — the
backward pass it needs is not reliably supported on MPS. The model's original
device is restored before returning, so an MPS-resident engine keeps working
after a heatmap render.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger("eyedetect.gradcam")

#: Heatmap opacity in the composite (§5-A A4: "40% alpha overlay").
HEATMAP_ALPHA = 0.4

#: Grad-CAM is CPU-only here regardless of EYE_DEVICE.
GRADCAM_DEVICE = "cpu"

#: Attributes probed, in order, for "the last conv block" of a timm/torchvision
#: model before falling back to the last ``Conv2d`` in module order.
_BLOCK_ATTRS = ("blocks", "layer4", "features", "stages")


def _as_rgb_uint8(img: np.ndarray) -> np.ndarray:
    arr = np.asarray(img)
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    if arr.ndim != 3:
        msg = f"expected an image array, got shape {arr.shape}"
        raise ValueError(msg)
    if arr.shape[2] == 4:
        arr = arr[:, :, :3]
    if arr.shape[2] != 3:
        msg = f"expected 3 channels, got {arr.shape[2]}"
        raise ValueError(msg)
    if arr.dtype != np.uint8:
        arr = np.clip(arr.astype(np.float64), 0.0, 255.0).astype(np.uint8)
    return np.ascontiguousarray(arr)


def _overlay(display_rgb: np.ndarray, activation: np.ndarray) -> np.ndarray:
    """Composite a 0..1 activation map over the display image at 40% alpha."""
    height, width = display_rgb.shape[:2]
    cam = np.asarray(activation, dtype=np.float32)
    if cam.ndim != 2:
        cam = cam.reshape(cam.shape[-2], cam.shape[-1])
    if cam.shape != (height, width):
        cam = np.asarray(
            cv2.resize(cam, (width, height), interpolation=cv2.INTER_LINEAR),
            dtype=np.float32,
        )
    cam = np.clip(cam, 0.0, 1.0)

    heat_bgr = cv2.applyColorMap((cam * 255.0).astype(np.uint8), cv2.COLORMAP_JET)
    heat_rgb = cv2.cvtColor(heat_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)

    base = display_rgb.astype(np.float32)
    blended = (1.0 - HEATMAP_ALPHA) * base + HEATMAP_ALPHA * heat_rgb
    return np.clip(blended, 0.0, 255.0).astype(np.uint8)


def _write_png(rgb: np.ndarray, out_path: Path) -> None:
    """Write RGB uint8 as PNG, forcing the format rather than trusting the suffix."""
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(target, format="PNG")


def _pick_target_layer(model: Any) -> Any:
    """Return the last convolutional block of ``model`` for Grad-CAM."""
    for attr in _BLOCK_ATTRS:
        block = getattr(model, attr, None)
        if block is None:
            continue
        try:
            return block[-1]
        except (TypeError, IndexError, KeyError):
            return block

    from torch import nn

    convs = [m for m in model.modules() if isinstance(m, nn.Conv2d)]
    if not convs:
        msg = "model exposes no convolutional layer to attach Grad-CAM to"
        raise ValueError(msg)
    return convs[-1]


def _as_batched_tensor(input_tensor: Any) -> Any:
    """Coerce a CHW/NCHW numpy array or torch tensor to a cpu float32 batch."""
    import torch

    if isinstance(input_tensor, torch.Tensor):
        tensor = input_tensor
    else:
        array = np.ascontiguousarray(np.asarray(input_tensor), dtype=np.float32)
        tensor = torch.from_numpy(array)
    if tensor.ndim == 3:
        tensor = tensor.unsqueeze(0)
    if tensor.ndim != 4:
        msg = f"expected a CHW or NCHW input tensor, got shape {tuple(tensor.shape)}"
        raise ValueError(msg)
    return tensor.detach().to(device=GRADCAM_DEVICE, dtype=torch.float32)


def render_heatmap(
    model: Any, input_tensor: Any, display_rgb: np.ndarray, out_path: Path
) -> bool:
    """Render a Grad-CAM overlay to ``out_path`` as PNG. ``False`` on any failure.

    The whole body is guarded: a missing grad-cam wheel, an exotic architecture
    with no attachable conv block, a read-only storage directory or an MPS
    backward-pass gap must all cost the request its heatmap, nothing more.
    """
    original_device = None
    try:
        import torch
        from pytorch_grad_cam import GradCAM  # type: ignore[import-untyped]

        display = _as_rgb_uint8(display_rgb)
        batch = _as_batched_tensor(input_tensor)

        try:
            original_device = next(model.parameters()).device
        except (AttributeError, StopIteration):  # pragma: no cover - defensive
            original_device = None
        if original_device is not None and str(original_device) != GRADCAM_DEVICE:
            model.to(GRADCAM_DEVICE)
        model.eval()

        layers = [_pick_target_layer(model)]
        # Grad-CAM needs a backward pass, so it must run outside inference_mode.
        with torch.enable_grad(), GradCAM(model=model, target_layers=layers) as cam:
            activation = cam(input_tensor=batch)[0]

        _write_png(_overlay(display, activation), Path(out_path))
    except Exception:
        logger.warning("grad-cam render failed for %s", out_path, exc_info=True)
        return False
    else:
        return True
    finally:
        if original_device is not None and str(original_device) != GRADCAM_DEVICE:
            try:
                model.to(original_device)
            except Exception:  # noqa: BLE001 - restoring the device is best effort
                logger.warning("could not restore model device %s", original_device)


def mock_heatmap(display_rgb: np.ndarray, out_path: Path) -> bool:
    """Radial-gradient stand-in overlay used by the mock engine path.

    Deliberately *not* a saliency map: it demonstrates the overlay plumbing in
    demo mode, where ``model_version="mock-v0"`` already tells every consumer
    that no model produced this. Same 40% alpha and PNG output as the real one.
    """
    try:
        display = _as_rgb_uint8(display_rgb)
        height, width = display.shape[:2]

        yy = np.arange(height, dtype=np.float32).reshape(height, 1)
        xx = np.arange(width, dtype=np.float32).reshape(1, width)
        cy = (height - 1) / 2.0
        xc = (width - 1) / 2.0
        radius = np.sqrt(
            ((yy - cy) / max(cy, 1.0)) ** 2 + ((xx - xc) / max(xc, 1.0)) ** 2
        )
        activation = np.clip(1.0 - radius, 0.0, 1.0).astype(np.float32)

        _write_png(_overlay(display, activation), Path(out_path))
    except Exception:
        logger.warning("mock heatmap render failed for %s", out_path, exc_info=True)
        return False
    else:
        return True
