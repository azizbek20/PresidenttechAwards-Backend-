"""Fine-tune timm ``efficientnet_b0`` for 5-grade ICDR diabetic retinopathy.

Data: APTOS 2019 (train/val, stratified split) and IDRiD (CC BY 4.0) as an
untouched *external* test set. Inputs are the cached arrays written by
``prepare_dr.py`` (already retina-cropped and resized to 224 exactly as the
backend does).

Output, consumed unchanged by ``backend/app/inference/torch_engine.py``::

    <out>/model.pt      plain state_dict (load with weights_only=True)
    <out>/arch.txt      "efficientnet_b0"
    <out>/metrics.json  val + external-test metrics, SHA-256 of model.pt

The clinically relevant number is the *referable* decision the backend makes:
``p_ref = sum(probs[2:]) >= 0.5`` (app/inference/decision.py), so sensitivity,
specificity and AUC are reported for exactly that rule, next to QWK.

    python training/train_dr.py --data D:/EYE_Detect_Backend_run/data --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import numpy as np
import timm
import torch
import torch.nn.functional as F
from sklearn.metrics import accuracy_score, cohen_kappa_score, roc_auc_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset
from torchvision.transforms import v2

ARCH = "efficientnet_b0"
NUM_CLASSES = 5
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)
REFERABLE_THRESHOLD = 0.5


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


class Fundus(Dataset):
    def __init__(self, x: np.ndarray, y: np.ndarray, train: bool) -> None:
        self.x, self.y = x, y
        self.tf = (
            v2.Compose([
                v2.RandomHorizontalFlip(),
                v2.RandomVerticalFlip(),
                v2.RandomAffine(degrees=180, scale=(0.95, 1.10)),
                v2.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
            ])
            if train
            else None
        )

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, i: int) -> tuple[torch.Tensor, int]:
        img = torch.from_numpy(self.x[i]).permute(2, 0, 1)  # uint8 CHW
        if self.tf is not None:
            img = self.tf(img)
        return img, int(self.y[i])


def normalise(batch: torch.Tensor, device: str) -> torch.Tensor:
    x = batch.to(device, non_blocking=True).float() / 255.0
    return (x - MEAN.to(device)) / STD.to(device)


@torch.no_grad()
def predict(model: torch.nn.Module, x: np.ndarray, device: str, tta: bool = True) -> np.ndarray:
    model.eval()
    out = []
    for i in range(0, len(x), 64):
        b = normalise(torch.from_numpy(x[i : i + 64]).permute(0, 3, 1, 2), device)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device == "cuda"):
            p = model(b).float().softmax(1)
            if tta:  # flips are label-preserving for fundus photos
                p = p + model(b.flip(3)).float().softmax(1)
                p = p + model(b.flip(2)).float().softmax(1)
                p = p / 3
        out.append(p.cpu().numpy())
    return np.concatenate(out)


def metrics(probs: np.ndarray, y: np.ndarray) -> dict[str, float]:
    grade = probs.argmax(1)
    p_ref = probs[:, 2:].sum(1)
    ref_true = y >= 2
    ref_pred = p_ref >= REFERABLE_THRESHOLD
    tp = int((ref_pred & ref_true).sum())
    tn = int((~ref_pred & ~ref_true).sum())
    return {
        "n": int(len(y)),
        "qwk": float(cohen_kappa_score(y, grade, weights="quadratic")),
        "accuracy": float(accuracy_score(y, grade)),
        "referable_auc": float(roc_auc_score(ref_true, p_ref)),
        "referable_sensitivity": tp / max(int(ref_true.sum()), 1),
        "referable_specificity": tn / max(int((~ref_true).sum()), 1),
        "referable_threshold": REFERABLE_THRESHOLD,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=25)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--lr", type=float, default=3e-4)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--idrid-train", action="store_true",
                    help="also train on the IDRiD train split (x3) and test on its official test split only")
    args = ap.parse_args()
    seed_all(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    cache = args.data / "cache"
    ax, ay = np.load(cache / "aptos_x.npy"), np.load(cache / "aptos_y.npy")
    ex, ey = np.load(cache / "idrid_x.npy"), np.load(cache / "idrid_y.npy")
    # prepare_dr.py caches IDRiD as sorted(test.parquet, train.parquet).
    n_idrid_test = 103
    idx_tr, idx_va = train_test_split(
        np.arange(len(ay)), test_size=0.15, stratify=ay, random_state=args.seed
    )
    tx, ty = ax[idx_tr], ay[idx_tr]
    if args.idrid_train:
        tx = np.concatenate([tx] + [ex[n_idrid_test:]] * 3)
        ty = np.concatenate([ty] + [ey[n_idrid_test:]] * 3)
        ex, ey = ex[:n_idrid_test], ey[:n_idrid_test]
    tr = DataLoader(Fundus(tx, ty, True), batch_size=args.batch,
                    shuffle=True, num_workers=0, drop_last=True, pin_memory=True)

    model = timm.create_model(ARCH, pretrained=True, num_classes=NUM_CLASSES).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    steps = args.epochs * len(tr)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=steps, pct_start=0.1)
    scaler = torch.amp.GradScaler(enabled=device == "cuda")

    # Mild class weighting: APTOS is ~50% grade 0; full inverse-frequency
    # weighting over-calls grades 1/3, so use the square root.
    counts = np.bincount(ty, minlength=NUM_CLASSES).astype(np.float64)
    w = torch.tensor((counts.sum() / counts) ** 0.5, dtype=torch.float32, device=device)
    w = w / w.mean()

    args.out.mkdir(parents=True, exist_ok=True)
    best, best_ep, history = -1.0, -1, []
    for ep in range(1, args.epochs + 1):
        model.train()
        t0, run = time.time(), 0.0
        for img, lab in tr:
            x = normalise(img, device)
            lab = lab.to(device)
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device == "cuda"):
                loss = F.cross_entropy(model(x), lab, weight=w, label_smoothing=0.05)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            run += float(loss)
        val = metrics(predict(model, ax[idx_va], device, tta=False), ay[idx_va])
        score = val["qwk"] + val["referable_auc"]
        history.append({"epoch": ep, "loss": run / len(tr), **val})
        print(f"ep {ep:02d} loss {run/len(tr):.3f} val qwk {val['qwk']:.3f} "
              f"auc {val['referable_auc']:.3f} sens {val['referable_sensitivity']:.3f} "
              f"spec {val['referable_specificity']:.3f} ({time.time()-t0:.0f}s)", flush=True)
        if score > best:
            best, best_ep = score, ep
            torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()},
                        args.out / "model.pt")

    state = torch.load(args.out / "model.pt", map_location=device, weights_only=True)
    model.load_state_dict(state)
    result = {
        "arch": ARCH,
        "num_classes": NUM_CLASSES,
        "input_size": 224,
        "best_epoch": best_ep,
        "val_aptos": metrics(predict(model, ax[idx_va], device), ay[idx_va]),
        "external_test_idrid": metrics(predict(model, ex, device), ey),
        "external_test_set": "IDRiD official test (103)" if args.idrid_train else "IDRiD train+test (516)",
        "train": {"dataset": "APTOS 2019 (85% stratified)" + (" + IDRiD train x3" if args.idrid_train else ""),
                  "n": int(len(ty)),
                  "epochs": args.epochs, "lr": args.lr, "batch": args.batch, "seed": args.seed},
        "sha256": hashlib.sha256((args.out / "model.pt").read_bytes()).hexdigest(),
        "history": history,
    }
    (args.out / "arch.txt").write_text(ARCH + "\n", encoding="utf-8")
    (args.out / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
