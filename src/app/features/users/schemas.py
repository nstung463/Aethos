"""Pydantic schemas for user resources."""

from pydantic import BaseModel


class UserSummary(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    is_active: bool = True
