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
Services: `13000` (user frontend), `18000` (user backend), `19000` (admin backend), `13307` (MySQL), `16379` (Redis).

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

### ML Training
```bash
uv run python -m ml_pipeline.data_process.preprocess
uv run python -m ml_pipeline.training.train_baseline    # ItemCF
uv run python -m ml_pipeline.training.train_sasrec      # SASRec
uv run python -m ml_pipeline.training.train_deepfm      # DeepFM
```

### Data Scripts
```bash
uv run python scripts/init_admin.py                  # Create admin account (idempotent)
uv run python scripts/import_jamendo.py              # Import Jamendo tracks with full streaming
uv run python -m ml_pipeline.data_process.generate_lastfm_data       # LastFM 1K users + interactions
uv run python -m ml_pipeline.data_process.generate_synthetic_data    # Synthetic 60 users
```

## Architecture

### Shared Package (`common/`)
Code shared between user backend and admin backend, mounted via Docker volumes at `/opt/common`.
- `common/models/` — SQLAlchemy ORM models (7 tables)
- `common/database.py` — Async engine + session factory
- `common/core/security.py` — JWT encode/decode
- `common/config.py` — Pydantic Settings
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
- `api/training.py` — Trigger preprocess + model training (async subprocess)
- `api/status.py` — System stats (data counts, model availability)

### Track Sources (by ID prefix)
- `DZ{id}` — Deezer API, 30s preview, proxy refreshes signed URL
- `JM{id}` — Jamendo API, full streaming URL stored in `preview_url`
- `LFM{hash}` — Synthetic tracks from LastFM artist mapping, no audio

### ML Pipeline (`ml_pipeline/`)
Independent from web servers. Inference entry: `ml_pipeline/inference/pipeline.py`.
- `models/` — ItemCF, SASRec, DeepFM, MatrixFactorization
- `training/` — Training scripts, output to `data/models/`
- `inference/recall.py` — Multi-recall: SASRec + ItemCF + tag-based + genre-aware popularity
- `inference/ranking.py` — DeepFM ranking (70%) + recall score (30%)
- `inference/pipeline.py` — Full pipeline with MMR diversity re-ranking
- `data_process/` — Preprocessing, LastFM/synthetic data generation, feature engineering

### Recommendation Flow (4-Level Fallback)
1. Redis cache (`rec:user:{id}`, 30min TTL)
2. ML pipeline — multi-recall (SASRec + ItemCF + tag + genre-popularity) → DeepFM ranking → MMR diversity rerank
3. Offline precomputed (`offline_recommendations` table)
4. Popularity cold-start

### User Frontend (`frontend/`)
Vue 3 + Vite + Pinia. Views: Home, Discover, Login, Register, Favorites, Profile.

## Key Conventions

- Package manager: `uv`. Dependencies in `pyproject.toml` / `uv.lock`.
- All DB access is async (`aiomysql`).
- Redis keys: `rec:user:{id}` (recommendation cache), `user:seq:{id}` (SASRec sequence via LPUSH).
- On login, `auth_service.py:warm_user_sequence()` loads MySQL history into Redis for SASRec.
- Model artifacts on disk at `data/models/`. Genre mappings at `data/processed/track_genres.json`.
- Config: `.env` for Docker defaults, `.env.local` for local overrides.
- Training uses genre-balanced data from `track_genres.json` and `genre_tracks.json`.
