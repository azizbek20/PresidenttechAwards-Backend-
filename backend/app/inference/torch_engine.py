"""Torch inference engine (spec §5-A A3, corrections C1/C9).

Imported **lazily** by the frozen ``engine.get_engine``, so the mock path never
pays for importing torch. Construction failures are the caller's contract:
``get_engine`` wraps any exception raised here in ``UnavailableEngine`` (which
reports ``model_loaded=False`` and makes ``/api/v1/predict`` answer
``503 model_unavailable``). Raising a clear exception on a missing or
digest-mismatched checkpoint is therefore the CORRECT behaviour — never a
silent fallback to mock output (C9).

LICENSING (C1)
--------------
``sakshamkr1/ResNet50-APTOS-DR`` is CC-BY-NC-4.0 and ships a fully pickled
model; it is not used here and must not be. Supported artifacts are:

1. a plain **state_dict** at ``EYE_MODEL_DIR/model.pt`` loaded into a timm
   architecture named by ``EYE_MODEL_DIR/arch.txt`` (default
   ``efficientnet_b0``, ``num_classes=5``);
2. a locally present ``jdelgado2002/diabetic_retinopathy_detection`` (MIT)
   snapshot: ``model.safetensors`` or ``pytorch_model.bin`` beside a
   ``config.json``, either directly in ``EYE_MODEL_DIR`` or in the usual
   repo-named subdirectory.

``torch.load`` is **never** called with ``weights_only=False`` — a pickled
checkpoint is arbitrary code execution. ``.safetensors`` is preferred where
both exist. When ``EYE_MODEL_SHA256`` is set the digest of the artifact file is
verified BEFORE it is opened by the loader; a mismatch refuses the model.

AIR-GAPPED
----------
Nothing in this module reaches the network, at import time or load time:
``timm.create_model`` is always called with ``pretrained=False`` and weights
come only from the local ``EYE_MODEL_DIR``. Model delivery is an out-of-band
operation (a mounted read-only volume), not a runtime download.

DEVICE (orchestrator addendum, mirrored in ``app/config.py``)
-------------------------------------------------------------
``EYE_DEVICE`` is ``cpu`` (default, and mandatory for tests/CI/Docker/gates),
``mps`` (Apple-silicon dev runs; falls back to cpu with a WARNING when MPS is
genuinely unavailable) or ``auto`` (mps when available, else cpu). Everything
is float32 — MPS has no float64 — and outputs are moved back to cpu before any
``.numpy()`` conversion. Grad-CAM always runs on cpu (see ``gradcam.py``).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import timm
import torch

from app.inference.engine import ModelUnavailable, Prediction
from app.inference.preprocess import to_model_input

logger = logging.getLogger("eyedetect.torch_engine")

#: ICDR grades 0..4 — the wire contract fixes this at five classes.
NUM_CLASSES = 5

DEFAULT_ARCH = "efficientnet_b0"
ARCH_FILE = "arch.txt"
STATE_DICT_FILE = "model.pt"

#: Hugging-Face style weight files, safetensors first (no pickle at all).
HF_WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")
HF_CONFIG_FILE = "config.json"

#: Where a locally staged ``jdelgado2002/diabetic_retinopathy_detection``
#: snapshot is looked for, relative to ``EYE_MODEL_DIR``.
HF_SUBDIRS = (
    ".",
    "diabetic_retinopathy_detection",
    "jdelgado2002/diabetic_retinopathy_detection",
)

_DIGEST_CHUNK = 1 << 20


@dataclass(frozen=True)
class Checkpoint:
    """A located, not yet loaded, model artifact."""

    path: Path
    kind: str  # "state_dict" | "safetensors" | "hf_pickle"
    arch: str
    num_classes: int


def sha256_file(path: Path) -> str:
    """Streaming SHA-256 of ``path`` as lowercase hex."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_DIGEST_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_device(requested: str) -> str:
    """Map ``EYE_DEVICE`` onto a torch device string, never raising.

    ``cpu`` is honoured verbatim; ``mps`` degrades to cpu with a WARNING when
    the backend is not genuinely available; ``auto`` prefers mps when it is.
    """
    if requested == "cpu":
        return "cpu"

    backend = getattr(torch.backends, "mps", None)
    mps_available = bool(backend is not None and backend.is_available())

    if requested == "mps":
        if mps_available:
            return "mps"
        logger.warning("EYE_DEVICE=mps requested but MPS is unavailable — using cpu")
        return "cpu"
    if requested == "auto":
        return "mps" if mps_available else "cpu"

    logger.warning("unknown EYE_DEVICE=%r — using cpu", requested)
    return "cpu"


