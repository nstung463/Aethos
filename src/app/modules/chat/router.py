"""OpenAI-compatible v1 API endpoints."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.errors import GraphInterrupt

from src.ai.agents.ethos import create_ethos_agent
from src.ai.permissions import PermissionContext, PermissionMode, PermissionSubject, set_mode
from src.ai.tools.filesystem import resolve_media_block_support
from src.app.core.settings import get_settings
from src.app.dependencies import (
    enforce_rate_limit,
    get_auth_repository,
    get_checkpointer,
    get_current_user,
    get_daytona_session_manager,
    get_file_store,
    get_thread_store,
)
from src.app.modules.auth.repository import AuthRepository
from src.app.modules.auth.schemas import PermissionProfilePayload
from src.app.modules.auth.repository import AuthUser
from src.app.modules.chat.schemas import ChatRequest, Message
from src.app.services.chat_tasks import fallback_title, generate_follow_ups_task, generate_title_task
from src.app.services.daytona_manager import DaytonaSessionManager
from src.app.services.file_store import FileStore
from src.app.services.permissions import PermissionContextService
from src.app.services.rate_limiter import RateLimitRule
from src.app.services.thread_store import ThreadStore
from src.backends.daytona import DaytonaUnavailableError
from src.backends.local import LocalSandbox as LocalBackend
from src.config import build_chat_model, get_model_registry
from src.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["v1"])
_SANDBOX_ATTACHMENTS_ROOT = "/tmp/ethos/attachments"


def _extract_resume_command(request: "ChatRequest"):
    """Return a LangGraph Command(resume=...) if the request carries a resume payload, else None."""
    from langgraph.types import Command
    metadata = getattr(request, "metadata", None) or {}
    resume_payload = metadata.get("resume")
    if resume_payload is None:
        return None
    return Command(resume=resume_payload)


def _extract_resume_payload(request: "ChatRequest") -> dict[str, Any] | None:
    metadata = getattr(request, "metadata", None) or {}
    resume_payload = metadata.get("resume")
    if not isinstance(resume_payload, dict):
        return None
    return resume_payload


def _resolve_model_id(model_id: str) -> str:
    specs = get_model_registry()
    registry = {spec.id: spec for spec in specs}
    if model_id in registry:
        return model_id
    raise HTTPException(
        status_code=404,
        detail=f"Unknown model: {model_id!r}. Available: {sorted(registry.keys())}",
    )


def _to_lc_messages(messages: list[Message]):
    result = []
    for message in messages:
        if message.role == "system":
            result.append(SystemMessage(content=message.content))
        elif message.role == "assistant":
            result.append(AIMessage(content=message.content))
        elif message.role == "tool":
            if not message.tool_call_id:
                logger.warning("Tool message missing tool_call_id, skipping")
                continue
            result.append(ToolMessage(content=message.content, tool_call_id=message.tool_call_id))
        else:
            result.append(HumanMessage(content=message.content))
    return result


def _parse_content(content) -> tuple[str, str]:
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, list):
        return str(content), ""

    text_parts: list[str] = []
    thinking_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            text_parts.append(str(block))
            continue
        block_type = block.get("type", "")
        if block_type == "thinking":
            thinking_parts.append(block.get("thinking", ""))
        elif block_type == "text":
            text_parts.append(block.get("text", ""))

    return "".join(text_parts), "".join(thinking_parts)


def _extract_text(content) -> str:
    text, _ = _parse_content(content)
    return text


def _format_tool_input(input_data: Any) -> str:
    """Format tool input parameters for streaming."""
    if not input_data:
        return ""
    if isinstance(input_data, dict):
        if len(input_data) == 1:
            key, value = next(iter(input_data.items()))
            return f"{key}={json.dumps(value) if not isinstance(value, str) else value}"
        return json.dumps(input_data)
    return str(input_data)


def _extract_file_ids(request: ChatRequest) -> list[str]:
    file_ids: list[str] = []
    seen: set[str] = set()

    def add_file_id(value: Any) -> None:
        if not isinstance(value, str) or not value or value in seen:
            return
        seen.add(value)
        file_ids.append(value)

    for file_id in request.file_ids:
        add_file_id(file_id)

    for item in request.files:
        add_file_id(item.get("id"))
        nested = item.get("file")
        if isinstance(nested, dict):
            add_file_id(nested.get("id"))

    metadata = request.metadata or {}
    extra_ids = metadata.get("file_ids")
    if isinstance(extra_ids, list):
        for file_id in extra_ids:
            add_file_id(file_id)

    return file_ids


def _pick_edit_target(request: ChatRequest, file_ids: list[str]) -> str | None:
    metadata = request.metadata or {}
    for key in ("target_file_id", "edit_target_file_id"):
        value = metadata.get(key)
        if isinstance(value, str):
            return value
    return file_ids[0] if file_ids else None


def _extract_user_api_keys(request: ChatRequest) -> dict[str, str]:
    metadata = request.metadata or {}
    raw_keys = metadata.get("user_api_keys")
    if not isinstance(raw_keys, dict):
        return {}

    result: dict[str, str] = {}
    for provider in ("openrouter", "anthropic", "openai"):
        value = raw_keys.get(provider)
        if isinstance(value, str) and value.strip():
            result[provider] = value.strip()
    return result


_VALID_PROVIDERS = frozenset(
    {
        "openrouter",
        "anthropic",
        "openai",
        "azure_openai",
        "openai_compatible",
        "deepseek",
        "together",
        "groq",
        "xai",
        "fireworks",
        "perplexity",
        "google_genai",
        "bedrock",
    }
)


def _extract_profile(request: ChatRequest) -> dict | None:
    metadata = request.metadata or {}
    raw = metadata.get("profile")
    if not isinstance(raw, dict):
        return None
    provider = str(raw.get("provider", "")).strip().lower()
    model = str(raw.get("model", "")).strip()
    if not provider or not model:
        return None
    if provider not in _VALID_PROVIDERS:
        logger.warning("Unknown provider in profile: %r - falling back to registry", provider)
        return None
    api_key = str(raw.get("api_key", "")).strip()
    base_url = str(raw.get("base_url", "")).strip() or None
    deployment = str(raw.get("deployment", "")).strip() or None
    api_version = str(raw.get("api_version", "")).strip() or None
    settings = get_settings()
    if provider == "openai_compatible" and base_url and not settings.allow_custom_provider_endpoints:
        raise HTTPException(status_code=403, detail="Custom provider endpoints are disabled")
    return {
        "provider": provider,
        "model": model,
        "api_key": api_key,
        "base_url": base_url,
        "deployment": deployment,
        "api_version": api_version,
    }


def _extract_permission_override_mode(request: ChatRequest) -> PermissionMode | None:
    metadata = request.metadata or {}
    raw_override = metadata.get("permission_override")
    if not isinstance(raw_override, dict):
        return None
    raw_mode = raw_override.get("mode")
    if not isinstance(raw_mode, str) or not raw_mode.strip():
        return None
    return PermissionMode(raw_mode.strip())


def _resolve_resume_grant_matcher(resume_payload: dict[str, Any]) -> tuple[str, str] | None:
    grant = resume_payload.get("grant")
    if not isinstance(grant, dict):
        return None
    scope = str(grant.get("scope", "")).strip().lower()
    subject = str(grant.get("subject", "")).strip().lower()
    matcher = grant.get("path")
    if not isinstance(matcher, str) or not matcher.strip():
        matcher = grant.get("command")
    if not isinstance(matcher, str) or not matcher.strip():
        return None
    if scope not in {"thread", "user"}:
        return None
    if subject not in {member.value for member in PermissionSubject}:
        return None
    return scope, subject, matcher.strip()


def _extract_requested_thread_id(request: ChatRequest) -> str | None:
    if request.thread_id and request.thread_id.strip():
        return request.thread_id.strip()
    if request.chat_id and request.chat_id.strip():
        return request.chat_id.strip()
    if request.session_id and request.session_id.strip():
        return request.session_id.strip()
    metadata = request.metadata or {}
    for key in ("session_id", "chat_id", "conversation_id", "thread_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_thread(
    *,
    request: ChatRequest,
    current_user: AuthUser,
    thread_store: ThreadStore,
) -> dict[str, Any]:
    requested_thread_id = _extract_requested_thread_id(request)
    if requested_thread_id:
        thread = thread_store.get_owned_thread(thread_id=requested_thread_id, user_id=current_user.id)
        if not thread:
            raise HTTPException(status_code=404, detail="Thread not found")
        thread_store.touch_thread(thread_id=requested_thread_id, user_id=current_user.id)
        return thread
    return thread_store.create_thread(user_id=current_user.id)


def _sandbox_attachment_path(file_id: str, filename: str) -> str:
    safe_name = Path(filename).name or file_id
    return f"{_SANDBOX_ATTACHMENTS_ROOT}/{file_id}/{safe_name}"


def _workspace_root_for_backend(backend) -> Path:
    root = getattr(backend, "root", None)
    if isinstance(root, Path):
        return root.resolve()
    return Path("/").resolve()


def _extract_backend_selection(request: ChatRequest) -> tuple[str, str | None]:
    metadata = request.metadata or {}
    raw_backend = metadata.get("backend")
    if not isinstance(raw_backend, dict):
        return "sandbox", None

    mode = str(raw_backend.get("mode", "sandbox")).strip().lower()
    if mode not in {"sandbox", "local"}:
        return "sandbox", None

    root_dir = raw_backend.get("root_dir")
    if isinstance(root_dir, str) and root_dir.strip():
        return mode, root_dir.strip()
    return mode, None


def _apply_permission_override(
    context: PermissionContext | None,
    *,
    override_mode: PermissionMode | None,
    workspace_root: Path,
) -> PermissionContext | None:
    if override_mode is None:
        return context
    base_context = context
    if base_context is None:
        from src.ai.permissions import build_default_permission_context

        base_context = build_default_permission_context(workspace_root=workspace_root)
    return set_mode(base_context, override_mode)


def _apply_resume_grant(
    *,
    request: ChatRequest,
    service: PermissionContextService,
    user_id: str,
    thread_id: str,
) -> None:
    resume_payload = _extract_resume_payload(request)
    if not resume_payload or not resume_payload.get("approved", False):
        return
    resolved = _resolve_resume_grant_matcher(resume_payload)
    if resolved is None:
        return
    scope, subject, matcher = resolved
    service.grant_rule_for_scope(
        user_id=user_id,
        thread_id=thread_id,
        scope=scope,
        subject=subject,
        matcher=matcher,
    )


def _stage_attached_files(
    *,
    request: ChatRequest,
    backend,
    file_ids: list[str],
    current_user: AuthUser,
    store: FileStore,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], str | None, list[Message]]:
    records: dict[str, dict[str, Any]] = {}
    sandbox_paths: dict[str, str] = {}

    for file_id in file_ids:
        record = store.get_file(file_id, owner_user_id=current_user.id)
        if not record:
            raise HTTPException(status_code=404, detail=f"Attached file not found: {file_id}")

        filename = record.get("filename", file_id)
        sandbox_path = _sandbox_attachment_path(file_id, filename)
        upload_response = backend.upload_files([(sandbox_path, Path(record["path"]).read_bytes())])
        if not upload_response or upload_response[0].error:
            error = upload_response[0].error if upload_response else "no response from sandbox"
            raise HTTPException(status_code=502, detail=f"Failed to stage file into sandbox: {error}")

        records[file_id] = record
        sandbox_paths[file_id] = sandbox_path

    target_file_id = _pick_edit_target(request, file_ids)
    target_path = sandbox_paths.get(target_file_id) if target_file_id else None
    attached_lines = [
        f"- {records[file_id].get('filename', file_id)} -> {sandbox_paths[file_id]}"
        for file_id in file_ids
    ]
    instruction = (
        "The user's attached files have been staged into the sandbox.\n"
        "Use sandbox filesystem tools such as read_file, read_media_file, edit_file, write_file, glob, and grep.\n"
        "Do not say the file is missing until you have checked the staged sandbox paths below.\n"
        "Attached files in sandbox:\n"
        + "\n".join(attached_lines)
    )
    if target_path:
        instruction += (
            "\n\nPrimary edit target:\n"
            f"- {target_path}\n"
            "If the user asks to modify the uploaded file, edit this file in place and keep it valid."
        )

    staged_messages = [Message(role="system", content=instruction), *request.messages]
    return records, sandbox_paths, target_file_id, staged_messages


def _publish_edited_file(
    source_record: dict[str, Any],
    backend,
    sandbox_path: str,
    *,
    store: FileStore,
    current_user: AuthUser,
    thread_id: str,
) -> dict[str, Any]:
    downloads = backend.download_files([sandbox_path])
    if not downloads or downloads[0].error or downloads[0].content is None:
        error = downloads[0].error if downloads else "no response from sandbox"
        raise HTTPException(status_code=502, detail=f"Failed to read edited sandbox file: {error}")

    source_name = source_record.get("filename", "edited.py")
    stem = Path(source_name).stem
    suffix = Path(source_name).suffix or ".py"
    output_name = f"{stem}.edited{suffix}"
    return store.import_bytes(
        filename=output_name,
        content=downloads[0].content,
        content_type=source_record.get("meta", {}).get("content_type"),
        owner_user_id=current_user.id,
        thread_id=thread_id,
    )


def _sse(delta: dict[str, Any], model: str, finish_reason: str | None = None) -> str:
    payload = {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _stream_response(
    *,
    agent: object,
    agent_input: Any,
    model: str,
    thread_id: str,
    backend,
    store: FileStore,
    current_user: AuthUser,
    source_records: dict[str, dict[str, Any]] | None = None,
    sandbox_paths: dict[str, str] | None = None,
    target_file_id: str | None = None,
    messages: list[Message] | None = None,
) -> AsyncIterator[str]:
    config = {"configurable": {"thread_id": thread_id}}
    msg_count = len(messages) if messages else 0
    logger.info("Streaming chat request started (model=%s, session_id=%s, messages=%d)", model, thread_id, msg_count)

    async for event in agent.astream_events(agent_input, config=config, version="v2"):
        kind = event["event"]

        if kind == "on_chat_model_stream":
            chunk = event["data"]["chunk"]
            text, thinking = _parse_content(chunk.content)
            if thinking:
                yield _sse({"reasoning_content": thinking}, model)
            if text:
                yield _sse({"content": text}, model)
        elif kind == "on_tool_start":
            tool_name = event.get("name", "tool")
            tool_input = event.get("data", {}).get("input", {})
            yield _sse({"tool_event": {"name": tool_name, "input": tool_input, "phase": "start"}}, model)
            input_str = _format_tool_input(tool_input)
            if input_str:
                yield _sse({"reasoning_content": f"Using tool `{tool_name}` with params: {input_str}\n"}, model)
            else:
                yield _sse({"reasoning_content": f"Using tool `{tool_name}`\n"}, model)
        elif kind == "on_tool_end":
            tool_name = event.get("name", "tool")
            output = event.get("data", {}).get("output", "")
            yield _sse({"tool_event": {"name": tool_name, "output": str(output), "phase": "end"}}, model)

    # After the event loop ends, check for pending LangGraph interrupt
    try:
        snapshot = await agent.aget_state(config)
        for task in getattr(snapshot, "tasks", []):
            for intr in getattr(task, "interrupts", []):
                yield _sse({"permission_request": intr.value}, model)
    except Exception:
        logger.debug("aget_state not available or failed — skipping interrupt check")

    if (
        source_records
        and sandbox_paths
        and target_file_id
        and target_file_id in source_records
        and target_file_id in sandbox_paths
        and source_records[target_file_id].get("filename", "").lower().endswith(".py")
    ):
        try:
            output_file = _publish_edited_file(
                source_records[target_file_id],
                backend,
                sandbox_paths[target_file_id],
                store=store,
                current_user=current_user,
                thread_id=thread_id,
            )
            yield _sse(
                {
                    "output_file": output_file,
                    "sandbox_path": sandbox_paths[target_file_id],
                },
                model,
            )
        except Exception as exc:
            logger.exception("Failed to publish streamed output file")
            yield _sse(
                {"reasoning_content": f"Edited file was created in sandbox but publishing failed: {exc}"},
                model,
            )

    logger.info("Streaming chat request finished (model=%s, session_id=%s)", model, thread_id)
    yield _sse({}, model, finish_reason="stop")
    yield "data: [DONE]\n\n"


async def _stream_resume_response(
    *,
    agent: object,
    agent_input: Any,
    model: str,
    thread_id: str,
    backend,
    store: FileStore,
    current_user: AuthUser,
    source_records: dict[str, dict[str, Any]] | None = None,
    sandbox_paths: dict[str, str] | None = None,
    target_file_id: str | None = None,
) -> AsyncIterator[str]:
    """Stream a resumed run via ainvoke to avoid provider streaming issues on resume."""
    config = {"configurable": {"thread_id": thread_id}}
    logger.info("Streaming resumed chat request started (model=%s, session_id=%s)", model, thread_id)

    try:
        result = await agent.ainvoke(agent_input, config=config)
        last = result["messages"][-1]
        content, thinking = _parse_content(last.content)
        if thinking:
            yield _sse({"reasoning_content": thinking}, model)
        if content:
            yield _sse({"content": content}, model)
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
            yield _sse({"permission_request": interrupts[0]}, model)

    if (
        source_records
        and sandbox_paths
        and target_file_id
        and target_file_id in source_records
        and target_file_id in sandbox_paths
        and source_records[target_file_id].get("filename", "").lower().endswith(".py")
    ):
        try:
            output_file = _publish_edited_file(
                source_records[target_file_id],
                backend,
                sandbox_paths[target_file_id],
                store=store,
                current_user=current_user,
                thread_id=thread_id,
            )
            yield _sse(
                {
                    "output_file": output_file,
                    "sandbox_path": sandbox_paths[target_file_id],
                },
                model,
            )
        except Exception as exc:
            logger.exception("Failed to publish streamed output file after resume")
            yield _sse(
                {"reasoning_content": f"Edited file was created in sandbox but publishing failed: {exc}"},
                model,
            )

    logger.info("Streaming resumed chat request finished (model=%s, session_id=%s)", model, thread_id)
    yield _sse({}, model, finish_reason="stop")
    yield "data: [DONE]\n\n"


@router.get("/models")
async def list_models():
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": spec.id,
                "object": "model",
                "created": now,
                "owned_by": "ethos",
                "info": {
                    "meta": {
                        "capabilities": {
                            "file_upload": True,
                            "file_context": True,
                            "vision": True,
                            "web_search": True,
                            "image_generation": False,
                            "code_interpreter": True,
                            "citations": True,
                            "status_updates": True,
                        }
                    }
                },
            }
            for spec in get_model_registry()
        ],
    }


@router.post("/threads")
async def create_thread(
    http_request: Request,
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    settings = get_settings()
    enforce_rate_limit(
        request=http_request,
        rule=RateLimitRule(
            scope="threads_create",
            limit=settings.thread_creations_limit,
            window_seconds=settings.thread_creations_window_seconds,
        ),
        user=current_user,
    )
    return thread_store.create_thread(user_id=current_user.id)


@router.get("/threads/{thread_id}/permissions")
async def get_thread_permissions(
    thread_id: str,
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
    auth_repo: AuthRepository = Depends(get_auth_repository),
):
    if not thread_store.get_owned_thread(thread_id=thread_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Thread not found")
    service = PermissionContextService(auth_repo, thread_store)
    bundle = service.get_thread_permissions_bundle(thread_id=thread_id, user_id=current_user.id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return bundle


@router.patch("/threads/{thread_id}/permissions")
async def update_thread_permissions(
    thread_id: str,
    payload: PermissionProfilePayload,
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
    auth_repo: AuthRepository = Depends(get_auth_repository),
):
    if not thread_store.get_owned_thread(thread_id=thread_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Thread not found")
    service = PermissionContextService(auth_repo, thread_store)
    updated = service.update_thread_overlay(
        thread_id=thread_id,
        user_id=current_user.id,
        profile=payload.model_dump(),
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    bundle = service.get_thread_permissions_bundle(thread_id=thread_id, user_id=current_user.id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return bundle


@router.post("/threads/{thread_id}/permissions/promote", response_model=PermissionProfilePayload)
async def promote_thread_permissions(
    thread_id: str,
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
    auth_repo: AuthRepository = Depends(get_auth_repository),
):
    if not thread_store.get_owned_thread(thread_id=thread_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Thread not found")
    service = PermissionContextService(auth_repo, thread_store)
    promoted = service.promote_thread_permissions(thread_id=thread_id, user_id=current_user.id)
    if promoted is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return promoted


@router.post("/chat/completions")
async def chat_completions(
    request: ChatRequest,
    http_request: Request,
    daytona_manager: DaytonaSessionManager = Depends(get_daytona_session_manager),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
    auth_repo: AuthRepository = Depends(get_auth_repository),
    store: FileStore = Depends(get_file_store),
    checkpointer: BaseCheckpointSaver = Depends(get_checkpointer),
):
    settings = get_settings()
    enforce_rate_limit(
        request=http_request,
        rule=RateLimitRule(
            scope="chat_requests",
            limit=settings.chat_requests_limit,
            window_seconds=settings.chat_requests_window_seconds,
        ),
        user=current_user,
    )
    thread = _resolve_thread(request=request, current_user=current_user, thread_store=thread_store)
    thread_id = thread["id"]
    permission_service = PermissionContextService(auth_repo, thread_store)
    _apply_resume_grant(
        request=request,
        service=permission_service,
        user_id=current_user.id,
        thread_id=thread_id,
    )
    file_ids = _extract_file_ids(request)
    backend_mode, local_root_dir = _extract_backend_selection(request)
    if backend_mode == "local":
        if local_root_dir:
            local_root = Path(local_root_dir).expanduser().resolve()
            if not local_root.exists() or not local_root.is_dir():
                raise HTTPException(status_code=400, detail=f"Local backend root_dir is invalid: {local_root}")
            backend = LocalBackend(root_dir=str(local_root))
        else:
            backend = LocalBackend()
    else:
        try:
            backend = daytona_manager.get_backend(thread_id)
        except DaytonaUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    workspace_root = _workspace_root_for_backend(backend)
    permission_context = permission_service.build_effective_context(
        user_id=current_user.id,
        thread_id=thread_id,
        workspace_root=workspace_root,
    )
    permission_context = _apply_permission_override(
        permission_context,
        override_mode=_extract_permission_override_mode(request),
        workspace_root=workspace_root,
    )

    source_records = None
    sandbox_paths = None
    target_file_id = None
    effective_messages = request.messages

    if file_ids:
        source_records, sandbox_paths, target_file_id, effective_messages = _stage_attached_files(
            request=request,
            backend=backend,
            file_ids=file_ids,
            current_user=current_user,
            store=store,
        )

    profile = _extract_profile(request)
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
        )
    else:
        resolved_model = _resolve_model_id(request.model)
        user_api_keys = _extract_user_api_keys(request)
        registry = {spec.id: spec for spec in get_model_registry()}
        spec = registry[resolved_model]
        resolved_provider = spec.provider
        model = build_chat_model(spec.provider, spec.model, api_keys=user_api_keys)

    capability_model_name = profile["model"] if profile else spec.model
    media_block_support = resolve_media_block_support(resolved_provider, capability_model_name)
    agent = create_ethos_agent(
        model=model,
        backend=backend,
        permission_context=permission_context,
        checkpointer=checkpointer,
        media_block_support=media_block_support,
    )

    logger.info(
        "Chat completion request received (model=%s -> %s, session_id=%s, stream=%s, messages=%d, files=%d, client=%s)",
        request.model,
        resolved_model,
        thread_id,
        request.stream,
        len(effective_messages),
        len(file_ids),
        http_request.client.host if http_request.client else "unknown",
    )

    resume_command = _extract_resume_command(request)
    if resume_command is not None:
        agent_input = resume_command
    else:
        agent_input = {"messages": _to_lc_messages(effective_messages)}

    config = {"configurable": {"thread_id": thread_id}}

    if request.stream:
        stream_iterator = (
            _stream_resume_response(
                agent=agent,
                agent_input=agent_input,
                model=resolved_model,
                thread_id=thread_id,
                backend=backend,
                store=store,
                current_user=current_user,
                source_records=source_records,
                sandbox_paths=sandbox_paths,
                target_file_id=target_file_id,
            )
            if resume_command is not None
            else _stream_response(
                agent=agent,
                agent_input=agent_input,
                model=resolved_model,
                thread_id=thread_id,
                backend=backend,
                store=store,
                current_user=current_user,
                source_records=source_records,
                sandbox_paths=sandbox_paths,
                target_file_id=target_file_id,
                messages=effective_messages,
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
        content = _extract_text(last.content)
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

    output_file = None
    if (
        source_records
        and sandbox_paths
        and target_file_id
        and target_file_id in source_records
        and target_file_id in sandbox_paths
        and source_records[target_file_id].get("filename", "").lower().endswith(".py")
    ):
        output_file = _publish_edited_file(
            source_records[target_file_id],
            backend,
            sandbox_paths[target_file_id],
            store=store,
            current_user=current_user,
            thread_id=thread_id,
        )

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
    if output_file and sandbox_paths and target_file_id:
        response["output_file"] = output_file
        response["sandbox_path"] = sandbox_paths[target_file_id]

    logger.info("Chat completion request finished (model=%s, session_id=%s)", resolved_model, thread_id)
    return response


@router.post("/tasks/title")
async def generate_title(
    request: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    del current_user
    profile = _extract_profile(request)
    try:
        if profile:
            result = await generate_title_task(
                model_id=profile["model"],
                messages=request.messages,
                api_keys={"api_key": profile["api_key"]},
                profile_provider=profile["provider"],
                profile_model=profile["model"],
                profile_base_url=profile["base_url"],
                profile_api_version=profile["api_version"],
                profile_deployment=profile["deployment"],
            )
        else:
            resolved_model = _resolve_model_id(request.model)
            user_api_keys = _extract_user_api_keys(request)
            result = await generate_title_task(
                model_id=resolved_model,
                messages=request.messages,
                api_keys=user_api_keys,
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Title generation failed")
        return {"title": fallback_title(request.messages)}

    title = result.title.strip() or fallback_title(request.messages)
    return {"title": title}


@router.post("/tasks/follow-ups")
async def generate_follow_ups(
    request: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    del current_user
    profile = _extract_profile(request)
    try:
        if profile:
            result = await generate_follow_ups_task(
                model_id=profile["model"],
                messages=request.messages,
                api_keys={"api_key": profile["api_key"]},
                profile_provider=profile["provider"],
                profile_model=profile["model"],
                profile_base_url=profile["base_url"],
                profile_api_version=profile["api_version"],
                profile_deployment=profile["deployment"],
            )
        else:
            resolved_model = _resolve_model_id(request.model)
            user_api_keys = _extract_user_api_keys(request)
            result = await generate_follow_ups_task(
                model_id=resolved_model,
                messages=request.messages,
                api_keys=user_api_keys,
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Follow-up generation failed")
        return {"follow_ups": []}

    return {"follow_ups": result.follow_ups}
