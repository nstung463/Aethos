"""Tool for writing auto-managed Ethos memory."""

from __future__ import annotations

from pathlib import Path

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.app.services.memory_store import MemoryStore


class RememberInput(BaseModel):
    memory: str = Field(description="Long-lived project memory to store. Do not include secrets or credentials.")


def build_remember_tool(root_dir: str | Path, memory_store: MemoryStore | None = None) -> StructuredTool:
    store = memory_store or MemoryStore()
    workspace_root = str(Path(root_dir).expanduser().resolve())

    def _remember(memory: str) -> str:
        try:
            path = store.append(workspace_root=workspace_root, memory=memory)
        except ValueError as exc:
            return f"Error: {exc}"
        return f"Stored memory in auto-managed Ethos memory at {path}"

    return StructuredTool.from_function(
        name="remember",
        func=_remember,
        description=(
            "Store durable project memory in Ethos' auto-managed memory file. "
            "Use this when the user explicitly asks you to remember a preference, "
            "project convention, or durable correction. Never store secrets, API keys, "
            "passwords, or credentials."
        ),
        infer_schema=False,
        args_schema=RememberInput,
    )
