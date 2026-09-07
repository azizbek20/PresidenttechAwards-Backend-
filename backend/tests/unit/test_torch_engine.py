"""Unit tests for `app.inference.torch_engine` (spec §5-A A5).

TWO CLASSES OF TEST, DELIBERATELY SEPARATED
-------------------------------------------
* **Unmarked** — the refusal paths (missing artifact, digest mismatch, no
  `weights_only=False`) and device resolution. These need neither a checkpoint
  nor labeled data, so they run in the default gate where they are useful.
* **`@pytest.mark.model`** — anything that must actually load a checkpoint or
  read a labeled sample. These SKIP with a stated reason when the artifact or
  the samples are absent, per §5-A: "If real labeled samples are unavailable,
  the grade test is skipped with a stated reason, not faked."

`tests/fixtures/aptos_samples/` is INTENTIONALLY ABSENT in this branch: no
lawfully-sourced, labeled APTOS images were available and nothing may be
downloaded (air-gapped rule, C1 licensing). Synthetic images are therefore
never used for a grade assertion here — only for execution-path coverage
elsewhere. Drop `no_dr.jpg`, `moderate.jpg` and `severe.jpg` into that
directory and the marked tests activate with no code change.
"""

from __future__ import annotations

import ast
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from app.inference import torch_engine
from app.inference.engine import ModelUnavailable, UnavailableEngine, get_engine
from app.inference.torch_engine import (
    NUM_CLASSES,
    TorchEngine,
    find_checkpoint,
    resolve_device,
    sha256_file,
)

TORCH_ENGINE_SOURCE = Path(torch_engine.__file__)
SAMPLES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "aptos_samples"
SAMPLE_FILES = ("no_dr.jpg", "moderate.jpg", "severe.jpg")

#: §5-A: grade >= 2 is "referable" territory for the severe sample.
REFERABLE_GRADE = 2


@dataclass(frozen=True)
class StubSettings:
    """Structural stand-in for `app.config.Settings` (frozen; read-only here)."""

    eye_model_dir: Path
    eye_model_sha256: str | None = None
    eye_model_version: str = "test-v0"
    eye_device: str = "cpu"
    engine_input_size: int = 224
    eye_model_source: str = "torch"
    eye_mode: str = "demo"


def _checkpoint_dir() -> Path | None:
    """The configured model dir, if it actually holds a supported artifact."""
    import os

    candidate = Path(os.environ.get("EYE_MODEL_DIR", "./models"))
    return candidate if find_checkpoint(candidate) is not None else None


def _samples_present() -> bool:
    return all((SAMPLES_DIR / name).is_file() for name in SAMPLE_FILES)


needs_checkpoint = pytest.mark.skipif(
    _checkpoint_dir() is None,
    reason=(
        "no licensed model artifact under EYE_MODEL_DIR (default ./models); "
        "model delivery is out-of-band and air-gapped (C1) — stage model.pt or "
        "an MIT-licensed safetensors snapshot to enable this test"
    ),
)
needs_real_samples = pytest.mark.skipif(
    not _samples_present(),
    reason=(
        f"no real labeled fundus samples in {SAMPLES_DIR} "
        f"({', '.join(SAMPLE_FILES)}); grade assertions require lawfully-sourced "
        "labeled data and are never faked with synthetic images (§5-A)"
    ),
)


# ---------------------------------------------------------------------------
# refusal paths — no checkpoint needed, so these run in the default gate
# ---------------------------------------------------------------------------
def test_missing_artifact_raises_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(ModelUnavailable, match="no model artifact"):
        TorchEngine(StubSettings(eye_model_dir=tmp_path))


def test_get_engine_wraps_a_missing_artifact(tmp_path: Path) -> None:
    """Frozen contract: a missing checkpoint is 503, never a mock substitution."""
    engine = get_engine(StubSettings(eye_model_dir=tmp_path))

    assert isinstance(engine, UnavailableEngine)
    assert engine.model_loaded is False
    with pytest.raises(ModelUnavailable):
        engine.predict(np.zeros((8, 8, 3), dtype=np.uint8))


