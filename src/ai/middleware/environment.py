"""Environment middleware — injects workspace context into the system prompt once per session."""

from __future__ import annotations

import logging
import platform
import subprocess
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path
from typing import Annotated, NotRequired, TypedDict

from langchain.agents.middleware.types import (
    AgentMiddleware,
    AgentState,
    ContextT,
    ModelRequest,
    ModelResponse,
    PrivateStateAttr,
    ResponseT,
)
from langgraph.runtime import Runtime

from src.ai.middleware._utils import append_system_section

logger = logging.getLogger(__name__)

# Filenames checked for project-level instructions, first match per directory wins.
_INSTRUCTION_FILES = ["AETHOS.md", "CLAUDE.md", ".aethos/instructions.md"]


def _run(cmd: list[str], cwd: str) -> str:
    return subprocess.check_output(
        cmd,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        stderr=subprocess.DEVNULL,
    ).strip()


def _git_info(cwd: str) -> dict[str, str] | None:
    try:
        branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
        status = _run(["git", "status", "--short"], cwd)
        commits = _run(["git", "log", "--oneline", "-5"], cwd)
        git_user = _run(["git", "config", "user.name"], cwd)
        return {"branch": branch, "status": status, "commits": commits, "user": git_user}
    except Exception:
        return None


class InstructionFile(TypedDict):
    path: str
    name: str
    content: str


def collect_project_instruction_files(root_dir: str) -> list[InstructionFile]:
    """Walk from root_dir up to the git root (or max 6 levels), collecting instruction files.

    At each directory level the first matching filename from _INSTRUCTION_FILES wins.
    Results are ordered outermost-first so lower (more specific) directories append last,
    giving project-level instructions priority when the model reads top-to-bottom.
    """
    found: list[InstructionFile] = []
    current = Path(root_dir).resolve()
    for _ in range(6):
        for name in _INSTRUCTION_FILES:
            path = current / name
            try:
                content = path.read_text(encoding="utf-8").strip()
                if content:
                    found.append({"path": str(path), "name": name, "content": content})
                break
            except OSError:
                continue
        if (current / ".git").exists():
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    found.reverse()  # outermost (global) first, innermost (project-specific) last
    return found


def _collect_project_instructions(root_dir: str) -> str | None:
    found = collect_project_instruction_files(root_dir)
    if not found:
        return None
    return "\n\n---\n\n".join(item["content"] for item in found)


def build_environment_section(root_dir: str, model_name: str | None = None) -> str:
    """Build the # Environment system prompt section for a given workspace root."""
    git = _git_info(root_dir)

    lines = [
        "# Environment",
        f"- Working directory: {root_dir}",
        f"- Is a git repository: {'yes' if git else 'no'}",
        f"- Platform: {platform.system().lower()}",
        f"- Today's date: {date.today().isoformat()}",
    ]

    if model_name:
        lines.append(f"- Model: {model_name}")

    if git:
        if git["user"]:
            lines.append(f"- Git user: {git['user']}")
        lines.append(f"- Current branch: {git['branch']}")
        if git["status"]:
            lines.append(f"\nGit status:\n{git['status']}")
        if git["commits"]:
            lines.append(f"\nRecent commits:\n{git['commits']}")

    instructions = _collect_project_instructions(root_dir)
    if instructions:
        lines.append(f"\n# Project Instructions\n\n{instructions}")

    return "\n".join(lines)


class _EnvState(AgentState):
    """Extends AgentState with a cached environment section string."""

    _env_section: NotRequired[Annotated[str | None, PrivateStateAttr]]


class _EnvStateUpdate(TypedDict):
    _env_section: str | None


class EnvironmentMiddleware(AgentMiddleware[_EnvState, ContextT]):
    """Computes workspace environment info once per session and injects it into the system prompt.

    Reads on first turn only (cached via PrivateStateAttr for the lifetime of the thread):
    - Current working directory
    - Git branch, status, recent commits, and user
    - Today's date and OS platform
    - Optional model name
    - Project instructions from AETHOS.md / CLAUDE.md hierarchy walk
    """

    state_schema = _EnvState

    def __init__(self, root_dir: str, model_name: str | None = None) -> None:
        self.root_dir = root_dir
        self.model_name = model_name

    def _compute(self) -> str:
        section = build_environment_section(self.root_dir, self.model_name)
        logger.debug("EnvironmentMiddleware: computed environment section (%d chars)", len(section))
        return section

    def before_agent(self, state: _EnvState, runtime: Runtime) -> _EnvStateUpdate | None:  # type: ignore[override]
        if "_env_section" in state:
            return None
        return _EnvStateUpdate(_env_section=self._compute())

    async def abefore_agent(self, state: _EnvState, runtime: Runtime) -> _EnvStateUpdate | None:  # type: ignore[override]
        if "_env_section" in state:
            return None
        return _EnvStateUpdate(_env_section=self._compute())

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        section: str | None = request.state.get("_env_section")
        if not section:
            return request
        return append_system_section(request, section)

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT]:
        return handler(self.modify_request(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        return await handler(self.modify_request(request))
