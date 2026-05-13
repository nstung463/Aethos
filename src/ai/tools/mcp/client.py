"""Shared MCP client runtime for Aethos tools."""

from __future__ import annotations

import asyncio
import json
import os
import time
from concurrent.futures import Future
from dataclasses import dataclass
from threading import Event, Lock, Thread
from typing import Any

from src.config import MCPServerSpec
from src.logger import get_logger

_logger = get_logger(__name__)

_DISCOVERY_CACHE_TTL_SECONDS = float(os.getenv("AETHOS_MCP_DISCOVERY_CACHE_TTL_SECONDS", "300") or "300")
_DISCOVERY_CACHE_LOCK = Lock()


def _tool_error_payload(*, server: str, tool: str, arguments: dict[str, Any] | None, exc: Exception) -> str:
    """Return a structured MCP tool failure payload instead of raising into the agent loop."""
    return json.dumps(
        {
            "server": server,
            "tool": tool,
            "arguments": _serialize_value(arguments or {}),
            "error": str(exc),
            "success": False,
        }
    )


def _is_unsupported_mcp_method(exc: Exception, method: str) -> bool:
    return f"Method '{method}' is not available." in str(exc)


@dataclass(frozen=True)
class MCPToolDescriptor:
    """Serializable snapshot of a discovered MCP tool."""

    server: str
    name: str
    description: str
    args_schema: type[Any] | None


@dataclass
class _DiscoveryCacheEntry:
    expires_at: float
    descriptors: list[MCPToolDescriptor] | None = None
    error: Exception | None = None
    ready: Event | None = None


def _import_multi_server_client() -> type:
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:  # pragma: no cover - exercised via tool return path
        raise RuntimeError(
            "langchain-mcp-adapters is required for MCP tools. Install the dependency to use MCP."
        ) from exc
    return MultiServerMCPClient


def _run(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    # FastAPI routes may inspect MCP metadata while already inside an event loop.
    # Run the coroutine on a dedicated thread in that case so sync call sites keep working.
    result: Future[Any] = Future()

    def _runner() -> None:
        try:
            value = asyncio.run(coro)
        except Exception as exc:
            result.set_exception(exc)
            return
        result.set_result(value)

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    return result.result()


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, type):
        return getattr(value, "__name__", str(value))
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if hasattr(value, "model_dump"):
        return _serialize_value(value.model_dump())
    if hasattr(value, "__dict__"):
        return _serialize_value(vars(value))
    return str(value)


