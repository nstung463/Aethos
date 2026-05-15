"""SQLAlchemy engine and session factory helpers."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _normalize_database_url(database_url: str) -> str:
    value = database_url.strip()
    if not value:
        raise ValueError("Database URL must be a non-empty string")
    return value


@lru_cache(maxsize=4)
def build_engine(database_url: str) -> Engine:
    return create_engine(_normalize_database_url(database_url), future=True)


@lru_cache(maxsize=4)
def build_session_factory(database_url: str) -> sessionmaker[Session]:
    return sessionmaker(
        bind=build_engine(database_url),
        autoflush=False,
        expire_on_commit=False,
        future=True,
    )


def session_dependency(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """Yield a request-scoped SQLAlchemy session from the shared factory."""

    session = session_factory()
    try:
        yield session
    finally:
        session.close()


__all__ = ["build_engine", "build_session_factory", "session_dependency"]
