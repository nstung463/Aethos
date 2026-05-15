"""Compatibility package for the migrated chat feature.

Deprecated for one release cycle. Do not add new logic or imports here;
use ``src.app.features.chat`` instead.
"""

from src.app.features.chat.router import router

__all__ = ["router"]
