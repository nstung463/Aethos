"""Skills middleware for progressive skill discovery."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, NotRequired, TypedDict

import yaml
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

from src.ai.middleware._utils import append_to_system_message

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

SKILLS_TEMPLATE = """## Skills

You have access to a skills library with specialized workflows.

**Available Skills:**

{skills_list}

**How to use skills (progressive disclosure):**
1. When a skill matches the task, read its full instructions: `read_file(path="{skills_dir}/<name>/SKILL.md")`
2. Follow the skill's workflow exactly.
3. Skills may reference helper files - use absolute paths as shown above.

When in doubt, check if a skill exists for the task before proceeding."""


class SkillMetadata(TypedDict):
    name: str
    description: str
    path: str


class SkillsState(AgentState):
    """Extends AgentState with loaded skills metadata."""

    skills_metadata: NotRequired[Annotated[list[SkillMetadata], PrivateStateAttr]]


class SkillsStateUpdate(TypedDict):
    skills_metadata: list[SkillMetadata]


def _parse_skill(skill_md: Path) -> SkillMetadata | None:
    try:
        content = skill_md.read_text(encoding="utf-8")
    except OSError:
        return None

    match = _FRONTMATTER_RE.match(content)
    if not match:
        logger.warning("No YAML frontmatter in %s", skill_md)
        return None

    try:
        data = yaml.safe_load(match.group(1))
    except yaml.YAMLError as exc:
        logger.warning("YAML error in %s: %s", skill_md, exc)
        return None

    if not isinstance(data, dict):
        return None

    name = str(data.get("name", "")).strip()
    description = str(data.get("description", "")).strip()
    if not name or not description:
        return None

    return SkillMetadata(name=name, description=description, path=str(skill_md))


def _scan_skills(skills_dir: str) -> list[SkillMetadata]:
    root = Path(skills_dir)
    if not root.exists():
        return []

    skills: dict[str, SkillMetadata] = {}
    for subdir in sorted(root.iterdir()):
        if not subdir.is_dir():
            continue
        skill_md = subdir / "SKILL.md"
        if not skill_md.exists():
            continue
        metadata = _parse_skill(skill_md)
        if metadata:
            skills[metadata["name"]] = metadata

    return list(skills.values())


class SkillsMiddleware(AgentMiddleware[SkillsState, ContextT]):
    """Scans skills/ once per session and injects skill metadata into the system prompt."""

    state_schema = SkillsState

    def __init__(self, skills_dir: str = "./skills") -> None:
        self.skills_dir = skills_dir

    def _format_skills_list(self, skills: list[SkillMetadata]) -> str:
        if not skills:
            return f"(No skills found in `{self.skills_dir}`)"
        lines = []
        for skill in skills:
            lines.append(f"- **{skill['name']}**: {skill['description']}")
            lines.append(f"  -> Read `{skill['path']}` for full instructions")
        return "\n".join(lines)

    def before_agent(  # type: ignore[override]
        self,
        state: SkillsState,
        runtime: Runtime,
    ) -> SkillsStateUpdate | None:
        if "skills_metadata" in state:
            return None
        skills = _scan_skills(self.skills_dir)
        logger.debug("Loaded %d skills from %s", len(skills), self.skills_dir)
        return SkillsStateUpdate(skills_metadata=skills)

    async def abefore_agent(  # type: ignore[override]
        self,
        state: SkillsState,
        runtime: Runtime,
    ) -> SkillsStateUpdate | None:
        if "skills_metadata" in state:
            return None
        skills = _scan_skills(self.skills_dir)
        return SkillsStateUpdate(skills_metadata=skills)

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        skills: list[SkillMetadata] = request.state.get("skills_metadata") or []
        if not skills:
            return request

        skills_list = self._format_skills_list(skills)
        section = SKILLS_TEMPLATE.format(
            skills_list=skills_list,
            skills_dir=self.skills_dir,
        )
        new_sys = append_to_system_message(request.system_message, section)
        return request.override(system_message=new_sys)

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
