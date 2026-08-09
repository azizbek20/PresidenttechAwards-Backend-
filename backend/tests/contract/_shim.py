"""Pre-merge stand-ins for the modules Agents A and B have not delivered yet.

WHY THIS EXISTS
---------------
Agent C owns the HTTP layer, but `api/predict.py` legitimately imports
`app.inference.{preprocess,quality,gradcam}` (Agent A) and `app.db.base` plus
the `app.db.crud` bodies (Agent B). On branch `feature/api` those files do not
exist and the frozen `crud.py` raises `NotImplementedError`, so without a shim
`import app.main` fails outright and NOTHING in this suite can run.

Per the brief, the shim lives ONLY in `tests/`. `app/` imports the real module
paths and gains the real implementations at merge.

HOW IT WORKS, AND WHY NOT `monkeypatch`
---------------------------------------
The frozen `tests/conftest.py` purges every `app.*` entry from `sys.modules`
and re-imports the tree for each test, so anything injected into `sys.modules`
(or patched onto a module object) before the client fixture is discarded. A
`sys.meta_path` finder survives that, because it is consulted on every fresh
import.

SELF-DISABLING
--------------
Each stub installs only when the real source file is absent from the worktree.
After the Phase 2 merge `app/inference/quality.py` and `app/db/base.py` exist,
every builder drops out, and this module becomes inert — it does not need to be
deleted, and it cannot mask a real implementation.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import importlib.util
import io
import sys
import types
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

APP_DIR = Path(__file__).resolve().parents[2] / "app"

#: Presence probes: one representative file per agent's delivery.
AGENT_A_PRESENT = (APP_DIR / "inference" / "quality.py").exists()
AGENT_B_PRESENT = (APP_DIR / "db" / "base.py").exists()

#: The blur convention pinned by `tests/test_frozen_kit.py` (grayscale at 512).
BLUR_SIZE = 512


# ==========================================================================
# Agent A stand-ins
# ==========================================================================
def _build_preprocess(module: types.ModuleType) -> None:
    from PIL import Image, ImageOps

    def load_rgb(raw: bytes) -> np.ndarray | None:
        try:
            with Image.open(io.BytesIO(raw)) as im:
                im = ImageOps.exif_transpose(im)
                return np.asarray(im.convert("RGB"), dtype=np.uint8)
        except Exception:  # noqa: BLE001 - `None` IS the failure contract
            return None

    def retina_crop(img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        ys, xs = np.where(gray >= 10)
        if ys.size == 0:
            return img
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        crop = img[y0:y1, x0:x1]
        h, w = crop.shape[:2]
        side = min(h, w)
        top = (h - side) // 2
        left = (w - side) // 2
        return crop[top : top + side, left : left + side]

    def to_model_input(img: np.ndarray, size: int) -> np.ndarray:
        from app.inference.engine import IMAGENET_MEAN, IMAGENET_STD

        resized = cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)
        chw = resized.astype(np.float32).transpose(2, 0, 1) / 255.0
        mean = np.asarray(IMAGENET_MEAN, dtype=np.float32).reshape(3, 1, 1)
        std = np.asarray(IMAGENET_STD, dtype=np.float32).reshape(3, 1, 1)
        return (chw - mean) / std

    def display_copy(img: np.ndarray) -> np.ndarray:
        return cv2.resize(img, (512, 512), interpolation=cv2.INTER_AREA).astype(
            np.uint8
        )

    module.load_rgb = load_rgb
    module.retina_crop = retina_crop
    module.to_model_input = to_model_input
    module.display_copy = display_copy


def _build_quality(module: types.ModuleType) -> None:
    from app.inference.mock_engine import mean_gray as _mean_gray

    @dataclass(frozen=True)
    class QualityReport:
        ok: bool
        quality: str
        blur_var: float
        mean_gray: float

    def assess(img_rgb: np.ndarray, settings: Any) -> QualityReport:
        small = cv2.resize(img_rgb, (BLUR_SIZE, BLUR_SIZE), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
        blur_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        mean = float(_mean_gray(img_rgb))
        h, w = img_rgb.shape[:2]
        ok = (
            blur_var >= settings.quality_blur_min_var
            and 20.0 <= mean <= 235.0
            and min(h, w) >= 300
        )
        return QualityReport(
            ok=ok, quality="good" if ok else "poor", blur_var=blur_var, mean_gray=mean
        )

    module.QualityReport = QualityReport
    module.assess = assess


def _build_gradcam(module: types.ModuleType) -> None:
    def render_heatmap(
        model: Any, input_tensor: Any, display_rgb: np.ndarray, out_path: Path
    ) -> bool:
        # No torch model exists pre-merge; the real renderer is Agent A's.
        return False

    def mock_heatmap(display_rgb: np.ndarray, out_path: Path) -> bool:
        try:
            h, w = display_rgb.shape[:2]
            yy, xx = np.ogrid[:h, :w]
            cy, cx = (h - 1) / 2.0, (w - 1) / 2.0
            dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
            heat = np.clip(1.0 - dist / (max(h, w) / 2.0), 0.0, 1.0)
            colour = cv2.applyColorMap((heat * 255).astype(np.uint8), cv2.COLORMAP_JET)
            base = cv2.cvtColor(display_rgb, cv2.COLOR_RGB2BGR)
            blended = cv2.addWeighted(base, 0.6, colour, 0.4, 0.0)
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            return bool(cv2.imwrite(str(out_path), blended))
        except Exception:  # noqa: BLE001 - `False` IS the failure contract
            return False

    module.render_heatmap = render_heatmap
    module.mock_heatmap = mock_heatmap


# ==========================================================================
# Agent B stand-ins
# ==========================================================================
class _FakeSession:
    """Just enough surface for the API layer and the readiness probe."""

    def execute(self, *args: Any, **kwargs: Any) -> Any:
        return None

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


def _build_db_base(module: types.ModuleType) -> None:
    @contextmanager
    def get_session() -> Iterator[_FakeSession]:
        yield _FakeSession()

    def init_db() -> None:
        return None

    module.get_session = get_session
    module.init_db = init_db


def _build_crud(module: types.ModuleType) -> None:
    """Load the FROZEN crud source, then fill only the unimplemented bodies.

    Executing the real file first means `generate_patient_code` keeps its
    frozen body and any signature drift in `crud.py` still shows up here
    instead of being masked by a hand-written copy.
    """
    source_path = APP_DIR / "db" / "crud.py"
    module.__file__ = str(source_path)
    code = compile(source_path.read_text(encoding="utf-8"), str(source_path), "exec")
    exec(code, module.__dict__)  # noqa: S102 - loading our own frozen source
    _install_in_memory_crud(module)


def _install_in_memory_crud(module: types.ModuleType) -> None:
    from app.config import get_settings
    from app.schemas import DISCLAIMER

    # One store per module instance. The frozen conftest re-imports `app.*`
    # per test, so every test gets an empty database for free.
    rows: list[dict[str, Any]] = []
    patients: set[str] = set()

    def _wire_row(
        *,
        exam_id: str,
        patient_code: str | None,
        eye: str | None,
        image_path: str,
        quality: str,
        result: Any,
        model_version: str,
        heatmap_path: str | None,
        processed_at: datetime,
    ) -> dict[str, Any]:
        # C3: the DB keeps NULLs, the wire keeps the non-null placeholders.
        return {
            "exam_id": exam_id,
            "patient_id": patient_code,
            "eye": eye,
            "referable": result.referable,
            "probability": 0.0 if result.db_probability is None else result.db_probability,
            "icdr_grade": 0 if result.db_icdr_grade is None else result.db_icdr_grade,
            "grade_label": result.grade_label,
            "decision": result.decision,
            "decision_text": result.decision_text,
            "quality": quality,
            "heatmap_url": heatmap_path,
            "image_url": image_path,
            "model_version": model_version,
            "processed_at": processed_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "disclaimer": DISCLAIMER,
            "request_id": str(uuid.uuid4()),
            "mode": get_settings().eye_mode,
        }

    def get_or_create_patient(session: Any, patient_code: str) -> Any:
        patients.add(patient_code)
        return patient_code

    def create_exam_with_result(
        session: Any,
        *,
        exam_id: str,
        patient_code: str | None,
        eye: str | None,
        image_path: str,
        content_sha256: str,
        quality: str,
        blur_var: float | None,
        mean_gray: float | None,
        result: Any,
        model_version: str,
        heatmap_path: str | None,
        processed_at: datetime,
        idempotency_key: str | None = None,
    ) -> None:
        if patient_code:
            patients.add(patient_code)
        rows.append(
            {
                "wire": _wire_row(
                    exam_id=exam_id,
                    patient_code=patient_code,
                    eye=eye,
                    image_path=image_path,
                    quality=quality,
                    result=result,
                    model_version=model_version,
                    heatmap_path=heatmap_path,
                    processed_at=processed_at,
                ),
                "sha": content_sha256,
                "patient": patient_code,
                "eye": eye,
                "at": processed_at,
                "key": idempotency_key,
                "blur_var": blur_var,
                "mean_gray": mean_gray,
                "db_probability": result.db_probability,
                "db_icdr_grade": result.db_icdr_grade,
            }
        )

    def _fresh(row: dict[str, Any], window_min: int) -> bool:
        at = row["at"]
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        age_s = (datetime.now(timezone.utc) - at).total_seconds()
        return age_s <= window_min * 60

    def find_recent_duplicate(
        session: Any,
        *,
        content_sha256: str,
        patient_code: str | None,
        eye: str | None,
        window_min: int,
    ) -> dict[str, Any] | None:
        """`patient_code=None` means UNCONSTRAINED, not `patient_code IS NULL`.

        Pinned by Agent B. C2 gives every blank-patient_id upload a fresh
        `P-XXXXXX`, so no stored row ever has a NULL patient code — matching on
        NULL would never hit and every ID-less retry would create exactly the
        duplicate exam C14 exists to prevent. For a header-less, ID-less client
        the dedup key is therefore (fingerprint, eye).
        """
        for row in reversed(rows):
            if row["sha"] != content_sha256 or row["eye"] != eye:
                continue
            if patient_code is not None and row["patient"] != patient_code:
                continue
            if _fresh(row, window_min):
                return dict(row["wire"])
        return None

    def find_by_idempotency_key(
        session: Any, *, idempotency_key: str, window_min: int
    ) -> tuple[dict[str, Any], str] | None:
        for row in reversed(rows):
            if row["key"] == idempotency_key and _fresh(row, window_min):
                return dict(row["wire"]), str(row["sha"])
        return None

    def list_exams(
        session: Any,
        limit: int = 50,
        offset: int = 0,
        patient_code: str | None = None,
    ) -> list[dict[str, Any]]:
        selected = [
            dict(r["wire"])
            for r in reversed(rows)
            if patient_code is None or r["patient"] == patient_code
        ]
        return selected[offset : offset + limit]

    def get_exam(session: Any, exam_id: str) -> dict[str, Any] | None:
        for row in reversed(rows):
            if row["wire"]["exam_id"] == exam_id:
                return dict(row["wire"])
        return None

    module.get_or_create_patient = get_or_create_patient
    module.create_exam_with_result = create_exam_with_result
    module.find_recent_duplicate = find_recent_duplicate
    module.find_by_idempotency_key = find_by_idempotency_key
    module.list_exams = list_exams
    module.get_exam = get_exam
    # Test-only handles: the raw store, so a test can count rows.
    module._rows = rows
    module._patients = patients


# ==========================================================================
# meta_path plumbing
# ==========================================================================
_BUILDERS: dict[str, Callable[[types.ModuleType], None]] = {}

if not AGENT_A_PRESENT:
    _BUILDERS["app.inference.preprocess"] = _build_preprocess
    _BUILDERS["app.inference.quality"] = _build_quality
    _BUILDERS["app.inference.gradcam"] = _build_gradcam

if not AGENT_B_PRESENT:
    _BUILDERS["app.db.base"] = _build_db_base
    _BUILDERS["app.db.crud"] = _build_crud


class _StubLoader(importlib.abc.Loader):
    def __init__(self, builder: Callable[[types.ModuleType], None]) -> None:
        self._builder = builder

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        return None

    def exec_module(self, module: types.ModuleType) -> None:
        self._builder(module)


class _StubFinder(importlib.abc.MetaPathFinder):
    def find_spec(
        self, fullname: str, path: Any = None, target: Any = None
    ) -> importlib.machinery.ModuleSpec | None:
        builder = _BUILDERS.get(fullname)
        if builder is None:
            return None
        return importlib.util.spec_from_loader(fullname, _StubLoader(builder))


_FINDER = _StubFinder()


def install() -> None:
    """Idempotently put the finder in front of the normal import machinery.

    It must be first: `app.db.crud` exists on disk with unimplemented bodies,
    so only a meta_path entry ahead of `PathFinder` can supply working ones.
    """
    if not _BUILDERS:
        return
    if not any(isinstance(f, _StubFinder) for f in sys.meta_path):
        sys.meta_path.insert(0, _FINDER)


def stubbed_modules() -> tuple[str, ...]:
    """Which imports this shim is currently answering (empty after merge)."""
    return tuple(sorted(_BUILDERS))
