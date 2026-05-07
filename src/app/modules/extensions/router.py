"""HTTP routes for Extensions settings: Skills and MCP."""

from __future__ import annotations

from urllib.parse import unquote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile

from src.app.core.settings import get_settings
from src.app.dependencies import enforce_rate_limit, get_current_user
from src.app.modules.auth.repository import AuthUser
from src.app.modules.extensions.schemas import (
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
from src.app.services.rate_limiter import RateLimitRule

router = APIRouter(prefix="/v1/extensions", tags=["extensions"])


def get_extensions_service() -> ExtensionsService:
    return ExtensionsService()


@router.get("/skills", response_model=SkillListPayload)
async def list_skills(
    root_dir: str = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.list_skills(root_dir=root_dir)


@router.get("/skills/{name}", response_model=SkillPayload)
async def get_skill(
    name: str,
    root_dir: str = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.get_skill(root_dir=root_dir, name=unquote(name))


@router.post("/skills/import", response_model=SkillImportPayload)
async def import_skill(
    request: Request,
    root_dir: str = Query(...),
    overwrite: bool = Query(False),
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
    return await service.import_skill(root_dir=root_dir, upload=file, overwrite=overwrite)


@router.delete("/skills/{name}")
async def delete_skill(
    name: str,
    root_dir: str = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.delete_skill(root_dir=root_dir, name=unquote(name))


@router.get("/mcp/servers", response_model=MCPServersPayload)
async def list_mcp_servers(
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.list_mcp_servers()


@router.get("/mcp/instructions", response_model=MCPInstructionsPayload)
async def get_mcp_instructions(
    current_user: AuthUser = Depends(get_current_user),
    service: ExtensionsService = Depends(get_extensions_service),
):
    del current_user
    return service.get_mcp_instructions()


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

