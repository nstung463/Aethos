"""FastAPI application bootstrap and lifecycle wiring."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from src.app.api.error_handling import (
    http_exception_handler,
    request_tracing_middleware,
    unhandled_exception_handler,
    validation_exception_handler,
)
from src.app.api.router import router as app_router
from src.app.core.logging import setup_logging
from src.app.core.settings import get_settings
from src.app.services.daytona_manager import build_daytona_session_manager
from src.app.services.database import get_database_config, get_sqlalchemy_session_factory, run_database_migrations
from src.app.services.postgres_checkpointer import PostgresCheckpointSaver
from src.app.services.profiler import startup_profiler
from src.app.services.runtime_state import shutdown_runtime_workers
from src.app.services.storage_paths import StoragePathsService
from src.logger import get_logger
from starlette.exceptions import HTTPException as StarletteHTTPException

setup_logging()
logger = get_logger(__name__)
startup_profiler.checkpoint("app_bootstrap_imported")


@asynccontextmanager
async def lifespan(app: FastAPI):
    startup_profiler.checkpoint("lifespan_start")
    settings = get_settings()
    startup_profiler.checkpoint("settings_loaded")
    database = get_database_config(settings)
    if not database.enabled or not database.is_configured:
        raise ValueError(
            "Checkpoint persistence now requires PostgreSQL. Set AETHOS_DATABASE_ENABLED=true and AETHOS_DATABASE_URL."
        )
    run_database_migrations(settings)
    # Alembic may reconfigure logging during startup; restore the app logger before serving requests.
    setup_logging()
    startup_profiler.checkpoint("database_migrations_checked")
    storage = StoragePathsService(settings)
    storage.ensure_project_metadata()
    startup_profiler.checkpoint("storage_initialized")

    checkpointer = PostgresCheckpointSaver(session_factory=get_sqlalchemy_session_factory(settings))
    app.state.checkpointer = checkpointer
    app.state.daytona_manager = build_daytona_session_manager()
    startup_profiler.checkpoint("runtime_services_ready")
    startup_profiler.report()
    try:
        yield
    finally:
        shutdown_runtime_workers(clear_cache=False)
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
