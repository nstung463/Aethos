"""Primary Aethos agent factory."""

import json
import os
import time
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver

from src.ai.permissions import PermissionContext
from src.ai.agents.subagents import DEFAULT_SUBAGENTS, build_task_tool
from src.ai.middleware import (
    EnvironmentMiddleware,
    MCPInstructionsMiddleware,
    MemoryMiddleware,
    NativeConnectionsMiddleware,
    SkillsMiddleware,
)
from src.ai.prompts.catalog import BASE_SYSTEM_PROMPT
from src.ai.skills import SkillRegistry
from src.ai.tools.filesystem.media_support import MediaBlockSupport
from src.backends.protocol import SandboxProtocol as FilesystemBackendProtocol
from src.app.services.storage_paths import StoragePathsService
from src.config import MCPServerSpec, get_mcp_servers, get_model, get_workspace
from src.logger import get_logger
from src.ai.tools.filesystem import build_filesystem_tools
from src.ai.tools.integrations import build_integration_tools
from src.ai.tools.mcp import MCPRuntime, build_mcp_tools
from src.ai.tools.orchestration import build_remember_tool, build_skill_tool
from src.ai.tools.session import build_present_output_file_tool
from src.ai.tools.shell import build_bash_tool, build_powershell_tool
from src.ai.tools.web import web_fetch_tool, web_search_tool
from src.backends.local import LocalBackend
from src.app.services.profiler import profile_phase

logger = get_logger(__name__)

_TOOL_POOL_CACHE_LOCK = Lock()


@dataclass(frozen=True)
class _ToolPoolCacheKey:
    root_dir: str
    backend_kind: str
    backend_root: str | None
    owner_user_id: str | None
    include_project_settings: bool
    include_task_tool: bool
    permission_signature: str
    media_block_signature: str
    mcp_signature: str
    model_signature: str | None


@dataclass
class _ToolPoolCacheEntry:
    expires_at: float
    tools: list[object]


def _current_tool_pool_cache_ttl_seconds() -> float:
    raw = os.getenv("AETHOS_TOOL_POOL_CACHE_TTL_SECONDS", "300")
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return 300.0


