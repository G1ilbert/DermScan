# DermScan

[![Latest Release](https://img.shields.io/github/v/release/G1ilbert/DermScan)](https://github.com/G1ilbert/DermScan/releases)

Production-grade AI skin lesion screening web app. Users upload a photo of a skin lesion and the system returns a confidence-gated risk assessment with a GradCAM attention heatmap. Designed for **pre-hospital screening** by the general public — never a substitute for a doctor.

---

## Model Versions

See all model versions and changelogs in [GitHub Releases](https://github.com/G1ilbert/DermScan/releases).

Latest:

| Version | Architecture    | Image Size | AUC    | Accuracy | Melanoma Recall | Epochs          | Key Changes                                                                              |
| ------- | --------------- | ---------- | ------ | -------- | --------------- | --------------- | ---------------------------------------------------------------------------------------- |
| v1.0    | EfficientNet-B4 | 224×224    | 0.9316 | 90%      | 79%             | 14 (early stop) | Initial training, AdamW lr=1e-4→5e-5 resume, pos_weight=4.60, Mixup α=0.4, patience=6    |

Download the latest `dermscan.onnx` from the release assets and place it in `models/`.

---

## Setup

### Prerequisites

- Docker & docker-compose
- (Optional, for local dev outside Docker) Python 3.11, Node.js 20

### 1. Clone and configure

```bash
git clone <this-repo> dermscan
cd dermscan
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Generate a real Fernet encryption key and put it in `backend/.env`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Run the stack

```bash
docker compose up --build
```

That brings up Postgres, Redis, Prometheus, Grafana, the FastAPI API, the ARQ worker, and the Next.js frontend. Apply migrations the first time:

```bash
docker compose exec api alembic upgrade head
```

Open:
- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001 (admin / admin)

### 3. Drop in a real model (optional)

Place an exported ONNX model at `models/dermscan.onnx`. If the file is absent, the worker logs a warning and returns a deterministic mock prediction so the UI is fully demoable without weights.

---

## Environment variables

### Backend (`backend/.env`)

| Variable | Purpose | Default |
|---|---|---|
| `APP_ENV` | environment label | `development` |
| `APP_DEBUG` | enables FastAPI debug mode | `true` |
| `DATABASE_URL` | async Postgres DSN | `postgresql+asyncpg://dermscan:dermscan@postgres:5432/dermscan` |
| `REDIS_URL` | Redis URL for ARQ | `redis://redis:6379/0` |
| `JWT_SECRET_KEY` | HS256 secret | — (required) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | access token lifetime | `15` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | refresh token lifetime | `7` |
| `ENCRYPTION_KEY` | Fernet key for field-level encryption | — (required) |
| `R2_ENDPOINT_URL` | Cloudflare R2 S3 endpoint | — |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | R2 credentials | — |
| `R2_BUCKET` | R2 bucket name | `dermscan-images` |
| `MODEL_PATH` | ONNX model location | `/models/dermscan.onnx` |
| `MODEL_INPUT_SIZE` | input resolution | `380` |
| `CONFIDENCE_THRESHOLD_HIGH` | `result` threshold | `0.90` |
| `CONFIDENCE_THRESHOLD_LOW` | `uncertain` floor | `0.70` |
| `CORS_ORIGINS` | comma-separated allowed origins | `http://localhost:3000` |
| `MAX_UPLOAD_BYTES` | image size cap | `10485760` |

### Frontend (`frontend/.env`)

| Variable | Purpose | Default |
|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | backend URL the browser hits | `http://localhost:8000` |
| `NEXT_PUBLIC_POLL_INTERVAL_MS` | scan-result polling cadence | `2000` |

---

## API reference

All responses follow the envelope `{ "success": bool, "data": <payload>, "error": <string|null> }`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | — | Liveness probe |
| `GET` | `/metrics` | — | Prometheus scrape endpoint |
| `POST` | `/auth/register` | — | Create account `{email, password}` |
| `POST` | `/auth/login` | — | Returns access + refresh token; sets refresh cookie |
| `POST` | `/auth/refresh` | refresh | Rotate tokens (cookie or `Bearer`) |
| `POST` | `/auth/logout` | — | Clear refresh cookie |
| `POST` | `/scan` | access | Multipart `file=` JPEG/PNG ≤ 10 MB; returns `{job_id, scan_id, status}` |
| `GET` | `/scan/result/{job_id}` | access | Poll for status / final result (presigned URLs + heatmap + band) |
| `GET` | `/scan/history?page=&page_size=` | access | Paginated user scans |
| `GET` | `/scan/report/{scan_id}` | access | Returns `application/pdf` screening report |
| `GET` | `/scan/fhir/{scan_id}?include_image=` | access | FHIR R4 `DiagnosticReport` JSON |

---

## Running tests

Backend:
```bash
cd backend
pip install -r requirements.txt
pytest -q
```

The test suite uses an in-memory SQLite via `aiosqlite` and stubs out R2 + Redis, so it runs without any infrastructure.

Frontend:
```bash
cd frontend
npm install --legacy-peer-deps
npm run lint
npm run build
```

---

## Training and exporting your own model

The pipeline expects a 380×380 RGB ImageNet-normalized input and a 7-class softmax output following the [ISIC 2019](https://challenge2019.isic-archive.com/) taxonomy: `melanoma, melanocytic_nevus, basal_cell_carcinoma, actinic_keratosis, benign_keratosis, dermatofibroma, vascular_lesion`.

Suggested training recipe:
1. Download ISIC 2019 (or HAM10000 for a smaller variant). Stratified-split train/val/test.
2. Fine-tune `efficientnet-b4` (timm) on 380×380 crops with class-balanced sampling and cross-entropy loss.
3. Export to ONNX:

```python
import torch
import timm

model = timm.create_model("efficientnet_b4", pretrained=False, num_classes=7)
model.load_state_dict(torch.load("best.pt", map_location="cpu"))
model.eval()
dummy = torch.randn(1, 3, 380, 380)
torch.onnx.export(
    model, dummy, "models/dermscan.onnx",
    input_names=["input"], output_names=["logits"],
    dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}},
    opset_version=17,
)
```

For real GradCAM (rather than the forward-only approximation in this scaffold), export the model with the final feature map as a second output so the worker can compute spatial activations directly.

---

