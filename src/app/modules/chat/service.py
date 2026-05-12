"""Chat service layer — orchestration of business logic."""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, AsyncIterator

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphInterrupt, GraphRecursionError
from langgraph.types import Command

from src.ai.agents.aethos import create_aethos_agent
from src.ai.permissions import PermissionContext, set_mode
from src.ai.tools.filesystem import resolve_media_block_support
from src.app.core.settings import Settings, get_settings
from src.app.dependencies import (
    enforce_rate_limit,
    get_auth_repository,
    get_checkpointer,
    get_current_user,
    get_daytona_session_manager,
    get_thread_store,
)
from src.app.modules.auth.repository import AuthRepository, AuthUser
from src.app.modules.chat.adapters import (
    enrich_tool_output,
    extract_text,
    extract_reasoning_from_chunk,
    extract_tool_output,
    format_tool_input,
    get_tool_display_label,
    parse_content,
    sanitize_tool_input,
    summarize_tool_input,
    to_lc_messages,
    workspace_root_for_backend,
)
from src.app.modules.chat.request_parser import (
    extract_backend_selection,
    extract_permission_override_mode,
    extract_profile,
    extract_requested_thread_id,
    extract_resume_command,
    extract_resume_payload,
    extract_user_api_keys,
    resolve_model_id,
    resolve_resume_grant_matcher,
)
from src.app.modules.chat.schemas import ChatRequest, ThreadUpdatePayload
from src.app.modules.chat.loop_guards import (
    CONTINUATION_NUDGE_STOP_REASON,
    DEFAULT_GRAPH_RECURSION_LIMIT,
    GRAPH_RECURSION_STOP_REASON,
    ContinuationNudgeGuard,
    LoopGuardSettings,
    build_continuation_nudge_input,
    resolve_loop_guard_settings,
    with_loop_guard_config,
)
from src.app.modules.chat.streaming import sse
from src.app.services.chat_tasks import fallback_title, generate_follow_ups_task, generate_title_task
from src.app.services.async_jsonl_checkpointer import AsyncJsonlCheckpointSaver
from src.app.services.daytona_manager import DaytonaSessionManager
from src.app.services.message_tracker import create_request_tracker
from src.app.services.permissions import PermissionContextService
from src.app.services.profiler import profile_phase
from src.app.services.rate_limiter import RateLimitRule
from src.app.services.storage_paths import StoragePathsService
from src.app.services.thread_store import ThreadStore
from src.backends.daytona import DaytonaUnavailableError
from src.backends.local import LocalSandbox as LocalBackend
from src.config import build_chat_model, get_model_registry
from src.logger import get_logger

logger = get_logger(__name__)


STALE_RUN_SECONDS = 300
_active_stream_runs: set[tuple[str, str]] = set()
_cancelled_stream_runs: set[tuple[str, str]] = set()
_active_stream_tasks: dict[tuple[str, str], asyncio.Task[Any]] = {}
_active_stream_runs_lock = Lock()


def _with_graph_recursion_limit(
    config: dict[str, Any] | None,
    *,
    thread_id: str,
    workspace_root: str | Path | None = None,
    guard_settings: LoopGuardSettings | None = None,
    continuation_nudge_count: int = 0,
) -> dict[str, Any]:
    """Ensure LangGraph gets loop guard config with an explicit thread id."""
    settings = guard_settings or resolve_loop_guard_settings(workspace_root=workspace_root)
    return with_loop_guard_config(
        config,
        thread_id=thread_id,
        settings=settings,
        continuation_nudge_count=continuation_nudge_count,
    )


async def _resolve_resume_input(agent: Any, agent_input: Any, config: dict[str, Any]) -> Any:
    """When agent_input is a Command(resume=...) and multiple interrupts are pending,
    remap resume to {interrupt_id: value} so LangGraph can route each one correctly."""
    if not isinstance(agent_input, Command):
        return agent_input
    try:
        snapshot = await agent.aget_state(config)
        pending = [
            intr
            for task in getattr(snapshot, "tasks", [])
            for intr in getattr(task, "interrupts", [])
        ]
    except Exception:
        return agent_input
    if len(pending) <= 1:
        return agent_input
    pending_ids = {str(intr.id) for intr in pending}
    if isinstance(agent_input.resume, dict) and pending_ids.issubset(set(agent_input.resume)):
        return agent_input
    return Command(resume={intr.id: agent_input.resume for intr in pending})


def _register_stream_run(thread_id: str, run_id: str) -> None:
    with _active_stream_runs_lock:
        _active_stream_runs.add((thread_id, run_id))
        _cancelled_stream_runs.discard((thread_id, run_id))


def _unregister_stream_run(thread_id: str, run_id: str) -> None:
    with _active_stream_runs_lock:
        _active_stream_runs.discard((thread_id, run_id))
        _cancelled_stream_runs.discard((thread_id, run_id))
        _active_stream_tasks.pop((thread_id, run_id), None)


def _attach_stream_run_task(thread_id: str, run_id: str) -> None:
    task = asyncio.current_task()
    if task is None:
        return
    with _active_stream_runs_lock:
        if (thread_id, run_id) in _active_stream_runs:
            _active_stream_tasks[(thread_id, run_id)] = task


def _request_stream_run_cancel(thread_id: str, run_id: str) -> None:
    with _active_stream_runs_lock:
        if (thread_id, run_id) in _active_stream_runs:
            _cancelled_stream_runs.add((thread_id, run_id))
            task = _active_stream_tasks.get((thread_id, run_id))
            if task is not None:
                task.cancel()


def _is_stream_run_cancel_requested(thread_id: str, run_id: str) -> bool:
    with _active_stream_runs_lock:
        return (thread_id, run_id) in _cancelled_stream_runs


def _is_stream_run_active(thread_id: str, run_id: str | None) -> bool:
    if not run_id:
        return False
    with _active_stream_runs_lock:
        return (thread_id, run_id) in _active_stream_runs


