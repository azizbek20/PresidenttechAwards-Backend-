"""Score a DR checkpoint through the *backend's own* inference path.

Runs ``load_rgb -> quality.assess -> retina_crop -> to_model_input -> TorchEngine.predict ->
decision.decide`` (exactly what ``POST /api/v1/predict`` does, shadow mode,
SHA-256 verified) on the IDRiD official test split. These are the numbers the
phone actually gets; ``train_dr.py``'s own metrics use flip-TTA and differ slightly.

Run with the *backend* venv:

    backend/venv/Scripts/python training/eval_backend_dr.py \
        --model-dir backend/models --idrid D:/EYE_Detect_Backend_run/data/idrid/test.parquet
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq
from sklearn.metrics import cohen_kappa_score, roc_auc_score

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", type=Path, required=True)
    ap.add_argument("--idrid", type=Path, required=True)
    ap.add_argument("--blur-min-var", type=float, default=None,
                    help="QUALITY_BLUR_MIN_VAR to apply (default: the config default)")
    args = ap.parse_args()
    if args.blur_min_var is not None:
        os.environ["QUALITY_BLUR_MIN_VAR"] = str(args.blur_min_var)

    sha = hashlib.sha256((args.model_dir / "model.pt").read_bytes()).hexdigest()
    os.environ.update(
        EYE_MODE="shadow", EYE_MODEL_SOURCE="torch", EYE_MODEL_DIR=str(args.model_dir),
        EYE_MODEL_SHA256=sha, EYE_MODEL_VERSION="eval", EYE_API_KEY="eval",
    )
    from app.config import get_settings
    from app.inference import preprocess as P
    from app.inference.decision import decide
    from app.inference.engine import get_engine
    from app.inference.quality import assess

    settings = get_settings()
    engine = get_engine(settings)
    if not hasattr(engine, "model_version") or type(engine).__name__ != "TorchEngine":
        raise SystemExit(f"model did not load: {engine!r}")

    df = pq.read_table(args.idrid).to_pandas()
    y, grade, p_ref, refer, ungradable = [], [], [], [], 0
    for _, row in df.iterrows():
        img = P.load_rgb(row["image"]["bytes"])
        if not assess(img, settings).ok:  # same gate, same order as the API
            ungradable += 1
            continue
        pred = engine.predict(P.to_model_input(P.retina_crop(img), settings.engine_input_size))
        d = decide(pred, True, settings.referable_threshold)
        y.append(int(row["label"]))
        grade.append(d.icdr_grade)
        p_ref.append(d.probability)
        refer.append(d.referable)
    y_a, ref_true, ref_pred = np.array(y), np.array(y) >= 2, np.array(refer)
    out = {
        "n_images": len(df),
        "ungradable": ungradable,
        "quality_blur_min_var": settings.quality_blur_min_var,
        "n_scored": len(y),
        "sha256": sha,
        "qwk": float(cohen_kappa_score(y_a, grade, weights="quadratic")),
        "referable_auc": float(roc_auc_score(ref_true, p_ref)),
        "referable_sensitivity": float((ref_pred & ref_true).sum() / ref_true.sum()),
        "referable_specificity": float((~ref_pred & ~ref_true).sum() / (~ref_true).sum()),
        "threshold": settings.referable_threshold,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
