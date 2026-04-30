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


class ThreadMessagePayload(BaseModel):
    id: str
    role: str
    content: str
    reasoning: str | None = None
    created_at: str
    status: str = "done"
    tool_events: list[str] = Field(default_factory=list)
    workspace_frames: list[dict[str, Any]] = Field(default_factory=list)
    stream_items: list[dict[str, Any]] = Field(default_factory=list)


class ThreadPayload(BaseModel):
    id: str
    user_id: str
    title: str | None = None
    summary: str | None = None
    created_at: int
    updated_at: int
    last_message_at: int | None = None
    workspace_root: str | None = None
    backend: str | None = None
    status: str = "idle"
    active_run_id: str | None = None
    run_started_at: int | None = None
    last_stop_run_id: str | None = None
    last_stop_reason: str | None = None
    last_interrupted_at: int | None = None
    model: str | None = None
    mode: str | None = None
    profile_id: str | None = None
    project: str | None = None
    is_favorite: bool = False
    permission_overlay: dict[str, Any] = Field(default_factory=dict)
    messages: list[ThreadMessagePayload] = Field(default_factory=list)


class ThreadListPayload(BaseModel):
    threads: list[ThreadPayload]


class ThreadUpdatePayload(BaseModel):
    title: str | None = None
    summary: str | None = None
    model: str | None = None
    mode: str | None = None
    profile_id: str | None = None
    project: str | None = None
    is_favorite: bool | None = None


class StopRunPayload(BaseModel):
    reason: str = "user_cancel"


class ContextStatusRequest(BaseModel):
    thread_id: str
    model: str
    context_window: int | None = None


class ActivatedRulePayload(BaseModel):
    path: str
    name: str
    source: str
    tokens: int


class ContextCategoryPayload(BaseModel):
    key: str
    label: str
    tokens: int
    percent: float
    source: str | None = None


class ContextGridSquarePayload(BaseModel):
    category_key: str
    category_label: str
    tokens: int


class ContextSuggestionPayload(BaseModel):
    severity: str
    title_key: str
    detail_key: str
    tokens: int = 0


class ContextStatusPayload(BaseModel):
    context_window: int
    used_tokens: int
    percent_used: int
    categories: list[ContextCategoryPayload] = Field(default_factory=list)
    grid_rows: list[list[ContextGridSquarePayload]] = Field(default_factory=list)
    suggestions: list[ContextSuggestionPayload] = Field(default_factory=list)
    activated_rules: list[ActivatedRulePayload] = Field(default_factory=list)
    is_estimated: bool = True


__all__ = [
    "ChatRequest",
    "ContextStatusPayload",
    "ContextStatusRequest",
    "Message",
    "ThreadListPayload",
    "ThreadMessagePayload",
    "ThreadPayload",
    "ThreadUpdatePayload",
    "StopRunPayload",
]
