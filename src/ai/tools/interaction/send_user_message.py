"""send_user_message tool — send a message to the user.

Mirrors BriefTool (legacy alias SendUserMessage) from claude-code-source.
Two execution modes:
  - use_interrupt=True  (LangGraph/API): pushes message as an interrupt event so
    the frontend/API receives it as a structured notification, then resumes.
  - use_interrupt=False (CLI/test): calls output_fn (default: print).
"""
from __future__ import annotations

from typing import Callable, Optional

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field


class SendUserMessageInput(BaseModel):
    message: str = Field(description="The message to display to the user.")


def build_send_user_message_tool(
    output_fn: Optional[Callable[[str], None]] = None,
    use_interrupt: bool = False,
) -> StructuredTool:
    """Build send_user_message tool.

    Args:
        output_fn: Custom output function for CLI/test mode (default: print).
        use_interrupt: When True, push the message via LangGraph interrupt() so the
            host receives it as a structured notification event before resuming.
    """
    fn = output_fn or print

    def _send(message: str) -> str:
        if use_interrupt:
            interrupt({"behavior": "notify", "message": message})
        else:
            fn(message)
        return "Message sent."

    return StructuredTool.from_function(
        name="send_user_message",
        func=_send,
        description=(
            "Send a message or update to the user outside of the normal response flow. "
            "Use for progress updates, warnings, or notifications during long tasks."
        ),
        args_schema=SendUserMessageInput,
    )
