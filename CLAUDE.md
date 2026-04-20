# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A personalized music recommendation system with multi-level fallback. Two backends (user + admin), one user frontend, MySQL 8 + Redis 7, and ML pipeline (ItemCF, SASRec, DeepFM).

## Development Commands

### Full Stack (Docker)
```bash
cp .env.example .env
docker-compose up -d --build
```
Services: `13000` (user frontend), `14000` (admin frontend), `18000` (user backend), `19000` (admin backend), `13307` (MySQL), `16379` (Redis).

No seeder container — admin backend auto-creates tables and admin account on startup.

### Backend (Local)
```bash
uv run uvicorn app.main:app --reload          # User backend
uv run uvicorn admin.main:app --reload --port 8001  # Admin backend
```
For local dev, set `MYSQL_HOST=localhost`, `MYSQL_PORT=13307`, `REDIS_HOST=localhost`, `REDIS_PORT=16379` in `.env.local`.

### Frontend
```bash
cd frontend && npm run dev      # User frontend (port 5173)
cd admin-web && npm run dev     # Admin frontend (port 5174)
```

### ML Training & Evaluation
```bash
uv run python -m ml_pipeline.data_process.preprocess
uv run python -m ml_pipeline.data_process.feature_engineering
uv run python -m ml_pipeline.training.train_baseline    # ItemCF + SVD
uv run python -m ml_pipeline.training.train_sasrec      # SASRec
uv run python -m ml_pipeline.training.train_deepfm      # DeepFM
uv run python -m ml_pipeline.evaluation.evaluate_trained  # Evaluate all trained models
```
All training/evaluation scripts accept optional `--task-id <id>` for progress tracking. Training progress goes to `data/training_progress/`, evaluation progress to `data/evaluation_progress/`.

### Data Scripts
```bash
uv run python scripts/import_jamendo.py              # Import Jamendo tracks with full streaming
uv run python -m ml_pipeline.data_process.generate_lastfm_data       # LastFM 1K users + interactions
uv run python -m ml_pipeline.data_process.generate_synthetic_data    # Synthetic 60 users
```

## Architecture

### Shared Package (`common/`)
Code shared between user backend and admin backend, mounted via Docker volumes at `/opt/common`.
- `common/models/` — SQLAlchemy ORM models (9 tables, including training_schedules + training_threshold_state)
- `common/database.py` — Async engine + session factory
- `common/core/security.py` — JWT encode/decode, password hashing (`hash_password`, `verify_password`)
- `common/config.py` — Pydantic Settings (`ACCESS_TOKEN_EXPIRE_MINUTES=480`)
- `common/schemas/` — Shared Pydantic schemas

### User Backend (`app/`)
FastAPI on port 18000. Re-exports from `common/` for backward compatibility.
- `api/` — Routes under `/api/v1/` (auth, users, tracks, interactions, recommendations, favorites)
- `services/` — Business logic. `recommendation_service.py` orchestrates the 4-level fallback.
- Audio proxy in `api/tracks.py` routes by track prefix: `JM` (Jamendo full stream), `DZ` (Deezer 30s preview).

### Admin Backend (`admin/`)
FastAPI on port 19000. Independent Docker container, imports from `common/`.
- `api/auth.py` — Admin login (checks role='admin')
- `api/tracks.py` — Batch track import + Deezer/Jamendo fetch
- `api/users.py` — Batch user import
- `api/interactions.py` — Batch interaction import
- `api/data.py` — Trigger LastFM/synthetic data generation
- `api/training.py` — Trigger preprocess + model training + evaluation + SSE progress streaming + history + eval-specific endpoints
- `api/scheduler.py` — CRUD for scheduled/auto-retraining tasks + threshold config
- `api/status.py` — System stats (data counts, model availability)
- `services/training_service.py` — Training subprocess orchestration with progress tracking
- `services/scheduler_service.py` — APScheduler wrapper (cron/interval/threshold)
- `main.py` — Lifespan: auto-creates DB tables + admin account, starts scheduler, recovers interrupted training

### Track Sources (by ID prefix)
- `DZ{id}` — Deezer API, 30s preview, proxy refreshes signed URL
- `JM{id}` — Jamendo API, full streaming URL stored in `preview_url`
- `LFM{hash}` — Synthetic tracks from LastFM artist mapping, no audio