def test_digest_mismatch_refuses_to_load(tmp_path: Path) -> None:
    """The digest is checked BEFORE the loader opens the file (C1)."""
    (tmp_path / "model.pt").write_bytes(b"not really a checkpoint")

    settings = StubSettings(eye_model_dir=tmp_path, eye_model_sha256="00" * 32)
    with pytest.raises(ModelUnavailable, match="SHA256 mismatch"):
        TorchEngine(settings)

    engine = get_engine(settings)
    assert engine.model_loaded is False


def test_digest_mismatch_is_detected_before_any_torch_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "model.pt").write_bytes(b"payload")

    def explode(*_args: object, **_kwargs: object) -> None:
        pytest.fail("torch.load must not run on a digest-mismatched artifact")

    monkeypatch.setattr("app.inference.torch_engine.torch.load", explode)
    with pytest.raises(ModelUnavailable, match="SHA256 mismatch"):
        TorchEngine(StubSettings(eye_model_dir=tmp_path, eye_model_sha256="ab" * 32))


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    payload = b"eye-detect-ai artifact bytes" * 1000
    artifact = tmp_path / "model.pt"
    artifact.write_bytes(payload)

    assert sha256_file(artifact) == hashlib.sha256(payload).hexdigest()


def test_torch_load_is_never_called_with_weights_only_false() -> None:
    """Safety regression (C1/§7): a pickled checkpoint is arbitrary code exec.

    Asserted over the parsed AST rather than the raw text, so the module may
    still *document* the rule it enforces.
    """
    tree = ast.parse(TORCH_ENGINE_SOURCE.read_text(encoding="utf-8"))

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "load"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "torch"
    ]
    assert calls, "expected at least one torch.load call to inspect"
    for call in calls:
        keywords = {kw.arg: kw.value for kw in call.keywords}
        weights_only = keywords.get("weights_only")
        assert isinstance(weights_only, ast.Constant), "weights_only must be passed"
        assert weights_only.value is True, ast.dump(call)


def test_module_performs_no_network_access_at_import() -> None:
    """Air-gapped: weights come from EYE_MODEL_DIR, never from a download."""
    source = TORCH_ENGINE_SOURCE.read_text(encoding="utf-8")

    forbidden_calls = (
        "hf_hub_download",
        "snapshot_download",
        "from_pretrained",
        "requests.",
    )
    for forbidden in forbidden_calls:
        assert forbidden not in source, forbidden
    assert "pretrained=False" in source


# ---------------------------------------------------------------------------
# checkpoint discovery
# ---------------------------------------------------------------------------
def test_find_checkpoint_returns_none_for_an_empty_dir(tmp_path: Path) -> None:
    assert find_checkpoint(tmp_path) is None
    assert find_checkpoint(tmp_path / "does-not-exist") is None


def test_find_checkpoint_prefers_the_state_dict_layout(tmp_path: Path) -> None:
    (tmp_path / "model.pt").write_bytes(b"x")
    (tmp_path / "model.safetensors").write_bytes(b"y")

    found = find_checkpoint(tmp_path)

    assert found is not None
    assert found.path.name == "model.pt"
    assert found.kind == "state_dict"
    assert found.arch == "efficientnet_b0"
    assert found.num_classes == NUM_CLASSES


def test_find_checkpoint_reads_arch_txt(tmp_path: Path) -> None:
    (tmp_path / "model.pt").write_bytes(b"x")
    (tmp_path / "arch.txt").write_text("resnet18\n", encoding="utf-8")

    found = find_checkpoint(tmp_path)

    assert found is not None
    assert found.arch == "resnet18"


def test_find_checkpoint_prefers_safetensors_over_pickle(tmp_path: Path) -> None:
    """No pickle at all when a safetensors artifact is available."""
    (tmp_path / "pytorch_model.bin").write_bytes(b"x")
    (tmp_path / "model.safetensors").write_bytes(b"y")

    found = find_checkpoint(tmp_path)

    assert found is not None
    assert found.kind == "safetensors"


def test_find_checkpoint_accepts_a_local_hf_snapshot_subdir(tmp_path: Path) -> None:
    """The MIT `jdelgado2002/diabetic_retinopathy_detection` layout (C1)."""
    snapshot = tmp_path / "diabetic_retinopathy_detection"
    snapshot.mkdir()
    (snapshot / "model.safetensors").write_bytes(b"y")
    (snapshot / "config.json").write_text(
        '{"architecture": "efficientnet_b0", "num_labels": 5}', encoding="utf-8"
    )

    found = find_checkpoint(tmp_path)

    assert found is not None
    assert found.path == snapshot / "model.safetensors"
    assert found.arch == "efficientnet_b0"
    assert found.num_classes == 5


