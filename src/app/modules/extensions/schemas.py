"""Schemas for the Extensions settings APIs."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator


class SkillPayload(BaseModel):
    name: str
    description: str
    source: str
    loaded_from: str
    aliases: list[str] = Field(default_factory=list)
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
    httpUrl: str | None = None
    auth_url: str | None = None
    has_instructions: bool = False
    status: str = "unknown"
    error: str | None = None
    # stdio-specific fields
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    # source: "env" | "settings" — indicates where the server is configured
    source: str = "env"
    # whether the server can be removed via the UI (only "settings" servers)
    can_remove: bool = False
    tools: list[dict] = Field(default_factory=list)
    resources: list[dict] = Field(default_factory=list)
    prompts: list[dict] = Field(default_factory=list)
    skill_prompts: list[dict] = Field(default_factory=list)


class MCPServersPayload(BaseModel):
    servers: list[MCPServerPayload]


class MCPInstructionsPayload(BaseModel):
    instructions: str | None = None


class MCPJSONConfigPayload(BaseModel):
    path: str
    content: str


class MCPJSONConfigInput(BaseModel):
    content: str


class ConnectionPayload(BaseModel):
    id: str
    provider: str
    account_label: str
    status: str
    capabilities: list[str] = Field(default_factory=list)
    scopes: list[str] = Field(default_factory=list)
    auth_type: str = "oauth2"
    tools_enabled: bool = True
    created_at: int
    updated_at: int
    last_refresh_at: int | None = None
    last_error: str | None = None


class ConnectionListPayload(BaseModel):
    project_key: str
    connections: list[ConnectionPayload] = Field(default_factory=list)


class ConnectionAuthorizationInput(BaseModel):
    redirect_to: str | None = None


class ConnectionAuthorizationPayload(BaseModel):
    provider: str
    authorization_url: str
    state: str


class ConnectionTestPayload(BaseModel):
    ok: bool
    provider: str
    label: str | None = None


class ConnectionScopesPayload(BaseModel):
    id: str
    scopes: list[str] = Field(default_factory=list)


class ConnectionToolsInput(BaseModel):
    enabled: bool


_SERVER_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


class MCPServerInput(BaseModel):
    """Body for adding or updating an MCP server in the workspace settings file."""

    name: str = Field(description="Unique server name (used as the key in tool names: mcp__{name}__*). Only letters, digits, hyphens, and underscores are allowed.")

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not v or not _SERVER_NAME_RE.match(v):
            raise ValueError(
                "Server name may only contain letters, digits, hyphens, and underscores (no spaces or '__')."
            )
        if "__" in v:
            raise ValueError("Server name must not contain '__' to avoid ambiguous tool names.")
        return v
    transport: str = Field(description="Transport type: stdio | sse | http | streamable_http | websocket")
    # HTTP / SSE / WebSocket
    url: str | None = Field(default=None, description="Server URL (for http, sse, websocket transports)")
    httpUrl: str | None = Field(default=None, description="Google Workspace / Gemini-style remote MCP HTTP URL")
    oauth: dict[str, Any] | None = Field(default=None, description="Remote MCP OAuth configuration")
    headers: dict[str, str] | None = Field(default=None, description="HTTP headers to send with every request")
    # stdio
    command: str | None = Field(default=None, description="Executable to run (for stdio transport)")
    args: list[str] = Field(default_factory=list, description="Arguments passed to the command")
    env: dict[str, str] | None = Field(default=None, description="Environment variables for the subprocess")
    cwd: str | None = Field(default=None, description="Working directory for the subprocess")
    # common
    auth_url: str | None = Field(default=None, description="OAuth / login URL shown when authentication is required")
    instructions: str | None = Field(default=None, description="Per-server instructions injected into the system prompt")

    def to_connection(self) -> dict[str, Any]:
        """Build the ``connection`` dict expected by MCPServerSpec / MultiServerMCPClient."""
        conn: dict[str, Any] = {"transport": self.transport}
        resolved_url = self.url or self.httpUrl
        if resolved_url is not None:
            conn["url"] = resolved_url
        if self.oauth:
            conn["oauth"] = self.oauth
        if self.headers:
            conn["headers"] = self.headers
        if self.command is not None:
            conn["command"] = self.command
        if self.args:
            conn["args"] = self.args
        if self.env:
            conn["env"] = self.env
        if self.cwd is not None:
            conn["cwd"] = self.cwd
        return conn


__all__ = [
    "ConnectionAuthorizationInput",
    "ConnectionAuthorizationPayload",
    "ConnectionListPayload",
    "ConnectionPayload",
    "ConnectionScopesPayload",
    "ConnectionTestPayload",
    "ConnectionToolsInput",
    "MCPJSONConfigInput",
    "MCPJSONConfigPayload",
    "MCPInstructionsPayload",
    "MCPServerInput",
    "MCPServerPayload",
    "MCPServersPayload",
    "SkillImportPayload",
    "SkillListPayload",
    "SkillPayload",
]