### ML Pipeline (`ml_pipeline/`)
Independent from web servers. Inference entry: `ml_pipeline/inference/pipeline.py`.
- `models/` — ItemCF, SASRec, DeepFM, MatrixFactorization
- `training/` — Training scripts, output to `data/models/`
- `training/progress.py` — File-based cross-process progress tracker (ProgressTracker), separate dirs for training and evaluation
- `evaluation/` — Model evaluation (evaluate_trained.py, metrics.py), outputs comparison_report.json
- `inference/recall.py` — Multi-recall: SASRec + ItemCF + tag-based + genre-aware popularity
- `inference/ranking.py` — DeepFM ranking (70%) + recall score (30%)
- `inference/pipeline.py` — Full pipeline with MMR diversity re-ranking
- `data_process/` — Preprocessing, LastFM/synthetic data generation, feature engineering

### Training Progress System
- Training scripts write progress to `data/training_progress/<task_id>.json` (atomic writes)
- Evaluation scripts write progress to `data/evaluation_progress/<task_id>.json`
- Per-task evaluation reports saved as `data/evaluation_progress/<task_id>_report.json`
- Admin backend reads these files via `ProgressTracker` static methods
- SSE endpoint (`/admin/training/progress/<task_id>/stream`) pushes real-time updates to frontend
- Evaluation has separate endpoints: `eval-progress`, `eval-history`, `eval-report/{task_id}`
- Global asyncio.Lock prevents parallel training execution
- `list_all_progress` skips `_report.json` files (they contain result arrays, not progress dicts)

### Scheduler System
- Uses APScheduler 3.x (AsyncIOScheduler) embedded in admin backend
- Three trigger modes: cron expression, fixed interval, data threshold
- Threshold checker runs every 10 minutes: compares current interaction count vs last training count
- Jobs configured with `max_instances=1`, `coalesce=True`, `misfire_grace_time=300`
- Schedule persistence: `training_schedules` table in MySQL

### Recommendation Flow (4-Level Fallback)
1. Redis cache (`rec:user:{id}`, 30min TTL)
2. ML pipeline — multi-recall (SASRec + ItemCF + tag + genre-popularity) → DeepFM ranking → MMR diversity rerank
3. Offline precomputed (`offline_recommendations` table)
4. Popularity cold-start

### User Frontend (`frontend/`)
Vue 3 + Vite + Pinia. Views: Home, Discover, Login, Register, Favorites, Profile, History, ArtistDetail.
- Home: personalized recommendations (similar tracks from top-played via ItemCF)
- Discover: genre browsing (random + ranking grid), search
- ArtistDetail: artist tracks + favorites
- Player bar: favorite button + artist link

### Admin Frontend (`admin-web/`)
Vue 3 + Vite + Pinia. Sidebar layout (220px fixed) + content area (max-width 1200px).
- `components/AppLayout.vue` — Sidebar + content shell
- `components/` — Shared: StatCard, ProgressBar, LogPanel, StatusBadge, LogDialog (log + eval results viewer)
- `views/Dashboard.vue` — Overview: stats + model status + recent training + recent evaluations
- `views/DataImport.vue` — Data source management
- `views/Training.vue` — Real-time training visualization (SSE) + history + log dialog
- `views/Scheduler.vue` — Scheduled task management + threshold config
- `views/Models.vue` — Model availability, evaluation metrics comparison, evaluation history + log dialog
- `stores/training.ts` — SSE connection management, active tasks, history
- `stores/scheduler.ts` — Schedule CRUD, threshold state

## Key Conventions

- Package manager: `uv`. Dependencies in `pyproject.toml` / `uv.lock` + `requirements.txt` (for Docker).
- All DB access is async (`aiomysql`).
- Redis keys: `rec:user:{id}` (recommendation cache), `user:seq:{id}` (SASRec sequence via LPUSH).
- On login, `auth_service.py:warm_user_sequence()` loads MySQL history into Redis for SASRec.
- Model artifacts on disk at `data/models/`. Genre mappings at `data/processed/track_genres.json`.
- Config: `.env` for Docker defaults, `.env.local` for local overrides.
- Training uses genre-balanced data from `track_genres.json` and `genre_tracks.json`.
- `data/` directory is gitignored — not tracked in version control.
- Model artifacts save index mappings (user2idx/track2idx) alongside weights for correct inference alignment.
- DeepFM evaluation/ranking uses model's own feature metadata (sparse_features, dense_features, sparse_dims) rather than feature_meta.json to avoid shape mismatches after re-running feature engineering.
- JWT admin token expires in 480 minutes (8 hours).
- Two git remotes: `origin` (Gitee), `github` (GitHub).
