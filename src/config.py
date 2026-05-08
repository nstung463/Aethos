"""LLM configuration — multi-provider via init_chat_model.

Supports:
- Native providers via ``init_chat_model`` (e.g. anthropic, openai)
- Common aliases to native providers:
  gemini -> google_genai, amazon -> bedrock, azure -> azure_openai
- Popular OpenAI-compatible providers via aliases:
  openrouter, deepseek, together, groq, xai, fireworks, perplexity
- Multiple logical models for Open WebUI: set ``AETHOS_MODEL_REGISTRY`` (JSON array).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.parse import urlsplit
from typing import Any, Mapping

import httpx
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_openai import ChatOpenAI

from src.ai.reasoning import build_reasoning_model_kwargs, sanitize_model_kwargs
from src.app.services.settings import SettingsService
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
        "base_url": "https://api.deepseek.com/",
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
    """One MCP server configuration exposed to Aethos tools."""

    name: str
    connection: dict[str, Any]
    auth_url: str | None = None
    instructions: str | None = None
    source: str | None = None


_BLOCKED_PROVIDER_HEADERS = {
    b"x-stainless-lang", b"x-stainless-package-version", b"x-stainless-os",
    b"x-stainless-arch", b"x-stainless-runtime", b"x-stainless-runtime-version",
    b"x-stainless-async", b"x-stainless-retry-count", b"user-agent",
}


class _StripStainlessTransport(httpx.HTTPTransport):
    """Drop X-Stainless-* and OpenAI SDK User-Agent headers that some providers block."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        clean = [(k, v) for k, v in request.headers.raw if k.lower() not in _BLOCKED_PROVIDER_HEADERS]
        request = httpx.Request(request.method, request.url, headers=clean, content=request.content)
        return super().handle_request(request)


