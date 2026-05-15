"""Top-level HTTP router assembly for the application."""

from fastapi import APIRouter

from src.app.features.auth.router import router as auth_router
from src.app.features.chat.router import router as chat_router
from src.app.features.extensions.router import router as extensions_router
from src.app.features.files.router import router as files_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(chat_router)
router.include_router(extensions_router)
router.include_router(files_router)

__all__ = ["router"]
