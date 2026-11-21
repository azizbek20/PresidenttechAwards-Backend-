"""Fine-tune timm ``efficientnet_b0`` on the licence-clean ISIC skin set and export ONNX.

Input pipeline matches ``backend/app/analysis/analyzer.py::_to_input`` exactly:
the *whole* RGB image is resized to 224x224 with ``cv2.INTER_AREA`` (no crop),
scaled to 0..1 and ImageNet-normalised.

Splits are grouped by ``lesion_id`` so several photos of one lesion never land
on both sides of the train/test boundary.

Output::

    <out>/skin.onnx     logits [N, 5] in catalogue order (opset 17)
    <out>/metrics.json  val/test metrics (overall and clinical-photo subset)

    python training/train_skin.py --data D:/EYE_Detect_Backend_run/data/skin --out <dir>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import timm
import torch
import torch.nn.functional as F
from sklearn.metrics import balanced_accuracy_score, confusion_matrix, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from torch.utils.data import DataLoader, Dataset
from torchvision.transforms import v2

ARCH = "efficientnet_b0"
SIZE = 224
CLASSES = ["nevus", "benign_keratosis", "actinic_keratosis", "carcinoma", "melanoma"]
HIGH_RISK = [3, 4]
MEAN = torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1)
STD = torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1)


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load_images(df: pd.DataFrame, img_dir: Path) -> np.ndarray:
    out = np.empty((len(df), SIZE, SIZE, 3), dtype=np.uint8)
    for i, isic_id in enumerate(df["isic_id"]):
        bgr = cv2.imread(str(img_dir / f"{isic_id}.jpg"), cv2.IMREAD_COLOR)
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        out[i] = cv2.resize(rgb, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    return out


class Lesions(Dataset):
    def __init__(self, x: np.ndarray, y: np.ndarray, train: bool) -> None:
        self.x, self.y = x, y
        self.tf = (
            v2.Compose([
                v2.RandomHorizontalFlip(),
                v2.RandomVerticalFlip(),
                v2.RandomAffine(degrees=180, scale=(0.85, 1.15), translate=(0.05, 0.05)),
                v2.ColorJitter(brightness=0.25, contrast=0.25, saturation=0.2, hue=0.03),
                v2.RandomApply([v2.GaussianBlur(5, sigma=(0.1, 1.5))], p=0.2),
            ])
            if train
            else None
        )

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, i: int) -> tuple[torch.Tensor, int]:
        img = torch.from_numpy(self.x[i]).permute(2, 0, 1)
        if self.tf is not None:
            img = self.tf(img)
        return img, int(self.y[i])


def normalise(batch: torch.Tensor, device: str) -> torch.Tensor:
    x = batch.to(device, non_blocking=True).float() / 255.0
    return (x - MEAN.to(device)) / STD.to(device)


@torch.no_grad()
def predict(model: torch.nn.Module, x: np.ndarray, device: str) -> np.ndarray:
    model.eval()
    out = []
    for i in range(0, len(x), 64):
        b = normalise(torch.from_numpy(x[i : i + 64]).permute(0, 3, 1, 2), device)
        with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device == "cuda"):
            out.append(model(b).float().softmax(1).cpu().numpy())
    return np.concatenate(out)


def metrics(probs: np.ndarray, y: np.ndarray) -> dict:
    if len(y) == 0:
        return {"n": 0}
    pred = probs.argmax(1)
    hr_true = np.isin(y, HIGH_RISK)
    hr_pred = np.isin(pred, HIGH_RISK)
    p_hr = probs[:, HIGH_RISK].sum(1)
    cm = confusion_matrix(y, pred, labels=list(range(len(CLASSES))))
    recall = {c: float(cm[i, i] / cm[i].sum()) if cm[i].sum() else None for i, c in enumerate(CLASSES)}
    res = {
        "n": int(len(y)),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)),
        "per_class_recall": recall,
        "high_risk_sensitivity": float((hr_pred & hr_true).sum() / max(hr_true.sum(), 1)),
        "high_risk_specificity": float((~hr_pred & ~hr_true).sum() / max((~hr_true).sum(), 1)),
        "confusion_matrix": cm.tolist(),
    }
    if 0 < hr_true.sum() < len(y):
        res["high_risk_auc"] = float(roc_auc_score(hr_true, p_hr))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=20)
    ap.add_argument("--batch", type=int, default=48)
    ap.add_argument("--lr", type=float, default=4e-4)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    seed_all(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"

    df = pd.read_csv(args.data / "manifest.csv")
    df = df[[(args.data / "images" / f"{i}.jpg").exists() for i in df["isic_id"]]].reset_index(drop=True)
    x_all = load_images(df, args.data / "images")
    y_all = df["label"].to_numpy(np.int64)
    groups = df["lesion_id"].astype(str).to_numpy()

    # 70 / 15 / 15 split, grouped by lesion.
    sgkf = StratifiedGroupKFold(n_splits=7, shuffle=True, random_state=args.seed)
    folds = [te for _, te in sgkf.split(x_all, y_all, groups)]
    test_idx, val_idx = folds[0], folds[1]
    train_idx = np.setdiff1d(np.arange(len(y_all)), np.concatenate([test_idx, val_idx]))
    clinical = df["image_type"].str.startswith("clinical").to_numpy()

    tr = DataLoader(Lesions(x_all[train_idx], y_all[train_idx], True), batch_size=args.batch,
                    shuffle=True, num_workers=0, drop_last=True, pin_memory=True)
    model = timm.create_model(ARCH, pretrained=True, num_classes=len(CLASSES)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr,
                                                total_steps=args.epochs * len(tr), pct_start=0.1)
    scaler = torch.amp.GradScaler(enabled=device == "cuda")
    counts = np.bincount(y_all[train_idx], minlength=len(CLASSES)).astype(np.float64)
    w = torch.tensor((counts.sum() / counts) ** 0.5, dtype=torch.float32, device=device)
    w = w / w.mean()

    args.out.mkdir(parents=True, exist_ok=True)
    ckpt = args.out / "skin_best.pt"
    best, best_ep, history = -1.0, -1, []
    for ep in range(1, args.epochs + 1):
        model.train()
        t0, run = time.time(), 0.0
        for img, lab in tr:
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device == "cuda"):
                loss = F.cross_entropy(model(normalise(img, device)), lab.to(device),
                                       weight=w, label_smoothing=0.05)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            run += float(loss)
        val = metrics(predict(model, x_all[val_idx], device), y_all[val_idx])
        score = val["balanced_accuracy"] + val.get("high_risk_auc", 0.0)
        history.append({"epoch": ep, "loss": run / len(tr), "val_bacc": val["balanced_accuracy"],
                        "val_hr_auc": val.get("high_risk_auc")})
        print(f"ep {ep:02d} loss {run/len(tr):.3f} val bacc {val['balanced_accuracy']:.3f} "
              f"hr_auc {val.get('high_risk_auc', 0):.3f} hr_sens {val['high_risk_sensitivity']:.3f} "
              f"({time.time()-t0:.0f}s)", flush=True)
        if score > best:
            best, best_ep = score, ep
            torch.save({k: v.detach().cpu() for k, v in model.state_dict().items()}, ckpt)

    model.load_state_dict(torch.load(ckpt, map_location=device, weights_only=True))
    p_test = predict(model, x_all[test_idx], device)
    result = {
        "arch": ARCH, "classes": CLASSES, "input_size": SIZE, "best_epoch": best_ep,
        "counts": {"train": int(len(train_idx)), "val": int(len(val_idx)), "test": int(len(test_idx))},
        "val": metrics(predict(model, x_all[val_idx], device), y_all[val_idx]),
        "test": metrics(p_test, y_all[test_idx]),
        "test_clinical_photos": metrics(p_test[clinical[test_idx]], y_all[test_idx][clinical[test_idx]]),
        "test_dermoscopic": metrics(p_test[~clinical[test_idx]], y_all[test_idx][~clinical[test_idx]]),
        "data": "ISIC Archive, CC-0 + CC-BY only (see manifest.csv for attributions)",
        "history": history,
    }

    # ONNX export (CPU, fp32) + parity check against torch.
    model = model.float().cpu().eval()
    onnx_path = args.out / "skin.onnx"
    dummy = torch.randn(1, 3, SIZE, SIZE)
    torch.onnx.export(model, dummy, onnx_path, input_names=["input"], output_names=["logits"],
                      dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}}, opset_version=17)
    import onnxruntime as ort
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    sample = normalise(torch.from_numpy(x_all[test_idx[:16]]).permute(0, 3, 1, 2), "cpu")
    with torch.no_grad():
        ref = model(sample).numpy()
    got = sess.run(None, {"input": sample.numpy()})[0]
    result["onnx_max_abs_diff"] = float(np.abs(ref - got).max())
    result["sha256"] = hashlib.sha256(onnx_path.read_bytes()).hexdigest()

    (args.out / "metrics.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2))


if __name__ == "__main__":
    main()