def _text_from_prompt_content(content: Any) -> str:
    data = _serialize_value(content)
    if isinstance(data, str):
        return data
    if isinstance(data, list):
        parts: list[str] = []
        for block in data:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
                    continue
                nested = block.get("content")
                if nested is not None:
                    nested_text = _text_from_prompt_content(nested)
                    if nested_text:
                        parts.append(nested_text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(part for part in parts if part)
    if isinstance(data, dict):
        text = data.get("text")
        if isinstance(text, str):
            return text
        nested = data.get("content")
        if nested is not None:
            return _text_from_prompt_content(nested)
    return ""


@dataclass
class MCPRuntime:
    """Thin synchronous wrapper around MultiServerMCPClient."""

    servers: list[MCPServerSpec]

    @classmethod
    def clear_discovery_cache(cls) -> None:
        with _DISCOVERY_CACHE_LOCK:
            cache = getattr(cls, "_discovery_cache", None)
            if isinstance(cache, dict):
                cache.clear()

    @property
    def server_names(self) -> list[str]:
        return [server.name for server in self.servers]

    def has_servers(self) -> bool:
        return bool(self.servers)

    def _discovery_cache_key(self) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
        key_parts: list[tuple[str, tuple[tuple[str, str], ...]]] = []
        for spec in self.servers:
            normalized_connection = tuple(
                sorted((str(k), json.dumps(_serialize_value(v), sort_keys=True, ensure_ascii=False)) for k, v in spec.connection.items())
            )
            key_parts.append((spec.name, normalized_connection))
        return tuple(sorted(key_parts))

    @staticmethod
    def _cache_valid(entry: _DiscoveryCacheEntry) -> bool:
        return time.time() < entry.expires_at and entry.descriptors is not None

    @staticmethod
    def _current_ttl_seconds() -> float:
        # Re-read env on every lookup so devs can tune without restart in local loops.
        raw = os.getenv("AETHOS_MCP_DISCOVERY_CACHE_TTL_SECONDS", str(_DISCOVERY_CACHE_TTL_SECONDS))
        try:
            ttl = float(raw)
        except (TypeError, ValueError):
            ttl = _DISCOVERY_CACHE_TTL_SECONDS
        return max(0.0, ttl)

    def discover_tool_descriptors(self) -> list[MCPToolDescriptor]:
        """Discover MCP tools with process-level TTL cache + in-flight dedupe."""
        if not self.has_servers():
            return []

        cache_key = self._discovery_cache_key()
        now = time.time()
        waiter: Event | None = None

        with _DISCOVERY_CACHE_LOCK:
            cache = getattr(MCPRuntime, "_discovery_cache", None)
            if cache is None:
                cache = {}
                setattr(MCPRuntime, "_discovery_cache", cache)
            entry = cache.get(cache_key)

            if entry is not None and self._cache_valid(entry):
                return list(entry.descriptors or [])

            if entry is not None and entry.ready is not None and not entry.ready.is_set():
                waiter = entry.ready
            else:
                ready = Event()
                cache[cache_key] = _DiscoveryCacheEntry(
                    expires_at=now + self._current_ttl_seconds(),
                    descriptors=None,
                    error=None,
                    ready=ready,
                )
                waiter = None

        if waiter is not None:
            waiter.wait()
            with _DISCOVERY_CACHE_LOCK:
                cache = getattr(MCPRuntime, "_discovery_cache", {})
                refreshed = cache.get(cache_key)
                if refreshed is not None and self._cache_valid(refreshed):
                    return list(refreshed.descriptors or [])
                if refreshed is not None and refreshed.error is not None:
                    _logger.warning("MCP tool discovery failed: %s", refreshed.error)
                    return []
                return []

        try:
            descriptors = self._discover_tool_descriptors_uncached()
            error: Exception | None = None
        except Exception as exc:
            _logger.warning("MCP tool discovery failed: %s", exc)
            descriptors = []
            error = exc

        with _DISCOVERY_CACHE_LOCK:
            cache = getattr(MCPRuntime, "_discovery_cache", {})
            current = cache.get(cache_key)
            if current is not None:
                ttl = self._current_ttl_seconds()
                current.descriptors = list(descriptors)
                current.error = error
                current.expires_at = time.time() + ttl
                if current.ready is not None and not current.ready.is_set():
                    current.ready.set()

                # Lightweight eviction to keep cache bounded.
                max_entries_raw = os.getenv("AETHOS_MCP_DISCOVERY_CACHE_MAX_ENTRIES", "32")
                try:
                    max_entries = max(1, int(max_entries_raw))
                except (TypeError, ValueError):
                    max_entries = 32
                if len(cache) > max_entries:
                    stale_keys = [k for k, v in cache.items() if time.time() >= v.expires_at]
                    for stale_key in stale_keys:
                        cache.pop(stale_key, None)
                    if len(cache) > max_entries:
                        # Drop oldest by expires_at first.
                        for drop_key, _ in sorted(cache.items(), key=lambda item: item[1].expires_at)[: len(cache) - max_entries]:
                            cache.pop(drop_key, None)

        return list(descriptors)

    def _discover_tool_descriptors_uncached(self) -> list[MCPToolDescriptor]:
        async def _inner() -> list[MCPToolDescriptor]:
            client = self._get_client()
            result: list[MCPToolDescriptor] = []
            for server in self.server_names:
                try:
                    tools = await client.get_tools(server_name=server)
                    for tool in tools:
                        result.append(
                            MCPToolDescriptor(
                                server=server,
                                name=str(getattr(tool, "name", "")),
                                description=str(getattr(tool, "description", "") or ""),
                                args_schema=getattr(tool, "args_schema", None),
                            )
                        )
                except Exception as exc:
                    _logger.warning("MCP tool discovery failed for %r: %s", server, exc)
            return result

        return _run(_inner())

    def _config_map(self) -> dict[str, dict[str, Any]]:
        return {server.name: dict(server.connection) for server in self.servers}

    def _get_client(self) -> Any:
        client_cls = _import_multi_server_client()
        return client_cls(self._config_map())

    def _require_server(self, server: str) -> None:
        if not self.has_servers():
            raise ValueError("No MCP servers are configured.")
        if server not in self.server_names:
            raise ValueError(f"Unknown MCP server '{server}'. Available: {', '.join(self.server_names)}")

    def invoke_tool(self, server: str, tool: str, arguments: dict[str, Any] | None = None) -> str:
        self._require_server(server)

        async def _inner() -> str:
            client = self._get_client()
            tools = await client.get_tools(server_name=server)
            for candidate in tools:
                if candidate.name == tool or candidate.name.endswith(f"__{tool}"):
                    payload = arguments or {}
                    if hasattr(candidate, "ainvoke"):
                        result = await candidate.ainvoke(payload)
                    else:
                        result = candidate.invoke(payload)
                    return json.dumps(
                        {
                            "server": server,
                            "tool": tool,
                            "result": _serialize_value(result),
                        }
                    )
            raise ValueError(f"MCP tool '{tool}' was not found on server '{server}'.")

        try:
            return _run(_inner())
        except Exception as exc:
            _logger.warning("MCP tool invocation failed for %r/%r: %s", server, tool, exc)
            return _tool_error_payload(server=server, tool=tool, arguments=arguments, exc=exc)

    def list_tools(self, server: str | None = None) -> str:
        targets = [server] if server else self.server_names
        if not targets:
            return json.dumps({"tools": []})
        for target in targets:
            self._require_server(target)

        async def _inner() -> str:
            client = self._get_client()
            tools: list[dict[str, Any]] = []
            for target in targets:
                for item in await client.get_tools(server_name=target):
                    data = _serialize_value(item)
                    if isinstance(data, dict):
                        data["server"] = target
                        tools.append(data)
                    else:
                        tools.append({"server": target, "name": str(data)})
            return json.dumps({"tools": tools})

        return _run(_inner())

    def list_resources(self, server: str | None = None) -> str:
        targets = [server] if server else self.server_names
        if not targets:
            return json.dumps({"resources": []})
        for target in targets:
            self._require_server(target)

        async def _inner() -> str:
            client = self._get_client()
            resources: list[dict[str, Any]] = []
            for target in targets:
                async with client.session(target) as session:
                    try:
                        response = await session.list_resources()
                    except Exception as exc:
                        if _is_unsupported_mcp_method(exc, "resources/list"):
                            _logger.info("MCP server %r does not expose resources/list; skipping.", target)
                            continue
                        raise
                    items = getattr(response, "resources", response)
                    for item in items:
                        data = _serialize_value(item)
                        if isinstance(data, dict):
                            data["server"] = target
                            resources.append(data)
                        else:
                            resources.append({"server": target, "value": data})
            return json.dumps({"resources": resources})

        return _run(_inner())

    def read_resource(self, server: str, uri: str) -> str:
        self._require_server(server)

        async def _inner() -> str:
            client = self._get_client()
            async with client.session(server) as session:
                try:
                    response = await session.read_resource(uri)
                except Exception as exc:
                    if _is_unsupported_mcp_method(exc, "resources/read"):
                        return json.dumps(
                            {
                                "server": server,
                                "uri": uri,
                                "error": f"MCP server '{server}' does not expose resource reads.",
                            }
                        )
                    raise
                contents = getattr(response, "contents", response)
                return json.dumps(
                    {
                        "server": server,
                        "uri": uri,
                        "contents": _serialize_value(contents),
                    }
                )

        return _run(_inner())

    def list_prompts(self, server: str | None = None) -> str:
        targets = [server] if server else self.server_names
        if not targets:
            return json.dumps({"prompts": []})
        for target in targets:
            self._require_server(target)

        async def _inner() -> str:
            client = self._get_client()
            prompts: list[dict[str, Any]] = []
            for target in targets:
                async with client.session(target) as session:
                    if not hasattr(session, "list_prompts"):
                        continue
                    response = await session.list_prompts()
                    items = getattr(response, "prompts", response)
                    for item in items:
                        data = _serialize_value(item)
                        if isinstance(data, dict):
                            data["server"] = target
                            prompts.append(data)
                        else:
                            prompts.append({"server": target, "value": data})
            return json.dumps({"prompts": prompts})

        return _run(_inner())

    def get_prompt(self, server: str, name: str, arguments: dict[str, Any] | None = None) -> str:
        self._require_server(server)

        async def _inner() -> str:
            client = self._get_client()
            async with client.session(server) as session:
                if not hasattr(session, "get_prompt"):
                    raise ValueError(f"MCP server '{server}' does not expose prompts.")
                response = await session.get_prompt(name, arguments=arguments or {})
                data = _serialize_value(response)
                if isinstance(data, dict):
                    messages = data.get("messages")
                    if isinstance(messages, list):
                        parts: list[str] = []
                        for message in messages:
                            if isinstance(message, dict):
                                text = _text_from_prompt_content(message.get("content"))
                                if text:
                                    parts.append(text)
                            else:
                                text = _text_from_prompt_content(message)
                                if text:
                                    parts.append(text)
                        return "\n\n".join(part for part in parts if part)
                    text = _text_from_prompt_content(data)
                    return text or json.dumps(data, ensure_ascii=False)
                return _text_from_prompt_content(data) or str(data)

        return _run(_inner())

    def discover_tools(self) -> list[tuple[str, Any]]:
        """Synchronously discover all native tools from all configured servers.

        Returns a list of (server_name, langchain_tool) pairs.  Per-server
        failures are logged and skipped so a single unreachable server does
        not prevent the rest from loading.
        """
        descriptors = self.discover_tool_descriptors()
        return [(item.server, item) for item in descriptors]

    def auth_url_for(self, server: str) -> str | None:
        for spec in self.servers:
            if spec.name == server:
                return spec.auth_url
        return None
