"""HTTP routes for public marketing and growth surfaces."""

from fastapi import APIRouter

router = APIRouter(prefix="/marketing", tags=["marketing"])
