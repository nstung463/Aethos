from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import MappingProxyType


class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "accept_edits"
    BYPASS_PERMISSIONS = "bypass_permissions"
    DONT_ASK = "dont_ask"


class PermissionBehavior(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"
    PASSTHROUGH = "passthrough"


class PermissionSubject(str, Enum):
    READ = "read"
    EDIT = "edit"
    BASH = "bash"
    POWERSHELL = "powershell"
    SKILL = "skill"
    MCP = "mcp"


class PermissionSource(str, Enum):
    POLICY = "policy"
    CLI = "cli"
    SESSION = "session"
    LOCAL = "local"
    PROJECT = "project"
    USER = "user"


@dataclass(frozen=True)
class PermissionRule:
    subject: PermissionSubject
    behavior: PermissionBehavior
    source: PermissionSource
    matcher: str | None = None


@dataclass(frozen=True)
class PermissionSuggestion:
    kind: str
    value: str


@dataclass(frozen=True)
class PermissionDecision:
    behavior: PermissionBehavior
    reason: str
    matched_rule: PermissionRule | None = None
    suggestions: tuple[PermissionSuggestion, ...] = ()
    # IMPORTANT: use MappingProxyType, not dict, since this is a frozen dataclass
    # Default: MappingProxyType({})
    metadata: MappingProxyType = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True)
class PermissionContext:
    mode: PermissionMode
    workspace_root: Path
    working_directories: tuple[Path, ...]
    rules: tuple[PermissionRule, ...] = ()
    headless: bool = False
