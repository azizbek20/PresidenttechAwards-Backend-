"""Decode APTOS 2019 / IDRiD parquet files into cached uint8 arrays.

Every image goes through the *backend's own* ``retina_crop`` and the same
``cv2.resize(..., INTER_AREA)`` that ``to_model_input`` uses, so the model is
trained on exactly the pixels the server will feed it at inference time.

    python training/prepare_dr.py --data D:/EYE_Detect_Backend_run/data

Writes ``<data>/cache/{aptos,idrid}_{x,y}.npy`` (N x 224 x 224 x 3 uint8, N int64).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
import pyarrow.parquet as pq

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))
from app.inference.preprocess import load_rgb, retina_crop  # noqa: E402

SIZE = 224


def to_pixels(raw: bytes) -> np.ndarray:
    # Same steps as the API: load_rgb (EXIF-corrected RGB) -> retina_crop on the
    # full-resolution image -> INTER_AREA to SIZE. No pre-shrinking: a resize
    # before the crop gives slightly different pixels than the server sees.
    arr = load_rgb(raw)
    if arr is None:
        raise ValueError("undecodable image")
    return cv2.resize(retina_crop(arr), (SIZE, SIZE), interpolation=cv2.INTER_AREA)


def convert(files: list[Path], label_col: str) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for f in files:
        df = pq.read_table(f).to_pandas()
        for _, row in df.iterrows():
            xs.append(to_pixels(row["image"]["bytes"]))
            ys.append(int(row[label_col]))
    return np.stack(xs).astype(np.uint8), np.asarray(ys, dtype=np.int64)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    args = ap.parse_args()
    out = args.data / "cache"
    out.mkdir(parents=True, exist_ok=True)

    jobs = {
        "aptos": ([args.data / "aptos" / "train.parquet"], "label_code"),
        "idrid": (sorted((args.data / "idrid").glob("*.parquet")), "label"),
    }
    for name, (files, col) in jobs.items():
        x, y = convert(files, col)
        np.save(out / f"{name}_x.npy", x)
        np.save(out / f"{name}_y.npy", y)
        print(name, x.shape, np.bincount(y, minlength=5).tolist())


if __name__ == "__main__":
    main()
