"""HTTP routes for internal administration."""

from fastapi import APIRouter

router = APIRouter(prefix="/admin", tags=["admin"])
