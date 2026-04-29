"""Reasoning/thinking capability helpers for chat models.

These helpers normalize UI-friendly reasoning settings into provider-specific
model kwargs while degrading safely when a provider/model is unlikely to
support them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


REASONING_MODEL_TOKENS = ("o1", "o3", "o4", "reason", "gpt-5", "gpt5")
OPENROUTER_REASONING_MODEL_TOKENS = (
    *REASONING_MODEL_TOKENS,
    "claude-3.7",
    "claude-4",
    "claude-opus-4",
    "claude-sonnet-4",
    "gemini-2.5",
    "gemini-3",
    "grok",
    "qwen3",
    "qwen-3",
    "thinking",
)


@dataclass(frozen=True)
class ReasoningCapabilities:
    """High-level reasoning/thinking support for a provider/model pair."""

    supports_reasoning_effort: bool = False
    supports_thinking_budget: bool = False
    supports_reasoning_output: bool = False
    effort_options: tuple[str, ...] = ()


def resolve_reasoning_capabilities(provider: str, model_name: str) -> ReasoningCapabilities:
    """Return coarse reasoning support based on provider/model heuristics.

    The result is intentionally conservative. Unknown providers return no
    support, but callers may still pass raw ``model_kwargs`` manually.
    """

    normalized_provider = provider.strip().lower()
    normalized_model = model_name.strip().lower()
    is_deepseek_v4 = "deepseek-v4" in normalized_model
    is_gpt5_family = "gpt-5" in normalized_model or "gpt5" in normalized_model

    if normalized_provider == "deepseek":
        supports_reasoning = is_deepseek_v4 or "reasoner" in normalized_model
        return ReasoningCapabilities(
            supports_reasoning_effort=supports_reasoning,
            supports_reasoning_output=supports_reasoning,
            effort_options=("none", "high", "max") if is_deepseek_v4 else ("low", "medium", "high"),
        )

    if normalized_provider == "openrouter":
        supports_reasoning = is_deepseek_v4 or any(
            token in normalized_model
            for token in OPENROUTER_REASONING_MODEL_TOKENS
        )
        return ReasoningCapabilities(
            supports_reasoning_effort=supports_reasoning,
            supports_reasoning_output=supports_reasoning,
            effort_options=("none", "minimal", "low", "medium", "high", "xhigh"),
        )

    if normalized_provider in {"openai", "together", "groq", "xai", "fireworks", "perplexity"}:
        supports_reasoning = any(
            token in normalized_model
            for token in REASONING_MODEL_TOKENS
        )
        return ReasoningCapabilities(
            supports_reasoning_effort=supports_reasoning,
            supports_reasoning_output=supports_reasoning,
            effort_options=("none", "low", "medium", "high") if is_gpt5_family else ("low", "medium", "high"),
        )

    if normalized_provider in {"azure_openai", "openai_compatible"}:
        supports_reasoning = any(
            token in normalized_model
            for token in REASONING_MODEL_TOKENS
        )
        return ReasoningCapabilities(
            supports_reasoning_effort=supports_reasoning,
            supports_reasoning_output=supports_reasoning,
            effort_options=("none", "low", "medium", "high") if is_gpt5_family else ("low", "medium", "high"),
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
    if effort not in capabilities.effort_options:
        effort = None

    if normalized_provider == "deepseek" and capabilities.supports_reasoning_effort:
        if effort == "none" or reasoning_enabled is False:
            return {"extra_body": {"thinking": {"type": "disabled"}}}

        if reasoning_enabled is not False:
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            if effort:
                kwargs["reasoning_effort"] = effort
        return kwargs

    if capabilities.supports_reasoning_effort and effort == "none":
        if normalized_provider in {"openai", "azure_openai", "openai_compatible", "openrouter"}:
            if normalized_provider == "openrouter":
                kwargs["extra_body"] = {"reasoning": {"effort": "none"}}
            else:
                kwargs["reasoning_effort"] = "none"
        return kwargs

    if capabilities.supports_reasoning_effort and reasoning_enabled is not False:
        if effort:
            if normalized_provider == "openrouter":
                kwargs["extra_body"] = {"reasoning": {"effort": effort}}
            else:
                kwargs["reasoning_effort"] = effort

    if normalized_provider == "anthropic" and capabilities.supports_thinking_budget and reasoning_enabled is not False:
        thinking: dict[str, Any] = {"type": "enabled"}
        if isinstance(thinking_budget_tokens, int) and thinking_budget_tokens > 0:
            thinking["budget_tokens"] = thinking_budget_tokens
        kwargs["thinking"] = thinking

    return kwargs
