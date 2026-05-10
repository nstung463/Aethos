"""OpenAI-compatible v1 API endpoints."""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from src.app.core.settings import get_settings
from src.app.dependencies import (
    enforce_rate_limit,
    get_auth_repository,
    get_current_user,
    get_thread_store,
)
from src.app.modules.auth.repository import AuthRepository, AuthUser
from src.app.modules.auth.schemas import PermissionProfilePayload
from src.app.modules.chat.request_parser import (
    extract_profile,
    extract_user_api_keys,
    resolve_model_id,
)
from src.app.modules.chat.schemas import (
    ChatRequest,
    ContextStatusPayload,
    ContextStatusRequest,
    StopRunPayload,
    ThreadListPayload,
    ThreadPayload,
    ThreadUpdatePayload,
)
from src.app.modules.chat.service import ChatService, get_chat_service
from src.app.services.context_status import build_context_status
from src.app.services.chat_tasks import fallback_title, generate_follow_ups_task, generate_title_task
from src.app.services.permissions import PermissionContextService
from src.app.services.rate_limiter import RateLimitRule
from src.app.services.thread_store import ThreadStore
from src.config import get_mcp_servers, get_model_registry
from src.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["v1"])


def _safe_title_result(result: object) -> str | None:
    title = getattr(result, "title", None)
    if not isinstance(title, str):
        return None
    stripped = title.strip()
    return stripped or None


def _safe_follow_ups_result(result: object) -> list[str] | None:
    follow_ups = getattr(result, "follow_ups", None)
    if not isinstance(follow_ups, list):
        return None
    if not all(isinstance(item, str) for item in follow_ups):
        return None
    return follow_ups


@router.get("/models")
async def list_models():
    """List available models."""
    now = int(time.time())
    return {
        "object": "list",
        "data": [
            {
                "id": spec.id,
                "object": "model",
                "created": now,
                "owned_by": "aethos",
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
    chat_service: ChatService = Depends(get_chat_service),
):
    """Create a new thread."""
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
    return chat_service.create_thread(user_id=current_user.id)


@router.get("/threads", response_model=ThreadListPayload)
async def list_threads(
    current_user: AuthUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """List user-owned threads with persisted checkpoint messages."""
    return await chat_service.list_threads(user_id=current_user.id)


@router.get("/threads/{thread_id}", response_model=ThreadPayload)
async def get_thread(
    thread_id: str,
    current_user: AuthUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Get a user-owned thread with persisted checkpoint messages."""
    return await chat_service.get_thread(thread_id=thread_id, user_id=current_user.id)


@router.patch("/threads/{thread_id}", response_model=ThreadPayload)
async def update_thread(
    thread_id: str,
    payload: ThreadUpdatePayload,
    current_user: AuthUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Update user-facing thread metadata."""
    chat_service.update_thread(thread_id=thread_id, user_id=current_user.id, payload=payload)
    return await chat_service.get_thread(thread_id=thread_id, user_id=current_user.id)


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    current_user: AuthUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Delete user-owned thread metadata."""
    return chat_service.delete_thread(thread_id=thread_id, user_id=current_user.id)


@router.post("/threads/{thread_id}/runs/{run_id}/stop")
async def stop_thread_run(
    thread_id: str,
    run_id: str,
    payload: StopRunPayload,
    current_user: AuthUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Persist an explicit user stop for an active streaming run."""
    return await chat_service.stop_run(
        thread_id=thread_id,
        user_id=current_user.id,
        run_id=run_id,
        reason=payload.reason or "user_cancel",
    )


@router.get("/threads/{thread_id}/permissions")
async def get_thread_permissions(
    thread_id: str,
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
    auth_repo: AuthRepository = Depends(get_auth_repository),
):
    """Get thread permissions."""
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
    """Update thread permissions."""
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
    """Promote thread permissions to user default."""
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
    current_user: AuthUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
):
    """Main chat completion endpoint."""
    return await chat_service.run_completion(request, http_request, current_user)


@router.post("/context/status", response_model=ContextStatusPayload)
async def context_status(
    payload: ContextStatusRequest,
    current_user: AuthUser = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    """Return approximate context usage and prompt rule files for the composer."""
    thread = thread_store.get_owned_thread(thread_id=payload.thread_id, user_id=current_user.id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    root_dir = str(thread.get("workspace_root") or "").strip()
    if not root_dir:
        raise HTTPException(status_code=409, detail="Thread workspace is not initialized")
    try:
        thread_payload = await chat_service.get_thread(thread_id=payload.thread_id, user_id=current_user.id)
        messages = [message for message in thread_payload.get("messages", []) if isinstance(message, dict)]
        return build_context_status(
            root_dir=root_dir,
            model=payload.model,
            messages=messages,
            context_window=payload.context_window,
            mcp_servers=get_mcp_servers(root_dir, owner_user_id=current_user.id),
            owner_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks/title")
async def generate_title(
    request: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    """Generate a title for messages."""
    del current_user
    settings = get_settings()
    profile = extract_profile(request, settings)
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
                profile_reasoning_enabled=profile["reasoning_enabled"],
                profile_reasoning_effort=profile["reasoning_effort"],
                profile_thinking_budget_tokens=profile["thinking_budget_tokens"],
                profile_model_kwargs=profile["model_kwargs"],
            )
        else:
            resolved_model = resolve_model_id(request.model)
            user_api_keys = extract_user_api_keys(request)
            result = await generate_title_task(
                model_id=resolved_model,
                messages=request.messages,
                api_keys=user_api_keys,
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Title generation failed (model=%s, messages=%d)", request.model, len(request.messages))
        return {"title": fallback_title(request.messages)}

    return {"title": _safe_title_result(result) or fallback_title(request.messages)}


@router.post("/tasks/follow-ups")
async def generate_follow_ups(
    request: ChatRequest,
    current_user: AuthUser = Depends(get_current_user),
):
    """Generate follow-up questions."""
    del current_user
    settings = get_settings()
    profile = extract_profile(request, settings)
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
                profile_reasoning_enabled=False,
                profile_reasoning_effort="none",
                profile_thinking_budget_tokens=None,
                profile_model_kwargs=profile["model_kwargs"],
            )
        else:
            resolved_model = resolve_model_id(request.model)
            user_api_keys = extract_user_api_keys(request)
            result = await generate_follow_ups_task(
                model_id=resolved_model,
                messages=request.messages,
                api_keys=user_api_keys,
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Follow-up generation failed (model=%s, messages=%d)", request.model, len(request.messages))
        return {"follow_ups": []}

    return {"follow_ups": _safe_follow_ups_result(result) or []}
