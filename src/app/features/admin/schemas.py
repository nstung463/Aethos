"""Schemas for administrative actions."""

from pydantic import BaseModel


class FeatureFlagUpdate(BaseModel):
    key: str
    enabled: bool
