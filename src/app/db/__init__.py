"""Shared database primitives for ORM metadata and session wiring."""

from __future__ import annotations

from src.app.db.base import Base, get_metadata
from src.app.db.session import build_engine, build_session_factory, session_dependency

__all__ = [
    "Base",
    "build_engine",
    "build_session_factory",
    "get_metadata",
    "session_dependency",
]
