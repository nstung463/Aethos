"""Database configuration, metadata loading, and shared SQLAlchemy helpers."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Generator
from functools import lru_cache

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.app.core.settings import Settings, get_settings
from src.app.db import build_engine, build_session_factory, session_dependency
from src.app.db.base import Base


def load_database_models() -> None:
    """Import ORM models so the shared metadata is fully populated."""

    import src.app.db.models  # noqa: F401


@dataclass(frozen=True)
class DatabaseConfig:
    """Resolved database settings for storage migration phases."""

    enabled: bool
    url: str | None
    auto_migrate: bool

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.url.strip())


def get_database_config(settings: Settings | None = None) -> DatabaseConfig:
    active = settings or get_settings()
    return DatabaseConfig(
        enabled=active.database_enabled,
        url=active.database_url,
        auto_migrate=active.database_auto_migrate,
    )


@lru_cache(maxsize=4)
def _build_sqlalchemy_engine(database_url: str) -> Engine:
    return build_engine(database_url)


@lru_cache(maxsize=4)
def _build_sqlalchemy_session_factory(database_url: str) -> sessionmaker[Session]:
    return build_session_factory(database_url)


def get_database_metadata() -> MetaData:
    load_database_models()
    return Base.metadata


def get_sqlalchemy_engine(settings: Settings | None = None) -> Engine:
    active = settings or get_settings()
    config = get_database_config(active)
    if not config.is_configured or config.url is None:
        raise ValueError("Database engine requested without AETHOS_DATABASE_URL")
    load_database_models()
    return _build_sqlalchemy_engine(config.url)


def get_sqlalchemy_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    active = settings or get_settings()
    config = get_database_config(active)
    if not config.is_configured or config.url is None:
        raise ValueError("Database session factory requested without AETHOS_DATABASE_URL")
    load_database_models()
    return _build_sqlalchemy_session_factory(config.url)


def get_sqlalchemy_session(settings: Settings | None = None) -> Generator[Session, None, None]:
    yield from session_dependency(get_sqlalchemy_session_factory(settings))


def run_database_migrations(settings: Settings | None = None) -> None:
    active = settings or get_settings()
    config = get_database_config(active)
    if not config.enabled or not config.auto_migrate or not config.is_configured or config.url is None:
        return

    load_database_models()
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", config.url)
    command.upgrade(alembic_config, "head")


__all__ = [
    "DatabaseConfig",
    "get_database_config",
    "get_database_metadata",
    "get_sqlalchemy_engine",
    "get_sqlalchemy_session",
    "get_sqlalchemy_session_factory",
    "load_database_models",
    "run_database_migrations",
    "_build_sqlalchemy_engine",
    "_build_sqlalchemy_session_factory",
]
