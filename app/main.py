"""
Music Recommendation System - FastAPI Application Entry Point
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.utils import close_redis

# Import routers
from app.api.auth import router as auth_router
from app.api.users import router as users_router
from app.api.tracks import router as tracks_router
from app.api.interactions import router as interactions_router
from app.api.recommendations import router as recommendations_router
from app.api.favorites import router as favorites_router
from app.api.artists import router as artists_router

settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.APP_DEBUG else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("music_rec")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info(f"🎵 {settings.APP_NAME} starting up...")
    # Auto-create new tables (e.g., artist_favorites)
    from common.database import Base, engine
    import common.models  # noqa: F401 - ensure all models are registered
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    logger.info(f"🎵 {settings.APP_NAME} shutting down...")
    await close_redis()


app = FastAPI(
    title="Music Recommendation System API",
    description="个性化音乐推荐系统 - 支持协同过滤、DeepFM、SASRec 等多种推荐策略",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:13000",   # Frontend dev (new port)
        "http://127.0.0.1:13000",
        "http://localhost:18000",   # Backend self-reference
        "http://localhost:3000",    # Legacy fallback
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
register_exception_handlers(app)

# Register routers
API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(users_router, prefix=API_PREFIX)
app.include_router(tracks_router, prefix=API_PREFIX)
app.include_router(interactions_router, prefix=API_PREFIX)
app.include_router(recommendations_router, prefix=API_PREFIX)
app.include_router(favorites_router, prefix=API_PREFIX)
app.include_router(artists_router, prefix=API_PREFIX)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": settings.APP_NAME}
