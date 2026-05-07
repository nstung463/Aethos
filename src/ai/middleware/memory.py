"""Memory middleware for AGENTS.md injection."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
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

MEMORY_TEMPLATE = """<agent_memory>
{content}
</agent_memory>

<memory_guidelines>
The above <agent_memory> may include project instruction context and auto-managed Ethos memory.

- When the user asks you to remember something, use the `remember` tool to store
  long-lived memory in the auto-managed Ethos memory file, not in AGENTS.md.
- Treat AGENTS.md, CLAUDE.md, and .ethos/instructions.md as user-managed
  instruction documents, not as the primary memory store.
- Capture WHY feedback was given, not just the surface correction.
- Never store API keys or credentials in memory files.
</memory_guidelines>"""


class MemoryState(AgentState):
    """Extends AgentState with loaded memory content."""

    memory_contents: NotRequired[Annotated[str | None, PrivateStateAttr]]


class MemoryStateUpdate(TypedDict):
    memory_contents: str | None


class MemoryMiddleware(AgentMiddleware[MemoryState, ContextT]):
    """Loads project instructions and auto-managed memory once per session."""

    state_schema = MemoryState

    def __init__(self, agents_md_path: str = "./AGENTS.md", auto_memory_path: str | None = None) -> None:
        self.agents_md_path = agents_md_path
        self.auto_memory_path = auto_memory_path

    def _load(self) -> str | None:
        sections: list[str] = []
        agents_path = Path(self.agents_md_path)
        if agents_path.exists():
            content = agents_path.read_text(encoding="utf-8").strip()
            if content:
                sections.append(f"## Project Instructions ({agents_path.name})\n{content}")
        else:
            logger.debug("AGENTS.md not found at %s", self.agents_md_path)

        if self.auto_memory_path:
            memory_path = Path(self.auto_memory_path)
            if memory_path.exists():
                content = memory_path.read_text(encoding="utf-8").strip()
                if content:
                    sections.append(f"## Auto Memory ({memory_path})\n{content}")

        return "\n\n".join(sections) or None

    def before_agent(  # type: ignore[override]
        self,
        state: MemoryState,
        runtime: Runtime,
    ) -> MemoryStateUpdate | None:
        if "memory_contents" in state:
            return None
        content = self._load()
        if content:
            logger.debug("Loaded AGENTS.md from %s", self.agents_md_path)
        return MemoryStateUpdate(memory_contents=content)

    async def abefore_agent(  # type: ignore[override]
        self,
        state: MemoryState,
        runtime: Runtime,
    ) -> MemoryStateUpdate | None:
        if "memory_contents" in state:
            return None
        content = self._load()
        return MemoryStateUpdate(memory_contents=content)

    def modify_request(self, request: ModelRequest[ContextT]) -> ModelRequest[ContextT]:
        content: str | None = request.state.get("memory_contents")
        if not content:
            return request
        section = MEMORY_TEMPLATE.format(content=content)
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