def test_a_checkpoint_with_the_wrong_class_count_is_refused(tmp_path: Path) -> None:
    (tmp_path / "model.safetensors").write_bytes(b"y")
    (tmp_path / "config.json").write_text('{"num_labels": 3}', encoding="utf-8")

    with pytest.raises(ModelUnavailable, match="classes"):
        TorchEngine(StubSettings(eye_model_dir=tmp_path))


# ---------------------------------------------------------------------------
# per-checkpoint normalisation (a timm HF export's own pretrained_cfg mean/std)
# ---------------------------------------------------------------------------
def test_find_checkpoint_defaults_to_imagenet_normalisation_when_absent(tmp_path: Path) -> None:
    (tmp_path / "model.pt").write_bytes(b"x")

    found = find_checkpoint(tmp_path)

    assert found is not None
    assert found.mean == torch_engine.IMAGENET_MEAN
    assert found.std == torch_engine.IMAGENET_STD


def test_find_checkpoint_reads_normalisation_from_nested_pretrained_cfg(tmp_path: Path) -> None:
    """The layout an actual timm HF export uses (e.g. a ViT snapshot)."""
    (tmp_path / "model.safetensors").write_bytes(b"y")
    (tmp_path / "config.json").write_text(
        '{"architecture": "vit_large_patch16_224", "num_classes": 5, '
        '"pretrained_cfg": {"mean": [0.5, 0.5, 0.5], "std": [0.5, 0.5, 0.5]}}',
        encoding="utf-8",
    )

    found = find_checkpoint(tmp_path)

    assert found is not None
    assert found.mean == (0.5, 0.5, 0.5)
    assert found.std == (0.5, 0.5, 0.5)


def test_find_checkpoint_reads_a_top_level_mean_std_too(tmp_path: Path) -> None:
    (tmp_path / "model.safetensors").write_bytes(b"y")
    (tmp_path / "config.json").write_text(
        '{"num_classes": 5, "mean": [0.4, 0.4, 0.4], "std": [0.2, 0.2, 0.2]}',
        encoding="utf-8",
    )

    found = find_checkpoint(tmp_path)

    assert found is not None
    assert found.mean == (0.4, 0.4, 0.4)
    assert found.std == (0.2, 0.2, 0.2)


def test_find_checkpoint_ignores_a_malformed_mean_std(tmp_path: Path) -> None:
    """Wrong length / non-numeric — falls back to IMAGENET rather than raising."""
    (tmp_path / "model.safetensors").write_bytes(b"y")
    (tmp_path / "config.json").write_text(
        '{"num_classes": 5, "mean": [0.5, 0.5], "std": "not-a-list"}', encoding="utf-8"
    )

    found = find_checkpoint(tmp_path)

    assert found is not None
    assert found.mean == torch_engine.IMAGENET_MEAN
    assert found.std == torch_engine.IMAGENET_STD


def _bare_engine(mean: tuple[float, float, float], std: tuple[float, float, float]) -> TorchEngine:
    """A `TorchEngine` with `_mean`/`_std` set directly, bypassing `__init__`
    (which needs a real checkpoint) — this only exercises `_renormalise`'s math."""
    engine = TorchEngine.__new__(TorchEngine)
    engine._mean = mean
    engine._std = std
    return engine


def test_renormalise_is_a_no_op_for_imagenet_stats() -> None:
    engine = _bare_engine(torch_engine.IMAGENET_MEAN, torch_engine.IMAGENET_STD)
    chw = np.random.default_rng(0).standard_normal((3, 4, 4)).astype(np.float32)

    assert engine._renormalise(chw) is chw  # identity, not just equal


