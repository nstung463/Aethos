"""Reasoning/thinking capability helpers for chat models.

These helpers normalize UI-friendly reasoning settings into provider-specific
model kwargs while degrading safely when a provider/model is unlikely to
support them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ReasoningCapabilities:
    """High-level reasoning/thinking support for a provider/model pair."""

    supports_reasoning_effort: bool = False
    supports_thinking_budget: bool = False
    supports_reasoning_output: bool = False


def resolve_reasoning_capabilities(provider: str, model_name: str) -> ReasoningCapabilities:
    """Return coarse reasoning support based on provider/model heuristics.

    The result is intentionally conservative. Unknown providers return no
    support, but callers may still pass raw ``model_kwargs`` manually.
    """

    normalized_provider = provider.strip().lower()
    normalized_model = model_name.strip().lower()

    if normalized_provider in {"openai", "openrouter", "deepseek", "together", "groq", "xai", "fireworks", "perplexity"}:
        supports_reasoning = any(
            token in normalized_model
            for token in ("o1", "o3", "o4", "reason", "gpt-5", "gpt5")
        )
        return ReasoningCapabilities(
            supports_reasoning_effort=supports_reasoning,
            supports_reasoning_output=supports_reasoning,
        )

    if normalized_provider in {"azure_openai", "openai_compatible"}:
        supports_reasoning = any(
            token in normalized_model
            for token in ("o1", "o3", "o4", "reason", "gpt-5", "gpt5")
        )
        return ReasoningCapabilities(
            supports_reasoning_effort=supports_reasoning,
            supports_reasoning_output=supports_reasoning,
        )

    if normalized_provider == "anthropic":
        is_claude = "claude" in normalized_model
        return ReasoningCapabilities(
            supports_thinking_budget=is_claude,
            supports_reasoning_output=is_claude,
        )

    if normalized_provider in {"google_genai", "bedrock"}:
        return ReasoningCapabilities()

    return ReasoningCapabilities()


def sanitize_model_kwargs(value: Any) -> dict[str, Any]:
    """Return a shallow dict with string keys from arbitrary input."""

    if not isinstance(value, Mapping):
        return {}

    result: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        result[key] = item
    return result


def build_reasoning_model_kwargs(
    *,
    provider: str,
    model_name: str,
    reasoning_enabled: bool | None,
    reasoning_effort: str | None,
    thinking_budget_tokens: int | None,
) -> dict[str, Any]:
    """Map common reasoning controls to provider-specific model kwargs."""

    capabilities = resolve_reasoning_capabilities(provider, model_name)
    normalized_provider = provider.strip().lower()
    kwargs: dict[str, Any] = {}

    effort = (reasoning_effort or "").strip().lower() or None
    if effort not in {"low", "medium", "high"}:
        effort = None

    if capabilities.supports_reasoning_effort and reasoning_enabled is not False:
        if effort:
            kwargs["reasoning_effort"] = effort

    if normalized_provider == "anthropic" and capabilities.supports_thinking_budget and reasoning_enabled is not False:
        thinking: dict[str, Any] = {"type": "enabled"}
        if isinstance(thinking_budget_tokens, int) and thinking_budget_tokens > 0:
            thinking["budget_tokens"] = thinking_budget_tokens
        kwargs["thinking"] = thinking

    return kwargs

