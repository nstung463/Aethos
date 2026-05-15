"""HTTP routes for billing, payments, and subscription workflows."""

from fastapi import APIRouter

router = APIRouter(prefix="/payments", tags=["payments"])
