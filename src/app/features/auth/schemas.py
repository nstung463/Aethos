"""Pydantic schemas for authentication flows."""

from __future__ import annotations

from pydantic import BaseModel, Field


class GuestSessionRequest(BaseModel):
    display_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class SessionUserResponse(BaseModel):
    id: str
    display_name: str


class SessionResponse(TokenResponse):
    user: SessionUserResponse


class PermissionRulePayload(BaseModel):
    subject: str
    behavior: str
    matcher: str | None = None


class PermissionProfilePayload(BaseModel):
    mode: str | None = None
    working_directories: list[str] = Field(default_factory=list)
    rules: list[PermissionRulePayload] = Field(default_factory=list)