def _read_arch(model_dir: Path) -> str:
    arch_path = model_dir / ARCH_FILE
    if not arch_path.is_file():
        return DEFAULT_ARCH
    arch = arch_path.read_text(encoding="utf-8").strip()
    return arch or DEFAULT_ARCH


def _arch_from_hf_config(config_path: Path) -> tuple[str, int]:
    """Best-effort architecture + class count from a HF ``config.json``."""
    arch = DEFAULT_ARCH
    num_classes = NUM_CLASSES
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("unreadable %s — assuming %s/%d", config_path, arch, num_classes)
        return arch, num_classes

    if not isinstance(config, dict):
        return arch, num_classes

    for key in ("architecture", "arch", "model_name", "model_type"):
        value = config.get(key)
        if isinstance(value, str) and value:
            arch = value
            break
    else:
        architectures = config.get("architectures")
        if isinstance(architectures, list) and architectures:
            first = architectures[0]
            if isinstance(first, str) and first:
                arch = first

    labels = config.get("num_labels") or config.get("num_classes")
    if isinstance(labels, int) and labels > 0:
        num_classes = labels
    elif isinstance(config.get("id2label"), dict):
        num_classes = len(config["id2label"])

    return arch, num_classes


def find_checkpoint(model_dir: Path) -> Checkpoint | None:
    """Locate a supported artifact under ``model_dir``, in loader order."""
    state_dict = model_dir / STATE_DICT_FILE
    if state_dict.is_file():
        return Checkpoint(
            path=state_dict,
            kind="state_dict",
            arch=_read_arch(model_dir),
            num_classes=NUM_CLASSES,
        )

    for subdir in HF_SUBDIRS:
        base = (model_dir / subdir).resolve() if subdir != "." else model_dir
        if not base.is_dir():
            continue
        for name in HF_WEIGHT_FILES:
            weights = base / name
            if not weights.is_file():
                continue
            arch, num_classes = (DEFAULT_ARCH, NUM_CLASSES)
            config = base / HF_CONFIG_FILE
            if config.is_file():
                arch, num_classes = _arch_from_hf_config(config)
            kind = "safetensors" if name.endswith(".safetensors") else "hf_pickle"
            return Checkpoint(
                path=weights, kind=kind, arch=arch, num_classes=num_classes
            )

    return None


def _normalise_state_dict(raw: Any) -> dict[str, torch.Tensor]:
    """Unwrap the usual training-checkpoint envelopes and ``module.`` prefixes."""
    state = raw
    if isinstance(state, dict):
        for key in ("state_dict", "model_state_dict", "model"):
            inner = state.get(key)
            if isinstance(inner, dict):
                state = inner
                break
    if not isinstance(state, dict):
        msg = f"checkpoint is not a state_dict (got {type(raw).__name__})"
        raise ModelUnavailable(msg)
    return {
        (key.removeprefix("module.")): value
        for key, value in state.items()
    }


def _load_tensors(checkpoint: Checkpoint) -> dict[str, torch.Tensor]:
    if checkpoint.kind == "safetensors":
        from safetensors.torch import load_file

        return dict(load_file(str(checkpoint.path), device="cpu"))

    # NEVER weights_only=False: an untrusted pickle is arbitrary code execution.
    raw = torch.load(checkpoint.path, map_location="cpu", weights_only=True)
    return _normalise_state_dict(raw)


