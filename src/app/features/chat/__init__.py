"""Chat feature public surface.

This package intentionally keeps transport, request parsing, streaming helpers,
and orchestration close together because the chat flow spans all of them.
Import from here when a caller only needs the main router or service entrypoints.
"""

from src.app.features.chat.router import router
from src.app.features.chat.service import ChatService, get_chat_service

__all__ = ["ChatService", "get_chat_service", "router"]
