"""Build the few-shot reference images for PROMPT_VERSION=v2 (reproducible).

Picks one IDRiD *training* image per ICDR grade (0..4), downsizes it and writes
``app/inference/fewshot/v2/grade<N>.jpg`` plus ``examples.json``. Only the
expert grade from IDRiD is used as the label: IDRiD has no per-lesion labels
for these images, so the examples never state lesions we cannot verify.

The eval runs on the IDRiD *test* split, so these images never appear there;
the script also refuses an image whose pixels match any test image.

    python scripts/build_fewshot.py --idrid-dir ../../data/idrid

IDRiD (c) Porwal, Pachade, Kokare, CC BY 4.0.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path

import pyarrow.parquet as pq
from PIL import Image

OUT_DIR = Path(__file__).resolve().parents[1] / "app/inference/fewshot/v2"
LONG_SIDE = 1024
JPEG_QUALITY = 88
#: Fixed choice (file names inside train.parquet), one per grade, so a rebuild
#: is byte-for-byte stable. Picked as the first file of each grade in the split,
#: except grade 0: IDRiD_118 (train, grade 0) is byte-identical to IDRiD_064
#: (test, grade 3), so the next grade-0 file is used.
CHOSEN = {
    0: "IDRiD_138.jpg",
    1: "IDRiD_021.jpg",
    2: "IDRiD_003.jpg",
    3: "IDRiD_001.jpg",
    4: "IDRiD_005.jpg",
}


def _pixel_hash(raw: bytes) -> str:
    with Image.open(io.BytesIO(raw)) as im:
        small = im.convert("L").resize((64, 64))
        return hashlib.sha256(small.tobytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--idrid-dir", required=True, type=Path)
    args = parser.parse_args()

    train = pq.read_table(args.idrid_dir / "train.parquet").to_pylist()
    test = pq.read_table(args.idrid_dir / "test.parquet").to_pylist()
    test_hashes = {_pixel_hash(r["image"]["bytes"]) for r in test}
    by_name = {r["image"]["path"]: r for r in train}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    examples = []
    for grade, name in sorted(CHOSEN.items()):
        row = by_name[name]
        if row["label"] != grade:
            raise SystemExit(f"{name}: label {row['label']} != {grade}")
        raw = row["image"]["bytes"]
        if _pixel_hash(raw) in test_hashes:
            raise SystemExit(f"{name} also appears in the test split")
        with Image.open(io.BytesIO(raw)) as im:
            img = im.convert("RGB")
        img.thumbnail((LONG_SIDE, LONG_SIDE), Image.Resampling.LANCZOS)
        out_name = f"grade{grade}.jpg"
        img.save(OUT_DIR / out_name, format="JPEG", quality=JPEG_QUALITY)
        examples.append({"file": out_name, "icdr_grade": grade, "source": f"IDRiD train {name}"})

    manifest = {
        "attribution": "IDRiD (c) Prasanna Porwal, Samiksha Pachade, Manesh Kokare. CC BY 4.0.",
        "label_source": "IDRiD expert ICDR grade only (no lesion labels)",
        "examples": examples,
    }
    (OUT_DIR / "examples.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(examples)} examples to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
