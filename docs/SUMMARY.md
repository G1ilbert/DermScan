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

---

## CI/CD Fixes & Training Pipeline

Work that landed after the Supabase auth migration: making the GitHub
Actions pipeline green end-to-end and starting on real model weights.

### GitHub Actions CI/CD Fixes

| Commit    | Problem                                                                                                                                                                                          | Solution                                                                                                                                                                                                                                                                       |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `6e86bcf` | Node.js 20 deprecation warnings on every workflow run; major-version pins were drifting onto runtimes scheduled for removal.                                                                     | Pinned to current Node.js 24-compatible patch versions: `actions/checkout@v4.2.2`, `actions/setup-python@v5.6.0`, `actions/setup-node@v4.4.0`. No floating major tags.                                                                                                          |
| `25d1023` | Backend job exited 1. Two unrelated bugs hidden behind the same exit code: (1) all 11 fixture-using tests errored at `Base.metadata.create_all` with `Compiler can't render element of type JSONB`. (2) `ruff check .` reported 54 diagnostics on a clean checkout. | (1) The old `JSONB.__visit_name__ = "JSON"` trick no longer works in SQLAlchemy 2.x — the per-class compiler dispatch table is baked at class-creation time. Replaced with `@compiles(JSONB, "sqlite") → "JSON"` and `@compiles(UUID, "sqlite") → "CHAR(36)"` hooks in `tests/conftest.py`. (2) `ruff --fix` auto-fixed UP035 / UP006 / UP007 / I001 / F401 across 16 files; the two B904 sites in `routers/auth.py` (raise-without-from inside `except`) were fixed by hand. Verified locally: 16 passed, lint clean. |
| `5059b17` | Frontend job warned `Some specified paths were not resolved, unable to cache dependencies`; cache-dependency-path pointed at `frontend/package-lock.json` but the lockfile didn't exist. | Generated the lockfile via `npm install --legacy-peer-deps --package-lock-only` and committed it. Cache key now resolves and subsequent installs hit the GH Actions npm cache.                                                                                                  |
| `6661986` | Next.js build failed during static generation: `useSearchParams() should be wrapped in a suspense boundary` on `/login`. Next.js 14 hard-requires this for any client component reading search params during prerender. | Split [`frontend/app/login/page.tsx`](../frontend/app/login/page.tsx) into a `LoginForm` child (owns `useSearchParams()` and the `?next=` redirect) and a parent `LoginPage` that renders the form inside `<Suspense fallback={null}>`. `/login` now prerenders as static (○) again. |
| `165f594` | Docker build failed with `"/app/public" not found` in the runner stage. The runner stage copies `/app/public` from the builder, but Next.js's default project doesn't ship the directory and we never created one. | Added empty [`frontend/public/.gitkeep`](../frontend/public/.gitkeep). Directory now exists in the build context, the runner stage's `COPY` succeeds.                                                                                                                            |

### Local Training Pipeline

We need real ONNX weights to replace the in-tree mock. First attempt was
on a Kaggle kernel; we moved to local training on an RTX 2060 Super after
hitting repeated OOM and API-mismatch issues.

**Things that broke and how we resolved them:**

- **Kaggle kernel OOM-killed mid-epoch** with the original recipe
  (`batch_size=32`, `img_size=380`, `nn.DataParallel`). Reduced to
  `batch_size=8`, `img_size=224`, and disabled `DataParallel`. Stable on
  the local 8GB card.
- **Albumentations API drift.** Three breaking changes that surfaced as
  `TypeError`/`ValueError` at first batch:
  - `RandomResizedCrop` now requires a tuple — `(size, size)` instead of a
    single int.
  - `GaussNoise(var_limit=...)` removed in favor of `std_range`.
  - `CoarseDropout` parameters renamed (`min_holes`/`max_holes` →
    `num_holes_range`, similar for size).
- **`BCEWithLogitsLoss(label_smoothing=...)` raised `TypeError`.** Unlike
  `CrossEntropyLoss`, BCE has no label-smoothing kwarg — removed it.
