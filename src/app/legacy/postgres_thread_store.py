"""Compatibility shim for the legacy PostgreSQL thread repository import path."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.app.repositories.thread_repository import ThreadRepository
from src.app.services.storage_paths import StoragePathsService


@dataclass(frozen=True)
class PostgresThreadRepository(ThreadRepository):
    """Back-compat wrapper that preserves the old constructor shape.

    Runtime code should depend on ``ThreadRepository`` directly.
    """

    engine: Engine
    storage: StoragePathsService

    def __init__(self, *, engine: Engine, storage: StoragePathsService) -> None:
        object.__setattr__(self, "engine", engine)
        object.__setattr__(self, "storage", storage)
        object.__setattr__(
            self,
            "session_factory",
            sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True, class_=Session),
        )


__all__ = ["PostgresThreadRepository"]
