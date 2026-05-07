# DermScan — Project Summary

## What was built and why

DermScan is a full-stack AI screening web app for skin lesions, scaffolded across 15 sequential, separately-committed feature tasks. The system is **end-to-end demoable without trained model weights** — the worker falls back to a deterministic mock when `models/dermscan.onnx` is absent — but every interface that a real model needs is wired through.

The pipeline is intentionally split into three deployment units (API, worker, frontend) sharing Postgres + Redis + R2, because:

- **Inference is bursty and CPU-heavy.** Decoupling it behind ARQ means an upload spike never blocks API request handling, and workers scale horizontally independent of the API.
- **Image data must never sit on disk.** R2 is the single source of truth for both the original image and the heatmap; both API and worker fetch on demand and we hand the browser short-lived presigned URLs instead of streaming through our own bandwidth.
- **PII has different blast-radius rules than scan data.** Emails are encrypted at the column level (Fernet) with a separate SHA-256 lookup column for unique-email enforcement. Scan results live in plain JSONB because they are clinically meaningless without the bucket they refer to.

### Key design decisions

| Decision | Why |
|---|---|
| Confidence gate (`>=0.90 / 0.70-0.89 / <0.70`) lives in **both** the worker and the result service | Worker writes the band onto the prediction so audit + history always show what the user saw; service recomputes it on read so threshold changes via env vars don't require backfilling old rows. |
| Email lookup hash + encrypted email | Lets us enforce unique emails and find users at login without ever decrypting the table — and a leaked DB dump cannot be reverse-mapped to plaintext addresses without the Fernet key. |
| ARQ over Celery | ARQ is async-native, single-process, and uses Redis directly — no broker/result-backend split. Far less moving parts, fits the rest of the async stack, and the queue is small enough that we don't need Celery's routing/priority machinery. |
| ONNX Runtime over PyTorch | Smaller container, deterministic CPU inference, no CUDA dependency. Future GPU acceleration is a one-flag change to the providers list. |
| Forward-only "GradCAM-ish" heatmap | Real GradCAM needs gradients. ORT does forward only. Documented in the ONNX export instructions: bake the final activation map as a second graph output, then the worker computes a real CAM in `inference.run_inference`. |
| Token storage: access in localStorage, refresh in httpOnly cookie | Access tokens are short-lived (15 min); refresh tokens never enter JS. `refresh_token` is path-scoped to `/auth` so it is never sent on `/scan` requests. |
| Audit middleware non-blocking on failure | Audit must never break the user-facing path — `try/except` swallows DB errors and just logs them. The user requesting a scan should not be punished for a Postgres hiccup on the audit table. |

---

## Features implemented (with file references)

| Feature | Files |
|---|---|
| Project bootstrap | [docker-compose.yml](docker-compose.yml), [docker-compose.override.yml](docker-compose.override.yml), [prometheus.yml](prometheus.yml), [backend/.env.example](backend/.env.example), [frontend/.env.example](frontend/.env.example) |
| Async DB layer + models | [backend/app/database.py](backend/app/database.py), [backend/app/models/user.py](backend/app/models/user.py), [backend/app/models/scan.py](backend/app/models/scan.py), [backend/app/models/audit_log.py](backend/app/models/audit_log.py) |
| Field-level encryption | [backend/app/middleware/encryption.py](backend/app/middleware/encryption.py) |
| Alembic migrations | [backend/alembic.ini](backend/alembic.ini), [backend/alembic/env.py](backend/alembic/env.py), [backend/alembic/versions/20260101_0000_0001_initial.py](backend/alembic/versions/20260101_0000_0001_initial.py) |
| JWT auth | [backend/app/services/auth_service.py](backend/app/services/auth_service.py), [backend/app/routers/auth.py](backend/app/routers/auth.py), [backend/app/schemas/auth.py](backend/app/schemas/auth.py) |
| Scan API + R2 + ARQ queue | [backend/app/routers/scan.py](backend/app/routers/scan.py), [backend/app/services/scan_service.py](backend/app/services/scan_service.py), [backend/app/services/storage_service.py](backend/app/services/storage_service.py) |
| ONNX inference + GradCAM heatmap + missing-model fallback | [backend/app/worker/inference.py](backend/app/worker/inference.py), [backend/app/worker/tasks.py](backend/app/worker/tasks.py) |
| PDF report | [backend/app/services/report_service.py](backend/app/services/report_service.py) |
| FHIR R4 DiagnosticReport | [backend/app/services/fhir_service.py](backend/app/services/fhir_service.py) |
| Prometheus metrics | [backend/app/services/metrics.py](backend/app/services/metrics.py), [backend/app/main.py](backend/app/main.py) |
| Audit middleware | [backend/app/middleware/audit.py](backend/app/middleware/audit.py) |
| Grafana dashboard | [infra/grafana/dashboard.json](infra/grafana/dashboard.json) |
| Frontend scan flow | [frontend/app/scan/page.tsx](frontend/app/scan/page.tsx), [frontend/app/scan/result/[jobId]/page.tsx](frontend/app/scan/result/[jobId]/page.tsx) |
| Frontend components | [frontend/components/ImageUploader.tsx](frontend/components/ImageUploader.tsx), [frontend/components/ConsentModal.tsx](frontend/components/ConsentModal.tsx), [frontend/components/ConfidenceGate.tsx](frontend/components/ConfidenceGate.tsx), [frontend/components/ResultCard.tsx](frontend/components/ResultCard.tsx), [frontend/components/HeatmapOverlay.tsx](frontend/components/HeatmapOverlay.tsx) |
| Auth UI + history | [frontend/app/login/page.tsx](frontend/app/login/page.tsx), [frontend/app/register/page.tsx](frontend/app/register/page.tsx), [frontend/app/history/page.tsx](frontend/app/history/page.tsx) |
| Typed API client | [frontend/lib/api.ts](frontend/lib/api.ts) |
| CI/CD | [.github/workflows/ci.yml](.github/workflows/ci.yml), [backend/ruff.toml](backend/ruff.toml), [frontend/.eslintrc.json](frontend/.eslintrc.json) |
| Terraform IaC | [infra/terraform/main.tf](infra/terraform/main.tf), [infra/terraform/variables.tf](infra/terraform/variables.tf), [infra/terraform/outputs.tf](infra/terraform/outputs.tf) |
| Tests | [backend/tests/conftest.py](backend/tests/conftest.py), [backend/tests/test_auth.py](backend/tests/test_auth.py), [backend/tests/test_scan.py](backend/tests/test_scan.py), [backend/tests/test_inference.py](backend/tests/test_inference.py) |

