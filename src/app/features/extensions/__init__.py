"""Extensions feature public surface.

This package groups three related but distinct concerns behind one API surface:
skills/MCP settings, native connection management, and OAuth callback handling.
Import from here when a caller only needs the top-level router.
"""

from src.app.features.extensions.router import get_extensions_service, router
from src.app.features.extensions.service import ExtensionsService

__all__ = ["ExtensionsService", "get_extensions_service", "router"]

