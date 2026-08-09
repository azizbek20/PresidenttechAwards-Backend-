"""Frozen engine contract (spec §4.5, C9). DO NOT EDIT.

NOTE on the ``auto`` source: §4.5's parenthetical still mentions
``mock | torch | auto``, but that is residual v1 wording — C9 and §4.9 DELETE
``auto``. A deployment that silently degrades to mock predictions is a safety
failure, not a convenience. Only ``mock`` and ``torch`` are accepted here; the
config layer rejects anything else before this module is reached.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, TypedDict, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    import numpy as np

logger = logging.getLogger("eyedetect.engine")

#: ImageNet normalisation constants. FROZEN and shared: ``preprocess.to_model_input``
#: (Agent A) MUST use these, because ``mock_engine`` inverts the exact same
#: transform to recover mean gray from a normalised tensor. If the two drift,
#: every demo verdict shifts silently.
IMAGENET_MEAN: tuple[float, float, float] = (0.485, 0.456, 0.406)
IMAGENET_STD: tuple[float, float, float] = (0.229, 0.224, 0.225)


class ModelUnavailable(RuntimeError):
    """Raised when a torch engine has no verified, license-cleared artifact.

    The API maps this to ``503 {"error": "model_unavailable", ...}``. It is
    never converted into a mock prediction (C9).
    """


class Prediction(TypedDict):
    grade: int  # 0..4
    probs: list[float]  # len 5, sums to 1.0
    model_version: str


@runtime_checkable
class InferenceEngine(Protocol):
    model_loaded: bool

    def predict(self, img: "np.ndarray") -> Prediction: ...


class UnavailableEngine:
    """Stand-in engine used when a torch artifact cannot be loaded.

    It exists so the app can still *start* (and report 503 on
    ``/health/ready`` and ``/api/v1/predict``) instead of crashing at boot —
    the behaviour §4.9 requires for shadow mode without a model.
    """

    model_loaded: bool = False

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def predict(self, img: "np.ndarray") -> Prediction:
        raise ModelUnavailable(self.reason)


def get_engine(settings) -> InferenceEngine:  # noqa: ANN001 - frozen signature
    """Build the engine for the configured source.

    ``torch_engine`` is imported lazily so the mock path never imports torch.
    A missing/invalid checkpoint yields :class:`UnavailableEngine` (503 at the
    API), never a silent mock substitution.
    """
    source = settings.eye_model_source

    if source == "mock":
        if settings.eye_mode == "shadow":
            # Defence in depth: config.Settings already refuses this combination.
            raise ValueError(
                "EYE_MODE=shadow can never use the mock engine (C9)."
            )
        from app.inference.mock_engine import MockEngine

        return MockEngine()

    if source == "torch":
        try:
            from app.inference.torch_engine import TorchEngine
        except ImportError as exc:  # torch absent, or module not built yet
            logger.error("torch engine unavailable: %s", exc)
            return UnavailableEngine(f"torch engine import failed: {exc}")
        try:
            return TorchEngine(settings)
        except Exception as exc:  # missing / digest-mismatched checkpoint
            logger.error("torch engine failed to load: %s", exc)
            return UnavailableEngine(str(exc))

    raise ValueError(f"unknown EYE_MODEL_SOURCE={source!r} (expected mock|torch)")