---

## Known limitations and future improvements

1. **Forward-only heatmap.** ORT cannot compute gradients, so the current "GradCAM" is either an approximation from a second feature-map output or, when only the logits head is exported, a deterministic mock CAM. Fix: re-export the model with the final activation map as a second graph output and switch on `len(outputs) > 1` in `inference.run_inference`.
2. **No model weights.** `models/dermscan.onnx` is a `.gitkeep`. The worker explicitly logs a warning and returns a mock so the system runs end-to-end without weights.
3. **Single-region storage.** R2 is one bucket; for multi-region or HA, add a second bucket and replicate via a lifecycle rule.
4. **Rate limiting and abuse.** `/scan` is gated only by JWT — there is no per-user rate limit. Easy to add via `slowapi` or in front of the API at Cloudflare.
5. **No DICOM ingestion.** Hospital integration would normally take DICOM, not JPEG. The FHIR resource is a *simulation* — it serializes correctly but is not pushed to a FHIR server.
6. **Email verification flow not implemented.** Registration is one-step; in production add an email-verification token + SMTP service.
7. **Refresh-token revocation list.** Tokens are stateless. To force-logout a stolen refresh token before its 7-day expiry, add a Redis-backed blacklist keyed by `jti`.
8. **GradCAM frontend overlay** uses CSS `mix-blend-multiply` which works for most images but loses contrast on very dark lesions. A canvas-based blend would be more faithful.

---

## How this maps to Perceptra's role requirements

| Stripe | Where it shows up |
|---|---|
| **Software Engineering (SE)** | Clean Pydantic-typed contracts; Pydantic Settings for env; envelope response shape; consistent module layout (`routers / services / schemas / models / middleware`). API and worker share a single source of truth (`app.models`, `app.services`). |
| **SDE / fullstack** | End-to-end vertical slice: typed React client (`frontend/lib/api.ts`) ↔ FastAPI ↔ ARQ worker. Confidence gate enforced both server-side (worker writes band) and on read (service recomputes), with three explicit UI states (`ConfidenceGate.tsx`). Drag-drop uploader with a client-side blur heuristic to catch obviously bad images before they hit the queue. |
| **Deep Learning Researcher** | Inference module is the canonical surface for a real ResearchEng to plug a model into: `preprocess()` exposes input shape and ImageNet normalization; `run_inference()` returns a `dataclass` with logits / probabilities / heatmap; `classify_band()` is the model-agnostic policy layer. Mock fallback is deterministic for the same input bytes so research changes can be diffed against a stable baseline. |
| **DevOps / Platform** | Multi-stage Dockerfiles, full docker-compose with Postgres + Redis + Prometheus + Grafana, Alembic migrations, GitHub Actions matrix (backend lint+test, frontend lint+build, container build, Railway deploy), Terraform for Railway services + R2 bucket, audit log table populated by a non-blocking middleware. |

---

## Replacing the mock ONNX model with a real trained model

1. **Train.** Fine-tune EfficientNet-B4 on ISIC 2019 (or HAM10000), output 7-class softmax. Recipe in [README.md](README.md#training-and-exporting-your-own-model).
2. **Export to ONNX.** Use opset 17, dynamic batch axis, and crucially export the final activation map as a second output named e.g. `feature_map`:
   ```python
   torch.onnx.export(
       model, dummy, "dermscan.onnx",
       input_names=["input"], output_names=["logits", "feature_map"],
       dynamic_axes={"input": {0: "batch"}, "logits": {0: "batch"}, "feature_map": {0: "batch"}},
       opset_version=17,
   )
   ```
3. **Drop in.** Place the file at `models/dermscan.onnx` and restart the worker. The container mounts `./models:/models:ro`, so a new model is a single `docker compose up -d worker` away.
4. **Verify.** Watch `docker compose logs worker` for `Loaded ONNX model from /models/dermscan.onnx`. The fallback warning will be silent.
5. **Tune the gate.** Update `CONFIDENCE_THRESHOLD_HIGH` and `CONFIDENCE_THRESHOLD_LOW` in `.env` based on your held-out validation calibration. No code change required.
6. **Smoke-test the full pipeline:**
   ```bash
   docker compose exec api pytest -q tests/test_inference.py
   ```
   The "model missing → mock" test will start failing, which is the signal that the real path is now wired up. Replace it with a real fixture image and a label assertion.
7. **Calibrate per-class thresholds (optional).** The current gate is global. To trade per-class sensitivity (e.g. require extra evidence for `melanoma` to avoid false-negatives), make `CONFIDENCE_THRESHOLD_*` a JSON map keyed by label and update `classify_band` accordingly.

---

## Commit history

15 sequential feature commits + 1 worker-cleanup fix, all on `main`. `git log --oneline` shows the full sequence in implementation order.
