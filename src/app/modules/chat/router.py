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
from src.app.modules.chat.schemas import ChatRequest
from src.app.modules.chat.service import ChatService, get_chat_service
from src.app.services.chat_tasks import fallback_title, generate_follow_ups_task, generate_title_task
from src.app.services.permissions import PermissionContextService
from src.app.services.rate_limiter import RateLimitRule
from src.app.services.thread_store import ThreadStore
from src.config import get_model_registry
from src.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["v1"])


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
        logger.exception("Title generation failed")
        return {"title": fallback_title(request.messages)}

    title = result.title.strip() or fallback_title(request.messages)
    return {"title": title}


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
        logger.exception("Follow-up generation failed")
        return {"follow_ups": []}

    return {"follow_ups": result.follow_ups}
