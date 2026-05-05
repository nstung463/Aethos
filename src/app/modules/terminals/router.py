from __future__ import annotations

import json
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from src.app.core.settings import get_settings
from src.app.dependencies import (
    get_rate_limiter,
    get_current_user,
    get_open_terminal_api_key,
    get_open_terminal_base_url,
    get_terminal_name,
    get_thread_store,
    require_websocket_user,
)
from src.app.modules.auth.repository import AuthUser
from src.app.services.rate_limiter import RateLimitRule
from src.app.services.thread_store import ThreadStore
from src.logger import get_logger

router = APIRouter(prefix="/api/terminals", tags=["terminals"])
logger = get_logger(__name__)

DEFAULT_SANDBOX_ID = "default"
STREAMING_CONTENT_TYPES = ("application/octet-stream", "image/", "application/pdf", "application/zip", "audio/", "video/")
STRIPPED_RESPONSE_HEADERS = frozenset(("transfer-encoding", "connection", "content-encoding", "content-length"))


def _require_owned_thread(*, sandbox_id: str, current_user: AuthUser, thread_store: ThreadStore) -> None:
    if not thread_store.get_owned_thread(thread_id=sandbox_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Thread not found")


def _auth_headers(api_key: str) -> dict[str, str]:
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


async def _proxy(
    *,
    method: str,
    path: str,
    request: Request,
    base_url: str,
    api_key: str,
    query: dict[str, str] | None = None,
) -> Response:
    url = f"{base_url}{path}"
    params = urlencode(query or {})
    if params:
        url = f"{url}?{params}"

    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            upstream = await client.request(
                method,
                url,
                headers=_auth_headers(api_key),
                content=(await request.body()) or None,
            )
        except httpx.TimeoutException as exc:
            logger.warning("Terminal proxy timed out (method=%s, path=%s, url=%s)", method, path, url)
            raise HTTPException(
                status_code=504,
                detail=f"Timed out while proxying terminal request {method} {path} to {url}",
            ) from exc
        except httpx.RequestError as exc:
            logger.warning("Terminal proxy request failed (method=%s, path=%s, url=%s, error=%s)", method, path, url, exc)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to proxy terminal request {method} {path} to {url}: {exc}",
            ) from exc

        content_type = upstream.headers.get("content-type", "")
        headers = {
            key: value
            for key, value in upstream.headers.items()
            if key.lower() not in STRIPPED_RESPONSE_HEADERS
        }

        if any(token in content_type for token in STREAMING_CONTENT_TYPES):
            async def stream_content():
                async for chunk in upstream.aiter_bytes():
                    yield chunk

            return StreamingResponse(
                stream_content(),
                status_code=upstream.status_code,
                headers=headers,
                background=BackgroundTask(upstream.aclose),
            )

        content = await upstream.aread()
        await upstream.aclose()
        return Response(content=content, status_code=upstream.status_code, headers=headers)


