"""FastAPI application bootstrap and lifecycle wiring."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from src.app.error_handling import (
    http_exception_handler,
    request_tracing_middleware,
    unhandled_exception_handler,
    validation_exception_handler,
)
from src.app.router import router as app_router
from src.app.core.logging import setup_logging
from src.app.core.settings import get_settings
from src.app.services.daytona_manager import build_daytona_session_manager
from src.app.services.async_jsonl_checkpointer import AsyncJsonlCheckpointSaver
from src.app.services.storage_paths import StoragePathsService
from src.logger import get_logger
from starlette.exceptions import HTTPException as StarletteHTTPException

setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    storage = StoragePathsService(settings)
    storage.migrate_legacy_workspace()
    storage.ensure_project_metadata()
    storage.checkpoints_base_dir().mkdir(parents=True, exist_ok=True)

    # Use JSONL-based checkpoint saver for complete message history
    checkpointer = AsyncJsonlCheckpointSaver(base_dir=storage.checkpoints_base_dir())
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
    app.middleware("http")(request_tracing_middleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    app.include_router(app_router)
    return app
