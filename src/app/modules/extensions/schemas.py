"""Schemas for the Extensions settings APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkillPayload(BaseModel):
    name: str
    description: str
    source: str
    loaded_from: str
    path: str | None = None
    root_dir: str | None = None
    server: str | None = None
    remote_name: str | None = None
    when_to_use: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    argument_hint: str | None = None
    arguments: list[str] = Field(default_factory=list)
    model: str | None = None
    effort: str | None = None
    context: str | None = None
    agent: str | None = None
    paths: list[str] = Field(default_factory=list)
    raw_frontmatter: dict = Field(default_factory=dict)
    body: str | None = None
    can_delete: bool = False


class SkillListPayload(BaseModel):
    root_dir: str
    skills: list[SkillPayload]


class SkillImportPayload(BaseModel):
    skill: SkillPayload
    warnings: list[str] = Field(default_factory=list)


class MCPServerPayload(BaseModel):
    name: str
    transport: str | None = None
    url: str | None = None
    auth_url: str | None = None
    has_instructions: bool = False
    status: str = "unknown"
    error: str | None = None
    tools: list[dict] = Field(default_factory=list)
    resources: list[dict] = Field(default_factory=list)
    prompts: list[dict] = Field(default_factory=list)
    skill_prompts: list[dict] = Field(default_factory=list)


class MCPServersPayload(BaseModel):
    servers: list[MCPServerPayload]


class MCPInstructionsPayload(BaseModel):
    instructions: str | None = None


__all__ = [
    "MCPInstructionsPayload",
    "MCPServerPayload",
    "MCPServersPayload",
    "SkillImportPayload",
    "SkillListPayload",
    "SkillPayload",
]