class ChatService:
    """Orchestrates chat-domain business logic."""

    def __init__(
        self,
        auth_repo: AuthRepository,
        thread_store: ThreadStore,
        daytona_manager: DaytonaSessionManager,
        checkpointer: BaseCheckpointSaver,
        settings: Settings,
    ):
        self._auth_repo = auth_repo
        self._thread_store = thread_store
        self._daytona_manager = daytona_manager
        self._checkpointer = checkpointer
        self._settings = settings
        self._workspace_checkpointers: dict[str, BaseCheckpointSaver] = {}

    def create_thread(self, user_id: str) -> dict[str, Any]:
        """Create a new thread for a user."""
        thread = self._thread_store.create_thread(user_id=user_id)
        return {
            "id": thread["id"],
            "user_id": thread["user_id"],
            "created_at": thread["created_at"],
            "updated_at": thread["updated_at"],
            "permission_overlay": thread["permission_overlay"],
        }

    def _checkpointer_for_workspace(self, workspace_root: str | Path | None) -> BaseCheckpointSaver:
        if workspace_root is None or not isinstance(self._checkpointer, AsyncJsonlCheckpointSaver):
            return self._checkpointer
        storage = StoragePathsService(self._settings)
        storage.ensure_project_metadata(workspace_root)
        storage.migrate_legacy_workspace(workspace_root)
        base_dir = str(storage.checkpoints_base_dir(workspace_root))
        checkpointer = self._workspace_checkpointers.get(base_dir)
        if checkpointer is None:
            checkpointer = AsyncJsonlCheckpointSaver(base_dir=base_dir)
            self._workspace_checkpointers[base_dir] = checkpointer
        return checkpointer

    def _checkpointer_for_thread(self, thread: dict[str, Any]) -> BaseCheckpointSaver:
        workspace_root = thread.get("workspace_root")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return self._checkpointer_for_workspace(workspace_root)
        return self._checkpointer

    @staticmethod
    def _iso_from_epoch(value: int | float | None) -> str:
        if value is None:
            return ""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(value))

    @staticmethod
    def _message_text_and_reasoning(entry: dict[str, Any]) -> tuple[str, str | None]:
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        content = message.get("content") if isinstance(message, dict) else []
        if not isinstance(content, list):
            return str(content or ""), None, []

        text_parts: list[str] = []
        reasoning_parts: list[str] = []
        direct_reasoning = message.get("reasoning_content")
        if isinstance(direct_reasoning, str):
            reasoning_parts.append(direct_reasoning)
        additional_kwargs = message.get("additional_kwargs")
        if isinstance(additional_kwargs, dict):
            additional_reasoning = additional_kwargs.get("reasoning_content")
            if isinstance(additional_reasoning, str):
                reasoning_parts.append(additional_reasoning)
        for block in content:
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue
            block_type = block.get("type")
            if block_type == "text":
                text_parts.append(str(block.get("text", "")))
            elif block_type == "thinking":
                reasoning_parts.append(str(block.get("thinking", "")))
            elif "text" in block:
                text_parts.append(str(block.get("text", "")))

        unique_reasoning_parts: list[str] = []
        seen_reasoning_parts: set[str] = set()
        for part in reasoning_parts:
            stripped = part.strip()
            if not stripped or stripped in seen_reasoning_parts:
                continue
            unique_reasoning_parts.append(stripped)
            seen_reasoning_parts.add(stripped)
        reasoning = "\n".join(unique_reasoning_parts).strip() or None
        return "\n".join(part for part in text_parts if part), reasoning

    @staticmethod
    def _tool_result_text(block: dict[str, Any]) -> str:
        content = block.get("content", "")
        if isinstance(content, list):
            return extract_text(content)
        return str(content or "")

    @staticmethod
    def _frame_status_for_output(tool_name: str, output_text: str) -> str:
        if tool_name in {"bash", "powershell"}:
            first_line = output_text.splitlines()[0] if output_text else ""
            if first_line.startswith("Exit code:"):
                try:
                    exit_code = int(first_line.split(":", 1)[1].strip())
                except ValueError:
                    return "completed"
                return "completed" if exit_code == 0 else "failed"
        return "completed"

    @staticmethod
    def _run_step_kind_for_tool(tool_name: str) -> str:
        if tool_name.startswith("task_") or tool_name.startswith("team_"):
            return "subagent"
        return "tool"

    @staticmethod
    def _tool_step_id(tool_call_id: str | None) -> str:
        if tool_call_id:
            return f"step_tool_{tool_call_id}"
        return f"step_{uuid.uuid4().hex}"

    @staticmethod
    def _permission_step_id(message_id: str | None) -> str:
        if message_id:
            return f"step_permission_{message_id}"
        return f"step_{uuid.uuid4().hex}"

    @staticmethod
    def _run_step_to_workspace_frame(step: dict[str, Any]) -> dict[str, Any] | None:
        if step.get("kind") != "tool":
            return None
        return {
            "id": f"frame_{step.get('id') or uuid.uuid4().hex}",
            "timestamp": str(step.get("startedAt") or ""),
            "toolName": str(step.get("toolName") or step.get("tool_name") or "tool"),
            "input": step.get("input") if isinstance(step.get("input"), dict) else {},
            "status": str(step.get("status") or "completed"),
            **({"summary": step["summary"]} if isinstance(step.get("summary"), str) else {}),
            **({"output": step["output"]} if isinstance(step.get("output"), str) else {}),
            **({"rawOutput": step["rawOutput"]} if isinstance(step.get("rawOutput"), str) else {}),
            **({"collapsed": step["collapsed"]} if isinstance(step.get("collapsed"), bool) else {}),
            **({"lineCount": step["lineCount"]} if isinstance(step.get("lineCount"), int) else {}),
            **({"classification": step["classification"]} if isinstance(step.get("classification"), str) else {}),
            **({"artifact": step["artifact"]} if isinstance(step.get("artifact"), dict) else {}),
        }

    @classmethod
    def _run_steps_to_workspace_frames(cls, run_steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        for step in run_steps:
            frame = cls._run_step_to_workspace_frame(step)
            if frame is not None:
                frames.append(frame)
        return frames

    @staticmethod
    def _extract_interrupt_payloads(value: Any) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        if isinstance(value, dict):
            if isinstance(value.get("behavior"), str):
                payloads.append(value)
            for key in ("value", "values", "interrupts"):
                nested = value.get(key)
                if nested is not None:
                    payloads.extend(ChatService._extract_interrupt_payloads(nested))
        elif isinstance(value, (list, tuple)):
            for item in value:
                payloads.extend(ChatService._extract_interrupt_payloads(item))
        return payloads

    async def _load_pending_permission_request(
        self,
        *,
        thread_id: str,
        checkpointer: BaseCheckpointSaver,
    ) -> dict[str, Any] | None:
        getter = getattr(checkpointer, "aget_tuple", None) or getattr(checkpointer, "get_tuple", None)
        if getter is None:
            return None

        try:
            result = getter({"configurable": {"thread_id": thread_id}})
            checkpoint_tuple = await result if asyncio.iscoroutine(result) else result
        except Exception:
            logger.warning("Failed to load checkpoint tuple for thread_id=%s", thread_id)
            return None

        if checkpoint_tuple is None:
            return None

        for _, channel, value in getattr(checkpoint_tuple, "pending_writes", []) or []:
            if channel != "__interrupt__":
                continue
            for payload in self._extract_interrupt_payloads(value):
                if payload.get("behavior") in {"ask", "deny", "ask_user"}:
                    return payload
        return None

    async def _load_thread_messages(
        self,
        thread_id: str,
        *,
        checkpointer: BaseCheckpointSaver | None = None,
        thread_status: str | None = None,
        last_stop_reason: str | None = None,
    ) -> list[dict[str, Any]]:
        getter = getattr(checkpointer or self._checkpointer, "get_full_message_entries", None)
        if getter is None:
            return []
        pending_permission_request = (
            await self._load_pending_permission_request(thread_id=thread_id, checkpointer=checkpointer or self._checkpointer)
            if thread_status == "requires_action"
            else None
        )
        try:
            entries = await getter({"configurable": {"thread_id": thread_id}})
        except Exception:
            logger.warning("Failed to load checkpoint messages for thread_id=%s", thread_id)
            return []

        messages: list[dict[str, Any]] = []
        pending_steps: dict[str, dict[str, Any]] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("type") or entry.get("message", {}).get("role") or "user")
            if role == "system":
                continue
            message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
            content = message.get("content") if isinstance(message, dict) else []
            if (
                role == "user"
                and isinstance(content, list)
                and content
                and all(isinstance(block, dict) and block.get("type") == "tool_result" for block in content)
            ):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    tool_use_id = str(block.get("tool_use_id") or "")
                    if not tool_use_id:
                        continue
                    run_step = pending_steps.pop(tool_use_id, None)
                    if run_step is None:
                        continue
                    output_text = self._tool_result_text(block)
                    run_step["output"] = output_text
                    run_step["status"] = self._frame_status_for_output(
                        str(run_step.get("toolName") or "tool"),
                        output_text,
                    )
                    run_step["endedAt"] = str(entry.get("timestamp") or run_step.get("startedAt") or "")
                    shell_meta = enrich_tool_output(
                        str(run_step.get("toolName") or "tool"),
                        run_step.get("input", {}),
                        output_text,
                    )
                    if isinstance(shell_meta.get("output"), str):
                        run_step["output"] = shell_meta["output"]
                    if isinstance(shell_meta.get("raw_output"), str):
                        run_step["rawOutput"] = shell_meta["raw_output"]
                    if isinstance(shell_meta.get("collapsed"), bool):
                        run_step["collapsed"] = shell_meta["collapsed"]
                    if isinstance(shell_meta.get("line_count"), int):
                        run_step["lineCount"] = shell_meta["line_count"]
                    if isinstance(shell_meta.get("classification"), str):
                        run_step["classification"] = shell_meta["classification"]
                    if isinstance(shell_meta.get("artifact"), dict):
                        run_step["artifact"] = shell_meta["artifact"]
                continue
            message_id = str(entry.get("uuid") or uuid.uuid4())
            run_steps: list[dict[str, Any]] = []
            stream_items: list[dict[str, Any]] = []
            text, reasoning = self._message_text_and_reasoning(entry)
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_use_id = str(block.get("id") or "")
                    step_id = self._tool_step_id(tool_use_id or None)
                    tool_name = str(block.get("name") or "tool")
                    tool_input = block.get("input") if isinstance(block.get("input"), dict) else {}
                    tool_summary = summarize_tool_input(tool_name, tool_input)
                    run_steps.append(
                        {
                            "id": step_id,
                            "runId": None,
                            "messageId": message_id,
                            "parentStepId": None,
                            "kind": self._run_step_kind_for_tool(tool_name),
                            "status": "in_progress",
                            "startedAt": str(entry.get("timestamp") or ""),
                            "endedAt": None,
                            "toolCallId": tool_use_id,
                            "toolName": tool_name,
                            "agentPath": None,
                            "input": tool_input,
                            **({"summary": tool_summary} if tool_summary else {}),
                        }
                    )
                    if tool_use_id:
                        pending_steps[tool_use_id] = run_steps[-1]
                    stream_items.append(
                        {
                            "id": str(uuid.uuid4()),
                            "type": "run_step",
                            "runStepId": step_id,
                        }
                    )
            if not text and not reasoning and not run_steps:
                continue
            normalized_role = role if role in {"user", "assistant", "system"} else "user"
            is_tool_only_assistant_message = (
                normalized_role == "assistant"
                and not text
                and not reasoning
                and run_steps
                and all(step.get("kind") == "tool" for step in run_steps)
            )
            if is_tool_only_assistant_message and messages:
                previous_message = messages[-1]
                previous_run_steps = previous_message.get("run_steps")
                previous_is_tool_only_assistant_message = (
                    previous_message.get("role") == "assistant"
                    and not previous_message.get("content")
                    and not previous_message.get("reasoning")
                    and isinstance(previous_run_steps, list)
                    and previous_run_steps
                    and all(step.get("kind") == "tool" for step in previous_run_steps)
                )
                if previous_is_tool_only_assistant_message:
                    previous_message_id = str(previous_message.get("id") or "")
                    for step in run_steps:
                        step["messageId"] = previous_message_id
                    previous_run_steps.extend(run_steps)
                    previous_message.setdefault("stream_items", []).extend(stream_items)
                    previous_message["message_type"] = "tool_activity"
                    previous_message["workspace_frames"] = self._run_steps_to_workspace_frames(previous_run_steps)
                    continue
            messages.append(
                {
                    "id": message_id,
                    "role": normalized_role,
                    "message_type": "tool_activity" if is_tool_only_assistant_message else "text",
                    "content": text,
                    "reasoning": reasoning,
                    "created_at": str(entry.get("timestamp") or ""),
                    "status": "done",
                    "tool_events": [],
                    "run_steps": run_steps,
                    "workspace_frames": self._run_steps_to_workspace_frames(run_steps),
                    "stream_items": stream_items,
                }
            )

        if thread_status == "interrupted" or last_stop_reason is not None:
            for run_step in pending_steps.values():
                run_step["status"] = "interrupted"
                run_step["endedAt"] = run_step.get("endedAt") or run_step.get("startedAt") or ""
        elif thread_status == "requires_action":
            for run_step in pending_steps.values():
                run_step["status"] = "pending"
            if pending_permission_request is not None:
                for message in reversed(messages):
                    if message.get("role") != "assistant":
                        continue
                    message["permission_request"] = pending_permission_request
                    permission_step = {
                        "id": self._permission_step_id(str(message.get("id") or "")),
                        "runId": None,
                        "messageId": message.get("id"),
                        "parentStepId": None,
                        "kind": "permission",
                        "status": "pending",
                        "startedAt": message.get("created_at") or "",
                        "endedAt": None,
                        "permissionRequest": pending_permission_request,
                    }
                    if not message.get("run_steps"):
                        message["run_steps"] = [permission_step]
                    elif not any(step.get("kind") == "permission" for step in message["run_steps"]):
                        message["run_steps"].append(permission_step)
                    message["workspace_frames"] = self._run_steps_to_workspace_frames(message.get("run_steps", []))
                    break
        for message in messages:
            if not message.get("run_steps"):
                if message.get("permission_request"):
                    message["run_steps"] = [
                        {
                            "id": self._permission_step_id(str(message.get("id") or "")),
                            "runId": None,
                            "messageId": message.get("id"),
                            "parentStepId": None,
                            "kind": "permission",
                            "status": "pending",
                            "startedAt": message.get("created_at") or "",
                            "endedAt": None,
                            "permissionRequest": message.get("permission_request"),
                        }
                    ]
                else:
                    message["run_steps"] = []
            message["workspace_frames"] = self._run_steps_to_workspace_frames(message.get("run_steps", []))
        return messages

    async def _thread_payload(self, thread: dict[str, Any], *, include_messages: bool = True) -> dict[str, Any]:
        thread = self._reconcile_stale_run(thread)
        messages = (
            await self._load_thread_messages(
                str(thread["id"]),
                checkpointer=self._checkpointer_for_thread(thread),
                thread_status=str(thread.get("status") or ""),
                last_stop_reason=(
                    str(thread["last_stop_reason"])
                    if thread.get("last_stop_reason") is not None
                    else None
                ),
            )
            if include_messages
            else []
        )
        title = thread.get("title") or (messages[0]["content"][:56] if messages else "New conversation")
        updated_at = int(thread.get("updated_at") or thread.get("created_at") or time.time())
        return {
            "id": thread["id"],
            "user_id": thread["user_id"],
            "title": title,
            "summary": thread.get("summary"),
            "created_at": int(thread.get("created_at") or updated_at),
            "updated_at": updated_at,
            "last_message_at": thread.get("last_message_at"),
            "workspace_root": thread.get("workspace_root"),
            "backend": thread.get("backend"),
            "status": thread.get("status") or "idle",
            "active_run_id": thread.get("active_run_id"),
            "run_started_at": thread.get("run_started_at"),
            "last_stop_run_id": thread.get("last_stop_run_id"),
            "last_stop_reason": thread.get("last_stop_reason"),
            "last_interrupted_at": thread.get("last_interrupted_at"),
            "model": thread.get("model"),
            "mode": thread.get("mode"),
            "profile_id": thread.get("profile_id"),
            "project": thread.get("project"),
            "is_favorite": bool(thread.get("is_favorite", False)),
            "permission_overlay": thread.get("permission_overlay") or {},
            "messages": messages,
        }

    def _reconcile_stale_run(self, thread: dict[str, Any]) -> dict[str, Any]:
        if thread.get("status") != "running":
            return thread
        thread_id = str(thread.get("id") or "")
        run_id = thread.get("active_run_id")
        started_at = thread.get("run_started_at")
        is_stale = (
            not _is_stream_run_active(thread_id, str(run_id) if run_id else None)
            and isinstance(started_at, int)
            and int(time.time()) - started_at > STALE_RUN_SECONDS
        )
        if not is_stale:
            return thread
        updated = self._thread_store.stop_run(
            thread_id=thread_id,
            user_id=str(thread.get("user_id")),
            run_id=str(run_id),
            reason="stale_run",
        )
        return updated or thread

    async def list_threads(self, user_id: str) -> dict[str, Any]:
        threads = self._thread_store.list_threads(user_id=user_id)
        return {"threads": [await self._thread_payload(thread, include_messages=False) for thread in threads]}

    async def get_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any]:
        thread = self._thread_store.get_owned_thread(thread_id=thread_id, user_id=user_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        return await self._thread_payload(thread)

    def update_thread(self, *, thread_id: str, user_id: str, payload: ThreadUpdatePayload) -> dict[str, Any]:
        title = payload.title.strip() if payload.title is not None else None
        summary = payload.summary.strip() if payload.summary is not None else None
        model = payload.model.strip() if payload.model is not None else None
        mode = payload.mode.strip() if payload.mode is not None else None
        profile_id = payload.profile_id.strip() if payload.profile_id is not None else None
        project = payload.project.strip() if payload.project is not None else None
        if payload.title is not None and not title:
            raise HTTPException(status_code=400, detail="Thread title cannot be empty")
        updated = self._thread_store.update_thread_metadata(
            thread_id=thread_id,
            user_id=user_id,
            title=title,
            summary=summary,
            model=model,
            mode=mode,
            profile_id=profile_id,
            project=project,
            is_favorite=payload.is_favorite,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Thread not found")
        return updated

    def delete_thread(self, *, thread_id: str, user_id: str) -> dict[str, bool]:
        thread = self._thread_store.get_owned_thread(thread_id=thread_id, user_id=user_id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        if not self._thread_store.delete_thread(thread_id=thread_id, user_id=user_id):
            raise HTTPException(status_code=404, detail="Thread not found")
        checkpointer = self._checkpointer_for_thread(thread)
        checkpoints_dir = getattr(checkpointer, "checkpoints_dir", None)
        if checkpoints_dir is not None:
            thread_dir = Path(checkpoints_dir) / thread_id
            try:
                if thread_dir.exists() and thread_dir.is_dir():
                    for path in sorted(thread_dir.rglob("*"), reverse=True):
                        if path.is_file():
                            path.unlink()
                        elif path.is_dir():
                            path.rmdir()
                    thread_dir.rmdir()
            except Exception:
                logger.warning("Failed to delete checkpoint data for thread_id=%s", thread_id)
        return {"deleted": True}

    def resolve_thread(
        self,
        request: ChatRequest,
        current_user: AuthUser,
    ) -> dict[str, Any]:
        """Get or create thread, touch if existing."""
        requested_thread_id = extract_requested_thread_id(request)
        if requested_thread_id:
            thread = self._thread_store.get_owned_thread(thread_id=requested_thread_id, user_id=current_user.id)
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")
            self._thread_store.touch_thread(thread_id=requested_thread_id, user_id=current_user.id)
            return thread
        return self._thread_store.create_thread(user_id=current_user.id)

    def build_backend(self, request: ChatRequest, thread_id: str) -> Any:
        """Create backend instance (Daytona or LocalSandbox)."""
        backend_mode, local_root_dir = extract_backend_selection(request)
        if backend_mode == "local":
            if local_root_dir:
                local_root = Path(local_root_dir).expanduser().resolve()
                if not local_root.exists() or not local_root.is_dir():
                    raise HTTPException(status_code=400, detail=f"Local backend root_dir is invalid: {local_root}")
                return LocalBackend(root_dir=str(local_root))
            return LocalBackend()
        else:
            try:
                return self._daytona_manager.get_backend(thread_id)
            except DaytonaUnavailableError as exc:
                logger.warning(
                    "Daytona backend unavailable; falling back to local backend (thread_id=%s): %s",
                    thread_id,
                    exc,
                )
                return LocalBackend()

    @staticmethod
    def _backend_name(backend: Any) -> str:
        if isinstance(backend, LocalBackend):
            return "local"
        return backend.__class__.__name__.lower()

    def _update_session_runtime(
        self,
        *,
        thread_id: str,
        user_id: str,
        workspace_root: Path,
        backend: Any,
        status: str,
        last_message_at: int | None = None,
        active_run_id: str | None = None,
        run_started_at: int | None = None,
        last_stop_reason: str | None = None,
        last_interrupted_at: int | None = None,
        clear_active_run: bool = False,
        clear_stop_reason: bool = False,
    ) -> None:
        self._thread_store.update_session_metadata(
            thread_id=thread_id,
            user_id=user_id,
            workspace_root=str(workspace_root.resolve()),
            backend=self._backend_name(backend),
            status=status,
            last_message_at=last_message_at,
            active_run_id=active_run_id,
            run_started_at=run_started_at,
            last_stop_reason=last_stop_reason,
            last_interrupted_at=last_interrupted_at,
            clear_active_run=clear_active_run,
            clear_stop_reason=clear_stop_reason,
        )

    def build_permission_context(
        self,
        request: ChatRequest,
        user_id: str,
        thread_id: str,
        workspace_root: Path,
    ) -> PermissionContext | None:
        """Build effective permission context with optional overrides."""
        permission_service = PermissionContextService(self._auth_repo, self._thread_store)
        context = permission_service.build_effective_context(
            user_id=user_id,
            thread_id=thread_id,
            workspace_root=workspace_root,
        )
        override_mode = extract_permission_override_mode(request)
        if override_mode is None:
            return context
        base_context = context
        if base_context is None:
            from src.ai.permissions import build_default_permission_context

            base_context = build_default_permission_context(workspace_root=workspace_root)
        return set_mode(base_context, override_mode)

    def apply_resume_grant(
        self,
        request: ChatRequest,
        user_id: str,
        thread_id: str,
    ) -> None:
        """Persist resume grant into permission context if approved."""
        resume_payload = extract_resume_payload(request)
        if not resume_payload or not resume_payload.get("approved", False):
            return
        resolved = resolve_resume_grant_matcher(resume_payload)
        if resolved is None:
            return
        scope, subject, matcher = resolved
        permission_service = PermissionContextService(self._auth_repo, self._thread_store)
        permission_service.grant_rule_for_scope(
            user_id=user_id,
            thread_id=thread_id,
            scope=scope,
            subject=subject,
            matcher=matcher,
        )

    async def append_interruption_event(
        self,
        *,
        thread_id: str,
        run_id: str,
        reason: str,
        workspace_root: Path | None = None,
    ) -> None:
        append = getattr(self._checkpointer_for_workspace(workspace_root), "append_interruption_event", None)
        if append is None:
            return
        try:
            await append(thread_id=thread_id, run_id=run_id, reason=reason)
        except Exception:
            logger.warning("Failed to append interruption event for thread_id=%s run_id=%s", thread_id, run_id)

    async def stop_run(self, *, thread_id: str, user_id: str, run_id: str, reason: str) -> dict[str, Any]:
        _request_stream_run_cancel(thread_id, run_id)
        updated = self._thread_store.stop_run(
            thread_id=thread_id,
            user_id=user_id,
            run_id=run_id,
            reason=reason,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Active run not found")
        workspace_root = None
        thread = self._thread_store.get_owned_thread(thread_id=thread_id, user_id=user_id)
        if thread and isinstance(thread.get("workspace_root"), str):
            workspace_root = Path(str(thread["workspace_root"]))
        await self.append_interruption_event(
            thread_id=thread_id,
            run_id=run_id,
            reason=reason,
            workspace_root=workspace_root,
        )
        return {"stopped": True, "thread_id": thread_id, "run_id": run_id, "reason": reason}

    def resolve_model(self, request: ChatRequest) -> tuple[Any, str, str, str]:
        """Resolve model, provider, and capability model name.

        Returns:
            (model, resolved_model_id, resolved_provider, capability_model_name)
        """
        profile = extract_profile(request, self._settings)
        if profile:
            resolved_model = profile["model"]
            resolved_provider = profile["provider"]
            model = build_chat_model(
                profile["provider"],
                profile["model"],
                api_keys={"api_key": profile["api_key"]},
                base_url=profile["base_url"],
                api_version=profile["api_version"],
                deployment=profile["deployment"],
                reasoning_enabled=profile["reasoning_enabled"],
                reasoning_effort=profile["reasoning_effort"],
                thinking_budget_tokens=profile["thinking_budget_tokens"],
                model_kwargs=profile["model_kwargs"],
            )
            return model, resolved_model, resolved_provider, profile["model"]
        else:
            resolved_model = resolve_model_id(request.model)
            user_api_keys = extract_user_api_keys(request)
            registry = {spec.id: spec for spec in get_model_registry()}
            spec = registry[resolved_model]
            resolved_provider = spec.provider
            model = build_chat_model(spec.provider, spec.model, api_keys=user_api_keys)
            return model, resolved_model, resolved_provider, spec.model


    def build_agent(
        self,
        model: Any,
        backend: Any,
        permission_context: PermissionContext | None,
        media_block_support: tuple[bool, bool],
        owner_user_id: str | None = None,
        workspace_root: Path | None = None,
    ) -> Any:
        """Create aethos agent."""
        return create_aethos_agent(
            model=model,
            backend=backend,
            permission_context=permission_context,
            checkpointer=self._checkpointer_for_workspace(workspace_root),
            media_block_support=media_block_support,
            owner_user_id=owner_user_id,
        )

    async def _record_runtime_stop(
        self,
        *,
        thread_id: str,
        user_id: str,
        run_id: str | None,
        workspace_root: str | None,
        backend: Any,
        reason: str,
    ) -> None:
        if run_id:
            await self.append_interruption_event(
                thread_id=thread_id,
                run_id=run_id,
                reason=reason,
                workspace_root=workspace_root,
            )
            stopped = self._thread_store.stop_run(
                thread_id=thread_id,
                user_id=user_id,
                run_id=run_id,
                reason=reason,
            )
            if stopped is not None:
                return
        self._update_session_runtime(
            thread_id=thread_id,
            user_id=user_id,
            workspace_root=workspace_root,
            backend=backend,
            status="interrupted",
            last_stop_reason=reason,
            last_interrupted_at=int(time.time()),
            clear_active_run=bool(run_id),
        )

    @staticmethod
    def _stream_stop_delta(reason: str, guard_settings: LoopGuardSettings) -> dict[str, Any]:
        delta: dict[str, Any] = {"stop_reason": reason}
        if reason == GRAPH_RECURSION_STOP_REASON:
            delta["recursion_limit"] = guard_settings.graph_recursion_limit
        return delta

    @staticmethod
    def _saw_tool_after_last_human(messages: list[Any]) -> bool:
        for message in reversed(messages):
            message_type = getattr(message, "type", "")
            if message_type in {"human", "user"}:
                return False
            if message_type == "tool":
                return True
        return any(getattr(message, "type", "") == "tool" for message in messages)

    async def _collect_interrupts(self, agent: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
        interrupts: list[dict[str, Any]] = []
        try:
            snapshot = await agent.aget_state(config)
            for task in getattr(snapshot, "tasks", []):
                for intr in getattr(task, "interrupts", []):
                    interrupts.append(intr.value)
        except Exception:
            logger.debug("aget_state not available or failed; skipping interrupt check")
        return interrupts

    async def _stream_agent_iteration_live(
        self,
        *,
        agent: Any,
        agent_input: Any,
        model: str,
        config: dict[str, Any],
        allow_disconnect_checks: bool,
        thread_id: str | None = None,
        run_id: str | None = None,
        http_request: Request | None = None,
    ) -> AsyncIterator[tuple[str, Any]]:
        assistant_text_parts: list[str] = []
        interrupts: list[dict[str, Any]] = []
        _tool_input_cache: dict[str, Any] = {}
        saw_output = False
        saw_tool_event = False
        interrupted_reason: str | None = None
        first_event_logged = False
        first_token_logged = False
        stream_started_at = time.perf_counter()

        def _log_stream_latency(stage: str) -> None:
            logger.info(
                "stream_latency stage=%s session_id=%s run_id=%s delta_ms=%.2f",
                stage,
                thread_id or "-",
                run_id or "-",
                (time.perf_counter() - stream_started_at) * 1000,
            )

        try:
            async for event in agent.astream_events(agent_input, config=config, version="v2"):
                if not first_event_logged:
                    _log_stream_latency("first_event")
                    first_event_logged = True
                if allow_disconnect_checks and thread_id and run_id and http_request is not None:
                    if _is_stream_run_cancel_requested(thread_id, run_id):
                        interrupted_reason = "user_cancel"
                        break
                    if await http_request.is_disconnected():
                        interrupted_reason = "client_disconnect"
                        break

                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text, thinking = parse_content(chunk.content)
                    thinking = thinking or extract_reasoning_from_chunk(chunk)
                    if not first_token_logged and (thinking or text):
                        _log_stream_latency("first_token")
                        first_token_logged = True
                    if thinking:
                        saw_output = True
                        yield "frame", sse({"reasoning_content": thinking}, model)
                    if text:
                        saw_output = True
                        assistant_text_parts.append(text)
                        yield "frame", sse({"content": text}, model)
                elif kind == "on_tool_start":
                    if not first_token_logged:
                        _log_stream_latency("first_visible_output")
                        first_token_logged = True
                    saw_output = True
                    saw_tool_event = True
                    tool_name = event.get("name", "tool")
                    tool_input = sanitize_tool_input(event.get("data", {}).get("input", {}))
                    tool_call_id = str(event.get("run_id", tool_name))
                    _tool_input_cache[tool_call_id] = tool_input
                    step_id = self._tool_step_id(tool_call_id)
                    label = summarize_tool_input(tool_name, tool_input)
                    yield "frame", sse(
                        {
                            "tool_event": {
                                "step_id": step_id,
                                "tool_call_id": tool_call_id,
                                "name": tool_name,
                                "input": tool_input,
                                "phase": "start",
                                **({"summary": label} if label else {}),
                            }
                        },
                        model,
                    )
                elif kind == "on_tool_end":
                    if not first_token_logged:
                        _log_stream_latency("first_visible_output")
                        first_token_logged = True
                    saw_output = True
                    saw_tool_event = True
                    tool_name = event.get("name", "tool")
                    event_data = event.get("data", {})
                    raw_output = event_data.get("output", "")
                    tool_call_id = str(event.get("run_id", tool_name))
                    tool_input = _tool_input_cache.pop(tool_call_id, sanitize_tool_input(event_data.get("input", {})))
                    output_text = extract_tool_output(raw_output)
                    shell_meta = enrich_tool_output(tool_name, tool_input, output_text)
                    yield "frame", sse(
                        {
                            "tool_event": {
                                "step_id": self._tool_step_id(tool_call_id),
                                "tool_call_id": tool_call_id,
                                **shell_meta,
                                "name": tool_name,
                                "phase": "end",
                            }
                        },
                        model,
                    )
        except GraphInterrupt:
            interrupts = await self._collect_interrupts(agent, config)
            for intr in interrupts:
                yield "frame", sse({"permission_request": intr}, model)
        if interrupted_reason is None and not interrupts:
            interrupts = await self._collect_interrupts(agent, config)
            for intr in interrupts:
                yield "frame", sse({"permission_request": intr}, model)

        yield "result", {
            "assistant_text": "".join(assistant_text_parts),
            "interrupts": interrupts,
            "saw_output": saw_output,
            "saw_tool_event": saw_tool_event,
            "interrupted_reason": interrupted_reason,
        }

    async def stream_response(
        self,
        *,
        agent: Any,
        agent_input: Any,
        model: str,
        thread_id: str,
        backend: Any,
        current_user: AuthUser,
        messages: list[Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream agent events (content, thinking, tool calls, interrupts)."""
        workspace_root = workspace_root_for_backend(backend)
        guard_settings = resolve_loop_guard_settings(workspace_root=workspace_root)
        config = _with_graph_recursion_limit(config, thread_id=thread_id, guard_settings=guard_settings)
        msg_count = len(messages) if messages else 0
        logger.info("Streaming chat request started (model=%s, session_id=%s, messages=%d)", model, thread_id, msg_count)
        nudge_count = 0
        current_input = agent_input
        saw_output = False
        final_status = "idle"
        guard = ContinuationNudgeGuard()

        try:
            while True:
                iteration_config = _with_graph_recursion_limit(
                    config,
                    thread_id=thread_id,
                    workspace_root=workspace_root,
                    guard_settings=guard_settings,
                    continuation_nudge_count=nudge_count,
                )
                result: dict[str, Any] | None = None
                async for item_type, item in self._stream_agent_iteration_live(
                    agent=agent,
                    agent_input=current_input,
                    model=model,
                    config=iteration_config,
                    allow_disconnect_checks=False,
                ):
                    if item_type == "frame":
                        yield item
                    else:
                        result = item
                if result is None:
                    result = {
                        "assistant_text": "",
                        "interrupts": [],
                        "saw_output": False,
                        "saw_tool_event": False,
                        "interrupted_reason": None,
                    }
                saw_output = saw_output or bool(result["saw_output"])
                decision = guard.evaluate(
                    assistant_text=str(result["assistant_text"]),
                    saw_tool_event=bool(result["saw_tool_event"]),
                    saw_interrupt=bool(result["interrupts"]),
                    nudge_count=nudge_count,
                    settings=guard_settings,
                )
                if decision.should_nudge:
                    nudge_count += 1
                    logger.info(
                        "Continuation nudge triggered (%s/%s) for session_id=%s: %s",
                        nudge_count,
                        guard_settings.continuation_nudge_limit,
                        thread_id,
                        decision.matched_text[-120:],
                    )
                    current_input = build_continuation_nudge_input()
                    continue
                if decision.stop_after_cap:
                    final_status = "interrupted"
                    self._update_session_runtime(
                        thread_id=thread_id,
                        user_id=current_user.id,
                        workspace_root=workspace_root,
                        backend=backend,
                        status="interrupted",
                        last_stop_reason=CONTINUATION_NUDGE_STOP_REASON,
                        last_interrupted_at=int(time.time()),
                    )
                    yield sse(self._stream_stop_delta(CONTINUATION_NUDGE_STOP_REASON, guard_settings), model, finish_reason="stop")
                    yield "data: [DONE]\n\n"
                    return
                final_status = "requires_action" if result["interrupts"] else "idle"
                logger.info("Streaming chat request finished (model=%s, session_id=%s)", model, thread_id)
                yield sse({}, model, finish_reason="stop")
                yield "data: [DONE]\n\n"
                return
        except GraphRecursionError:
            final_status = "interrupted"
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status="interrupted",
                last_stop_reason=GRAPH_RECURSION_STOP_REASON,
                last_interrupted_at=int(time.time()),
            )
            yield sse(self._stream_stop_delta(GRAPH_RECURSION_STOP_REASON, guard_settings), model, finish_reason="length")
            yield "data: [DONE]\n\n"
            return
        finally:
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status=final_status,
                last_message_at=int(time.time()) if saw_output else None,
            )
        return
        interrupts: list[dict[str, Any]] = []
        saw_output = False
        final_status = "idle"
        # Cache tool inputs from on_tool_start keyed by run_id — on_tool_end may not include input.
        _tool_input_cache: dict[str, Any] = {}

        try:
            async for event in agent.astream_events(agent_input, config=config, version="v2"):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text, thinking = parse_content(chunk.content)
                    thinking = thinking or extract_reasoning_from_chunk(chunk)
                    if thinking:
                        saw_output = True
                        yield sse({"reasoning_content": thinking}, model)
                    if text:
                        saw_output = True
                        yield sse({"content": text}, model)
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    tool_input = sanitize_tool_input(event.get("data", {}).get("input", {}))
                    tool_call_id = str(event.get("run_id", tool_name))
                    _tool_input_cache[tool_call_id] = tool_input
                    step_id = self._tool_step_id(tool_call_id)
                    label = summarize_tool_input(tool_name, tool_input)
                    yield sse(
                        {
                            "tool_event": {
                                "step_id": step_id,
                                "tool_call_id": tool_call_id,
                                "name": tool_name,
                                "input": tool_input,
                                "phase": "start",
                                **({"summary": label} if label else {}),
                            }
                        },
                        model,
                    )
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "tool")
                    event_data = event.get("data", {})
                    raw_output = event_data.get("output", "")
                    tool_call_id = str(event.get("run_id", tool_name))
                    tool_input = _tool_input_cache.pop(tool_call_id, sanitize_tool_input(event_data.get("input", {})))
                    output_text = extract_tool_output(raw_output)
                    shell_meta = enrich_tool_output(tool_name, tool_input, output_text)
                    yield sse(
                        {
                            "tool_event": {
                                "step_id": self._tool_step_id(tool_call_id),
                                "tool_call_id": tool_call_id,
                                **shell_meta,
                                "name": tool_name,
                                "phase": "end",
                            }
                        },
                        model,
                    )

            # Check for pending interrupts
            try:
                snapshot = await agent.aget_state(config)
                for task in getattr(snapshot, "tasks", []):
                    for intr in getattr(task, "interrupts", []):
                        interrupts.append(intr.value)
                        yield sse({"permission_request": intr.value}, model)
            except Exception:
                logger.debug("aget_state not available or failed — skipping interrupt check")

            final_status = "requires_action" if interrupts else "idle"
            logger.info("Streaming chat request finished (model=%s, session_id=%s)", model, thread_id)
            yield sse({}, model, finish_reason="stop")
            yield "data: [DONE]\n\n"
        except GraphRecursionError:
            final_status = "interrupted"
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status="interrupted",
                last_stop_reason=GRAPH_RECURSION_STOP_REASON,
                last_interrupted_at=int(time.time()),
            )
            yield sse(self._stream_stop_delta(GRAPH_RECURSION_STOP_REASON, guard_settings), model, finish_reason="length")
            yield "data: [DONE]\n\n"
        finally:
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status=final_status,
                last_message_at=int(time.time()) if saw_output else None,
            )

    async def stream_response_with_run(
        self,
        *,
        agent: Any,
        agent_input: Any,
        model: str,
        thread_id: str,
        run_id: str,
        backend: Any,
        current_user: AuthUser,
        http_request: Request,
        messages: list[Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream a run and persist explicit interruption state on disconnect."""
        workspace_root = workspace_root_for_backend(backend)
        guard_settings = resolve_loop_guard_settings(workspace_root=workspace_root)
        config = _with_graph_recursion_limit(config, thread_id=thread_id, guard_settings=guard_settings)
        msg_count = len(messages) if messages else 0
        logger.info("Streaming chat request started (model=%s, session_id=%s, messages=%d)", model, thread_id, msg_count)
        nudge_count = 0
        current_input = agent_input
        saw_output = False
        final_status = "idle"
        interrupted_reason: str | None = None
        guard = ContinuationNudgeGuard()

        try:
            _attach_stream_run_task(thread_id, run_id)
            yield sse({"run_id": run_id}, model)
            while True:
                iteration_config = _with_graph_recursion_limit(
                    config,
                    thread_id=thread_id,
                    workspace_root=workspace_root,
                    guard_settings=guard_settings,
                    continuation_nudge_count=nudge_count,
                )
                result: dict[str, Any] | None = None
                async for item_type, item in self._stream_agent_iteration_live(
                    agent=agent,
                    agent_input=current_input,
                    model=model,
                    config=iteration_config,
                    allow_disconnect_checks=True,
                    thread_id=thread_id,
                    run_id=run_id,
                    http_request=http_request,
                ):
                    if item_type == "frame":
                        yield item
                    else:
                        result = item
                if result is None:
                    result = {
                        "assistant_text": "",
                        "interrupts": [],
                        "saw_output": False,
                        "saw_tool_event": False,
                        "interrupted_reason": None,
                    }
                interrupted_reason = result["interrupted_reason"]
                saw_output = saw_output or bool(result["saw_output"])
                if interrupted_reason is not None:
                    final_status = "interrupted"
                    await self.append_interruption_event(
                        thread_id=thread_id,
                        run_id=run_id,
                        reason=interrupted_reason,
                        workspace_root=workspace_root,
                    )
                    break
                decision = guard.evaluate(
                    assistant_text=str(result["assistant_text"]),
                    saw_tool_event=bool(result["saw_tool_event"]),
                    saw_interrupt=bool(result["interrupts"]),
                    nudge_count=nudge_count,
                    settings=guard_settings,
                )
                if decision.should_nudge:
                    nudge_count += 1
                    logger.info(
                        "Continuation nudge triggered (%s/%s) for session_id=%s: %s",
                        nudge_count,
                        guard_settings.continuation_nudge_limit,
                        thread_id,
                        decision.matched_text[-120:],
                    )
                    current_input = build_continuation_nudge_input()
                    continue
                if decision.stop_after_cap:
                    interrupted_reason = CONTINUATION_NUDGE_STOP_REASON
                    final_status = "interrupted"
                    await self.append_interruption_event(
                        thread_id=thread_id,
                        run_id=run_id,
                        reason=interrupted_reason,
                        workspace_root=workspace_root,
                    )
                    yield sse(self._stream_stop_delta(CONTINUATION_NUDGE_STOP_REASON, guard_settings), model, finish_reason="stop")
                    yield "data: [DONE]\n\n"
                    break
                final_status = "requires_action" if result["interrupts"] else "idle"
                logger.info("Streaming chat request finished (model=%s, session_id=%s)", model, thread_id)
                yield sse({}, model, finish_reason="stop")
                yield "data: [DONE]\n\n"
                break
        except GraphRecursionError:
            interrupted_reason = GRAPH_RECURSION_STOP_REASON
            final_status = "interrupted"
            await self.append_interruption_event(
                thread_id=thread_id,
                run_id=run_id,
                reason=interrupted_reason,
                workspace_root=workspace_root,
            )
            yield sse(self._stream_stop_delta(GRAPH_RECURSION_STOP_REASON, guard_settings), model, finish_reason="length")
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            interrupted_reason = "user_cancel" if _is_stream_run_cancel_requested(thread_id, run_id) else "client_disconnect"
            final_status = "interrupted"
            await self.append_interruption_event(
                thread_id=thread_id,
                run_id=run_id,
                reason=interrupted_reason,
                workspace_root=workspace_root,
            )
            raise
        finally:
            _unregister_stream_run(thread_id, run_id)
            if interrupted_reason is not None:
                self._thread_store.stop_run(
                    thread_id=thread_id,
                    user_id=current_user.id,
                    run_id=run_id,
                    reason=interrupted_reason,
                )
                return
            latest_thread = self._thread_store.get_owned_thread(thread_id=thread_id, user_id=current_user.id)
            if latest_thread and latest_thread.get("last_stop_run_id") == run_id:
                return
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status=final_status,
                last_message_at=int(time.time()) if saw_output else None,
                clear_active_run=True,
            )
        return
        interrupts: list[dict[str, Any]] = []
        saw_output = False
        final_status = "idle"
        interrupted_reason: str | None = None
        # Cache tool inputs from on_tool_start keyed by run_id — on_tool_end may not include input.
        _tool_input_cache: dict[str, Any] = {}

        try:
            _attach_stream_run_task(thread_id, run_id)
            yield sse({"run_id": run_id}, model)
            async for event in agent.astream_events(agent_input, config=config, version="v2"):
                if _is_stream_run_cancel_requested(thread_id, run_id):
                    interrupted_reason = "user_cancel"
                    break
                if await http_request.is_disconnected():
                    interrupted_reason = "client_disconnect"
                    break
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text, thinking = parse_content(chunk.content)
                    thinking = thinking or extract_reasoning_from_chunk(chunk)
                    if thinking:
                        saw_output = True
                        yield sse({"reasoning_content": thinking}, model)
                    if text:
                        saw_output = True
                        yield sse({"content": text}, model)
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    tool_input = sanitize_tool_input(event.get("data", {}).get("input", {}))
                    tool_call_id = str(event.get("run_id", tool_name))
                    _tool_input_cache[tool_call_id] = tool_input
                    step_id = self._tool_step_id(tool_call_id)
                    label = summarize_tool_input(tool_name, tool_input)
                    yield sse(
                        {
                            "tool_event": {
                                "step_id": step_id,
                                "tool_call_id": tool_call_id,
                                "name": tool_name,
                                "input": tool_input,
                                "phase": "start",
                                **({"summary": label} if label else {}),
                            }
                        },
                        model,
                    )
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "tool")
                    event_data = event.get("data", {})
                    raw_output = event_data.get("output", "")
                    tool_call_id = str(event.get("run_id", tool_name))
                    tool_input = _tool_input_cache.pop(tool_call_id, sanitize_tool_input(event_data.get("input", {})))
                    output_text = extract_tool_output(raw_output)
                    shell_meta = enrich_tool_output(tool_name, tool_input, output_text)
                    yield sse(
                        {
                            "tool_event": {
                                "step_id": self._tool_step_id(tool_call_id),
                                "tool_call_id": tool_call_id,
                                **shell_meta,
                                "name": tool_name,
                                "phase": "end",
                            }
                        },
                        model,
                    )

            if interrupted_reason is None:
                try:
                    snapshot = await agent.aget_state(config)
                    for task in getattr(snapshot, "tasks", []):
                        for intr in getattr(task, "interrupts", []):
                            interrupts.append(intr.value)
                            yield sse({"permission_request": intr.value}, model)
                except Exception:
                    logger.debug("aget_state not available or failed - skipping interrupt check")

                final_status = "requires_action" if interrupts else "idle"
                logger.info("Streaming chat request finished (model=%s, session_id=%s)", model, thread_id)
                yield sse({}, model, finish_reason="stop")
                yield "data: [DONE]\n\n"
            else:
                final_status = "interrupted"
                await self.append_interruption_event(
                    thread_id=thread_id,
                    run_id=run_id,
                    reason=interrupted_reason,
                    workspace_root=workspace_root,
                )
        except GraphRecursionError:
            interrupted_reason = GRAPH_RECURSION_STOP_REASON
            final_status = "interrupted"
            await self.append_interruption_event(
                thread_id=thread_id,
                run_id=run_id,
                reason=interrupted_reason,
                workspace_root=workspace_root,
            )
            yield sse(self._stream_stop_delta(GRAPH_RECURSION_STOP_REASON, guard_settings), model, finish_reason="length")
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            interrupted_reason = "user_cancel" if _is_stream_run_cancel_requested(thread_id, run_id) else "client_disconnect"
            final_status = "interrupted"
            await self.append_interruption_event(
                thread_id=thread_id,
                run_id=run_id,
                reason=interrupted_reason,
                workspace_root=workspace_root,
            )
            raise
        finally:
            _unregister_stream_run(thread_id, run_id)
            if interrupted_reason is not None:
                self._thread_store.stop_run(
                    thread_id=thread_id,
                    user_id=current_user.id,
                    run_id=run_id,
                    reason=interrupted_reason,
                )
                return
            latest_thread = self._thread_store.get_owned_thread(thread_id=thread_id, user_id=current_user.id)
            if latest_thread and latest_thread.get("last_stop_run_id") == run_id:
                return
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status=final_status,
                last_message_at=int(time.time()) if saw_output else None,
                clear_active_run=True,
            )

    async def stream_resume_response(
        self,
        *,
        agent: Any,
        agent_input: Any,
        model: str,
        thread_id: str,
        run_id: str,
        backend: Any,
        current_user: AuthUser,
        http_request: Request,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream a resumed run with LangGraph events."""
        workspace_root = workspace_root_for_backend(backend)
        guard_settings = resolve_loop_guard_settings(workspace_root=workspace_root)
        config = _with_graph_recursion_limit(config, thread_id=thread_id, guard_settings=guard_settings)
        logger.info("Streaming resumed chat request started (model=%s, session_id=%s)", model, thread_id)
        nudge_count = 0
        saw_output = False
        final_status = "idle"
        interrupted_reason: str | None = None
        guard = ContinuationNudgeGuard()

        try:
            _attach_stream_run_task(thread_id, run_id)
            yield sse({"run_id": run_id}, model)
            current_input = await _resolve_resume_input(agent, agent_input, config)
            while True:
                iteration_config = _with_graph_recursion_limit(
                    config,
                    thread_id=thread_id,
                    workspace_root=workspace_root,
                    guard_settings=guard_settings,
                    continuation_nudge_count=nudge_count,
                )
                result: dict[str, Any] | None = None
                async for item_type, item in self._stream_agent_iteration_live(
                    agent=agent,
                    agent_input=current_input,
                    model=model,
                    config=iteration_config,
                    allow_disconnect_checks=True,
                    thread_id=thread_id,
                    run_id=run_id,
                    http_request=http_request,
                ):
                    if item_type == "frame":
                        yield item
                    else:
                        result = item
                if result is None:
                    result = {
                        "assistant_text": "",
                        "interrupts": [],
                        "saw_output": False,
                        "saw_tool_event": False,
                        "interrupted_reason": None,
                    }
                interrupted_reason = result["interrupted_reason"]
                saw_output = saw_output or bool(result["saw_output"])
                if interrupted_reason is not None:
                    final_status = "interrupted"
                    await self.append_interruption_event(
                        thread_id=thread_id,
                        run_id=run_id,
                        reason=interrupted_reason,
                        workspace_root=workspace_root,
                    )
                    break
                decision = guard.evaluate(
                    assistant_text=str(result["assistant_text"]),
                    saw_tool_event=bool(result["saw_tool_event"]),
                    saw_interrupt=bool(result["interrupts"]),
                    nudge_count=nudge_count,
                    settings=guard_settings,
                )
                if decision.should_nudge:
                    nudge_count += 1
                    logger.info(
                        "Continuation nudge triggered (%s/%s) for resumed session_id=%s: %s",
                        nudge_count,
                        guard_settings.continuation_nudge_limit,
                        thread_id,
                        decision.matched_text[-120:],
                    )
                    current_input = build_continuation_nudge_input()
                    continue
                if decision.stop_after_cap:
                    interrupted_reason = CONTINUATION_NUDGE_STOP_REASON
                    final_status = "interrupted"
                    await self.append_interruption_event(
                        thread_id=thread_id,
                        run_id=run_id,
                        reason=interrupted_reason,
                        workspace_root=workspace_root,
                    )
                    yield sse(self._stream_stop_delta(CONTINUATION_NUDGE_STOP_REASON, guard_settings), model, finish_reason="stop")
                    yield "data: [DONE]\n\n"
                    break
                final_status = "requires_action" if result["interrupts"] else "idle"
                logger.info("Streaming resumed chat request finished (model=%s, session_id=%s)", model, thread_id)
                yield sse({}, model, finish_reason="stop")
                yield "data: [DONE]\n\n"
                break
        except GraphRecursionError:
            interrupted_reason = GRAPH_RECURSION_STOP_REASON
            final_status = "interrupted"
            await self.append_interruption_event(
                thread_id=thread_id,
                run_id=run_id,
                reason=interrupted_reason,
                workspace_root=workspace_root,
            )
            yield sse(self._stream_stop_delta(GRAPH_RECURSION_STOP_REASON, guard_settings), model, finish_reason="length")
            yield "data: [DONE]\n\n"
        except asyncio.CancelledError:
            interrupted_reason = "user_cancel" if _is_stream_run_cancel_requested(thread_id, run_id) else "client_disconnect"
            await self.append_interruption_event(
                thread_id=thread_id,
                run_id=run_id,
                reason=interrupted_reason,
                workspace_root=workspace_root,
            )
            raise
        finally:
            if interrupted_reason is None and _is_stream_run_cancel_requested(thread_id, run_id):
                interrupted_reason = "user_cancel"
                await self.append_interruption_event(
                    thread_id=thread_id,
                    run_id=run_id,
                    reason=interrupted_reason,
                    workspace_root=workspace_root,
                )
            if interrupted_reason is None and await http_request.is_disconnected():
                interrupted_reason = "client_disconnect"
                await self.append_interruption_event(
                    thread_id=thread_id,
                    run_id=run_id,
                    reason=interrupted_reason,
                    workspace_root=workspace_root,
                )
            if interrupted_reason is not None:
                self._thread_store.stop_run(
                    thread_id=thread_id,
                    user_id=current_user.id,
                    run_id=run_id,
                    reason=interrupted_reason,
                )
                return
            latest_thread = self._thread_store.get_owned_thread(thread_id=thread_id, user_id=current_user.id)
            if latest_thread and latest_thread.get("last_stop_run_id") == run_id:
                return
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status=final_status,
                last_message_at=int(time.time()) if saw_output else None,
                clear_active_run=True,
            )
        return
        interrupts: list[dict[str, Any]] = []
        saw_output = False
        final_status = "idle"
        interrupted_reason: str | None = None

        try:
            _attach_stream_run_task(thread_id, run_id)
            yield sse({"run_id": run_id}, model)
            try:
                resolved_input = await _resolve_resume_input(agent, agent_input, config)
                _tool_input_cache: dict[str, Any] = {}
                async for event in agent.astream_events(resolved_input, config=config, version="v2"):
                    if _is_stream_run_cancel_requested(thread_id, run_id):
                        interrupted_reason = "user_cancel"
                        break
                    if await http_request.is_disconnected():
                        interrupted_reason = "client_disconnect"
                        break
                    kind = event["event"]

                    if kind == "on_chat_model_stream":
                        chunk = event["data"]["chunk"]
                        text, thinking = parse_content(chunk.content)
                        thinking = thinking or extract_reasoning_from_chunk(chunk)
                        if thinking:
                            saw_output = True
                            yield sse({"reasoning_content": thinking}, model)
                        if text:
                            saw_output = True
                            yield sse({"content": text}, model)
                    elif kind == "on_tool_start":
                        tool_name = event.get("name", "tool")
                        tool_input = sanitize_tool_input(event.get("data", {}).get("input", {}))
                        tool_call_id = str(event.get("run_id", tool_name))
                        _tool_input_cache[tool_call_id] = tool_input
                        saw_output = True
                        step_id = self._tool_step_id(tool_call_id)
                        label = summarize_tool_input(tool_name, tool_input)
                        yield sse(
                            {
                                "tool_event": {
                                    "step_id": step_id,
                                    "tool_call_id": tool_call_id,
                                    "name": tool_name,
                                    "input": tool_input,
                                    "phase": "start",
                                    **({"summary": label} if label else {}),
                                }
                            },
                            model,
                        )
                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "tool")
                        event_data = event.get("data", {})
                        raw_output = event_data.get("output", "")
                        tool_call_id = str(event.get("run_id", tool_name))
                        tool_input = _tool_input_cache.pop(tool_call_id, sanitize_tool_input(event_data.get("input", {})))
                        output_text = extract_tool_output(raw_output)
                        shell_meta = enrich_tool_output(tool_name, tool_input, output_text)
                        saw_output = True
                        yield sse(
                            {
                                "tool_event": {
                                    "step_id": self._tool_step_id(tool_call_id),
                                    "tool_call_id": tool_call_id,
                                    **shell_meta,
                                    "name": tool_name,
                                    "phase": "end",
                                }
                            },
                            model,
                        )

            except GraphInterrupt:
                logger.info("GraphInterrupt raised in resumed streaming path (model=%s, session_id=%s)", model, thread_id)
                try:
                    snapshot = await agent.aget_state(config)
                    interrupts = [
                        intr.value
                        for task in getattr(snapshot, "tasks", [])
                        for intr in getattr(task, "interrupts", [])
                    ]
                except Exception:
                    logger.debug("aget_state not available or failed - skipping interrupt check")
                    interrupts = []
                if interrupts:
                    yield sse({"permission_request": interrupts[0]}, model)
            except GraphRecursionError:
                interrupted_reason = GRAPH_RECURSION_STOP_REASON
                final_status = "interrupted"
                await self.append_interruption_event(
                    thread_id=thread_id,
                    run_id=run_id,
                    reason=interrupted_reason,
                    workspace_root=workspace_root,
                )
                yield sse(self._stream_stop_delta(GRAPH_RECURSION_STOP_REASON, guard_settings), model, finish_reason="length")
                yield "data: [DONE]\n\n"
                return

            if interrupted_reason is None:
                if not interrupts:
                    try:
                        snapshot = await agent.aget_state(config)
                        for task in getattr(snapshot, "tasks", []):
                            for intr in getattr(task, "interrupts", []):
                                interrupts.append(intr.value)
                                yield sse({"permission_request": intr.value}, model)
                    except Exception:
                        logger.debug("aget_state not available or failed - skipping interrupt check")

                final_status = "requires_action" if interrupts else "idle"
                logger.info("Streaming resumed chat request finished (model=%s, session_id=%s)", model, thread_id)
                yield sse({}, model, finish_reason="stop")
                yield "data: [DONE]\n\n"
            else:
                final_status = "interrupted"
                await self.append_interruption_event(
                    thread_id=thread_id,
                    run_id=run_id,
                    reason=interrupted_reason,
                    workspace_root=workspace_root,
                )
        except asyncio.CancelledError:
            interrupted_reason = "user_cancel" if _is_stream_run_cancel_requested(thread_id, run_id) else "client_disconnect"
            await self.append_interruption_event(
                thread_id=thread_id,
                run_id=run_id,
                reason=interrupted_reason,
                workspace_root=workspace_root,
            )
            raise
        finally:
            if interrupted_reason is None and _is_stream_run_cancel_requested(thread_id, run_id):
                interrupted_reason = "user_cancel"
                await self.append_interruption_event(
                    thread_id=thread_id,
                    run_id=run_id,
                    reason=interrupted_reason,
                    workspace_root=workspace_root,
                )
            if interrupted_reason is None and await http_request.is_disconnected():
                interrupted_reason = "client_disconnect"
                await self.append_interruption_event(
                    thread_id=thread_id,
                    run_id=run_id,
                    reason=interrupted_reason,
                    workspace_root=workspace_root,
                )
            _unregister_stream_run(thread_id, run_id)
            if interrupted_reason is not None:
                self._thread_store.stop_run(
                    thread_id=thread_id,
                    user_id=current_user.id,
                    run_id=run_id,
                    reason=interrupted_reason,
                )
                return
            latest_thread = self._thread_store.get_owned_thread(thread_id=thread_id, user_id=current_user.id)
            if latest_thread and latest_thread.get("last_stop_run_id") == run_id:
                return
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status=final_status,
                last_message_at=int(time.time()) if saw_output else None,
                clear_active_run=True,
            )

    async def run_completion(
        self,
        request: ChatRequest,
        http_request: Request,
        current_user: AuthUser,
    ) -> StreamingResponse | dict:
        """Main orchestrator for chat completion request."""
        request_id = getattr(http_request.state, "request_id", None)
        with profile_phase(
            "chat_run_completion",
            request_id=request_id if isinstance(request_id, str) else None,
            metadata={
                "user_id": current_user.id,
                "stream": request.stream,
                "requested_model": request.model,
                "message_count": len(request.messages),
            },
        ) as profiler:
            enforce_rate_limit(
                request=http_request,
                rule=RateLimitRule(
                    scope="chat_requests",
                    limit=self._settings.chat_requests_limit,
                    window_seconds=self._settings.chat_requests_window_seconds,
                ),
                user=current_user,
            )
            profiler.mark("rate_limit")

            thread = self.resolve_thread(request=request, current_user=current_user)
            thread_id = thread["id"]
            profiler.mark("resolve_thread")

            self.apply_resume_grant(
                request=request,
                user_id=current_user.id,
                thread_id=thread_id,
            )
            profiler.mark("apply_resume_grant")

            backend = self.build_backend(request, thread_id)
            workspace_root = workspace_root_for_backend(backend)
            resume_command = extract_resume_command(request)
            is_resume = resume_command is not None
            run_id = f"run_{uuid.uuid4().hex}" if request.stream else None
            if run_id is not None:
                _register_stream_run(thread_id, run_id)
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status="running",
                active_run_id=run_id,
                run_started_at=int(time.time()) if run_id is not None else None,
                clear_stop_reason=True,
            )
            profiler.mark("build_backend_and_runtime")

            permission_context = self.build_permission_context(
                request=request,
                user_id=current_user.id,
                thread_id=thread_id,
                workspace_root=workspace_root,
            )
            profiler.mark("build_permission_context")

            effective_messages = request.messages

            model, resolved_model, resolved_provider, capability_model_name = self.resolve_model(request)
            media_block_support = resolve_media_block_support(resolved_provider, capability_model_name)
            profiler.mark("resolve_model")

            agent = self.build_agent(
                model=model,
                backend=backend,
                permission_context=permission_context,
                media_block_support=media_block_support,
                owner_user_id=current_user.id,
                workspace_root=workspace_root,
            )
            profiler.mark("build_agent")

            logger.info(
                "Chat completion request received (model=%s -> %s, session_id=%s, stream=%s, messages=%d, client=%s)",
                request.model,
                resolved_model,
                thread_id,
                request.stream,
                len(effective_messages),
                http_request.client.host if http_request.client else "unknown",
            )

            # Track which messages are from current request
            tracker = create_request_tracker(
                thread_id=thread_id,
                incoming_messages=effective_messages,
                is_resume=is_resume,
            )
            profiler.mark("build_request_tracker")

            if resume_command is not None:
                agent_input = resume_command
            else:
                agent_input = {"messages": to_lc_messages(effective_messages)}
            profiler.mark("prepare_agent_input")

            # Build config with tracking info
            config = _with_graph_recursion_limit({
                "configurable": {
                    "thread_id": thread_id,
                    "message_request_tracker": tracker.to_dict(),
                    "is_resume": is_resume,
                }
            }, thread_id=thread_id, workspace_root=workspace_root)
            profiler.mark("build_graph_config")

        if request.stream:
            stream_iterator = (
                self.stream_resume_response(
                    agent=agent,
                    agent_input=agent_input,
                    model=resolved_model,
                    thread_id=thread_id,
                    run_id=run_id or f"run_{uuid.uuid4().hex}",
                    backend=backend,
                    current_user=current_user,
                    http_request=http_request,
                    config=config,
                )
                if resume_command is not None
                else self.stream_response_with_run(
                    agent=agent,
                    agent_input=agent_input,
                    model=resolved_model,
                    thread_id=thread_id,
                    run_id=run_id or f"run_{uuid.uuid4().hex}",
                    backend=backend,
                    current_user=current_user,
                    http_request=http_request,
                    messages=effective_messages,
                    config=config,
                )
            )
            return StreamingResponse(
                stream_iterator,
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        guard_settings = resolve_loop_guard_settings(workspace_root=workspace_root)

        try:
            if resume_command is not None:
                content_parts: list[str] = []
                resolved_input = await _resolve_resume_input(agent, agent_input, config)
                async for event in agent.astream_events(resolved_input, config=config, version="v2"):
                    if event["event"] != "on_chat_model_stream":
                        continue
                    chunk = event["data"]["chunk"]
                    text, _ = parse_content(chunk.content)
                    if text:
                        content_parts.append(text)
                content = "".join(content_parts)
            else:
                guard = ContinuationNudgeGuard()
                nudge_count = 0
                current_input = agent_input
                while True:
                    iteration_config = _with_graph_recursion_limit(
                        config,
                        thread_id=thread_id,
                        workspace_root=workspace_root,
                        guard_settings=guard_settings,
                        continuation_nudge_count=nudge_count,
                    )
                    result = await agent.ainvoke(current_input, config=iteration_config)
                    last = result["messages"][-1]
                    content = extract_text(last.content)
                    saw_tool_message = self._saw_tool_after_last_human(result.get("messages", []))
                    decision = guard.evaluate(
                        assistant_text=content,
                        saw_tool_event=saw_tool_message,
                        saw_interrupt=False,
                        nudge_count=nudge_count,
                        settings=guard_settings,
                    )
                    if decision.should_nudge:
                        nudge_count += 1
                        logger.info(
                            "Continuation nudge triggered (%s/%s) for session_id=%s: %s",
                            nudge_count,
                            guard_settings.continuation_nudge_limit,
                            thread_id,
                            decision.matched_text[-120:],
                        )
                        current_input = build_continuation_nudge_input()
                        continue
                    if decision.stop_after_cap:
                        self._update_session_runtime(
                            thread_id=thread_id,
                            user_id=current_user.id,
                            workspace_root=workspace_root,
                            backend=backend,
                            status="interrupted",
                            last_stop_reason=CONTINUATION_NUDGE_STOP_REASON,
                            last_interrupted_at=int(time.time()),
                        )
                        return JSONResponse({
                            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                            "object": "chat.completion",
                            "created": int(time.time()),
                            "model": resolved_model,
                            "choices": [{
                                "index": 0,
                                "message": {"role": "assistant", "content": content},
                                "finish_reason": "stop",
                                "delta": {},
                                "stop_reason": CONTINUATION_NUDGE_STOP_REASON,
                            }],
                            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                            "thread_id": thread_id,
                            "session_id": thread_id,
                        })
                    break
        except GraphInterrupt:
            logger.info("GraphInterrupt raised in non-streaming path (model=%s, session_id=%s)", resolved_model, thread_id)
            try:
                snapshot = await agent.aget_state(config)
                interrupts = [
                    intr.value
                    for task in getattr(snapshot, "tasks", [])
                    for intr in getattr(task, "interrupts", [])
                ]
            except Exception:
                logger.debug("aget_state not available or failed — skipping interrupt check")
                interrupts = []
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status="requires_action",
            )
            return JSONResponse({
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": resolved_model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": ""},
                    "finish_reason": "stop",
                    "delta": {},
                    "permission_request": interrupts[0] if interrupts else None,
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "thread_id": thread_id,
                "session_id": thread_id,
            })
        except GraphRecursionError:
            logger.info(
                "GraphRecursionError raised in non-streaming path (model=%s, session_id=%s, recursion_limit=%s)",
                resolved_model,
                thread_id,
                guard_settings.graph_recursion_limit,
            )
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status="interrupted",
                last_stop_reason=GRAPH_RECURSION_STOP_REASON,
                last_interrupted_at=int(time.time()),
            )
            return JSONResponse({
                "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": resolved_model,
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": ""},
                    "finish_reason": "length",
                    "delta": {},
                    "stop_reason": GRAPH_RECURSION_STOP_REASON,
                }],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "thread_id": thread_id,
                "session_id": thread_id,
            })
        except Exception:
            logger.exception(
                "Chat completion request failed (model=%s, session_id=%s, stream=%s, resume=%s)",
                resolved_model,
                thread_id,
                request.stream,
                is_resume,
            )
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root,
                backend=backend,
                status="idle",
            )
            raise

        response = {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": resolved_model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "thread_id": thread_id,
            "session_id": thread_id,
        }

        self._update_session_runtime(
            thread_id=thread_id,
            user_id=current_user.id,
            workspace_root=workspace_root,
            backend=backend,
            status="idle",
            last_message_at=int(time.time()),
        )
        logger.info("Chat completion request finished (model=%s, session_id=%s)", resolved_model, thread_id)
        return response


_chat_service_cache: dict[tuple[int, int, int, int, int], ChatService] = {}

def get_chat_service(request: Request) -> ChatService:
    """DI factory for ChatService."""
    auth_repo = get_auth_repository()
    thread_store = get_thread_store()
    daytona_manager = get_daytona_session_manager(request)
    checkpointer = get_checkpointer(request)
    settings = get_settings()
    key = (id(auth_repo), id(thread_store), id(daytona_manager), id(checkpointer), id(settings))
    service = _chat_service_cache.get(key)
    if service is None:
        service = ChatService(auth_repo, thread_store, daytona_manager, checkpointer, settings)
        _chat_service_cache[key] = service
    return service

def _clear_chat_service_cache() -> None:
    _chat_service_cache.clear()

get_chat_service.cache_clear = _clear_chat_service_cache  # type: ignore[attr-defined]