class TorchEngine:
    """Real DR classifier over a locally staged, digest-verified checkpoint."""

    def __init__(self, settings: Any) -> None:  # frozen call site: get_engine(settings)
        self.model_loaded = False

        model_dir = Path(settings.eye_model_dir)
        self._model_version = str(settings.eye_model_version)
        self._input_size = int(getattr(settings, "engine_input_size", 224))
        self._device = resolve_device(str(getattr(settings, "eye_device", "cpu")))

        checkpoint = find_checkpoint(model_dir)
        if checkpoint is None:
            msg = (
                f"no model artifact under {model_dir} — expected {STATE_DICT_FILE} "
                f"or one of {HF_WEIGHT_FILES} (air-gapped: stage it out of band)"
            )
            raise ModelUnavailable(msg)

        expected_digest = getattr(settings, "eye_model_sha256", None)
        if expected_digest:
            actual = sha256_file(checkpoint.path)
            if actual.lower() != str(expected_digest).strip().lower():
                msg = (
                    f"EYE_MODEL_SHA256 mismatch for {checkpoint.path}: expected "
                    f"{str(expected_digest).lower()}, got {actual} — refusing to load"
                )
                raise ModelUnavailable(msg)
            logger.info("artifact digest verified: %s", checkpoint.path)
        else:
            logger.warning(
                "EYE_MODEL_SHA256 is unset — loading %s without digest verification",
                checkpoint.path,
            )

        if checkpoint.num_classes != NUM_CLASSES:
            msg = (
                f"checkpoint declares {checkpoint.num_classes} classes, "
                f"but the ICDR wire contract needs {NUM_CLASSES}"
            )
            raise ModelUnavailable(msg)

        model = timm.create_model(
            checkpoint.arch, pretrained=False, num_classes=NUM_CLASSES
        )
        model.load_state_dict(_load_tensors(checkpoint), strict=True)
        model.eval()
        model.to(device=self._device, dtype=torch.float32)

        self.model = model
        self.checkpoint = checkpoint
        self.model_loaded = True
        logger.info(
            "torch engine ready: arch=%s device=%s version=%s artifact=%s",
            checkpoint.arch,
            self._device,
            self._model_version,
            checkpoint.path,
        )

    @property
    def device(self) -> str:
        return self._device

    @property
    def model_version(self) -> str:
        return self._model_version

    def _as_model_input(self, img: np.ndarray) -> np.ndarray:
        """Accept either a normalised CHW tensor or a raw HWC RGB image.

        ``api/predict.py`` passes ``to_model_input(retina_crop(img))`` while
        tests hand engines raw pixels; the frozen mock tolerates both, so the
        torch engine must too or the two engines would not be substitutable.
        """
        arr = np.asarray(img)
        is_chw_float = (
            arr.ndim == 3
            and arr.shape[0] == 3
            and np.issubdtype(arr.dtype, np.floating)
        )
        if is_chw_float:
            return np.ascontiguousarray(arr, dtype=np.float32)
        return to_model_input(arr, self._input_size)

    def predict(self, img: np.ndarray) -> Prediction:
        if not self.model_loaded:  # pragma: no cover - construction raises first
            raise ModelUnavailable("torch engine has no loaded model")

        batch = torch.from_numpy(self._as_model_input(img)).unsqueeze(0)
        batch = batch.to(device=self._device, dtype=torch.float32)

        with torch.inference_mode():
            logits = self.model(batch)
            probs_t = torch.softmax(logits.float(), dim=1)[0]

        # MPS has no float64 and numpy() needs host memory: come back to cpu first.
        probs = probs_t.detach().to("cpu").numpy().astype(np.float64)
        if probs.shape[0] != NUM_CLASSES:  # pragma: no cover - guarded at load
            msg = f"model returned {probs.shape[0]} logits, expected {NUM_CLASSES}"
            raise ModelUnavailable(msg)

        return Prediction(
            grade=int(np.argmax(probs)),
            probs=[float(p) for p in probs],
            model_version=self._model_version,
        )
