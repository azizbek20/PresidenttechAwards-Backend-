"""Inference for the non-fundus analysis types.

Source selection, per analysis type, mirrors the DR engine's safety rules:

* ``<EYE_MODEL_DIR>/analysis/<type>.onnx`` exists → :class:`OnnxAnalyzer`
  (real model; logits in :mod:`app.analysis.catalog` condition order).
* otherwise, ``EYE_MODE=demo`` → :class:`MockAnalyzer` (deterministic colour
  heuristics, ``model_version`` starts with ``mock-``).
* otherwise (shadow) → :class:`ModelUnavailable` → ``503 model_unavailable``.
  A mock result is never served outside demo mode.

Models are only ever read from local disk — no runtime downloads.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Protocol

import numpy as np

from app.analysis.catalog import AnalysisType, Condition
from app.inference.engine import IMAGENET_MEAN, IMAGENET_STD, ModelUnavailable

logger = logging.getLogger("eyedetect.analysis")

MOCK_VERSION = "mock-analysis-v0"
INPUT_SIZE = 224

_TOP_PROB = 0.70


class Analyzer(Protocol):
    model_version: str

    def predict(self, img_rgb: np.ndarray) -> list[float]:
        """Probabilities aligned with ``analysis_type.conditions``; sums to 1."""
        ...


# ---------------------------------------------------------------------------
# demo mock
# ---------------------------------------------------------------------------
def colour_cue(img_rgb: np.ndarray) -> str:
    """Dominant colour cue of the central region: red/yellow/dark/pale/normal.

    Deliberately crude: it exists so the demo can show every risk colour on
    the phone with ordinary photos, not to detect anything.
    """
    arr = np.asarray(img_rgb, dtype=np.float64)
    h, w = arr.shape[:2]
    centre = arr[h // 4 : h - h // 4 or h, w // 4 : w - w // 4 or w]
    if centre.size == 0:
        centre = arr
    r, g, b = (float(centre[..., i].mean()) for i in range(3))
    gray = (r + g + b) / 3.0
    sat = float((centre.max(axis=-1) - centre.min(axis=-1)).mean())

    if gray < 70:
        return "dark"
    if r - g > 45 and r - b > 45:
        return "red"
    if (r + g) / 2.0 - b > 40 and abs(r - g) < 35:
        return "yellow"
    if gray > 185 and sat < 30:
        return "pale"
    return "normal"


class MockAnalyzer:
    def __init__(self, analysis_type: AnalysisType) -> None:
        self.analysis_type = analysis_type
        self.model_version = MOCK_VERSION

    def predict(self, img_rgb: np.ndarray) -> list[float]:
        conditions = self.analysis_type.conditions
        cue = colour_cue(img_rgb)
        top = next((i for i, c in enumerate(conditions) if c.cue == cue), 0)
        rest = (1.0 - _TOP_PROB) / (len(conditions) - 1)
        probs = [rest] * len(conditions)
        probs[top] = _TOP_PROB
        return probs


# ---------------------------------------------------------------------------
# real model (ONNX)
# ---------------------------------------------------------------------------
def _to_input(img_rgb: np.ndarray) -> np.ndarray:
    import cv2

    resized = cv2.resize(
        np.ascontiguousarray(img_rgb, dtype=np.uint8),
        (INPUT_SIZE, INPUT_SIZE),
        interpolation=cv2.INTER_AREA,
    )
    chw = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
    mean = np.asarray(IMAGENET_MEAN, dtype=np.float32).reshape(3, 1, 1)
    std = np.asarray(IMAGENET_STD, dtype=np.float32).reshape(3, 1, 1)
    return ((chw - mean) / std)[None, ...].astype(np.float32)


def _softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max()
    e = np.exp(z)
    return e / e.sum()


class OnnxAnalyzer:
    def __init__(self, analysis_type: AnalysisType, path: Path) -> None:
        import onnxruntime as ort

        self.analysis_type = analysis_type
        self.session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        n_out = self.session.get_outputs()[0].shape[-1]
        expected = len(analysis_type.conditions)
        if isinstance(n_out, int) and n_out != expected:
            raise ValueError(
                f"{path.name}: model outputs {n_out} classes, catalogue expects {expected}"
            )
        self.model_version = f"{analysis_type.code}-{path.stem}-onnx"

    def predict(self, img_rgb: np.ndarray) -> list[float]:
        out = self.session.run(None, {self.input_name: _to_input(img_rgb)})[0]
        logits = np.asarray(out, dtype=np.float64).reshape(-1)
        if logits.shape[0] != len(self.analysis_type.conditions):
            raise ValueError("model output size does not match the catalogue")
        if np.all(logits >= 0) and abs(float(logits.sum()) - 1.0) < 1e-3:
            probs = logits  # model already ends in softmax
        else:
            probs = _softmax(logits)
        return [float(p) for p in probs]


# ---------------------------------------------------------------------------
# registry
# ---------------------------------------------------------------------------
_cache: dict[tuple[str, str], Analyzer] = {}
_lock = threading.Lock()


def model_path(model_dir: Path, type_code: str) -> Path:
    return Path(model_dir) / "analysis" / f"{type_code}.onnx"


def get_analyzer(analysis_type: AnalysisType, *, model_dir: Path, mode: str) -> Analyzer:
    """Return the analyser for ``analysis_type`` or raise ``ModelUnavailable``."""
    path = model_path(model_dir, analysis_type.code)
    key = (analysis_type.code, str(path))
    with _lock:
        cached = _cache.get(key)
        if cached is not None:
            return cached

        analyzer: Analyzer | None = None
        if path.is_file():
            try:
                analyzer = OnnxAnalyzer(analysis_type, path)
            except Exception as exc:  # broken artefact: never silently mock in shadow
                logger.error("analysis model %s failed to load: %s", path, exc)
                if mode != "demo":
                    raise ModelUnavailable(str(exc)) from exc

        if analyzer is None:
            if mode != "demo":
                raise ModelUnavailable(f"no model for analysis type {analysis_type.code!r}")
            # Not cached: a model file dropped in later is picked up without
            # a restart, and the mock is free to construct.
            return MockAnalyzer(analysis_type)

        _cache[key] = analyzer
        return analyzer


def is_real_model_available(analysis_type: AnalysisType, model_dir: Path) -> bool:
    return model_path(model_dir, analysis_type.code).is_file()


def top_condition(analysis_type: AnalysisType, probs: list[float]) -> tuple[Condition, float]:
    idx = int(np.argmax(probs))
    return analysis_type.conditions[idx], float(probs[idx])
