"""FastAPI application bootstrap and lifecycle wiring."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app.router import router as app_router
from src.app.core.logging import setup_logging
from src.app.core.settings import get_settings
from src.app.services.daytona_manager import build_daytona_session_manager
from src.app.services.async_jsonl_checkpointer import AsyncJsonlCheckpointSaver
from src.app.services.migration import migrate_sqlite_to_jsonl
from src.logger import get_logger

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.checkpoints_db.parent.mkdir(parents=True, exist_ok=True)

    # Auto-migrate SQLite checkpoints to JSONL on startup
    if settings.checkpoints_db.exists():
        logger.info("Found existing SQLite checkpoints database, migrating to JSONL format...")
        await migrate_sqlite_to_jsonl(settings.checkpoints_db, settings.checkpoints_db.parent)

    # Use JSONL-based checkpoint saver for complete message history
    checkpointer = AsyncJsonlCheckpointSaver(base_dir=settings.checkpoints_db.parent)
    app.state.checkpointer = checkpointer
    app.state.daytona_manager = build_daytona_session_manager()
    try:
        yield
    finally:
        app.state.daytona_manager.shutdown()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=settings.app_description,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )
    app.include_router(app_router)
    return app
