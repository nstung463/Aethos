"""Skills middleware for progressive skill discovery."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
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

from src.ai.middleware._utils import append_to_system_message
from src.ai.skills import SkillRegistry

SKILLS_TEMPLATE = """## Skills

You have access to a skills library with specialized workflows.

Available skills:

{skills_list}

How to use skills:
- Available skills are listed in this system-reminder section.
- If the user message starts with `/<skill-name>`, treat it as an explicit skill invocation and pass the remaining text as skill args.
- When a skill matches the user's request, this is a BLOCKING REQUIREMENT: invoke the relevant `skill` tool BEFORE generating any other response about the task.
- NEVER mention a skill without actually calling the `skill` tool.
- Do not invoke a skill that is already running.
- Do not use the `skill` tool for built-in CLI commands.
- If you see a <command-name> tag in the current conversation turn, the skill has ALREADY been loaded - follow the instructions directly instead of calling the tool again."""

LOADED_SKILLS_REMINDER = """## Loaded Skill Reminder

The following skills have already been loaded in this conversation: {skill_names}.
If one of these skills is relevant and you see its <command-name> tag in the conversation, follow the loaded instructions directly instead of invoking the `skill` tool again."""


class SkillsState(AgentState):
    """Extends AgentState with loaded skills metadata."""

    skills_listing: NotRequired[Annotated[str | None, PrivateStateAttr]]
    invoked_skills: NotRequired[Annotated[dict[str, dict], PrivateStateAttr]]


class SkillsStateUpdate(TypedDict):
    skills_listing: str | None


class SkillsMiddleware(AgentMiddleware[SkillsState, ContextT]):
    """Injects compact skill discovery guidance into the system prompt."""

    state_schema = SkillsState

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        *,
        root_dir: str | None = None,
        max_listing_chars: int = 8000,
    ) -> None:
        if registry is None and root_dir is None:
            root_dir = "."
        self.registry = registry or SkillRegistry(root_dir or ".")
        self.max_listing_chars = max_listing_chars

    def before_agent(  # type: ignore[override]
        self,
        state: SkillsState,
        runtime: Runtime,
    ) -> SkillsStateUpdate | None:
        if "skills_listing" in state:
            return None
        listing = self.registry.render_listing(max_chars=self.max_listing_chars)
        return SkillsStateUpdate(skills_listing=listing or None)

    async def abefore_agent(  # type: ignore[override]
        self,
        state: SkillsState,
        runtime: Runtime,
    ) -> SkillsStateUpdate | None:
        if "skills_listing" in state:
            return None
        listing = self.registry.render_listing(max_chars=self.max_listing_chars)
        return SkillsStateUpdate(skills_listing=listing or None)

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        skills_listing: str | None = request.state.get("skills_listing")
        if not skills_listing:
            return request

        section = SKILLS_TEMPLATE.format(skills_list=skills_listing)
        invoked_skills = request.state.get("invoked_skills") or {}
        if invoked_skills:
            names = ", ".join(sorted(str(name) for name in invoked_skills))
            section += "\n\n" + LOADED_SKILLS_REMINDER.format(skill_names=names)
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
