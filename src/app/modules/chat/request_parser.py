"""ChatRequest parsing and extraction utilities.

Pure functions for extracting and validating data from incoming chat requests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from langgraph.types import Command

from src.ai.permissions import PermissionMode, PermissionSubject
from src.app.modules.chat.schemas import ChatRequest
from src.app.core.settings import Settings


_VALID_PROVIDERS = frozenset(
    {
        "openrouter",
        "anthropic",
        "openai",
        "azure_openai",
        "openai_compatible",
        "deepseek",
        "together",
        "groq",
        "xai",
        "fireworks",
        "perplexity",
        "google_genai",
        "bedrock",
    }
)


def extract_resume_command(request: ChatRequest) -> Command | None:
    """Return a LangGraph Command(resume=...) if the request carries a resume payload, else None."""
    metadata = getattr(request, "metadata", None) or {}
    resume_payload = metadata.get("resume")
    if resume_payload is None:
        return None
    return Command(resume=resume_payload)


def extract_resume_payload(request: ChatRequest) -> dict[str, Any] | None:
    """Extract raw resume payload from request metadata."""
    metadata = getattr(request, "metadata", None) or {}
    resume_payload = metadata.get("resume")
    if not isinstance(resume_payload, dict):
        return None
    return resume_payload


def resolve_model_id(model_id: str) -> str:
    """Validate model ID against registry, raise 404 if unknown."""
    from src.config import get_model_registry

    specs = get_model_registry()
    registry = {spec.id: spec for spec in specs}
    if model_id in registry:
        return model_id
    raise HTTPException(
        status_code=404,
        detail=f"Unknown model: {model_id!r}. Available: {sorted(registry.keys())}",
    )


def extract_file_ids(request: ChatRequest) -> list[str]:
    """De-duplicate file IDs from multiple request locations."""
    file_ids: list[str] = []
    seen: set[str] = set()

    def add_file_id(value: Any) -> None:
        if not isinstance(value, str) or not value or value in seen:
            return
        seen.add(value)
        file_ids.append(value)

    for file_id in request.file_ids:
        add_file_id(file_id)

    for item in request.files:
        add_file_id(item.get("id"))
        nested = item.get("file")
        if isinstance(nested, dict):
            add_file_id(nested.get("id"))

    metadata = request.metadata or {}
    extra_ids = metadata.get("file_ids")
    if isinstance(extra_ids, list):
        for file_id in extra_ids:
            add_file_id(file_id)

    return file_ids


def pick_edit_target(request: ChatRequest, file_ids: list[str]) -> str | None:
    """Choose primary file to edit from metadata or first file in list."""
    metadata = request.metadata or {}
    for key in ("target_file_id", "edit_target_file_id"):
        value = metadata.get(key)
        if isinstance(value, str):
            return value
    return file_ids[0] if file_ids else None


def extract_user_api_keys(request: ChatRequest) -> dict[str, str]:
    """Extract per-provider API keys from metadata."""
    metadata = request.metadata or {}
    raw_keys = metadata.get("user_api_keys")
    if not isinstance(raw_keys, dict):
        return {}

    result: dict[str, str] = {}
    for provider in ("openrouter", "anthropic", "openai"):
        value = raw_keys.get(provider)
        if isinstance(value, str) and value.strip():
            result[provider] = value.strip()
    return result


def extract_profile(request: ChatRequest, settings: Settings) -> dict | None:
    """Parse and validate custom provider profile from metadata.

    Raises HTTPException if custom endpoints are disallowed by settings.
    """
    metadata = request.metadata or {}
    raw = metadata.get("profile")
    if not isinstance(raw, dict):
        return None
    provider = str(raw.get("provider", "")).strip().lower()
    model = str(raw.get("model", "")).strip()
    if not provider or not model:
        return None
    if provider not in _VALID_PROVIDERS:
        return None
    api_key = str(raw.get("api_key", "")).strip()
    base_url = str(raw.get("base_url", "")).strip() or None
    deployment = str(raw.get("deployment", "")).strip() or None
    api_version = str(raw.get("api_version", "")).strip() or None
    reasoning_enabled_raw = raw.get("reasoning_enabled")
    reasoning_enabled = reasoning_enabled_raw if isinstance(reasoning_enabled_raw, bool) else None
    reasoning_effort = str(raw.get("reasoning_effort", "")).strip().lower() or None
    if reasoning_effort not in {None, "none", "minimal", "low", "medium", "high", "xhigh", "max"}:
        reasoning_effort = None
    thinking_budget_tokens_raw = raw.get("thinking_budget_tokens")
    thinking_budget_tokens = (
        thinking_budget_tokens_raw
        if isinstance(thinking_budget_tokens_raw, int) and thinking_budget_tokens_raw > 0
        else None
    )
    model_kwargs = raw.get("model_kwargs")
    if not isinstance(model_kwargs, dict):
        model_kwargs = None
    if provider == "openai_compatible" and base_url and not settings.allow_custom_provider_endpoints:
        raise HTTPException(status_code=403, detail="Custom provider endpoints are disabled")
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "deployment": deployment,
        "api_version": api_version,
        "reasoning_enabled": reasoning_enabled,
        "reasoning_effort": reasoning_effort,
        "thinking_budget_tokens": thinking_budget_tokens,
        "model_kwargs": model_kwargs,
    }


def extract_permission_override_mode(request: ChatRequest) -> PermissionMode | None:
    """Extract permission mode override from metadata."""
    metadata = request.metadata or {}
    raw_override = metadata.get("permission_override")
    if not isinstance(raw_override, dict):
        return None
    raw_mode = raw_override.get("mode")
    if not isinstance(raw_mode, str) or not raw_mode.strip():
        return None
    return PermissionMode(raw_mode.strip())


def resolve_resume_grant_matcher(resume_payload: dict[str, Any]) -> tuple[str, str, str] | None:
    """Extract and validate grant triple (scope, subject, matcher) from resume payload."""
    grant = resume_payload.get("grant")
    if not isinstance(grant, dict):
        return None
    scope = str(grant.get("scope", "")).strip().lower()
    subject = str(grant.get("subject", "")).strip().lower()
    matcher = grant.get("path")
    if not isinstance(matcher, str) or not matcher.strip():
        matcher = grant.get("command")
    if not isinstance(matcher, str) or not matcher.strip():
        return None
    if scope not in {"thread", "user"}:
        return None
    if subject not in {member.value for member in PermissionSubject}:
        return None
    return scope, subject, matcher.strip()


def extract_requested_thread_id(request: ChatRequest) -> str | None:
    """Extract thread ID from multiple possible request locations."""
    if request.thread_id and request.thread_id.strip():
        return request.thread_id.strip()
    if request.chat_id and request.chat_id.strip():
        return request.chat_id.strip()
    if request.session_id and request.session_id.strip():
        return request.session_id.strip()
    metadata = request.metadata or {}
    for key in ("session_id", "chat_id", "conversation_id", "thread_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_backend_selection(request: ChatRequest) -> tuple[str, str | None]:
    """Extract backend mode and optional root directory from metadata."""
    metadata = request.metadata or {}
    raw_backend = metadata.get("backend")
    if not isinstance(raw_backend, dict):
        return "sandbox", None

    mode = str(raw_backend.get("mode", "sandbox")).strip().lower()
    if mode not in {"sandbox", "local"}:
        return "sandbox", None

    root_dir = raw_backend.get("root_dir")
    if isinstance(root_dir, str) and root_dir.strip():
        return mode, root_dir.strip()
    return mode, None