class _AsyncStripStainlessTransport(httpx.AsyncHTTPTransport):
    """Async version: drop X-Stainless-* and OpenAI SDK User-Agent headers."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        clean = [(k, v) for k, v in request.headers.raw if k.lower() not in _BLOCKED_PROVIDER_HEADERS]
        request = httpx.Request(request.method, request.url, headers=clean, content=request.content)
        return await super().handle_async_request(request)


def _compat_http_clients() -> tuple[httpx.Client, httpx.AsyncClient]:
    """Sync + async httpx clients that strip X-Stainless-* headers for third-party provider compat."""
    return (
        httpx.Client(transport=_StripStainlessTransport()),
        httpx.AsyncClient(transport=_AsyncStripStainlessTransport()),
    )


class DeepSeekChatOpenAI(ChatOpenAI):
    """ChatOpenAI variant that preserves DeepSeek thinking-mode tool reasoning."""

    def _create_chat_result(self, response: Any, generation_info: dict | None = None):
        result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(
                exclude={"choices": {"__all__": {"message": {"parsed"}}}}
            )
        )
        for index, choice in enumerate(response_dict.get("choices", [])):
            if index >= len(result.generations):
                break
            reasoning_content = (choice.get("message") or {}).get("reasoning_content")
            message = result.generations[index].message
            if reasoning_content and isinstance(message, AIMessage):
                message.additional_kwargs["reasoning_content"] = reasoning_content
        return result

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict:
        messages = self._convert_input(input_).to_messages()
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        payload_messages = payload.get("messages")
        if not isinstance(payload_messages, list):
            return payload

        for source_message, payload_message in zip(messages, payload_messages, strict=False):
            if not isinstance(source_message, AIMessage) or not isinstance(payload_message, dict):
                continue
            reasoning_content = source_message.additional_kwargs.get("reasoning_content")
            if reasoning_content and payload_message.get("role") == "assistant":
                payload_message["reasoning_content"] = reasoning_content
        return payload

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ):
        generation_chunk = super()._convert_chunk_to_generation_chunk(
            chunk,
            default_chunk_class,
            base_generation_info,
        )
        if generation_chunk is None:
            return None
        choices = chunk.get("choices", []) or chunk.get("chunk", {}).get("choices", [])
        if not choices:
            return generation_chunk
        delta = choices[0].get("delta") or {}
        reasoning_content = delta.get("reasoning_content")
        if reasoning_content and isinstance(generation_chunk.message, AIMessageChunk):
            existing_reasoning = generation_chunk.message.additional_kwargs.get("reasoning_content")
            if not isinstance(existing_reasoning, str):
                generation_chunk.message.additional_kwargs["reasoning_content"] = reasoning_content
            elif not existing_reasoning.endswith(reasoning_content):
                generation_chunk.message.additional_kwargs["reasoning_content"] = existing_reasoning + reasoning_content
        return generation_chunk


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
        sync_client, async_client = _compat_http_clients()
        kwargs: dict[str, Any] = {
            "base_url": base_url,
            "temperature": 0.0,
            "http_client": sync_client,
            "http_async_client": async_client,
        }
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
        if provider == "deepseek":
            return DeepSeekChatOpenAI(model=model_name, **kwargs)
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

    If ``AETHOS_MODEL_REGISTRY`` is unset or empty, uses a single model from
    ``AETHOS_PROVIDER`` + ``AETHOS_MODEL`` with id ``aethos`` (defaults: openrouter +
    ``openai/gpt-4o-mini``).

    ``AETHOS_MODEL_REGISTRY`` format (JSON array)::

        [
          {"id": "aethos", "provider": "openrouter", "model": "openai/gpt-4o-mini"},
          {"id": "aethos-azure", "provider": "azure", "model": "gpt-4o"}
        ]
    """
    raw = os.getenv("AETHOS_MODEL_REGISTRY", "").strip()
    if not raw:
        return [
            ModelSpec(
                id="aethos",
                provider=os.getenv("AETHOS_PROVIDER", "openrouter").strip().lower(),
                model=os.getenv("AETHOS_MODEL", "openai/gpt-4o-mini"),
            )
        ]
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AETHOS_MODEL_REGISTRY must be valid JSON: {e}") from e
    if not isinstance(data, list) or len(data) == 0:
        raise ValueError("AETHOS_MODEL_REGISTRY must be a non-empty JSON array")

    out: list[ModelSpec] = []
    seen: set[str] = set()
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"AETHOS_MODEL_REGISTRY[{i}] must be an object")
        mid = str(item.get("id", "")).strip()
        prov = str(item.get("provider", "")).strip().lower()
        mname = str(item.get("model", "")).strip()
        if not mid or not prov or not mname:
            raise ValueError(
                f"AETHOS_MODEL_REGISTRY[{i}] requires non-empty id, provider, and model"
            )
        if mid in seen:
            raise ValueError(f"Duplicate model id in AETHOS_MODEL_REGISTRY: {mid}")
        seen.add(mid)
        out.append(ModelSpec(id=mid, provider=prov, model=mname))
    return out


def get_model() -> BaseChatModel:
    """Resolve the default LLM from AETHOS_PROVIDER / AETHOS_MODEL (single-model mode)."""
    specs = get_model_registry()
    # When registry is single default from env, use it; else first entry for CLI tools.
    spec = specs[0]
    return build_chat_model(spec.provider, spec.model)


def get_workspace() -> str:
    """Return the workspace root directory."""
    return os.getenv("AETHOS_WORKSPACE", "./workspace")


_SUPPORTED_TRANSPORTS = frozenset({"stdio", "sse", "http", "streamable_http", "websocket"})
_CLAUDE_TYPE_TO_TRANSPORT = {
    "stdio": "stdio",
    "sse": "sse",
    "http": "http",
    "ws": "websocket",
    "websocket": "websocket",
}

_logger_cfg = logger  # reuse module-level logger


