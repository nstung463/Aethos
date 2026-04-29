"""Chat completion request and message models."""

from typing import Any

from pydantic import AliasChoices, BaseModel, Field

from src.config import get_model_registry


class Message(BaseModel):
    """OpenAI-compatible message."""

    role: str
    content: str
    tool_call_id: str | None = None
    reasoning_content: str | None = Field(
        default=None,
        validation_alias=AliasChoices("reasoning_content", "reasoning"),
    )


def _default_openai_model_id() -> str:
    """Default ``model`` field: first id in registry."""

    return get_model_registry()[0].id


class ChatRequest(BaseModel):
    """OpenAI-compatible chat completion request."""

    model: str = Field(default_factory=_default_openai_model_id)
    messages: list[Message]
    stream: bool = False
    thread_id: str | None = None
    session_id: str | None = None
    chat_id: str | None = None
    file_ids: list[str] = Field(default_factory=list)
    files: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


__all__ = ["ChatRequest", "Message"]