def _serialize_permission_context(permission_context: PermissionContext | None) -> str:
    if permission_context is None:
        return "none"
    payload = {
        "mode": getattr(permission_context.mode, "value", str(permission_context.mode)),
        "workspace_root": str(permission_context.workspace_root),
        "working_directories": [str(path) for path in permission_context.working_directories],
        "headless": permission_context.headless,
        "rules": [
            {
                "subject": getattr(rule.subject, "value", str(rule.subject)),
                "behavior": getattr(rule.behavior, "value", str(rule.behavior)),
                "source": getattr(rule.source, "value", str(rule.source)),
                "matcher": rule.matcher,
            }
            for rule in permission_context.rules
        ],
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _serialize_mcp_servers(mcp_servers: list[MCPServerSpec]) -> str:
    payload = [
        {
            "name": server.name,
            "connection": server.connection,
            "auth_url": server.auth_url,
        }
        for server in mcp_servers
    ]
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def _model_signature(model: BaseChatModel | None) -> str | None:
    if model is None:
        return None
    return str(getattr(model, "model_name", None) or getattr(model, "model", None) or type(model).__name__)


def _media_block_signature(media_block_support: MediaBlockSupport | None) -> str:
    if media_block_support is None:
        return "none"
    if is_dataclass(media_block_support):
        return json.dumps(asdict(media_block_support), sort_keys=True)
    # Backward-compatible fallback for unexpected runtime objects.
    return json.dumps(
        {
            "image_blocks": bool(getattr(media_block_support, "image_blocks", False)),
            "file_blocks": bool(getattr(media_block_support, "file_blocks", False)),
            "repr": str(media_block_support),
        },
        sort_keys=True,
    )


def _tool_pool_cache_key(
    *,
    root_dir: str,
    backend: FilesystemBackendProtocol | None,
    owner_user_id: str | None,
    include_project_settings: bool,
    include_task_tool: bool,
    permission_context: PermissionContext | None,
    media_block_support: MediaBlockSupport | None,
    mcp_servers: list[MCPServerSpec],
    model: BaseChatModel | None,
) -> _ToolPoolCacheKey:
    backend_kind = type(backend).__name__ if backend is not None else "local"
    backend_root_value = getattr(backend, "root", None) if backend is not None else None
    if isinstance(backend_root_value, Path):
        backend_root = str(backend_root_value)
    elif isinstance(backend_root_value, str):
        backend_root = backend_root_value
    else:
        backend_root = None
    return _ToolPoolCacheKey(
        root_dir=root_dir,
        backend_kind=backend_kind,
        backend_root=backend_root,
        owner_user_id=owner_user_id,
        include_project_settings=include_project_settings,
        include_task_tool=include_task_tool,
        permission_signature=_serialize_permission_context(permission_context),
        media_block_signature=_media_block_signature(media_block_support),
        mcp_signature=_serialize_mcp_servers(mcp_servers),
        model_signature=_model_signature(model) if include_task_tool else None,
    )


def _get_cached_tool_pool(cache_key: _ToolPoolCacheKey) -> list[object] | None:
    now = time.time()
    with _TOOL_POOL_CACHE_LOCK:
        cache = getattr(build_aethos_tools, "_tool_pool_cache", None)
        if not isinstance(cache, dict):
            return None
        entry = cache.get(cache_key)
        if entry is None:
            return None
        if now >= entry.expires_at:
            cache.pop(cache_key, None)
            return None
        return list(entry.tools)


def _store_cached_tool_pool(cache_key: _ToolPoolCacheKey, tools: list[object]) -> None:
    ttl = _current_tool_pool_cache_ttl_seconds()
    if ttl <= 0:
        return
    with _TOOL_POOL_CACHE_LOCK:
        cache = getattr(build_aethos_tools, "_tool_pool_cache", None)
        if cache is None:
            cache = {}
            setattr(build_aethos_tools, "_tool_pool_cache", cache)
        cache[cache_key] = _ToolPoolCacheEntry(expires_at=time.time() + ttl, tools=list(tools))
        max_entries_raw = os.getenv("AETHOS_TOOL_POOL_CACHE_MAX_ENTRIES", "64")
        try:
            max_entries = max(1, int(max_entries_raw))
        except (TypeError, ValueError):
            max_entries = 64
        if len(cache) > max_entries:
            expired = [key for key, value in cache.items() if time.time() >= value.expires_at]
            for key in expired:
                cache.pop(key, None)
            if len(cache) > max_entries:
                for key, _ in sorted(cache.items(), key=lambda item: item[1].expires_at)[: len(cache) - max_entries]:
                    cache.pop(key, None)


def clear_tool_pool_cache() -> None:
    with _TOOL_POOL_CACHE_LOCK:
        cache = getattr(build_aethos_tools, "_tool_pool_cache", None)
        if isinstance(cache, dict):
            cache.clear()


def _log_tool_build_phase(started_at: float, previous_at: float, phase: str) -> float:
    now = perf_counter()
    logger.info(
        "build_aethos_tools phase=%s delta_ms=%.2f total_ms=%.2f",
        phase,
        (now - previous_at) * 1000,
        (now - started_at) * 1000,
    )
    return now


def _include_project_settings_for_backend(backend: FilesystemBackendProtocol | None) -> bool:
    return backend is None or isinstance(backend, LocalBackend)


def build_aethos_tools(
    *,
    root_dir: str,
    backend: FilesystemBackendProtocol | None = None,
    model: BaseChatModel | None = None,
    permission_context: PermissionContext | None = None,
    media_block_support: MediaBlockSupport | None = None,
    owner_user_id: str | None = None,
    include_task_tool: bool = True,
) -> list[object]:
    started_at = perf_counter()
    previous_at = started_at
    include_project_settings = _include_project_settings_for_backend(backend)
    mcp_servers = get_mcp_servers(
        root_dir,
        owner_user_id=owner_user_id,
        include_project_settings=include_project_settings,
    )
    previous_at = _log_tool_build_phase(started_at, previous_at, "get_mcp_servers")
    cache_key = _tool_pool_cache_key(
        root_dir=root_dir,
        backend=backend,
        owner_user_id=owner_user_id,
        include_project_settings=include_project_settings,
        include_task_tool=include_task_tool,
        permission_context=permission_context,
        media_block_support=media_block_support,
        mcp_servers=mcp_servers,
        model=model,
    )
    cached_tools = _get_cached_tool_pool(cache_key)
    if cached_tools is not None:
        previous_at = _log_tool_build_phase(started_at, previous_at, "tool_pool_cache_hit")
        _log_tool_build_phase(started_at, previous_at, "return_cached_tools")
        return cached_tools
    previous_at = _log_tool_build_phase(started_at, previous_at, "tool_pool_cache_miss")
    fs_tools = build_filesystem_tools(
        root_dir=root_dir,
        backend=backend,
        permission_context=permission_context,
        media_block_support=media_block_support,
    )
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_filesystem_tools")
    extra_tools = []
    if backend is not None:
        if "bash" in backend.supported_shells:
            extra_tools.append(build_bash_tool(backend, permission_context=permission_context))
        if "powershell" in backend.supported_shells:
            extra_tools.append(build_powershell_tool(backend, permission_context=permission_context))
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_shell_tools")

    web_tools = [web_search_tool, web_fetch_tool]
    previous_at = _log_tool_build_phase(started_at, previous_at, "resolve_web_tools")
    integration_tools = build_integration_tools(
        root_dir=root_dir,
        owner_user_id=owner_user_id,
        permission_context=permission_context,
    )
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_integration_tools")
    mcp_runtime = MCPRuntime(mcp_servers)
    mcp_tools = build_mcp_tools(mcp_servers, runtime=mcp_runtime, permission_context=permission_context)
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_mcp_tools")
    skill_registry = SkillRegistry(
        root_dir,
        mcp_runtime=mcp_runtime,
        include_project_skills=include_project_settings,
    )
    skill_tool = build_skill_tool(skill_registry, permission_context=permission_context)
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_skill_tool")
    remember_tool = build_remember_tool(root_dir)
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_remember_tool")
    present_output_file_tool = build_present_output_file_tool(
        root_dir,
        backend=backend,
        owner_user_id=owner_user_id,
        permission_context=permission_context,
    )
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_present_output_file_tool")
    base_tools = fs_tools + extra_tools + web_tools + integration_tools + mcp_tools + [
        skill_tool,
        remember_tool,
        present_output_file_tool,
    ]
    if not include_task_tool:
        _log_tool_build_phase(started_at, previous_at, "return_base_tools")
        _store_cached_tool_pool(cache_key, base_tools)
        return base_tools
    if model is None:
        model = get_model()
    previous_at = _log_tool_build_phase(started_at, previous_at, "resolve_model_for_task_tool")
    subagent_skill_registry = SkillRegistry(
        root_dir,
        mcp_runtime=mcp_runtime,
        include_project_skills=include_project_settings,
    )
    subagent_skill_tool = build_skill_tool(subagent_skill_registry, permission_context=permission_context)
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_subagent_skill_tool")
    subagent_remember_tool = build_remember_tool(root_dir)
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_subagent_remember_tool")
    subagent_present_output_file_tool = build_present_output_file_tool(
        root_dir,
        backend=backend,
        owner_user_id=owner_user_id,
        permission_context=permission_context,
    )
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_subagent_present_output_file_tool")
    subagent_base_tools = fs_tools + extra_tools + web_tools + integration_tools + mcp_tools + [
        subagent_skill_tool,
        subagent_remember_tool,
        subagent_present_output_file_tool,
    ]
    task_tool = build_task_tool(
        model=model,
        subagents=DEFAULT_SUBAGENTS,
        base_tools=subagent_base_tools,
        default_middleware=_build_default_middleware(
            root_dir,
            mcp_servers,
            skill_registry=subagent_skill_registry,
            owner_user_id=owner_user_id,
        ),
    )
    previous_at = _log_tool_build_phase(started_at, previous_at, "build_task_tool")
    _log_tool_build_phase(started_at, previous_at, "return_all_tools")
    all_tools = base_tools + [task_tool]
    _store_cached_tool_pool(cache_key, all_tools)
    return all_tools


build_aethos_tools.clear_tool_pool_cache = clear_tool_pool_cache  # type: ignore[attr-defined]


def _build_default_middleware(
    root_dir: str,
    mcp_servers: list[MCPServerSpec],
    model_name: str | None = None,
    skill_registry: SkillRegistry | None = None,
    owner_user_id: str | None = None,
) -> list[AgentMiddleware]:
    """Create a fresh middleware stack for an Aethos agent instance.

    Execution order (before_agent / wrap_model_call):
      1. EnvironmentMiddleware      — cwd, git, date, platform, model, CLAUDE.md hierarchy
      2. MCPInstructionsMiddleware  — per-server MCP instructions (skipped when empty)
      3. SkillsMiddleware           — available skills list
      4. MemoryMiddleware           — AGENTS.md persistent context
    All sections are computed once on the first turn and cached via PrivateStateAttr.
    """
    return [
        EnvironmentMiddleware(root_dir=root_dir, model_name=model_name),
        MCPInstructionsMiddleware(servers=mcp_servers),
        NativeConnectionsMiddleware(root_dir=root_dir, owner_user_id=owner_user_id),
        SkillsMiddleware(registry=skill_registry, root_dir=root_dir),
        MemoryMiddleware(
            agents_md_path=f"{root_dir}/AGENTS.md",
            auto_memory_path=str(StoragePathsService().memory_file(root_dir)),
        ),
    ]


def create_aethos_agent(
    root_dir: str | None = None,
    backend: FilesystemBackendProtocol | None = None,
    model: BaseChatModel | None = None,
    permission_context: PermissionContext | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    media_block_support: MediaBlockSupport | None = None,
    owner_user_id: str | None = None,
) -> object:
    """Create and return a compiled Aethos agent."""
    raw_backend_root = getattr(backend, "root", None) if backend is not None else None
    if root_dir is None:
        backend_root = raw_backend_root
        if isinstance(backend_root, Path):
            root_dir = str(backend_root.resolve())
        elif isinstance(backend_root, str) and backend_root.strip():
            root_dir = backend_root.strip()
        else:
            root_dir = get_workspace()
    if model is None:
        model = get_model()
    logger.info("Creating Aethos agent (backend=%s, workspace=%s)", "sandbox" if backend else "local", root_dir)
    with profile_phase(
        "create_aethos_agent",
        metadata={
            "backend": "sandbox" if backend else "local",
            "workspace": root_dir,
        },
    ) as profiler:
        mcp_servers = get_mcp_servers(
            root_dir,
            owner_user_id=owner_user_id,
            include_project_settings=_include_project_settings_for_backend(backend),
        )
        profiler.mark("get_mcp_servers")
        all_tools = build_aethos_tools(
            root_dir=root_dir,
            backend=backend,
            model=model,
            permission_context=permission_context,
            media_block_support=media_block_support,
            owner_user_id=owner_user_id,
        )
        logger.debug("Agent tools prepared (count=%d)", len(all_tools))
        profiler.mark("build_aethos_tools")

        if checkpointer is None:
            checkpointer = MemorySaver()
        profiler.mark("resolve_checkpointer")
        model_name: str | None = getattr(model, "model_name", None) or getattr(model, "model", None)
        middleware = _build_default_middleware(
            root_dir,
            mcp_servers,
            model_name=model_name,
            skill_registry=SkillRegistry(
                root_dir,
                mcp_runtime=MCPRuntime(mcp_servers),
                include_project_skills=_include_project_settings_for_backend(backend),
            ),
            owner_user_id=owner_user_id,
        )
        profiler.mark("build_middleware")
        agent = create_agent(
            model=model,
            tools=all_tools,
            system_prompt=BASE_SYSTEM_PROMPT,
            middleware=middleware,
            checkpointer=checkpointer,
            name="aethos",
        )
        profiler.mark("create_langgraph_agent")
        return agent