- **`torch.cuda.amp` deprecation warning.** Switched to
  `torch.amp.autocast("cuda", ...)` and `torch.amp.GradScaler("cuda")`.
- **ISIC 2019 archive double-nests the image folder.** Inside the zip the
  layout is `ISIC_2019_Training_Input/ISIC_2019_Training_Input/*.jpg`.
  Updated the dataset path in `train.py` to point at the inner folder.
- **Decision to leave Kaggle.** After the OOM and the dependency churn,
  iterating locally on the RTX 2060 Super was faster than restarting
  Kaggle sessions. Same `train.py`, same export step, just runs against
  CUDA on the workstation.

### Current Status

- Training is in progress locally on the RTX 2060 Super (8GB VRAM).
- Expected output: `models/dermscan.onnx`, dropped into the repo's
  `models/` directory and picked up by the worker on next restart (the
  fallback warning will go silent — see "Replacing the mock ONNX model"
  above).
- CI/CD pipeline is green after the fixes above: backend lint+test,
  frontend lint+build, Docker image build, and the deploy gate all pass on
  `main`.

---

## Frontend Upgrade (Next.js 16 + React 19)

Major framework bump landed in [`0879b89`](https://github.com/G1ilbert/DermScan/commit/0879b89) along with the Cloudflare R2 → Supabase Storage migration in [`ba8bf6c`](https://github.com/G1ilbert/DermScan/commit/ba8bf6c).

### Version bumps

| Package              | From     | To       |
| -------------------- | -------- | -------- |
| `next`               | 14.2.5   | 16.2.5   |
| `react`              | 18.3.1   | 19.2.6   |
| `react-dom`          | 18.3.1   | 19.2.6   |
| `eslint-config-next` | 14.2.5   | 16.2.5   |
| `@types/react`       | 18.3.3   | 19.2.14  |
| `@types/react-dom`   | 18.3.0   | 19.2.3   |
| `eslint`             | 8.57.0   | 9.39.4   |

Next 16 enables Turbopack for the production build by default — no
config change needed; `npm run build` switched compilers transparently.

### ESLint flat-config migration

`eslint-config-next@16` ships a flat config and peer-depends on
ESLint ≥9, which forced two coupled changes:

- Legacy [`frontend/.eslintrc.json`](../frontend/.eslintrc.json) deleted; replaced with
  [`frontend/eslint.config.mjs`](../frontend/eslint.config.mjs) that imports
  `eslint-config-next/core-web-vitals` directly. The custom
  `@next/next/no-img-element: off` override moved into the flat config's
  rules block.
- ESLint 9's CLI removed `--ext`, so the npm `lint` script changed
  from `eslint . --ext .ts,.tsx` to plain `eslint .`. File globs now
  live in the flat config (`files: ["**/*.{ts,tsx}"]`).

Two unused inline `// eslint-disable-next-line @next/next/no-img-element`
comments in `components/HeatmapOverlay.tsx` were removed since the rule
is disabled globally now.

### ESLint 10 attempted, rolled back to 9.39.4

First pinned ESLint to the latest (10.3.0). The lint run crashed
inside `eslint-plugin-react`:

```
TypeError: Error while loading rule 'react/display-name':
contextOrFilename.getFilename is not a function
  at resolveBasedir (.../eslint-plugin-react/lib/util/version.js:31:100)
  at detectReactVersion (.../eslint-plugin-react/lib/util/version.js:85:19)
```

ESLint 10 dropped `context.getFilename()` in favor of `context.filename`
and the version of `eslint-plugin-react` pulled in transitively by
`eslint-config-next@16` hasn't shipped the migration yet. Pinned to
ESLint 9.39.4 — the latest 9.x line — where Next 16's plugin chain is
tested.

### Storage backend

Done in [`ba8bf6c`](https://github.com/G1ilbert/DermScan/commit/ba8bf6c) — Cloudflare R2 (boto3 / S3) is gone. Both buckets
now live in Supabase Storage:

- `scans` (private) — original uploaded images
- `heatmaps` (private) — GradCAM heatmaps written by the worker

`storage_service` rewritten around the Supabase Python client; the
interface picks up an explicit `bucket` argument:

```python
await upload(bucket, key, data, content_type=...)
await download(bucket, key)
await presign_get(bucket, key, expires_in=3600)
```

`SCANS_BUCKET` / `HEATMAPS_BUCKET` constants are exported from the
service so callers don't hardcode the strings. The `R2_*` env var
surface, the `boto3` / `botocore` deps, and the `R2_BUCKET` test env
in CI all dropped.

### Verification

- `npm run lint` — 0 warnings, 0 errors.
- `npm run build` — compiled clean via Turbopack, all 7 routes
  prerendered:
  ```
  ┌ ○ /
  ├ ○ /_not-found
  ├ ○ /history
  ├ ○ /login
  ├ ○ /register
  ├ ○ /scan
  └ ƒ /scan/result/[jobId]
  ```
  (○ static, ƒ dynamic — only the per-job result page is server-rendered
  on demand, which is the intended shape.)
- Backend `pytest -q` — 16 passed after the storage interface change;
  conftest stubs were updated to the new `(bucket, key)` signature.

### Mandatory tsconfig + next-env.d.ts edits

Next 16 made non-optional changes to two files on first build:

- [`frontend/tsconfig.json`](../frontend/tsconfig.json): `jsx` flipped from
  `"preserve"` to `"react-jsx"` (required under Next 16); added
  `.next/types/**/*.ts` and `.next/dev/types/**/*.ts` to `include` for
  typed routes.
- [`frontend/next-env.d.ts`](../frontend/next-env.d.ts): added
  `import "./.next/types/routes.d.ts"` for the typed-routes feature.

Both committed alongside the framework bump.

---

## Claude Code Automation — Capabilities & Limits

Retrospective notes on what Claude Code (this assistant) ended up
solving on the project, what required human hands, and where the
boundary actually sat. Compiled across the whole working session.

### Problems Claude Code successfully solved

Tracked end-to-end in the repo's commit history. Highlights:

- **CORS middleware missing Vercel domain in default config** — the
  middleware was correctly wired but `CORS_ORIGINS` defaulted to
  `http://localhost:3000`; bumped the default to include the
  production Vercel domain so the env-driven design still works.
- **Dockerfile CMD hardcoded port** — switched
  `CMD ["uvicorn", ..., "--port", "8000"]` to
  `CMD ["sh", "-c", "exec uvicorn ... --port ${PORT:-8000}"]` to
  honor Railway's runtime `$PORT` while keeping SIGTERM forwarding.
- **Redis/ARQ dependency removed** — replaced the queue substrate
  with a Supabase polling worker that claims rows via
  `SELECT ... FOR UPDATE SKIP LOCKED`, with crash-recovery and
  configurable poll interval.
- **Supabase Auth migration** — replaced custom JWT + bcrypt +
  SHA-256 email lookup with `service_client.auth.get_user`
  verification and a lazy local-user upsert dependency. Nine
  individually-committed tasks.
- **GitHub Actions Node 20 deprecation** — pinned
  `actions/checkout@v4.2.2`, `actions/setup-python@v5.6.0`,
  `actions/setup-node@v4.4.0`.
- **Backend pytest failures** — SQLAlchemy 2.x JSONB/UUID couldn't
  render on SQLite; replaced the old `__visit_name__` hack with
  `@compiles(JSONB|UUID, "sqlite")` hooks in `conftest.py`.
- **Ruff lint 54 diagnostics** — auto-fixed UP035 / UP006 / UP007 /
  I001 / F401 in one pass; the two B904 sites in `routers/auth.py`
  fixed by hand.
- **Next.js `useSearchParams` missing Suspense boundary** — split
  the `/login` page into a `LoginForm` child wrapped in
  `<Suspense fallback={null}>` so it prerenders as static again.
- **`frontend/public/` directory missing for Docker build** — added
  an empty `.gitkeep` so the runner stage's `COPY --from=builder
  /app/public ./public` resolves.
- **`@testing-library/react` peer dep conflict with React 19** —
  bumped 16.0.0 → 16.3.2 (peer range now `^18 || ^19`); added
  `@testing-library/dom@10.4.1` peer; `frontend/.npmrc` and
  `frontend/vercel.json` belt-and-braces for Vercel's installer.
- **Albumentations API breaking changes** in training:
  `RandomResizedCrop` tuple, `GaussNoise.std_range`, `CoarseDropout`
  param rename.
- **`BCEWithLogitsLoss(label_smoothing=...)` not supported** —
  removed; that kwarg is `CrossEntropyLoss`-only.
- **ONNX export `onnxscript` missing** — installed and the export
  succeeded.
- **ISIC 2019 dataset double-nested folder
  (`ISIC_2019_Training_Input/ISIC_2019_Training_Input/*.jpg`)** —
  fixed path in `train.py`.
- **Alembic async driver mismatch** — `psycopg2` vs `asyncpg`
  diagnosed; aligned the URL scheme used by Alembic with the runtime
  engine.
- **Supabase IPv4 compatibility** — switched the database URL to the
  Session Pooler endpoint so the Railway egress (IPv4-only at the
  time) could reach Postgres.
- **`.env.example` cleanup** — removed dead R2 / JWT /
  encryption-key vars left over from earlier auth/storage stacks.
- **`railway.json` per-service config** for api + worker so the
  Railpack auto-detect failure stops biting on monorepo deploys.
- **`vercel.json` `installCommand`** with `--legacy-peer-deps` so
  Vercel honors the same install behavior as the local `.npmrc`.

### What Claude Code cannot do without human help

The hard boundary is "anything behind a third-party auth wall or an
irrevocable consent step":

- **Login to Railway / Vercel / Supabase dashboard** — OAuth and
  device-code flows need a human at the browser. The CLI's
  `vercel login` worked because the user approved a device code on
  their own machine.
- **Generate or revoke GitHub PAT tokens safely** — the token has
  to be created by the user in their account UI; once exposed, it
  must be rotated by the user.
- **Accept Supabase "I understand" confirmation dialogs** — these
  are intentional friction for destructive ops and require a
  deliberate human click.
- **Set Root Directory in Railway dashboard** — per-service
  monorepo setting; `railway.json` only takes effect once Root
  Directory points at the matching subdirectory, and that toggle is
  dashboard-only.
- **Toggle Supabase email confirmation off** — auth provider
  settings are gated behind the dashboard.
- **Purchase add-ons** (e.g. Supabase IPv4) — billing
  authorizations require human consent and a saved payment method.

### Current suspected remaining issues

A short defensive checklist if CORS or scan submission misbehaves
after a deploy:

1. **Railway may still be serving a cached old image.** Force a
   redeploy from the Deployments tab; check that the visible commit
   SHA matches what's on `main`.
2. **`CORS_ORIGINS` in Railway may not include the exact Vercel
   domain.** Comma-separated, no spaces, exact protocol + host —
   `https://derm-scan.vercel.app,http://localhost:3000`.
3. **Double-slash `//scan` path in audit logs** means
   `NEXT_PUBLIC_API_BASE_URL` has a trailing slash. Strip it.
4. **Worker service not deployed yet.** The API will happily insert
   `pending` scan rows even if the worker is offline; the user-facing
   symptom is "scans stay pending forever." Confirm the worker
   service is up and polling.

### Scope boundary

Claude Code can:

- read and modify files in the repo,
- run terminal commands and tests locally,
- drive Chrome through the Chrome MCP for navigation, reads, and
  most clicks,
- inspect deploy logs, audit tables, and live network requests via
  the browser tools.

Claude Code cannot:

- click buttons that require dashboard authentication it doesn't
  have credentials for (without the user being signed in to that
  dashboard in the browser already),
- fill forms behind a login wall using credentials it doesn't
  possess,
- handle interactive "Are you sure?" confirmation dialogs on
  third-party platforms (each one needs a human approval click),
- upload arbitrary local files through Chrome MCP — `file_upload`
  is sandboxed against paths the user hasn't explicitly granted.

The right pattern is: Claude does the heavy lifting (code, configs,
research, log analysis, browser reads, repeatable edits) and hands
off the small set of actions that *must* be a human signal of
consent.
