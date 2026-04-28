"""Chat service layer — orchestration of business logic."""

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphInterrupt

from src.ai.agents.ethos import create_ethos_agent
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
    extract_text,
    format_tool_input,
    parse_content,
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
from src.app.modules.chat.schemas import ChatRequest
from src.app.modules.chat.streaming import sse
from src.app.services.chat_tasks import fallback_title, generate_follow_ups_task, generate_title_task
from src.app.services.daytona_manager import DaytonaSessionManager
from src.app.services.message_tracker import create_request_tracker
from src.app.services.permissions import PermissionContextService
from src.app.services.rate_limiter import RateLimitRule
from src.app.services.thread_store import ThreadStore
from src.backends.daytona import DaytonaUnavailableError
from src.backends.local import LocalSandbox as LocalBackend
from src.config import build_chat_model, get_model_registry
from src.logger import get_logger

logger = get_logger(__name__)


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
                raise HTTPException(status_code=503, detail=str(exc)) from exc

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
    ) -> None:
        self._thread_store.update_session_metadata(
            thread_id=thread_id,
            user_id=user_id,
            workspace_root=str(workspace_root.resolve()),
            backend=self._backend_name(backend),
            status=status,
            last_message_at=last_message_at,
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
    ) -> Any:
        """Create ethos agent."""
        return create_ethos_agent(
            model=model,
            backend=backend,
            permission_context=permission_context,
            checkpointer=self._checkpointer,
            media_block_support=media_block_support,
        )

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
        if config is None:
            config = {"configurable": {"thread_id": thread_id}}
        msg_count = len(messages) if messages else 0
        logger.info("Streaming chat request started (model=%s, session_id=%s, messages=%d)", model, thread_id, msg_count)
        interrupts: list[dict[str, Any]] = []
        saw_output = False
        final_status = "idle"

        try:
            async for event in agent.astream_events(agent_input, config=config, version="v2"):
                kind = event["event"]

                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text, thinking = parse_content(chunk.content)
                    if thinking:
                        saw_output = True
                        yield sse({"reasoning_content": thinking}, model)
                    if text:
                        saw_output = True
                        yield sse({"content": text}, model)
                elif kind == "on_tool_start":
                    tool_name = event.get("name", "tool")
                    tool_input = event.get("data", {}).get("input", {})
                    yield sse({"tool_event": {"name": tool_name, "input": tool_input, "phase": "start"}}, model)
                    input_str = format_tool_input(tool_input)
                    if input_str:
                        yield sse({"reasoning_content": f"Using tool `{tool_name}` with params: {input_str}\n"}, model)
                    else:
                        yield sse({"reasoning_content": f"Using tool `{tool_name}`\n"}, model)
                elif kind == "on_tool_end":
                    tool_name = event.get("name", "tool")
                    output = event.get("data", {}).get("output", "")
                    yield sse({"tool_event": {"name": tool_name, "output": str(output), "phase": "end"}}, model)

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
        finally:
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root_for_backend(backend),
                backend=backend,
                status=final_status,
                last_message_at=int(time.time()) if saw_output else None,
            )

    async def stream_resume_response(
        self,
        *,
        agent: Any,
        agent_input: Any,
        model: str,
        thread_id: str,
        backend: Any,
        current_user: AuthUser,
        config: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream a resumed run via ainvoke."""
        if config is None:
            config = {"configurable": {"thread_id": thread_id}}
        logger.info("Streaming resumed chat request started (model=%s, session_id=%s)", model, thread_id)
        interrupts: list[dict[str, Any]] = []
        saw_output = False
        final_status = "idle"

        try:
            try:
                result = await agent.ainvoke(agent_input, config=config)
                last = result["messages"][-1]
                content, thinking = parse_content(last.content)
                if thinking:
                    saw_output = True
                    yield sse({"reasoning_content": thinking}, model)
                if content:
                    saw_output = True
                    yield sse({"content": content}, model)
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

            final_status = "requires_action" if interrupts else "idle"
            logger.info("Streaming resumed chat request finished (model=%s, session_id=%s)", model, thread_id)
            yield sse({}, model, finish_reason="stop")
            yield "data: [DONE]\n\n"
        finally:
            self._update_session_runtime(
                thread_id=thread_id,
                user_id=current_user.id,
                workspace_root=workspace_root_for_backend(backend),
                backend=backend,
                status=final_status,
                last_message_at=int(time.time()) if saw_output else None,
            )

    async def run_completion(
        self,
        request: ChatRequest,
        http_request: Request,
        current_user: AuthUser,
    ) -> StreamingResponse | dict:
        """Main orchestrator for chat completion request."""
        enforce_rate_limit(
            request=http_request,
            rule=RateLimitRule(
                scope="chat_requests",
                limit=self._settings.chat_requests_limit,
                window_seconds=self._settings.chat_requests_window_seconds,
            ),
            user=current_user,
        )

        thread = self.resolve_thread(request=request, current_user=current_user)
        thread_id = thread["id"]

        self.apply_resume_grant(
            request=request,
            user_id=current_user.id,
            thread_id=thread_id,
        )

        backend = self.build_backend(request, thread_id)
        workspace_root = workspace_root_for_backend(backend)
        self._update_session_runtime(
            thread_id=thread_id,
            user_id=current_user.id,
            workspace_root=workspace_root,
            backend=backend,
            status="running",
        )

        permission_context = self.build_permission_context(
            request=request,
            user_id=current_user.id,
            thread_id=thread_id,
            workspace_root=workspace_root,
        )

        effective_messages = request.messages

        model, resolved_model, resolved_provider, capability_model_name = self.resolve_model(request)
        media_block_support = resolve_media_block_support(resolved_provider, capability_model_name)

        agent = self.build_agent(
            model=model,
            backend=backend,
            permission_context=permission_context,
            media_block_support=media_block_support,
        )

        logger.info(
            "Chat completion request received (model=%s -> %s, session_id=%s, stream=%s, messages=%d, client=%s)",
            request.model,
            resolved_model,
            thread_id,
            request.stream,
            len(effective_messages),
            http_request.client.host if http_request.client else "unknown",
        )

        resume_command = extract_resume_command(request)
        is_resume = resume_command is not None

        # Track which messages are from current request
        tracker = create_request_tracker(
            thread_id=thread_id,
            incoming_messages=effective_messages,
            is_resume=is_resume,
        )

        if resume_command is not None:
            agent_input = resume_command
        else:
            agent_input = {"messages": to_lc_messages(effective_messages)}

        # Build config with tracking info
        config = {
            "configurable": {
                "thread_id": thread_id,
                "message_request_tracker": tracker.to_dict(),
                "is_resume": is_resume,
            }
        }

        if request.stream:
            stream_iterator = (
                self.stream_resume_response(
                    agent=agent,
                    agent_input=agent_input,
                    model=resolved_model,
                    thread_id=thread_id,
                    backend=backend,
                    current_user=current_user,
                    config=config,
                )
                if resume_command is not None
                else self.stream_response(
                    agent=agent,
                    agent_input=agent_input,
                    model=resolved_model,
                    thread_id=thread_id,
                    backend=backend,
                    current_user=current_user,
                    messages=effective_messages,
                    config=config,
                )
            )
            return StreamingResponse(
                stream_iterator,
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
            )
        try:
            result = await agent.ainvoke(agent_input, config=config)
            last = result["messages"][-1]
            content = extract_text(last.content)
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
        except Exception:
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


def get_chat_service(
    auth_repo: AuthRepository = Depends(get_auth_repository),
    thread_store: ThreadStore = Depends(get_thread_store),
    daytona_manager: DaytonaSessionManager = Depends(get_daytona_session_manager),
    checkpointer: BaseCheckpointSaver = Depends(get_checkpointer),
    settings: Settings = Depends(get_settings),
) -> ChatService:
    """DI factory for ChatService."""
    return ChatService(auth_repo, thread_store, daytona_manager, checkpointer, settings)
