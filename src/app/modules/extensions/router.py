"""HTTP routes for Extensions settings: Skills and MCP."""

from __future__ import annotations

import html
import json
from urllib.parse import unquote
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse

from src.app.core.settings import get_settings
from src.app.dependencies import enforce_rate_limit, get_current_user
from src.app.modules.auth.repository import AuthUser
from src.app.modules.extensions.schemas import (
    ConnectionAuthorizationInput,
    ConnectionAuthorizationPayload,
    ConnectionListPayload,
    ConnectionPayload,
    ConnectionScopesPayload,
    ConnectionTestPayload,
    ConnectionToolsInput,
    MCPJSONConfigInput,
    MCPJSONConfigPayload,
    MCPInstructionsPayload,
    MCPServerInput,
    MCPServersPayload,
    SkillImportPayload,
    SkillListPayload,
    SkillPayload,
)
from src.app.modules.extensions.service import ExtensionsService
from src.app.services.connections import ConnectionService, SUPPORTED_CONNECTION_PROVIDERS
from src.app.services.rate_limiter import RateLimitRule

router = APIRouter(prefix="/v1/extensions", tags=["extensions"])


def get_extensions_service() -> ExtensionsService:
    return ExtensionsService()


def _connection_provider_or_400(provider: str) -> str:
    value = provider.strip().lower()
    if value not in SUPPORTED_CONNECTION_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported connection provider: {provider}")
    return value


def _request_origin(request: Request) -> str | None:
    origin = request.headers.get("origin")
    if origin:
        parsed = urlsplit(origin)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
    referer = request.headers.get("referer")
    if not referer:
        return None
    parsed = urlsplit(referer)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return None


def _validated_redirect_to_or_none(request: Request, redirect_to: str | None) -> str | None:
    if redirect_to is None:
        return None
    candidate = redirect_to.strip()
    if not candidate:
        return None
    parsed = urlsplit(candidate)
    if not parsed.scheme and not parsed.netloc:
        if candidate.startswith("/"):
            return candidate
        raise HTTPException(status_code=400, detail="redirect_to must be an absolute URL or root-relative path.")
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="redirect_to must use http or https.")
    request_origin = _request_origin(request)
    redirect_origin = f"{parsed.scheme}://{parsed.netloc}"
    if request_origin is None or redirect_origin != request_origin:
        raise HTTPException(status_code=400, detail="redirect_to origin must match the requesting app.")
    return candidate


def _connection_callback_html(*, account_label: str, redirect_to: str | None) -> str:
    safe_account_label = html.escape(account_label, quote=True)
    redirect_script = (
        "if (window.opener) { "
        "window.opener.postMessage({ type: 'aethos-connections-updated' }, window.location.origin); "
        "window.close(); "
        "} else { "
        + (
            f"window.location.replace({json.dumps(redirect_to)});"
            if isinstance(redirect_to, str) and redirect_to.strip()
            else ""
        )
        + " }"
    )
    return f"""
        <!doctype html>
        <html>
          <head><meta charset="utf-8"><title>Aethos Connection</title></head>
          <body style="font-family: sans-serif; padding: 24px;">
            <h1>Connection ready</h1>
            <p>{safe_account_label} is now connected to Aethos.</p>
            <p>You can close this window and refresh the Connections panel.</p>
            <script>{redirect_script}</script>
          </body>
        </html>
        """