@router.get("/")
async def list_terminals(
    request: Request,
    terminal_name: str = Depends(get_terminal_name),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    return [
        {
            "id": thread["id"],
            "name": terminal_name,
            "url": f"{request.base_url}api/terminals/{thread['id']}",
        }
        for thread in thread_store.list_threads(user_id=current_user.id)
    ]


@router.get("/{sandbox_id}/files/cwd")
async def get_cwd(
    sandbox_id: str,
    request: Request,
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(method="GET", path="/files/cwd", request=request, base_url=base_url, api_key=api_key)


@router.post("/{sandbox_id}/files/cwd")
async def set_cwd(
    sandbox_id: str,
    request: Request,
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(method="POST", path="/files/cwd", request=request, base_url=base_url, api_key=api_key)


@router.get("/{sandbox_id}/files/list")
async def list_files(
    sandbox_id: str,
    request: Request,
    directory: str = Query("/"),
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(
        method="GET",
        path="/files/list",
        request=request,
        base_url=base_url,
        api_key=api_key,
        query={"directory": directory},
    )


@router.get("/{sandbox_id}/files/read")
async def read_file(
    sandbox_id: str,
    request: Request,
    path: str = Query(...),
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(
        method="GET",
        path="/files/read",
        request=request,
        base_url=base_url,
        api_key=api_key,
        query={"path": path},
    )


@router.get("/{sandbox_id}/files/view")
async def view_file(
    sandbox_id: str,
    request: Request,
    path: str = Query(...),
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(
        method="GET",
        path="/files/view",
        request=request,
        base_url=base_url,
        api_key=api_key,
        query={"path": path},
    )


@router.post("/{sandbox_id}/files/upload")
async def upload_to_sandbox(
    sandbox_id: str,
    request: Request,
    directory: str = Query("/"),
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(
        method="POST",
        path="/files/upload",
        request=request,
        base_url=base_url,
        api_key=api_key,
        query={"directory": directory},
    )


@router.post("/{sandbox_id}/files/mkdir")
async def mkdir(
    sandbox_id: str,
    request: Request,
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(method="POST", path="/files/mkdir", request=request, base_url=base_url, api_key=api_key)


@router.delete("/{sandbox_id}/files/delete")
async def delete_entry(
    sandbox_id: str,
    request: Request,
    path: str = Query(...),
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(
        method="DELETE",
        path="/files/delete",
        request=request,
        base_url=base_url,
        api_key=api_key,
        query={"path": path},
    )


@router.post("/{sandbox_id}/files/move")
async def move_entry(
    sandbox_id: str,
    request: Request,
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(method="POST", path="/files/move", request=request, base_url=base_url, api_key=api_key)


@router.post("/{sandbox_id}/files/archive")
async def archive_files(
    sandbox_id: str,
    request: Request,
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(method="POST", path="/files/archive", request=request, base_url=base_url, api_key=api_key)


@router.get("/{sandbox_id}/ports")
async def list_ports(
    sandbox_id: str,
    request: Request,
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(method="GET", path="/ports", request=request, base_url=base_url, api_key=api_key)


@router.post("/{sandbox_id}/api/terminals")
async def create_terminal_session(
    sandbox_id: str,
    request: Request,
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    settings = get_settings()
    allowed, retry_after = get_rate_limiter().hit(
        rule=RateLimitRule(
            scope="terminal_create",
            limit=settings.terminal_create_limit,
            window_seconds=settings.terminal_create_window_seconds,
        ),
        key=f"user:{current_user.id}",
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for terminal_create. Retry in {retry_after}s.",
            headers={"Retry-After": str(retry_after)},
        )
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    return await _proxy(method="POST", path="/api/terminals", request=request, base_url=base_url, api_key=api_key)


@router.websocket("/{sandbox_id}/api/terminals/{session_id}")
async def terminal_ws(
    websocket: WebSocket,
    sandbox_id: str,
    session_id: str,
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    current_user = require_websocket_user(websocket)
    settings = get_settings()
    allowed, retry_after = get_rate_limiter().hit(
        rule=RateLimitRule(
            scope="terminal_connect",
            limit=settings.terminal_connect_limit,
            window_seconds=settings.terminal_connect_window_seconds,
        ),
        key=f"user:{current_user.id}",
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for terminal_connect. Retry in {retry_after}s.",
        )
    _require_owned_thread(sandbox_id=sandbox_id, current_user=current_user, thread_store=thread_store)
    await websocket.accept()
    ws_base = base_url.replace("https://", "wss://").replace("http://", "ws://")
    upstream_url = f"{ws_base}/api/terminals/{session_id}"

    import asyncio
    import websockets

    try:
        async with websockets.connect(upstream_url) as upstream:
            async def client_to_upstream() -> None:
                while True:
                    message = await websocket.receive()
                    if message["type"] == "websocket.disconnect":
                        break
                    if message.get("text") is not None:
                        text = message["text"]
                        try:
                            payload = json.loads(text)
                        except json.JSONDecodeError:
                            payload = None
                        if isinstance(payload, dict) and payload.get("type") == "auth":
                            await upstream.send(json.dumps({"type": "auth", "token": api_key}))
                        else:
                            await upstream.send(text)
                    elif message.get("bytes") is not None:
                        await upstream.send(message["bytes"])

            async def upstream_to_client() -> None:
                async for message in upstream:
                    if isinstance(message, bytes):
                        await websocket.send_bytes(message)
                    else:
                        await websocket.send_text(message)

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception(
            "Terminal websocket proxy failed (sandbox_id=%s, session_id=%s)",
            sandbox_id,
            session_id,
        )
        await websocket.close(code=1011, reason=str(exc)[:120])
