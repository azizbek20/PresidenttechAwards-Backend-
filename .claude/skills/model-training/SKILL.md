---
name: model-training
description: Train, evaluate, export and deploy the project's ML models: the diabetic-retinopathy EfficientNet-B0 (backend/models/model.pt), the skin-lesion ONNX model (backend/models/analysis/skin.onnx), and the on-device TFLite model. Use when working in training/ or backend/scripts/export_onnx.py, when swapping or upgrading a model, when tuning the quality-gate threshold, or when checking dataset licences.
---

# Models: train → evaluate → ship

`training/README.md` has the full results tables. This skill covers the workflow and the traps.

## Pipelines

```bash
# DR (fundus, ICDR 0-4): timm efficientnet_b0, APTOS 2019 + IDRiD train
python training/prepare_dr.py --data <data>                     # parquet -> cached 224px crops
python training/train_dr.py   --data <data> --out <run> --idrid-train
cp <run>/model.pt <run>/arch.txt backend/models/
python training/eval_backend_dr.py --model-dir backend/models \
    --idrid <data>/idrid/test.parquet --blur-min-var 8          # numbers the phone actually gets

# Skin lesions (ISIC, CC-BY only)
python training/fetch_skin.py --out <data>/skin                 # manifest.csv keeps every attribution
python training/train_skin.py --data <data>/skin --out <run>    # -> skin.onnx in <EYE_MODEL_DIR>/analysis/
```

Training uses its **own CUDA venv** (`torch==2.5.1+cu124`, `timm==1.0.*`, onnx/onnxruntime, pandas, scikit-learn, pyarrow). The backend venv pins CPU torch 2.3, so don't mix them.

## Serving a real model

```bash
cd backend
EYE_MODE=demo EYE_MODEL_SOURCE=torch EYE_MODEL_DIR=./models \
EYE_MODEL_VERSION=<run-name> EYE_MODEL_SHA256=<sha256 of model.pt> \
QUALITY_BLUR_MIN_VAR=8.0 uvicorn app.main:app --port 8000
```

- `EYE_MODEL_SOURCE` is one of `mock | torch | onnx`. Update `EYE_MODEL_VERSION` and `EYE_MODEL_SHA256` with every new checkpoint.
- **Lower `QUALITY_BLUR_MIN_VAR` to about 8 for real models.** At the stricter default, the gate rejects most real fundus photos, and the sicker the eye, the more often it rejects. The training README has the measurements.

## Hard rules

- The model format is a plain `state_dict` plus `arch.txt`, loaded with `torch.load(weights_only=True)`. Never use `weights_only=False`, and never download weights at runtime.
- **No CC-BY-NC (non-commercial) data or weights.** Keep the attribution manifest. External-eye, oral and nail analyses stay on the demo mock until licence-clean data exists.
- Preprocessing must match `app/api/predict.py` pixel for pixel: `load_rgb` → `retina_crop` → 224² `INTER_AREA` → ImageNet normalisation. `IMAGENET_MEAN/STD` live in `app/inference/engine.py`.
- Report results on the **IDRiD official test split** (never seen in training) and through the backend path with the quality gate on, not on the validation split.
- `@pytest.mark.model` tests run only with a checkpoint present: `pytest -q -m model`.

For general training technique (LR schedules, mixed precision, debugging loss), the global `ml-training-recipes` skill applies.