@router.get("/skills", response_model=SkillListPayload)
async def list_skills(
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.list_skills(root_dir=root_dir)


@router.get("/skills/{name}", response_model=SkillPayload)
async def get_skill(
    name: str,
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.get_skill(name=unquote(name), root_dir=root_dir)


@router.post("/skills/import", response_model=SkillImportPayload)
async def import_skill(
    request: Request,
    root_dir: str | None = Query(None),
    overwrite: bool = Query(False),
    scope: str = Query("user"),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    settings = get_settings()
    enforce_rate_limit(
        request=request,
        rule=RateLimitRule(
            scope="files_write",
            limit=settings.file_write_limit,
            window_seconds=settings.file_write_window_seconds,
        ),
        user=current_user,
    )
    return await service.import_skill(upload=file, overwrite=overwrite, scope=scope, root_dir=root_dir)


@router.delete("/skills/{name}")
async def delete_skill(
    name: str,
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.delete_skill(name=unquote(name), root_dir=root_dir)


@router.get("/mcp/servers", response_model=MCPServersPayload)
async def list_mcp_servers(
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.list_mcp_servers(root_dir=root_dir)


@router.get("/mcp/instructions", response_model=MCPInstructionsPayload)
async def get_mcp_instructions(
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.get_mcp_instructions(root_dir=root_dir)


@router.get("/mcp/config", response_model=MCPJSONConfigPayload)
async def get_mcp_config(
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.get_mcp_json_config()


@router.put("/mcp/config", response_model=MCPJSONConfigPayload)
async def update_mcp_config(
    body: MCPJSONConfigInput,
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.update_mcp_json_config(body)


@router.post("/mcp/refresh", response_model=MCPServersPayload)
async def refresh_mcp(
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.refresh_mcp()


@router.post("/mcp/servers", response_model=MCPServersPayload, status_code=201)
async def add_mcp_server(
    body: MCPServerInput,
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    """Add or update an MCP server in the workspace settings file."""
    del current_user
    return service.add_mcp_server(body)


@router.delete("/mcp/servers/{name}", response_model=MCPServersPayload)
async def remove_mcp_server(
    name: str,
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    """Remove a settings-file MCP server by name."""
    del current_user
    return service.remove_mcp_server(name)


@router.get("/connections", response_model=ConnectionListPayload)
async def list_connections(
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    return service.list_connections(owner_user_id=current_user.id, root_dir=root_dir)


@router.post("/connections/{provider}/authorize", response_model=ConnectionAuthorizationPayload)
async def begin_connection_authorization(
    request: Request,
    provider: str,
    body: ConnectionAuthorizationInput,
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    provider_name = _connection_provider_or_400(provider)
    return service.begin_connection_authorization(
        root_dir=root_dir,
        provider=provider_name,
        owner_user_id=current_user.id,
        body=ConnectionAuthorizationInput(
            redirect_to=_validated_redirect_to_or_none(request, body.redirect_to),
        ),
    )


@router.get("/connections/{provider}/callback", response_class=HTMLResponse)
async def handle_connection_callback(
    provider: str,
    code: str = Query(...),
    state: str = Query(...),
):
    provider_name = _connection_provider_or_400(provider)
    service = ConnectionService.for_oauth_state(provider=provider_name, state=state)  # type: ignore[arg-type]
    result = service.handle_callback(provider=provider_name, code=code, state=state)  # type: ignore[arg-type]
    account_label = str(result.get("account_label") or provider)
    redirect_to = result.get("redirect_to")
    return HTMLResponse(_connection_callback_html(account_label=account_label, redirect_to=redirect_to))


@router.post("/connections/{connection_id}/test", response_model=ConnectionTestPayload)
async def test_connection(
    connection_id: str,
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    return service.test_connection(connection_id=connection_id, owner_user_id=current_user.id, root_dir=root_dir)


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    return service.delete_connection(connection_id=connection_id, owner_user_id=current_user.id, root_dir=root_dir)


@router.patch("/connections/{connection_id}/tools", response_model=ConnectionPayload)
async def update_connection_tools(
    connection_id: str,
    body: ConnectionToolsInput,
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    return service.update_connection_tools(
        root_dir=root_dir,
        connection_id=connection_id,
        owner_user_id=current_user.id,
        body=body,
    )


@router.get("/connections/{connection_id}/scopes", response_model=ConnectionScopesPayload)
async def get_connection_scopes(
    connection_id: str,
    root_dir: str | None = Query(None),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    return service.get_connection_scopes(connection_id=connection_id, owner_user_id=current_user.id, root_dir=root_dir)