def _parse_mcp_items(
    items: list[tuple[str, dict[str, Any]]],
    source_label: str = "config",
    source_kind: str | None = None,
) -> list[MCPServerSpec]:
    """Convert a list of (name, raw_config) pairs into validated MCPServerSpec objects.

    Supported transports: stdio, sse, http / streamable_http, websocket.
    ``auth_url`` and ``instructions`` are extracted as top-level fields; the
    remaining dict becomes ``connection`` and is passed verbatim to
    MultiServerMCPClient.
    """
    servers: list[MCPServerSpec] = []
    seen: set[str] = set()
    for name, config in items:
        if name in seen:
            raise ValueError(f"Duplicate MCP server name in {source_label}: {name!r}")
        seen.add(name)
        config = dict(config)
        http_url = config.pop("httpUrl", None)
        if http_url is not None:
            if not isinstance(http_url, str):
                raise ValueError(f"httpUrl for MCP server {name!r} must be a string")
            config.setdefault("url", http_url)
        auth_url = config.pop("auth_url", None)
        if auth_url is not None and not isinstance(auth_url, str):
            raise ValueError(f"auth_url for MCP server {name!r} must be a string")
        instructions = config.pop("instructions", None)
        if instructions is not None and not isinstance(instructions, str):
            raise ValueError(f"instructions for MCP server {name!r} must be a string")
        transport = str(config.get("transport", "")).strip()
        if not transport:
            claude_type = str(config.get("type", "")).strip().lower()
            if claude_type:
                transport = _CLAUDE_TYPE_TO_TRANSPORT.get(claude_type, "")
                if not transport:
                    raise ValueError(
                        f"MCP server {name!r} has unsupported Claude-style type {claude_type!r}. "
                        f"Supported: {', '.join(sorted(_CLAUDE_TYPE_TO_TRANSPORT))}"
                    )
            elif "command" in config:
                transport = "stdio"
            elif "url" in config and "oauth" in config:
                transport = "streamable_http"
            else:
                raise ValueError(f"MCP server {name!r} requires 'transport'")
        config["transport"] = transport
        if transport not in _SUPPORTED_TRANSPORTS:
            raise ValueError(
                f"MCP server {name!r} has unsupported transport {transport!r}. "
                f"Supported: {', '.join(sorted(_SUPPORTED_TRANSPORTS))}"
            )
        servers.append(
            MCPServerSpec(
                name=name,
                connection=config,
                auth_url=auth_url,
                instructions=instructions,
                source=source_kind,
            )
        )
    return servers


def _parse_mcp_data(data: Any, source_label: str, *, source_kind: str | None = None) -> list[MCPServerSpec]:
    """Parse a decoded JSON value (dict or list) into MCPServerSpec objects."""
    if isinstance(data, dict):
        items: list[tuple[str, dict[str, Any]]] = []
        for name, config in data.items():
            if not isinstance(config, dict):
                raise ValueError(f"{source_label}[{name!r}] must be an object")
            items.append((str(name), dict(config)))
        return _parse_mcp_items(items, source_label, source_kind)
    if isinstance(data, list):
        items = []
        for idx, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(f"{source_label}[{idx}] must be an object")
            name = str(item.get("name", "")).strip()
            if not name:
                raise ValueError(f"{source_label}[{idx}] requires non-empty 'name'")
            config = dict(item)
            config.pop("name", None)
            items.append((name, config))
        return _parse_mcp_items(items, source_label, source_kind)
    raise ValueError(f"{source_label} must be a JSON object or array")


