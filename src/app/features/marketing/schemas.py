"""Schemas for campaigns, forms, and lead capture."""

from pydantic import BaseModel


class LeadCaptureRequest(BaseModel):
    email: str
    source: str | None = None
