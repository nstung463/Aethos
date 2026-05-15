"""Compatibility shim for code that still imports ``PostgresAuthRepository``.

The runtime repository is ``src.app.repositories.auth_repository.AuthRepository``.
"""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.app.repositories.auth_repository import AuthRepository as ORMAuthRepository


class PostgresAuthRepository(ORMAuthRepository):
    """Backwards-compatible constructor for callers that still pass an engine."""

    def __init__(
        self,
        engine: Engine,
        session_ttl_seconds: int = 30 * 24 * 60 * 60,
        session_refresh_interval_seconds: int = 5 * 60,
    ) -> None:
        # Preserve caller-provided engine configuration (pool/options/event hooks)
        # instead of reconstructing a new engine from URL.
        session_factory = sessionmaker(
            bind=engine,
            class_=Session,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )
        super().__init__(
            session_factory=session_factory,
            session_ttl_seconds=session_ttl_seconds,
            session_refresh_interval_seconds=session_refresh_interval_seconds,
        )
        self.engine = engine


__all__ = ["PostgresAuthRepository"]