def _parse_mcp_env_var() -> list[MCPServerSpec]:
    raw = os.getenv("AETHOS_MCP_SERVERS", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AETHOS_MCP_SERVERS must be valid JSON: {e}") from e
    return _parse_mcp_data(data, "AETHOS_MCP_SERVERS", source_kind="env")


def _native_provider_for_mcp_server(spec: MCPServerSpec) -> str | None:
    oauth = spec.connection.get("oauth")
    scopes = oauth.get("scopes") if isinstance(oauth, dict) else None
    if isinstance(scopes, list):
        normalized_scopes = {
            str(scope).strip().lower()
            for scope in scopes
            if isinstance(scope, str) and scope.strip()
        }
        if any("gmail" in scope for scope in normalized_scopes):
            return "google-gmail"
        if any("spreadsheets" in scope for scope in normalized_scopes):
            return "google-sheets"
        if any("calendar" in scope for scope in normalized_scopes):
            return "google-calendar"
        if any("drive" in scope for scope in normalized_scopes):
            return "google-drive"
        if normalized_scopes and all(
            any(prefix in scope for prefix in ("channels:", "groups:", "chat:", "search:"))
            for scope in normalized_scopes
        ):
            return "slack"

    url = spec.connection.get("url")
    if isinstance(url, str) and url.strip():
        host = urlsplit(url).netloc.lower()
        if "gmailmcp.googleapis.com" in host:
            return "google-gmail"
        if "drivemcp.googleapis.com" in host:
            return "google-drive"
        if "calendarmcp.googleapis.com" in host:
            return "google-calendar"
        if "sheetsmcp.googleapis.com" in host:
            return "google-sheets"
        if "slack.com" in host:
            return "slack"

    return None


def _filter_native_connection_mcp_servers(
    servers: list[MCPServerSpec],
    *,
    workspace: str,
    owner_user_id: str | None,
    include_project_settings: bool,
) -> list[MCPServerSpec]:
    if not owner_user_id or not servers:
        return servers

    from src.app.services.connections import ConnectionService

    service = ConnectionService(
        workspace_root=workspace,
        scope="project" if include_project_settings else "user",
    )
    enabled_providers = {
        item.provider
        for item in service.list_effective_connections(owner_user_id=owner_user_id)
        if item.status == "active" and item.tools_enabled
    }
    if not enabled_providers:
        return [server for server in servers if _native_provider_for_mcp_server(server) is None]

    filtered: list[MCPServerSpec] = []
    for server in servers:
        provider = _native_provider_for_mcp_server(server)
        if provider is None or provider in enabled_providers:
            filtered.append(server)
    return filtered


def _settings_path(workspace: str) -> "Path":
    return SettingsService().get_settings_file_path("project", workspace_root=workspace)


def _mcp_json_path(workspace: str) -> "Path":
    from pathlib import Path

    return Path(workspace).expanduser().resolve() / ".mcp.json"


def _load_mcp_from_settings(workspace: str) -> list[MCPServerSpec]:
    """Load MCP servers from ``{workspace}/.aethos/settings.json`` (Claude Code-compatible format).

    The file uses the ``mcpServers`` key (object map format).  Errors are
    logged and silently swallowed so a malformed file never crashes the agent.
    """
    path = _settings_path(workspace)
    try:
        data = SettingsService().get_settings_for_source("project", workspace_root=workspace)
        mcp_raw = data.get("mcpServers") if isinstance(data, dict) else None
        if not mcp_raw:
            return []
        return _parse_mcp_data(mcp_raw, f"{path}:mcpServers", source_kind="settings")
    except Exception as exc:
        _logger_cfg.warning("Failed to load MCP servers from %s: %s", path, exc)
        return []


def _load_mcp_from_mcp_json(workspace: str) -> list[MCPServerSpec]:
    """Load MCP servers from ``{workspace}/.mcp.json`` using Claude-style shape."""
    path = _mcp_json_path(workspace)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _logger_cfg.warning("Failed to load MCP servers from %s: %s", path, exc)
        return []
    if not isinstance(data, dict):
        _logger_cfg.warning("Ignoring non-object MCP config from %s", path)
        return []
    mcp_raw = data.get("mcpServers")
    if not mcp_raw:
        return []
    try:
        return _parse_mcp_data(mcp_raw, f"{path}:mcpServers", source_kind="mcp_json")
    except Exception as exc:
        _logger_cfg.warning("Failed to parse MCP servers from %s: %s", path, exc)
        return []


def save_mcp_server_to_settings(workspace: str, spec: MCPServerSpec) -> None:
    """Upsert *spec* into ``{workspace}/.aethos/settings.json``.

    Creates the file and parent directories if they do not exist.
    Existing servers with the same name are overwritten.
    """
    service = SettingsService()
    data = service.get_settings_for_source("project", workspace_root=workspace)
    servers: dict[str, Any] = data.get("mcpServers") or {}
    if not isinstance(servers, dict):
        servers = {}
    entry: dict[str, Any] = dict(spec.connection)
    if spec.auth_url:
        entry["auth_url"] = spec.auth_url
    if spec.instructions:
        entry["instructions"] = spec.instructions
    servers[spec.name] = entry
    service.update_settings_for_source(
        "project",
        {"mcpServers": servers},
        workspace_root=workspace,
    )


def _connection_to_claude_mcp_entry(spec: MCPServerSpec) -> dict[str, Any]:
    entry: dict[str, Any] = dict(spec.connection)
    transport = str(entry.pop("transport", "")).strip()
    if transport in {"http", "streamable_http"} and "url" in entry and "oauth" in entry:
        entry["httpUrl"] = entry.pop("url")
    if transport == "stdio":
        entry.pop("type", None)
    elif transport == "websocket":
        entry["type"] = "ws"
    elif "httpUrl" in entry and "oauth" in entry:
        pass
    elif transport:
        entry["type"] = transport
    if spec.auth_url:
        entry["auth_url"] = spec.auth_url
    if spec.instructions:
        entry["instructions"] = spec.instructions
    return entry


def read_mcp_json_config(workspace: str) -> dict[str, Any]:
    path = _mcp_json_path(workspace)
    if not path.exists():
        return {"mcpServers": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(".mcp.json must contain a JSON object")
    return raw


def write_mcp_json_config(workspace: str, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError(".mcp.json must contain a JSON object")
    mcp_raw = data.get("mcpServers")
    if mcp_raw is None:
        data = {"mcpServers": {}}
    else:
        _parse_mcp_data(mcp_raw, f"{_mcp_json_path(workspace)}:mcpServers", source_kind="mcp_json")
    SettingsService._atomic_write_json(_mcp_json_path(workspace), data)
    return data


def save_mcp_server_to_mcp_json(workspace: str, spec: MCPServerSpec) -> None:
    data = read_mcp_json_config(workspace)
    servers = data.get("mcpServers") or {}
    if not isinstance(servers, dict):
        servers = {}
    servers = dict(servers)
    servers[spec.name] = _connection_to_claude_mcp_entry(spec)
    write_mcp_json_config(workspace, {"mcpServers": servers})


def remove_mcp_server_from_settings(workspace: str, name: str) -> bool:
    """Remove the server *name* from ``{workspace}/.aethos/settings.json``.

    Returns ``True`` if the server was found and removed, ``False`` if it
    was not present in the settings file.  Raises on I/O or JSON errors.
    """
    service = SettingsService()
    data = service.get_settings_for_source("project", workspace_root=workspace)
    servers = data.get("mcpServers") or {}
    if not isinstance(servers, dict) or name not in servers:
        return False
    servers = dict(servers)
    del servers[name]
    updated = dict(data)
    updated["mcpServers"] = servers
    service.write_settings_for_source(
        "project",
        updated,
        workspace_root=workspace,
    )
    return True


def remove_mcp_server_from_mcp_json(workspace: str, name: str) -> bool:
    data = read_mcp_json_config(workspace)
    servers = data.get("mcpServers") or {}
    if not isinstance(servers, dict) or name not in servers:
        return False
    servers = dict(servers)
    del servers[name]
    write_mcp_json_config(workspace, {"mcpServers": servers})
    return True


def get_mcp_servers(
    workspace: str | None = None,
    *,
    owner_user_id: str | None = None,
    include_project_settings: bool = True,
) -> list[MCPServerSpec]:
    """Return MCP server configurations, merging env var and settings file.

    Supported transports: ``stdio``, ``sse``, ``http`` / ``streamable_http``,
    ``websocket``.

    Sources (earlier items take precedence over later items for same name):

    1. ``AETHOS_MCP_SERVERS`` environment variable (JSON object or array).
    2. Effective Aethos settings ``mcpServers`` merged through ``SettingsService``.
    3. ``{workspace}/.mcp.json`` in Claude / OpenClaude format.

    Example object map (env var or settings file):
    .. code-block:: json

        {
          "docs": {"transport": "streamable_http", "url": "https://example/mcp"},
          "math": {"transport": "stdio", "command": "python", "args": ["/srv/math.py"]},
          "rt":   {"transport": "websocket", "url": "ws://localhost:9000/ws"}
        }
    """
    resolved_workspace = workspace or get_workspace()
    env_servers = _parse_mcp_env_var()
    effective_settings = (
        SettingsService().get_effective_settings(workspace_root=resolved_workspace)
        if include_project_settings
        else SettingsService().get_effective_settings()
    )
    mcp_raw = effective_settings.get("mcpServers") if isinstance(effective_settings, dict) else None
    file_servers = _parse_mcp_data(
        mcp_raw,
        "effective_settings:mcpServers",
        source_kind="settings",
    ) if mcp_raw else []
    mcp_json_servers = _load_mcp_from_mcp_json(resolved_workspace) if include_project_settings else []
    env_names = {s.name for s in env_servers}
    merged = list(env_servers)
    for s in file_servers:
        if s.name not in env_names:
            merged.append(s)
    merged_names = {s.name for s in merged}
    for s in mcp_json_servers:
        if s.name not in merged_names:
            merged.append(s)
    return _filter_native_connection_mcp_servers(
        merged,
        workspace=resolved_workspace,
        owner_user_id=owner_user_id,
        include_project_settings=include_project_settings,
    )
