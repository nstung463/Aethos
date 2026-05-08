"""Managed file request schemas."""

from pydantic import AliasChoices, BaseModel, Field


class ContentUpdateRequest(BaseModel):
    content: str


class SelectLocalFolderRequest(BaseModel):
    root_dir: str | None = None


class ImportFromSandboxRequest(BaseModel):
    thread_id: str = Field(validation_alias=AliasChoices("thread_id", "sandbox_id"))
    path: str
    filename: str | None = None
    content_type: str | None = None


__all__ = ["ContentUpdateRequest", "ImportFromSandboxRequest", "SelectLocalFolderRequest"]
