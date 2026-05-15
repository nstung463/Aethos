"""Shared SQLAlchemy declarative base and metadata access for ORM models."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_metadata():
    """Return the application metadata after models have been imported."""

    return Base.metadata


__all__ = ["Base", "get_metadata"]
