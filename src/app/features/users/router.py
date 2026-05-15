"""HTTP routes for user management."""

from fastapi import APIRouter

router = APIRouter(prefix="/users", tags=["users"])
