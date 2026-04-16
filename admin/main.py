"""Admin Backend — Music Recommendation System Management API."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from admin.api import auth, tracks, users, interactions, data, training, status as status_api, scheduler
from admin.services.scheduler_service import SchedulerService
from ml_pipeline.training.progress import ProgressTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("admin")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Admin backend starting up...")

    # Mark any leftover "running" training tasks as interrupted
    ProgressTracker.mark_interrupted_on_startup()

    # Start scheduler
    svc = SchedulerService()
    await svc.start()
    app.state.scheduler = svc

    yield

    # Shutdown scheduler
    await svc.shutdown()
    logger.info("Admin backend shutting down...")


app = FastAPI(
    title="MusicRec Admin API",
    description="管理员后台 — 数据管理、模型训练",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(tracks.router)
app.include_router(users.router)
app.include_router(interactions.router)
app.include_router(data.router)
app.include_router(training.router)
app.include_router(status_api.router)
app.include_router(scheduler.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "MusicRec Admin"}
