"""Unit tests for `app.inference.gradcam` (spec §5-A A5).

The contract under test is a negative one: neither renderer may ever raise.
`api/predict.py` step 8 calls them best-effort, so an exception here would turn
a served prediction into a 500 for the sake of a decorative overlay.

The real Grad-CAM success path is exercised against a randomly initialised timm
model. That proves the plumbing (hooks, target layer, backward pass, overlay,
PNG write) — it asserts nothing clinical, and cannot: an untrained network's
saliency is noise.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.inference.gradcam import (
    GRADCAM_DEVICE,
    HEATMAP_ALPHA,
    mock_heatmap,
    render_heatmap,
)
from app.inference.preprocess import display_copy, load_rgb, retina_crop, to_model_input

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
INPUT_SIZE = 224


@pytest.fixture
def display(refer_jpeg_bytes: bytes) -> np.ndarray:
    img = load_rgb(refer_jpeg_bytes)
    assert img is not None
    return display_copy(img)


@pytest.fixture
def model_input(refer_jpeg_bytes: bytes) -> np.ndarray:
    img = load_rgb(refer_jpeg_bytes)
    assert img is not None
    return to_model_input(retina_crop(img), INPUT_SIZE)


def _assert_valid_png(path: Path, expected_size: tuple[int, int]) -> None:
    raw = path.read_bytes()
    assert raw.startswith(PNG_MAGIC), "not a PNG"
    # IHDR width/height live at bytes 16..24 of every PNG.
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == expected_size

    with Image.open(path) as opened:
        opened.load()
        assert opened.format == "PNG"
        assert opened.size == expected_size


# ---------------------------------------------------------------------------
# mock_heatmap
# ---------------------------------------------------------------------------
def test_mock_heatmap_writes_a_valid_png(display: np.ndarray, tmp_path: Path) -> None:
    out = tmp_path / "heat.png"

    assert mock_heatmap(display, out) is True

    height, width = display.shape[:2]
    _assert_valid_png(out, (width, height))


def test_mock_heatmap_forces_png_regardless_of_suffix(
    display: np.ndarray, tmp_path: Path
) -> None:
    """Storage names heatmaps `.png`; the encoder must not trust the suffix."""
    out = tmp_path / "heat.bin"

    assert mock_heatmap(display, out) is True
    assert out.read_bytes().startswith(PNG_MAGIC)


def test_mock_heatmap_creates_missing_parent_directories(
    display: np.ndarray, tmp_path: Path
) -> None:
    out = tmp_path / "deep" / "nested" / "heat.png"

    assert mock_heatmap(display, out) is True
    assert out.is_file()


def test_mock_heatmap_blends_at_40_percent(tmp_path: Path) -> None:
    """A flat gray plate makes the composite arithmetic checkable by hand."""
    assert HEATMAP_ALPHA == pytest.approx(0.4)
    flat = np.full((64, 64, 3), 100, dtype=np.uint8)
    out = tmp_path / "heat.png"

    assert mock_heatmap(flat, out) is True

    with Image.open(out) as opened:
        blended = np.asarray(opened.convert("RGB"), dtype=np.float32)

    # Every output pixel is 60% of the original plus 40% of a JET colour, so it
    # must sit between the untouched plate and the extremes of that mix.
    assert blended.min() >= 0.6 * 100 - 1
    assert blended.max() <= 0.6 * 100 + 0.4 * 255 + 1
    assert not np.allclose(blended, 100.0), "an overlay must actually change pixels"


def test_mock_heatmap_returns_false_on_garbage_input(tmp_path: Path) -> None:
    assert mock_heatmap("not an image", tmp_path / "x.png") is False  # type: ignore[arg-type]
    assert mock_heatmap(np.zeros((4,), dtype=np.uint8), tmp_path / "y.png") is False


def test_mock_heatmap_returns_false_when_the_path_is_unwritable(
    display: np.ndarray, tmp_path: Path
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"a file, not a directory")

    assert mock_heatmap(display, blocker / "heat.png") is False


# ---------------------------------------------------------------------------
# render_heatmap — failure paths
# ---------------------------------------------------------------------------
def test_render_heatmap_returns_false_for_a_non_model(
    display: np.ndarray, model_input: np.ndarray, tmp_path: Path
) -> None:
    out = tmp_path / "heat.png"

    assert render_heatmap(object(), model_input, display, out) is False
    assert not out.exists()


def test_render_heatmap_returns_false_when_the_forward_pass_raises(
    display: np.ndarray, model_input: np.ndarray, tmp_path: Path
) -> None:
    from torch import nn

    class Exploding(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.conv = nn.Conv2d(3, 4, 3)

        def forward(self, _x: object) -> None:
            msg = "forward pass failed"
            raise RuntimeError(msg)

    out = tmp_path / "heat.png"

    assert render_heatmap(Exploding(), model_input, display, out) is False
    assert not out.exists()


def test_render_heatmap_returns_false_for_a_bad_input_tensor(
    display: np.ndarray, tmp_path: Path
) -> None:
    import timm

    model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=5)

    bad_shape = np.zeros((7,), dtype=np.float32)
    assert render_heatmap(model, bad_shape, display, tmp_path / "a.png") is False
    assert render_heatmap(model, "not a tensor", display, tmp_path / "b.png") is False


def test_render_heatmap_returns_false_when_the_path_is_unwritable(
    display: np.ndarray, model_input: np.ndarray, tmp_path: Path
) -> None:
    import timm

    model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=5)
    blocker = tmp_path / "blocker"
    blocker.write_bytes(b"a file, not a directory")

    assert render_heatmap(model, model_input, display, blocker / "heat.png") is False


# ---------------------------------------------------------------------------
# render_heatmap — execution path (no clinical assertion, by design)
# ---------------------------------------------------------------------------
def test_render_heatmap_writes_a_valid_png(
    display: np.ndarray, model_input: np.ndarray, tmp_path: Path
) -> None:
    import timm

    model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=5)
    out = tmp_path / "sub" / "heat.png"

    assert render_heatmap(model, model_input, display, out) is True

    height, width = display.shape[:2]
    _assert_valid_png(out, (width, height))


def test_render_heatmap_leaves_the_model_usable_on_its_original_device(
    display: np.ndarray, model_input: np.ndarray, tmp_path: Path
) -> None:
    """Grad-CAM runs on cpu; it must hand the model back the way it found it."""
    import timm
    import torch

    model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=5)
    before = next(model.parameters()).device

    assert render_heatmap(model, model_input, display, tmp_path / "heat.png") is True

    after = next(model.parameters()).device
    assert after == before
    assert str(after) == GRADCAM_DEVICE

    with torch.inference_mode():
        logits = model(torch.from_numpy(model_input).unsqueeze(0))
    assert logits.shape == (1, 5)


def test_render_heatmap_accepts_a_batched_torch_tensor(
    display: np.ndarray, model_input: np.ndarray, tmp_path: Path
) -> None:
    import timm
    import torch

    model = timm.create_model("efficientnet_b0", pretrained=False, num_classes=5)
    batched = torch.from_numpy(model_input).unsqueeze(0)
    out = tmp_path / "heat.png"

    assert render_heatmap(model, batched, display, out) is True
    assert out.read_bytes().startswith(PNG_MAGIC)
