"""Shared MCP client runtime for Ethos tools."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any

from src.config import MCPServerSpec


def _import_multi_server_client() -> type:
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:  # pragma: no cover - exercised via tool return path
        raise RuntimeError(
            "langchain-mcp-adapters is required for MCP tools. Install the dependency to use MCP."
        ) from exc
    return MultiServerMCPClient


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _serialize_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
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

    @property
    def server_names(self) -> list[str]:
        return [server.name for server in self.servers]

    def has_servers(self) -> bool:
        return bool(self.servers)

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

        return _run(_inner())

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
                    response = await session.list_resources()
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
                response = await session.read_resource(uri)
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

    def auth_url_for(self, server: str) -> str | None:
        for spec in self.servers:
            if spec.name == server:
                return spec.auth_url
        return None
