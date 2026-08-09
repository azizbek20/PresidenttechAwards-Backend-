#!/usr/bin/env python3
"""Operator-run, air-gapped model fetch + digest recorder (SPEC.md §3, C1).

    python scripts/download_model.py --repo <hf-repo-id> --file model.pt
    python scripts/download_model.py --verify            # digest an existing file

THIS IS NOT PART OF THE SERVING PATH. The API never downloads anything at
import or request time (§5-A A3: "no network access at import or load time").
An operator runs this ONCE on a connected machine, checks the printed SHA-256
into `EYE_MODEL_SHA256`, and carries `models/` to the deployment. That is what
"air-gapped model delivery" means here — the artifact is auditable and pinned,
not fetched by a process that also serves patients.

LICENSING GATE (C1) — decided, not negotiable
---------------------------------------------
`sakshamkr1/ResNet50-APTOS-DR` is CC-BY-NC-4.0 (non-commercial) and ships a
full pickled model. It is refused below by repo id. Acceptable inputs are a
plain **state_dict** for a timm arch, or the MIT-licensed
`jdelgado2002/diabetic_retinopathy_detection`. Nothing downloaded here is "the
production model" — nothing is, until it is locally validated against the
clinical gate.

The download is done with `huggingface_hub`; this script never calls
`torch.load(..., weights_only=False)` and never unpickles what it fetched.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL_DIR = BACKEND_ROOT / "models"
CHUNK = 1024 * 1024

#: Refused outright. Keyed by lowercase repo id (C1).
BLOCKED_REPOS: dict[str, str] = {
    "sakshamkr1/resnet50-aptos-dr": (
        "CC-BY-NC-4.0 (non-commercial) and distributed as a full pickled model. "
        "Use a plain state_dict or jdelgado2002/diabetic_retinopathy_detection (MIT)."
    ),
}

#: Extensions we are willing to place in models/. `.bin`/`.pkl` are absent on
#: purpose: a pickle is arbitrary code execution at load time.
ALLOWED_SUFFIXES = {".pt", ".pth", ".safetensors", ".txt", ".json"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def report(path: Path) -> None:
    print(f"\n  file    {path}")
    print(f"  bytes   {path.stat().st_size:,d}")
    print(f"  sha256  {sha256_file(path)}")
    print("\nRecord that digest in .env:")
    print(f"  EYE_MODEL_SHA256={sha256_file(path)}")
    print("Shadow mode refuses to load an artifact whose digest does not match.\n")


def cmd_verify(model_dir: Path, filename: str) -> int:
    target = model_dir / filename
    if not target.is_file():
        print(f"error: {target} not found", file=sys.stderr)
        return 1
    report(target)
    return 0


def cmd_download(repo: str, filename: str, model_dir: Path, revision: str | None) -> int:
    if repo.lower() in BLOCKED_REPOS:
        print(f"REFUSED: {repo}\n  {BLOCKED_REPOS[repo.lower()]}", file=sys.stderr)
        return 2

    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        print(
            f"REFUSED: {filename} has suffix '{suffix}'.\n"
            f"  Allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}. Pickled formats are "
            "rejected — loading one is arbitrary code execution.",
            file=sys.stderr,
        )
        return 2

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("error: huggingface_hub is not installed in this environment", file=sys.stderr)
        return 1

    print(f"Downloading {repo}/{filename} (revision={revision or 'main'}) …")
    print("Confirm the repo's LICENSE yourself — this script only blocks the one")
    print("known-bad artifact; it cannot audit a licence for you.\n")

    cached = Path(
        hf_hub_download(repo_id=repo, filename=filename, revision=revision)
    )

    model_dir.mkdir(parents=True, exist_ok=True)
    target = model_dir / Path(filename).name
    shutil.copyfile(cached, target)  # copy out of the HF cache: models/ is the contract
    report(target)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fetch a licence-cleared checkpoint and print its SHA-256.",
        epilog="Run on a connected machine; carry models/ to the deployment.",
    )
    parser.add_argument("--repo", help="Hugging Face repo id, e.g. owner/name")
    parser.add_argument("--file", default="model.pt", help="file within the repo (default: model.pt)")
    parser.add_argument("--revision", default=None, help="pin a commit sha or tag (recommended)")
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=DEFAULT_MODEL_DIR,
        help=f"destination (default: {DEFAULT_MODEL_DIR})",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="skip the download; just digest --file inside --model-dir",
    )
    args = parser.parse_args(argv)

    if args.verify:
        return cmd_verify(args.model_dir, args.file)
    if not args.repo:
        parser.error("--repo is required unless --verify is given")
    return cmd_download(args.repo, args.file, args.model_dir, args.revision)


if __name__ == "__main__":
    raise SystemExit(main())
