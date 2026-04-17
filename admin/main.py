"""Admin Backend — Music Recommendation System Management API."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from admin.api import auth, tracks, users, interactions, data, training, status as status_api, scheduler
from admin.services.scheduler_service import SchedulerService
from common.core.security import hash_password
from common.database import async_session_factory, engine, Base
from ml_pipeline.training.progress import ProgressTracker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("admin")

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


async def _ensure_admin():
    """Create default admin account if it doesn't exist (idempotent)."""
    async with async_session_factory() as session:
        result = await session.execute(
            text("SELECT user_id FROM users WHERE username = :username"),
            {"username": ADMIN_USERNAME},
        )
        if result.first():
            logger.info(f"Admin user '{ADMIN_USERNAME}' already exists")
            return

        await session.execute(
            text("""
                INSERT INTO users (username, password_hash, role, age, gender, country)
                VALUES (:username, :password_hash, :role, :age, :gender, :country)
            """),
            {
                "username": ADMIN_USERNAME,
                "password_hash": hash_password(ADMIN_PASSWORD),
                "role": "admin",
                "age": 25,
                "gender": 1,
                "country": "China",
            },
        )
        await session.commit()
        logger.info(f"Created admin user: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")


async def _ensure_tables():
    """Ensure all ORM tables exist (handles existing databases)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Admin backend starting up...")

    # 1. Create tables if missing
    await _ensure_tables()

    # 2. Create admin account if missing
    await _ensure_admin()

    # 3. Mark leftover "running" training tasks as interrupted
    ProgressTracker.mark_interrupted_on_startup()

    # 4. Start scheduler
    svc = SchedulerService()
    await svc.start()
    app.state.scheduler = svc

    yield

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
