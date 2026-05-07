"""Shared middleware utilities."""

from __future__ import annotations

from typing import Any, Protocol

from langchain_core.messages import BaseMessage, SystemMessage


class RequestWithSystemPrompt(Protocol):
    """Protocol for the request attributes used by middleware prompt injection."""

    system_prompt: str | None
    state: dict[str, Any]

    def override(self, **kwargs: Any) -> Any: ...


def append_to_system_prompt(sys_prompt: str | None, text: str) -> str:
    """Append text to a string system prompt, creating one if needed."""
    if not sys_prompt:
        return text
    return sys_prompt + "\n\n" + text


def append_to_system_message(sys_msg: BaseMessage | None, text: str) -> SystemMessage:
    """Append text to a message-based system prompt, creating one if needed."""
    if sys_msg is None:
        return SystemMessage(content=text)

    content = sys_msg.content
    if isinstance(content, str):
        return SystemMessage(content=content + "\n\n" + text)

    return SystemMessage(content=[*content, {"type": "text", "text": "\n\n" + text}])


def append_system_section(request: RequestWithSystemPrompt, text: str) -> Any:
    """Append a section to whichever system prompt shape the request uses."""
    if hasattr(request, "system_prompt"):
        return request.override(system_prompt=append_to_system_prompt(request.system_prompt, text))

    legacy_system_message = getattr(request, "system_message", None)
    return request.override(system_message=append_to_system_message(legacy_system_message, text))