def test_renormalise_converts_between_normalisation_schemes() -> None:
    """A known 0..1 pixel value, expressed in IMAGENET space, must come back out
    correctly re-expressed in the checkpoint's own (0.5, 0.5, 0.5)/(0.5, 0.5, 0.5)
    space — i.e. `_renormalise` genuinely inverts-then-reapplies, not just scales."""
    engine = _bare_engine((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))

    pixel01 = 0.7  # arbitrary, non-special 0..1 pixel value, same on all 3 channels
    imagenet_mean = np.asarray(torch_engine.IMAGENET_MEAN, dtype=np.float32).reshape(3, 1, 1)
    imagenet_std = np.asarray(torch_engine.IMAGENET_STD, dtype=np.float32).reshape(3, 1, 1)
    imagenet_normalised = (pixel01 - imagenet_mean) / imagenet_std

    out = engine._renormalise(imagenet_normalised)

    # (0.7 - 0.5) / 0.5 == 0.4, uniformly across channels regardless of IMAGENET's
    # per-channel mean/std — proving the pixel01 round-trip actually happened.
    assert out.shape == (3, 1, 1)
    assert out == pytest.approx(0.4, abs=1e-5)


# ---------------------------------------------------------------------------
# device policy (orchestrator addendum) — always cpu in the gate
# ---------------------------------------------------------------------------
def test_cpu_is_honoured_verbatim() -> None:
    assert resolve_device("cpu") == "cpu"


def test_mps_falls_back_to_cpu_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(
        "app.inference.torch_engine.torch.backends.mps.is_available", lambda: False
    )

    with caplog.at_level(logging.WARNING, logger="eyedetect.torch_engine"):
        assert resolve_device("mps") == "cpu"

    assert "MPS is unavailable" in caplog.text


def test_auto_picks_cpu_without_mps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.inference.torch_engine.torch.backends.mps.is_available", lambda: False
    )

    assert resolve_device("auto") == "cpu"


def test_auto_and_mps_pick_mps_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.inference.torch_engine.torch.backends.mps.is_available", lambda: True
    )

    assert resolve_device("auto") == "mps"
    assert resolve_device("mps") == "mps"


def test_an_unknown_device_degrades_to_cpu(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="eyedetect.torch_engine"):
        assert resolve_device("cuda") == "cpu"

    assert "unknown EYE_DEVICE" in caplog.text


# ---------------------------------------------------------------------------
# real checkpoint / real labeled data — skipped, never faked
# ---------------------------------------------------------------------------
@pytest.mark.model
@needs_checkpoint
def test_engine_loads_and_predicts_a_distribution() -> None:
    model_dir = _checkpoint_dir()
    assert model_dir is not None

    engine = TorchEngine(StubSettings(eye_model_dir=model_dir))
    assert engine.model_loaded is True
    assert engine.device == "cpu", "gates must never depend on MPS"

    from app.inference.preprocess import load_rgb, retina_crop, to_model_input

    raw = (SAMPLES_DIR / "no_dr.jpg").read_bytes() if _samples_present() else None
    img = (
        load_rgb(raw)
        if raw is not None
        else np.full((512, 512, 3), 130, dtype=np.uint8)  # execution path only
    )
    assert img is not None

    pred = engine.predict(to_model_input(retina_crop(img), 224))

    assert len(pred["probs"]) == NUM_CLASSES
    assert sum(pred["probs"]) == pytest.approx(1.0, abs=1e-5)
    assert 0 <= pred["grade"] <= 4
    assert pred["model_version"] == "test-v0"


@pytest.mark.model
@needs_checkpoint
def test_engine_is_deterministic() -> None:
    model_dir = _checkpoint_dir()
    assert model_dir is not None

    engine = TorchEngine(StubSettings(eye_model_dir=model_dir))
    img = np.full((512, 512, 3), 130, dtype=np.uint8)

    assert engine.predict(img) == engine.predict(img)


@pytest.mark.model
@needs_checkpoint
@needs_real_samples
def test_severe_sample_is_graded_referable() -> None:
    """ONLY runs on real labeled data — synthetic images prove nothing here."""
    from app.inference.preprocess import load_rgb, retina_crop, to_model_input

    model_dir = _checkpoint_dir()
    assert model_dir is not None
    engine = TorchEngine(StubSettings(eye_model_dir=model_dir))

    img = load_rgb((SAMPLES_DIR / "severe.jpg").read_bytes())
    assert img is not None

    pred = engine.predict(to_model_input(retina_crop(img), 224))

    assert pred["grade"] >= REFERABLE_GRADE, pred
