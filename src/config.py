"""LLM configuration — multi-provider via init_chat_model.

Supports:
- Native providers via ``init_chat_model`` (e.g. anthropic, openai)
- Common aliases to native providers:
  gemini -> google_genai, amazon -> bedrock, azure -> azure_openai
- Popular OpenAI-compatible providers via aliases:
  openrouter, deepseek, together, groq, xai, fireworks, perplexity
- Multiple logical models for Open WebUI: set ``ETHOS_MODEL_REGISTRY`` (JSON array).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from src.ai.reasoning import build_reasoning_model_kwargs, sanitize_model_kwargs
from src.logger import get_logger

logger = get_logger(__name__)

PROVIDER_ALIASES = {
    "gemini": "google_genai",
    "google": "google_genai",
    "amazon": "bedrock",
    "bedrock": "bedrock",
    "azure": "azure_openai",
}

OPENAI_COMPATIBLE_PROVIDERS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "base_url_env": "OPENROUTER_BASE_URL",
        "api_key_env": "OPENROUTER_API_KEY",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "base_url_env": "TOGETHER_BASE_URL",
        "api_key_env": "TOGETHER_API_KEY",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "base_url_env": "GROQ_BASE_URL",
        "api_key_env": "GROQ_API_KEY",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "base_url_env": "XAI_BASE_URL",
        "api_key_env": "XAI_API_KEY",
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "base_url_env": "FIREWORKS_BASE_URL",
        "api_key_env": "FIREWORKS_API_KEY",
    },
    "perplexity": {
        "base_url": "https://api.perplexity.ai",
        "base_url_env": "PERPLEXITY_BASE_URL",
        "api_key_env": "PERPLEXITY_API_KEY",
    },
}

REQUEST_API_KEY_FIELDS = {
    "openrouter": "openrouter",
    "anthropic": "anthropic",
    "openai": "openai",
    "azure_openai": "openai",
}


@dataclass(frozen=True)
class ModelSpec:
    """One Open WebUI /v1/models entry backed by a concrete provider + model id."""

    id: str
    provider: str
    model: str
    base_url: str | None = None
    api_version: str | None = None
    deployment: str | None = None
    extra_headers: dict[str, str] | None = None


@dataclass(frozen=True)
class MCPServerSpec:
    """One MCP server configuration exposed to Ethos tools."""

    name: str
    connection: dict[str, Any]
    auth_url: str | None = None


def resolve_request_api_key(provider: str, api_keys: Mapping[str, str] | None = None) -> str:
    """Resolve an optional per-request API key for the given provider."""
    if not api_keys:
        return ""

    provider = provider.strip().lower()
    provider = PROVIDER_ALIASES.get(provider, provider)
    field = REQUEST_API_KEY_FIELDS.get(provider)
    if not field:
        return ""

    value = api_keys.get(field, "")
    return value.strip() if isinstance(value, str) else ""


def build_chat_model(
    provider: str,
    model_name: str,
    *,
    api_keys: Mapping[str, str] | None = None,
    base_url: str | None = None,
    api_version: str | None = None,
    deployment: str | None = None,
    reasoning_enabled: bool | None = None,
    reasoning_effort: str | None = None,
    thinking_budget_tokens: int | None = None,
    model_kwargs: Mapping[str, Any] | None = None,
) -> BaseChatModel:
    """Build a chat model from provider id and model name (init_chat_model style)."""
    provider = provider.strip().lower()
    provider = PROVIDER_ALIASES.get(provider, provider)
    logger.info("Building chat model (provider=%s, model=%s)", provider, model_name)
    merged_model_kwargs = sanitize_model_kwargs(model_kwargs)
    merged_model_kwargs.update(
        build_reasoning_model_kwargs(
            provider=provider,
            model_name=model_name,
            reasoning_enabled=reasoning_enabled,
            reasoning_effort=reasoning_effort,
            thinking_budget_tokens=thinking_budget_tokens,
        )
    )

    # Per-request API key (from profile or legacy user_api_keys)
    request_api_key = ""
    if api_keys:
        # Profile path sends {"api_key": "..."}, legacy sends {"openrouter": "...", ...}
        direct = api_keys.get("api_key", "")
        request_api_key = direct.strip() if direct else resolve_request_api_key(provider, api_keys)

    # openai_compatible: arbitrary base_url from profile (required)
    if provider == "openai_compatible":
        if not base_url:
            raise ValueError("openai_compatible provider requires base_url")
        kwargs: dict[str, Any] = {"base_url": base_url, "temperature": 0.0}
        kwargs.update(merged_model_kwargs)
        if request_api_key:
            kwargs["api_key"] = request_api_key
        return init_chat_model(f"openai:{model_name}", **kwargs)

    if provider in OPENAI_COMPATIBLE_PROVIDERS:
        conf = OPENAI_COMPATIBLE_PROVIDERS[provider]
        resolved_base = base_url or os.getenv(conf["base_url_env"], conf["base_url"])
        api_key = request_api_key or os.getenv(conf["api_key_env"], "")
        kwargs = {"base_url": resolved_base, "temperature": 0.0}
        kwargs.update(merged_model_kwargs)
        if api_key:
            kwargs["api_key"] = api_key
        return init_chat_model(f"openai:{model_name}", **kwargs)

    if provider == "azure_openai":
        resolved_version = (
            api_version
            or os.getenv("AZURE_OPENAI_API_VERSION")
            or os.getenv("OPENAI_API_VERSION")
            or "2024-12-01-preview"
        )
        kwargs = {"temperature": 0.0, "api_version": resolved_version}
        kwargs.update(merged_model_kwargs)
        if base_url:
            kwargs["azure_endpoint"] = base_url
        if deployment:
            kwargs["azure_deployment"] = deployment
        if request_api_key:
            kwargs["api_key"] = request_api_key
        return init_chat_model(f"azure_openai:{model_name}", **kwargs)

    kwargs = {"temperature": 0.0}
    kwargs.update(merged_model_kwargs)
    if request_api_key:
        kwargs["api_key"] = request_api_key
    return init_chat_model(f"{provider}:{model_name}", **kwargs)


def get_model_registry() -> list[ModelSpec]:
    """Models exposed at GET /v1/models (e.g. Open WebUI dropdown).

    If ``ETHOS_MODEL_REGISTRY`` is unset or empty, uses a single model from
    ``ETHOS_PROVIDER`` + ``ETHOS_MODEL`` with id ``ethos`` (defaults: openrouter +
    ``openai/gpt-4o-mini``).

    ``ETHOS_MODEL_REGISTRY`` format (JSON array)::

        [
          {"id": "ethos", "provider": "openrouter", "model": "openai/gpt-4o-mini"},
          {"id": "ethos-azure", "provider": "azure", "model": "gpt-4o"}
        ]
    """
    raw = os.getenv("ETHOS_MODEL_REGISTRY", "").strip()
    if not raw:
        return [
            ModelSpec(
                id="ethos",
                provider=os.getenv("ETHOS_PROVIDER", "openrouter").strip().lower(),
                model=os.getenv("ETHOS_MODEL", "openai/gpt-4o-mini"),
            )
        ]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"ETHOS_MODEL_REGISTRY must be valid JSON: {e}") from e
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("ETHOS_MODEL_REGISTRY must be a non-empty JSON array")

    out: list[ModelSpec] = []
    seen: set[str] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"ETHOS_MODEL_REGISTRY[{i}] must be an object")
        mid = str(item.get("id", "")).strip()
        prov = str(item.get("provider", "")).strip().lower()
        mname = str(item.get("model", "")).strip()
        if not mid or not prov or not mname:
            raise ValueError(
                f"ETHOS_MODEL_REGISTRY[{i}] requires non-empty id, provider, and model"
            )
        if mid in seen:
            raise ValueError(f"Duplicate model id in ETHOS_MODEL_REGISTRY: {mid}")
        seen.add(mid)
        out.append(ModelSpec(id=mid, provider=prov, model=mname))
    return out


def get_model() -> BaseChatModel:
    """Resolve the default LLM from ETHOS_PROVIDER / ETHOS_MODEL (single-model mode)."""
    specs = get_model_registry()
    # When registry is single default from env, use it; else first entry for CLI tools.
    spec = specs[0]
    return build_chat_model(spec.provider, spec.model)


def get_workspace() -> str:
    """Return the workspace root directory."""
    return os.getenv("ETHOS_WORKSPACE", "./workspace")


def get_mcp_servers() -> list[MCPServerSpec]:
    """Return MCP server configurations from ETHOS_MCP_SERVERS.

    Supported formats:

    1. Object map:
        {
          "docs": {"transport": "streamable_http", "url": "https://example/mcp", "auth_url": "https://example/login"}
        }

    2. Array:
        [
          {"name": "docs", "transport": "streamable_http", "url": "https://example/mcp"}
        ]
    """
    raw = os.getenv("ETHOS_MCP_SERVERS", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"ETHOS_MCP_SERVERS must be valid JSON: {e}") from e

    items: list[tuple[str, dict[str, Any]]]
    if isinstance(data, dict):
        items = []
        for name, config in data.items():
            if not isinstance(config, dict):
                raise ValueError(f"ETHOS_MCP_SERVERS['{name}'] must be an object")
            items.append((str(name), dict(config)))
    elif isinstance(data, list):
        items = []
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f"ETHOS_MCP_SERVERS[{idx}] must be an object")
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError(f"ETHOS_MCP_SERVERS[{idx}] requires non-empty 'name'")
            config = dict(item)
            config.pop("name", None)
            items.append((name, config))
    else:
        raise ValueError("ETHOS_MCP_SERVERS must be a JSON object or array")

    servers: list[MCPServerSpec] = []
    seen: set[str] = set()
    for name, config in items:
        if name in seen:
            raise ValueError(f"Duplicate MCP server name: {name}")
        seen.add(name)
        auth_url = config.pop("auth_url", None)
        if auth_url is not None and not isinstance(auth_url, str):
            raise ValueError(f"auth_url for MCP server '{name}' must be a string")
        transport = str(config.get("transport", "")).strip()
        if not transport:
            raise ValueError(f"MCP server '{name}' requires 'transport'")
        servers.append(MCPServerSpec(name=name, connection=config, auth_url=auth_url))
    return servers
