"""Feature-local exports for the canonical ORM-backed auth repository.

The runtime auth implementation remains anchored on
``src.app.repositories.auth_repository`` while feature-local callers import it
from the auth feature package.
"""

from __future__ import annotations

from src.app.repositories.auth_repository import AuthRepository, _hash_token

__all__ = ["AuthRepository", "_hash_token"]
