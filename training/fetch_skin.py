"""Download a licence-clean skin-lesion dataset from the ISIC Archive API.

Only images whose per-image ``copyright_license`` is **CC-0 or CC-BY** are
used (SPEC C1: no CC-BY-NC artefacts — which rules out HAM10000 / ISIC 2018-20).
Every CC-BY image's attribution is kept in ``manifest.csv`` so it can be
credited.

Classes (index order == ``app/analysis/catalog.py`` skin conditions):

    0 nevus             Nevus
    1 benign_keratosis  Seborrheic keratosis, solar lentigo, LPLK, lentigo NOS,
                        pigmented benign keratosis
    2 actinic_keratosis Solar or actinic keratosis
    3 carcinoma         Basal cell carcinoma, squamous cell carcinoma (all), keratoacanthoma
    4 melanoma          Melanoma NOS / in situ / invasive

Dermoscopic *and* clinical (ordinary camera) images are fetched; dermoscopic
nevi are capped because they would otherwise swamp everything else.

    python training/fetch_skin.py --out D:/EYE_Detect_Backend_run/data/skin
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

API = "https://api.isic-archive.com/api/v2/images/search/"
LICENCE = "(copyright_license:CC-0 OR copyright_license:CC-BY)"

CLASSES: dict[str, list[str]] = {
    "nevus": ["Nevus"],
    "benign_keratosis": [
        "Seborrheic keratosis", "Solar lentigo", "Lichen planus like keratosis",
        "Lentigo NOS", "Pigmented benign keratosis",
    ],
    "actinic_keratosis": ["Solar or actinic keratosis"],
    "carcinoma": [
        "Basal cell carcinoma", "Squamous cell carcinoma, NOS",
        "Squamous cell carcinoma in situ", "Squamous cell carcinoma, Invasive",
        "Keratoacanthoma",
    ],
    "melanoma": ["Melanoma, NOS", "Melanoma in situ", "Melanoma Invasive"],
}
#: Max dermoscopic images per class (clinical images are always all taken).
DERMOSCOPIC_CAP = {"nevus": 3500}
DEFAULT_CAP = 4000


def get_json(url: str) -> dict:
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)
        except Exception:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed: {url}")


def search(query: str, cap: int | None) -> list[dict]:
    url = API + "?" + urllib.parse.urlencode({"query": query, "limit": 100})
    rows: list[dict] = []
    while url and (cap is None or len(rows) < cap):
        page = get_json(url)
        rows.extend(page["results"])
        url = page.get("next")
    return rows if cap is None else rows[:cap]


def download(job: tuple[str, Path]) -> bool:
    url, path = job
    if path.exists():
        return True
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                path.write_bytes(r.read())
            return True
        except Exception:
            time.sleep(1 + attempt)
    return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    img_dir = args.out / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    listing = args.out / "listing.json"
    records: dict[str, dict] = (
        json.loads(listing.read_text(encoding="utf-8")) if listing.exists() else {}
    )
    for idx, (name, dxs) in enumerate(CLASSES.items() if not records else ()):
        dx_q = " OR ".join(f'diagnosis_3:"{d}"' for d in dxs)
        for kind, cap in (
            ("dermoscopic", DERMOSCOPIC_CAP.get(name, DEFAULT_CAP)),
            ('"clinical: close-up"', None),
            ('"clinical: overview"', None),
        ):
            rows = search(f"{LICENCE} AND image_type:{kind} AND ({dx_q})", cap)
            for r in rows:
                meta = r.get("metadata", {})
                clin = meta.get("clinical", {})
                lic = r.get("copyright_license")
                if lic not in ("CC-0", "CC-BY"):  # belt and braces
                    continue
                records[r["isic_id"]] = {
                    "isic_id": r["isic_id"],
                    "label": idx,
                    "class": name,
                    "diagnosis_3": clin.get("diagnosis_3", ""),
                    "image_type": meta.get("acquisition", {}).get("image_type", ""),
                    "lesion_id": clin.get("lesion_id") or r["isic_id"],
                    "patient_id": clin.get("patient_id") or "",
                    "license": lic,
                    "attribution": r.get("attribution", ""),
                    "url": r["files"]["thumbnail_256"]["url"],
                }
            print(f"{name:18s} {kind:24s} {len(rows)}", flush=True)

    # Cache the (slow, ~6 s/page) listing so an interrupted run resumes at the downloads.
    listing.write_text(json.dumps(records), encoding="utf-8")
    jobs = [(rec["url"], img_dir / f"{rec['isic_id']}.jpg") for rec in records.values()]
    with ThreadPoolExecutor(16) as pool:
        ok = []
        for i, good in enumerate(pool.map(download, jobs), 1):
            ok.append(good)
            if i % 1000 == 0:
                print(f"downloaded {i}/{len(jobs)}", flush=True)
    kept = [rec for rec, good in zip(records.values(), ok) if good]

    with (args.out / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(kept[0]))
        w.writeheader()
        w.writerows(kept)
    counts: dict[str, int] = {}
    for rec in kept:
        counts[rec["class"]] = counts.get(rec["class"], 0) + 1
    print("downloaded", len(kept), "of", len(records), counts)


if __name__ == "__main__":
    main()
