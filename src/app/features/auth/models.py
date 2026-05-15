"""Shared auth domain models and defaults."""

from __future__ import annotations

from dataclasses import dataclass


DEFAULT_PERMISSION_DEFAULTS = {
    "mode": None,
    "working_directories": [],
    "rules": [],
}


@dataclass(frozen=True)
class AuthUser:
    id: str
    display_name: str
    created_at: int


@dataclass(frozen=True)
class AuthSession:
    token: str
    user_id: str
    created_at: int
    expires_at: int
    last_used_at: int


__all__ = ["DEFAULT_PERMISSION_DEFAULTS", "AuthSession", "AuthUser"]
