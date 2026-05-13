"""Shared workspace runtime snapshots for fast-first-token chat paths."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from langchain_core.language_models import BaseChatModel

from src.ai.agents import aethos as aethos_agent
from src.ai.permissions import PermissionContext
from src.ai.skills import SkillRegistry
from src.ai.tools.filesystem.media_support import MediaBlockSupport
from src.ai.tools.mcp import MCPRuntime
from src.backends.protocol import SandboxProtocol as FilesystemBackendProtocol
from src.config import MCPServerSpec, get_mcp_servers
from src.logger import get_logger

logger = get_logger(__name__)

RuntimeReadinessState = Literal["core_ready", "warming", "fully_ready"]


@dataclass(frozen=True)
class WorkspaceRuntimeCacheKey:
    root_dir: str
    backend_kind: str
    backend_root: str | None
    owner_user_id: str | None
    include_project_settings: bool
    permission_signature: str
    media_block_signature: str
    mcp_signature: str
    model_signature: str | None


@dataclass
class WorkspaceRuntimeSnapshot:
    key: WorkspaceRuntimeCacheKey
    readiness_state: RuntimeReadinessState = "core_ready"
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_error: str | None = None
    mcp_servers: list[MCPServerSpec] = field(default_factory=list)
    mcp_runtime: MCPRuntime | None = None
    skill_registry: SkillRegistry | None = None
    core_tools: list[object] | None = None
    full_tools: list[object] | None = None
    full_tools_include_task_tool: bool = True
    warming: bool = False
    warming_started_at: float | None = None
    warming_completed_at: float | None = None

    @property
    def runtime_cache_hit(self) -> bool:
        return self.core_tools is not None


_RUNTIME_CACHE_LOCK = threading.Lock()
_RUNTIME_CACHE: dict[WorkspaceRuntimeCacheKey, WorkspaceRuntimeSnapshot] = {}
_PREWARM_THREADS: dict[WorkspaceRuntimeCacheKey, threading.Thread] = {}
_CORE_BUILD_EVENTS: dict[WorkspaceRuntimeCacheKey, threading.Event] = {}
_CORE_BUILD_ERRORS: dict[WorkspaceRuntimeCacheKey, BaseException] = {}


def _fast_first_token_enabled() -> bool:
    return os.getenv("AETHOS_FAST_FIRST_TOKEN_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def _workspace_prewarm_enabled() -> bool:
    return os.getenv("AETHOS_WORKSPACE_PREWARM_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def _partial_runtime_enabled() -> bool:
    return os.getenv("AETHOS_PARTIAL_RUNTIME_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def _context_runtime_reuse_enabled() -> bool:
    return os.getenv("AETHOS_CONTEXT_STATUS_RUNTIME_REUSE_ENABLED", "1").strip().lower() not in {"0", "false", "no"}


def _runtime_cache_key(
    *,
    root_dir: str,
    backend: FilesystemBackendProtocol | None,
    owner_user_id: str | None,
    permission_context: PermissionContext | None,
    media_block_support: MediaBlockSupport | None,
    model: BaseChatModel | None,
) -> tuple[WorkspaceRuntimeCacheKey, list[MCPServerSpec]]:
    include_project_settings = aethos_agent._include_project_settings_for_backend(backend)
    mcp_servers = get_mcp_servers(
        root_dir,
        owner_user_id=owner_user_id,
        include_project_settings=include_project_settings,
    )
    backend_kind = type(backend).__name__ if backend is not None else "local"
    backend_root_value = getattr(backend, "root", None) if backend is not None else None
    if isinstance(backend_root_value, Path):
        backend_root = str(backend_root_value)
    elif isinstance(backend_root_value, str):
        backend_root = backend_root_value
    else:
        backend_root = None
    return (
        WorkspaceRuntimeCacheKey(
            root_dir=root_dir,
            backend_kind=backend_kind,
            backend_root=backend_root,
            owner_user_id=owner_user_id,
            include_project_settings=include_project_settings,
            permission_signature=aethos_agent._serialize_permission_context(permission_context),
            media_block_signature=aethos_agent._media_block_signature(media_block_support),
            mcp_signature=aethos_agent._serialize_mcp_servers(mcp_servers),
            model_signature=aethos_agent._model_signature(model),
        ),
        mcp_servers,
    )


def get_runtime_snapshot(
    *,
    root_dir: str,
    backend: FilesystemBackendProtocol | None,
    owner_user_id: str | None,
    permission_context: PermissionContext | None,
    media_block_support: MediaBlockSupport | None,
    model: BaseChatModel | None,
) -> WorkspaceRuntimeSnapshot | None:
    key, _ = _runtime_cache_key(
        root_dir=root_dir,
        backend=backend,
        owner_user_id=owner_user_id,
        permission_context=permission_context,
        media_block_support=media_block_support,
        model=model,
    )
    with _RUNTIME_CACHE_LOCK:
        return _RUNTIME_CACHE.get(key)


def invalidate_runtime_snapshot(*, root_dir: str | None = None) -> None:
    with _RUNTIME_CACHE_LOCK:
        if root_dir is None:
            _RUNTIME_CACHE.clear()
            _CORE_BUILD_EVENTS.clear()
            _CORE_BUILD_ERRORS.clear()
            return
        doomed = [key for key in _RUNTIME_CACHE if key.root_dir == root_dir]
        for key in doomed:
            _RUNTIME_CACHE.pop(key, None)
            _CORE_BUILD_EVENTS.pop(key, None)
            _CORE_BUILD_ERRORS.pop(key, None)


def ensure_core_runtime(
    *,
    root_dir: str,
    backend: FilesystemBackendProtocol | None,
    owner_user_id: str | None,
    permission_context: PermissionContext | None,
    media_block_support: MediaBlockSupport | None,
    model: BaseChatModel | None,
) -> WorkspaceRuntimeSnapshot:
    key, mcp_servers = _runtime_cache_key(
        root_dir=root_dir,
        backend=backend,
        owner_user_id=owner_user_id,
        permission_context=permission_context,
        media_block_support=media_block_support,
        model=model,
    )
    should_build = False
    wait_event: threading.Event | None = None
    with _RUNTIME_CACHE_LOCK:
        snapshot = _RUNTIME_CACHE.get(key)
        if snapshot is not None and snapshot.core_tools is not None:
            return snapshot
        if snapshot is None:
            snapshot = WorkspaceRuntimeSnapshot(key=key, mcp_servers=mcp_servers)
            _RUNTIME_CACHE[key] = snapshot
        existing_event = _CORE_BUILD_EVENTS.get(key)
        if existing_event is None:
            wait_event = threading.Event()
            _CORE_BUILD_EVENTS[key] = wait_event
            should_build = True
        else:
            wait_event = existing_event

    if not should_build:
        assert wait_event is not None
        wait_event.wait()
        with _RUNTIME_CACHE_LOCK:
            build_error = _CORE_BUILD_ERRORS.pop(key, None)
            if build_error is not None:
                raise RuntimeError(f"Core runtime build failed for {root_dir}") from build_error
            snapshot = _RUNTIME_CACHE.get(key)
            if snapshot is None or snapshot.core_tools is None:
                raise RuntimeError(f"Core runtime build did not produce a snapshot for {root_dir}")
            return snapshot

    try:
        core_tools = aethos_agent.build_core_aethos_tools(
            root_dir=root_dir,
            backend=backend,
            permission_context=permission_context,
            media_block_support=media_block_support,
            owner_user_id=owner_user_id,
        )
        include_project_settings = aethos_agent._include_project_settings_for_backend(backend)
        mcp_runtime = MCPRuntime(mcp_servers)
        skill_registry = SkillRegistry(
            root_dir,
            mcp_runtime=mcp_runtime,
            include_project_skills=include_project_settings,
        )
        with _RUNTIME_CACHE_LOCK:
            snapshot = _RUNTIME_CACHE.get(key) or WorkspaceRuntimeSnapshot(key=key, mcp_servers=mcp_servers)
            snapshot.mcp_servers = mcp_servers
            snapshot.mcp_runtime = mcp_runtime
            snapshot.skill_registry = skill_registry
            snapshot.core_tools = list(core_tools)
            snapshot.updated_at = time.time()
            if snapshot.full_tools is not None:
                snapshot.readiness_state = "fully_ready"
            elif snapshot.warming:
                snapshot.readiness_state = "warming"
            else:
                snapshot.readiness_state = "core_ready"
            _RUNTIME_CACHE[key] = snapshot
            return snapshot
    except BaseException as exc:
        with _RUNTIME_CACHE_LOCK:
            snapshot = _RUNTIME_CACHE.get(key)
            if snapshot is not None:
                snapshot.last_error = str(exc)
                snapshot.updated_at = time.time()
            _CORE_BUILD_ERRORS[key] = exc
        raise
    finally:
        with _RUNTIME_CACHE_LOCK:
            event = _CORE_BUILD_EVENTS.pop(key, None)
        if event is not None:
            event.set()


def _finish_full_runtime(
    *,
    snapshot: WorkspaceRuntimeSnapshot,
    root_dir: str,
    backend: FilesystemBackendProtocol | None,
    owner_user_id: str | None,
    permission_context: PermissionContext | None,
    media_block_support: MediaBlockSupport | None,
    model: BaseChatModel | None,
    include_task_tool: bool,
) -> None:
    try:
        full_tools = aethos_agent.build_full_aethos_tools(
            root_dir=root_dir,
            backend=backend,
            model=model,
            permission_context=permission_context,
            media_block_support=media_block_support,
            owner_user_id=owner_user_id,
            include_task_tool=include_task_tool,
            mcp_servers=snapshot.mcp_servers,
            mcp_runtime=snapshot.mcp_runtime,
            skill_registry=snapshot.skill_registry,
        )
        with _RUNTIME_CACHE_LOCK:
            current = _RUNTIME_CACHE.get(snapshot.key)
            if current is None:
                return
            current.full_tools = list(full_tools)
            current.full_tools_include_task_tool = include_task_tool
            current.warming = False
            current.last_error = None
            current.readiness_state = "fully_ready"
            current.updated_at = time.time()
            current.warming_completed_at = current.updated_at
    except Exception as exc:
        logger.warning("Runtime prewarm failed for %s: %s", snapshot.key.root_dir, exc)
        with _RUNTIME_CACHE_LOCK:
            current = _RUNTIME_CACHE.get(snapshot.key)
            if current is None:
                return
            current.warming = False
            current.last_error = str(exc)
            current.readiness_state = "core_ready"
            current.updated_at = time.time()
            current.warming_completed_at = current.updated_at
    finally:
        with _RUNTIME_CACHE_LOCK:
            _PREWARM_THREADS.pop(snapshot.key, None)


def schedule_runtime_prewarm(
    *,
    root_dir: str,
    backend: FilesystemBackendProtocol | None,
    owner_user_id: str | None,
    permission_context: PermissionContext | None,
    media_block_support: MediaBlockSupport | None,
    model: BaseChatModel | None,
    include_task_tool: bool = True,
) -> WorkspaceRuntimeSnapshot:
    snapshot = ensure_core_runtime(
        root_dir=root_dir,
        backend=backend,
        owner_user_id=owner_user_id,
        permission_context=permission_context,
        media_block_support=media_block_support,
        model=model,
    )
    if not (_fast_first_token_enabled() and _workspace_prewarm_enabled() and _partial_runtime_enabled()):
        return snapshot
    with _RUNTIME_CACHE_LOCK:
        if snapshot.full_tools is not None and snapshot.full_tools_include_task_tool == include_task_tool:
            snapshot.readiness_state = "fully_ready"
            return snapshot
        existing = _PREWARM_THREADS.get(snapshot.key)
        if existing is not None and existing.is_alive():
            snapshot.warming = True
            snapshot.readiness_state = "warming"
            return snapshot
        snapshot.warming = True
        snapshot.readiness_state = "warming"
        snapshot.warming_started_at = time.time()
        snapshot.updated_at = snapshot.warming_started_at
        thread = threading.Thread(
            target=_finish_full_runtime,
            kwargs={
                "snapshot": snapshot,
                "root_dir": root_dir,
                "backend": backend,
                "owner_user_id": owner_user_id,
                "permission_context": permission_context,
                "media_block_support": media_block_support,
                "model": model,
                "include_task_tool": include_task_tool,
            },
            name=f"aethos-prewarm-{abs(hash(snapshot.key))}",
            daemon=True,
        )
        _PREWARM_THREADS[snapshot.key] = thread
        thread.start()
        return snapshot


def full_runtime_wait_required() -> bool:
    return not (_fast_first_token_enabled() and _partial_runtime_enabled())


def context_runtime_reuse_enabled() -> bool:
    return _context_runtime_reuse_enabled()
