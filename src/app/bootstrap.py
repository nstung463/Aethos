"""FastAPI application bootstrap and lifecycle wiring."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.app.router import router as app_router
from src.app.core.logging import setup_logging
from src.app.core.settings import get_settings
from src.app.services.daytona_manager import build_daytona_session_manager

setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.checkpoints_db.parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(settings.checkpoints_db)) as checkpointer:
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
