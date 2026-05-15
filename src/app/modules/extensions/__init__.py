"""Compatibility package for the migrated extensions feature.

Deprecated for one release cycle. Do not add new logic or imports here;
use ``src.app.features.extensions`` instead.
"""

from src.app.features.extensions.router import router

__all__ = ["router"]

