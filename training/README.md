# Model training

Reproducible training for the two real models the backend can serve.
Weights are **not** committed (`backend/models/` is git-ignored); rebuild them
with the commands below or copy them from wherever the team keeps artefacts.

> These are research/demo models. They are **not** clinically validated and
> must not be used for diagnosis. Every number below comes from public
> datasets, not from the target population or the phone camera used in the field.

## 1. Diabetic retinopathy (fundus) — `backend/models/model.pt`

| | |
|---|---|
| Architecture | timm `efficientnet_b0`, 5 classes (ICDR 0–4), ImageNet init |
| Train | APTOS 2019 (85 % stratified, 3 112 images) + IDRiD train split (413 images, oversampled ×3) |
| Validation | APTOS 2019 held-out 15 % (550 images) |
| Test | IDRiD **official test split** (103 images, **CC BY 4.0**, Porwal et al.) — never seen in training |
| Input | backend `load_rgb` → `retina_crop` → 224² `INTER_AREA` → ImageNet normalisation (pixel-identical to `app/api/predict.py`) |
| Format | plain `state_dict` + `arch.txt` — loaded by `torch_engine.py` with `weights_only=True` |

SPEC C1 explicitly allows "a timm `efficientnet_b0` fine-tune loaded as a plain
state_dict"; its own reference candidate was trained on APTOS 2019 as well.

```bash
python training/prepare_dr.py --data <data>     # parquet -> cached 224px crops
python training/train_dr.py   --data <data> --out <run> --idrid-train
cp <run>/model.pt <run>/arch.txt backend/models/
# numbers the phone actually gets (backend path, quality gate included):
backend/venv/Scripts/python training/eval_backend_dr.py --model-dir backend/models \
    --idrid <data>/idrid/test.parquet --blur-min-var 8
```

### Results — `dr-effb0-aptos-idrid-v2`

SHA-256 `20fb2b8e669b059e3f8db94fabb5b5a0c159d6df0a215b9b248c825b4dc0e2a3`.
Referable DR = grade ≥ 2, decided by the backend as `sum(p[2:]) >= 0.5`.

| Set | n | Referable AUC | Sensitivity | Specificity | QWK (0–4) |
|---|---|---|---|---|---|
| APTOS validation (same source as training) | 550 | 0.975 | 91.0 % | 92.4 % | 0.866 |
| **IDRiD official test, via backend** | 103 | **0.911** | **84.4 %** | **74.4 %** | 0.605 |

The IDRiD test is the honest number: different clinic, camera and grader.
Exact grade (0–4) agreement is moderate; the refer / don't-refer decision is
what the model is good for.

### Quality gate threshold — must be lowered for a real model

`QUALITY_BLUR_MIN_VAR` defaults to **50** in the frozen `config.py`. Measured on
real fundus photos it rejects **64 % of all IDRiD images and 85 % of grade-4
ones** (fundus photos are smooth by nature), and **81 of the 103** IDRiD test
images — so with a real model the app would answer "retake the photo" for most
good images, more often the sicker the eye.

Laplacian variance (gate convention, 512 px), IDRiD sample:

| Image | p5 | median | p95 |
|---|---|---|---|
| original, sharp | 16.4 | 34.8 | 63.0 |
| Gaussian defocus σ=1 (at 1024 px) | 5.5 | 11.5 | 20.5 |
| Gaussian defocus σ=2 | 2.4 | 4.0 | 6.2 |

`backend/.env.example` and `docker-compose.yml` therefore set
`QUALITY_BLUR_MIN_VAR=8.0` (all 103 test images graded, clear defocus still
rejected). Tests keep the config default of 50 — their synthetic fixtures sit
around 900–1200.

Data (Hugging Face mirrors):
`bumbledeep/aptos` → `<data>/aptos/train.parquet`,
`amin-nejad/idrid-disease-grading` → `<data>/idrid/{train,test}.parquet`.

## 2. Skin lesions — `backend/models/analysis/skin.onnx`

| | |
|---|---|
| Architecture | timm `efficientnet_b0` → ONNX (opset 17), 5 classes |
| Classes (catalogue order) | nevus · benign keratosis · actinic keratosis · carcinoma (BCC/SCC) · melanoma |
| Data | ISIC Archive, **only images whose own licence is CC-0 or CC-BY** (no CC-BY-NC, so no HAM10000 / ISIC 2018–2020 challenge sets) |
| Image types | dermoscopic (nevi capped at 3 500) + every clinical close-up / overview photo |
| Split | 70 / 15 / 15, grouped by `lesion_id` (no lesion on both sides) |
| Input | whole image → 224² `INTER_AREA` → ImageNet normalisation (identical to `app/analysis/analyzer.py`) |

```bash
python training/fetch_skin.py --out <data>/skin   # writes manifest.csv with every CC-BY attribution
python training/train_skin.py --data <data>/skin --out <run>
mkdir -p backend/models/analysis && cp <run>/skin.onnx backend/models/analysis/
```

### Results — `skin-effb0-isic-ccby`

SHA-256 `201cbc54ce701c1b6d921991b8109eefac104b4847dc3e18dcc1f8fbc0023f0c`.
20 epochs, best epoch 19 (by val balanced accuracy + high-risk AUC); split
11 176 / 2 235 / 2 236 images. ONNX vs torch max |Δlogit| = 9e-6.
High risk = carcinoma or melanoma (sum of their probabilities for the AUC,
arg-max class for sensitivity / specificity).

| Set | n | Balanced acc. (5 cls) | High-risk AUC | Sensitivity | Specificity |
|---|---|---|---|---|---|
| Validation | 2 235 | 0.765 | 0.907 | 80.9 % | 85.5 % |
| **Test (held-out lesions)** | 2 236 | **0.743** | **0.916** | **80.6 %** | **85.5 %** |
| Test — dermoscopic only | 1 848 | 0.711 | 0.921 | 80.8 % | 86.4 % |
| Test — clinical photos only | 388 | 0.660 | 0.890 | 79.9 % | 80.9 % |

Per-class test recall: nevus 94.7 %, benign keratosis 68.6 %, actinic keratosis
57.4 %, carcinoma 80.1 %, melanoma 70.8 %. Most melanoma misses go to *benign
keratosis* (75 of 483), the clinically dangerous direction. On clinical photos
melanoma recall is only **40 % (10 of 25)**: too few such images to trust, and
the main reason this model must not be presented as a melanoma detector.

**Known limitation:** the model classifies a *lesion*. It has no "healthy skin"
class, and most training images are dermoscopic, so ordinary phone photos are
out of its main domain — see `test_clinical_photos` in `metrics.json`.

## Running the backend with the real models

```bash
EYE_MODE=demo EYE_MODEL_SOURCE=torch EYE_MODEL_DIR=./models \
EYE_MODEL_VERSION=dr-effb0-aptos-idrid-v2 \
EYE_MODEL_SHA256=20fb2b8e669b059e3f8db94fabb5b5a0c159d6df0a215b9b248c825b4dc0e2a3 \
QUALITY_BLUR_MIN_VAR=8.0 uvicorn app.main:app --port 8000
```

`skin.onnx` is picked up automatically from `<EYE_MODEL_DIR>/analysis/`;
external eye, oral and nail stay on the demo mock (no licence-clean data).

## Environment

Training uses a separate CUDA venv (the backend pins CPU torch 2.3):
`torch==2.5.1+cu124`, `torchvision==0.20.1`, `timm==1.0.*`, `onnx`, `onnxruntime`,
`pandas`, `scikit-learn`, `opencv-python-headless`, `pyarrow`.
