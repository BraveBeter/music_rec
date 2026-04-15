# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A personalized music recommendation system with a complete recall-rank pipeline and multi-level fallback. Backend is FastAPI (async), frontend is Vue 3, with MySQL 8 + Redis 7 for persistence/caching, and a standalone ML pipeline (ItemCF, SASRec, DeepFM).

## Development Commands

### Full Stack (Docker)
```bash
cp .env.example .env                # First-time setup
docker-compose down -v --remove-orphans  # Clean slate (important before rebuild)
docker-compose up -d --build        # Build & start all 5 services
docker logs musicrec_seeder -f      # Watch data initialization
```

Services expose: `13000` (frontend), `18000` (backend), `13307` (MySQL), `16379` (Redis).

### Backend (Local)
```bash
uv run uvicorn app.main:app --reload
```
For local dev, set `MYSQL_HOST=localhost`, `MYSQL_PORT=13307`, `REDIS_HOST=localhost`, `REDIS_PORT=16379` in `.env.local`.

### Frontend
```bash
cd frontend && npm run dev
```

### ML Training
```bash
uv run python -m ml_pipeline.training.train_baseline   # ItemCF
uv run python -m ml_pipeline.training.train_sasrec      # SASRec sequence model
uv run python -m ml_pipeline.training.train_deepfm      # DeepFM ranking
```

### Tests
```bash
uv run pytest                                          # All tests
uv run pytest tests/test_foo.py -k "test_name"         # Single test
```

## Architecture

### Backend (`app/`)
FastAPI with async SQLAlchemy + aiomysql. Entry point: `app/main.py`.

- **`api/`** — Route handlers (auth, users, tracks, interactions, recommendations, favorites). All under `/api/v1/`.
- **`services/`** — Business logic layer. `recommendation_service.py` is the core orchestrator.
- **`models/`** — SQLAlchemy ORM models (7 tables: users, tracks, interactions, user_favorites, track_features, offline_recommendations, tags).
- **`schemas/`** — Pydantic request/response schemas.
- **`config.py`** — Pydantic Settings, reads from `.env` / `.env.local`.
- **`database.py`** — Async engine + session factory.
- **`utils/`** — Redis client singleton (`get_redis` / `close_redis`).

### ML Pipeline (`ml_pipeline/`)
Runs independently from the web server. Entry point for inference: `ml_pipeline/inference/pipeline.py`.

- **`models/`** — Model definitions: `item_cf.py`, `sasrec.py`, `deepfm.py`, `matrix_factorization.py`.
- **`training/`** — Training scripts for each model. Output goes to `data/models/`.
- **`inference/`** — `pipeline.py` orchestrates recall → ranking. `recall.py` does multi-recall (ItemCF + SASRec). `ranking.py` runs DeepFM (supports ONNX runtime).
- **`data_process/`** — `generate_synthetic_data.py` creates 60 synthetic users + 300K interactions. `feature_engineering.py` builds feature vectors. `preprocess.py` handles data prep.
- **`evaluation/`** — Metrics (NDCG, Hit Rate, etc.) and `evaluate_all.py` for comparison reports.

### Recommendation Flow (4-Level Fallback)
1. **Redis cache** (`rec:user:{id}`, 30min TTL) → return cached
2. **ML pipeline** — multi-recall (ItemCF + SASRec) → DeepFM ranking → return personalized
3. **Offline precomputed** — `offline_recommendations` table in MySQL
4. **Popularity cold-start** — global trending tracks

### Shared Contracts (`shared_contracts/`)
Pydantic models (`InteractionEvent`, `TrackFeatureVector`, `UserFeatureVector`) shared between backend and ML pipeline.

### Frontend (`frontend/`)
Vue 3 + Vite + Pinia. Views: Home, Discover, Login, Register, Favorites, Profile. Stores: auth, player, favorites.

### Data (`data/`)
- `data/models/` — Trained model artifacts (item_cf, sasrec, deepfm, svd subdirs)
- `data/raw/` — Raw data files
- `data/processed/` — Preprocessed data for training

## Key Conventions

- Python package manager is `uv` (not pip). Dependencies in `pyproject.toml` / `uv.lock`.
- Backend uses `aiomysql` for async MySQL — all DB access is async.
- Redis is used for: recommendation caching (`rec:user:{id}`) and user play sequences (`user:seq:{id}`, via LPUSH).
- User sequence tracking: `interaction_service.py` pushes track IDs to Redis list; ML pipeline reads it for SASRec input.
- Model artifacts are stored on disk under `data/models/` (not in a model registry).
- Config uses `.env` for Docker defaults, `.env.local` for local overrides (higher priority).
- The seeder (`scripts/seed_data.py`) fetches real track metadata from Deezer API (free, no auth). Needs proxy config (`HTTP_PROXY`) in Docker

Other standard you must allow:

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.
