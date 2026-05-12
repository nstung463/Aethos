"""Service layer for skills, MCP metadata, and native connections."""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from tempfile import NamedTemporaryFile
from typing import Any

from fastapi import HTTPException, UploadFile

from src.ai.middleware.mcp_instructions import build_mcp_instructions_section
from src.ai.skills.registry import SkillDefinition, SkillNotFoundError, SkillRegistry, _is_mcp_skill_prompt, strip_frontmatter
from src.ai.tools.mcp import MCPRuntime
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
    MCPServerPayload,
    MCPServersPayload,
    SkillImportPayload,
    SkillListPayload,
    SkillPayload,
)
from src.app.services.connections import ConnectionService, SUPPORTED_CONNECTION_PROVIDERS
from src.app.services.settings import SettingsService
from src.config import MCPServerSpec, _SUPPORTED_TRANSPORTS, get_mcp_servers, get_workspace

_MAX_SKILL_PACKAGE_BYTES = 25 * 1024 * 1024
_SKILL_PACKAGE_SUFFIXES = {".zip", ".skill"}
_SAFE_DIR_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_SUPPORTED_CONNECTION_PROVIDERS = set(SUPPORTED_CONNECTION_PROVIDERS)


@dataclass(frozen=True)
class _ValidatedArchive:
    archive_path: Path
    base_prefix: str
    skill_name: str
    install_dir_name: str
    warnings: list[str]


def _skill_to_payload(
    skill: SkillDefinition,
    *,
    body: str | None = None,
    delete_root: Path | None = None,
    overridden_by_project: bool = False,
) -> SkillPayload:
    can_delete = False
    if delete_root is not None and skill.path is not None and skill.source in {"aethos_project", "aethos_user"}:
        aethos_root = delete_root.resolve()
        try:
            skill.path.resolve().relative_to(aethos_root)
            can_delete = True
        except ValueError:
            can_delete = False
    return SkillPayload(
        name=skill.name,
        description=skill.description,
        source=skill.source,
        loaded_from=skill.loaded_from,
        aliases=list(skill.aliases),
        path=str(skill.path) if skill.path else None,
        root_dir=str(skill.root_dir) if skill.root_dir else None,
        server=skill.server,
        remote_name=skill.remote_name,
        when_to_use=skill.when_to_use,
        allowed_tools=list(skill.allowed_tools),
        argument_hint=skill.argument_hint,
        arguments=list(skill.arguments),
        model=skill.model,
        effort=skill.effort,
        context=skill.context,
        agent=skill.agent,
        paths=list(skill.paths),
        raw_frontmatter=skill.raw_frontmatter,
        body=body,
        can_delete=can_delete,
        overridden_by_project=overridden_by_project,
    )



class ExtensionsService:
    def __init__(
        self,
        mcp_servers: list[MCPServerSpec] | None = None,
        workspace: str | None = None,
        user_aethos_skill_root: str | Path | None = None,
        settings_service: SettingsService | None = None,
    ) -> None:
        self._workspace = workspace or get_workspace()
        self._settings_service = settings_service or SettingsService()
        self._mcp_servers = (
            mcp_servers
            if mcp_servers is not None
            else get_mcp_servers(self._workspace, include_project_settings=False)
        )
        self._user_aethos_skill_root = (
            Path(user_aethos_skill_root).expanduser().resolve()
            if user_aethos_skill_root is not None
            else SkillRegistry.default_user_aethos_skill_root()
        )

    def _skill_registry(self, root_dir: str | None = None) -> SkillRegistry:
        project_mode = bool(root_dir and root_dir.strip())
        workspace = root_dir or self._workspace
        return SkillRegistry(
            workspace,
            mcp_runtime=MCPRuntime(self._mcp_servers_for(root_dir)),
            user_aethos_skill_root=self._user_aethos_skill_root,
            include_project_skills=project_mode,
        )

    def _mcp_servers_for(self, root_dir: str | None = None) -> list[MCPServerSpec]:
        if not root_dir or not root_dir.strip():
            return list(self._mcp_servers)
        workspace = root_dir
        include_project_settings = bool(root_dir and root_dir.strip())
        return get_mcp_servers(workspace, include_project_settings=include_project_settings)

    @staticmethod
    def _normalize_mcp_scope(scope: str | None) -> str:
        value = (scope or "user").strip().lower()
        if value not in {"user", "project"}:
            raise HTTPException(status_code=400, detail="MCP scope must be 'user' or 'project'.")
        return value

    def _connection_service(self, root_dir: str | None = None) -> ConnectionService:
        workspace = root_dir if root_dir and root_dir.strip() else self._workspace
        return ConnectionService(workspace_root=workspace, scope="user")

    def _legacy_project_connection_service(self, root_dir: str | None = None) -> ConnectionService | None:
        if not root_dir or not root_dir.strip():
            return None
        return ConnectionService(workspace_root=root_dir)

    def _project_override_names(self, root_dir: str | None) -> set[str]:
        if not root_dir or not root_dir.strip():
            return set()
        skills_dir = Path(root_dir).expanduser().resolve() / ".aethos" / "skills"
        if not skills_dir.exists():
            return set()
        names: set[str] = set()
        for skill_md in skills_dir.glob("*/SKILL.md"):
            try:
                frontmatter, _body = strip_frontmatter(skill_md.read_text(encoding="utf-8"))
            except OSError:
                continue
            name = frontmatter.get("name") if isinstance(frontmatter, dict) else None
            if isinstance(name, str) and name.strip():
                names.add(name.strip())
        return names

    def list_skills(self, *, root_dir: str | None = None) -> SkillListPayload:
        registry = self._skill_registry(root_dir)
        override_names = self._project_override_names(root_dir)
        skills = [
            _skill_to_payload(
                skill,
                delete_root=self._user_aethos_skill_root,
                overridden_by_project=skill.source == "aethos_user" and skill.name in override_names,
            )
            for skill in registry.discover()
        ]
        resolved_root = Path(root_dir).expanduser().resolve() if root_dir and root_dir.strip() else self._user_aethos_skill_root
        return SkillListPayload(root_dir=str(resolved_root), skills=skills)

    def get_skill(self, *, name: str, root_dir: str | None = None) -> SkillPayload:
        registry = self._skill_registry(root_dir)
        try:
            skill = registry.get(name)
        except SkillNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        body = None
        if skill.loaded_from == "local" and skill.path is not None:
            _frontmatter, body = strip_frontmatter(skill.path.read_text(encoding="utf-8"))
        override_names = self._project_override_names(root_dir)
        return _skill_to_payload(
            skill,
            body=body,
            delete_root=self._user_aethos_skill_root,
            overridden_by_project=skill.source == "aethos_user" and skill.name in override_names,
        )

    async def import_skill(
        self,
        *,
        upload: UploadFile,
        overwrite: bool = False,
        scope: str = "user",
        root_dir: str | None = None,
    ) -> SkillImportPayload:
        if scope not in {"user", "project"}:
            raise HTTPException(status_code=400, detail="Skill scope must be 'user' or 'project'")
        if scope == "project" and (not root_dir or not root_dir.strip()):
            raise HTTPException(status_code=400, detail="Project skill uploads require root_dir")
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in _SKILL_PACKAGE_SUFFIXES:
            raise HTTPException(status_code=400, detail="Skill package must be a .zip or .skill file")

        archive_path: Path | None = None
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp:
            archive_path = Path(temp.name)
            total = 0
            try:
                while chunk := await upload.read(1024 * 1024):
                    total += len(chunk)
                    if total > _MAX_SKILL_PACKAGE_BYTES:
                        raise HTTPException(status_code=413, detail="Skill package exceeds size limit")
                    temp.write(chunk)
            except Exception:
                archive_path.unlink(missing_ok=True)
                raise

        try:
            if archive_path is None:
                raise HTTPException(status_code=400, detail="Skill package upload failed")
            validated = self._validate_archive(archive_path)
            target_root = (
                Path(root_dir).expanduser().resolve() / ".aethos" / "skills"
                if scope == "project" and root_dir is not None
                else self._user_aethos_skill_root
            )
            target = (target_root / validated.install_dir_name).resolve()
            try:
                target.relative_to(target_root.resolve())
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Skill install path is invalid") from exc
            if target.exists() and not overwrite:
                raise HTTPException(status_code=409, detail=f"Skill '{validated.install_dir_name}' already exists")

            target_root.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True)
            self._extract_archive(validated, target)

            registry = self._skill_registry(root_dir if scope == "project" else None)
            skill = registry.get(validated.skill_name)
            return SkillImportPayload(
                skill=_skill_to_payload(skill, delete_root=self._user_aethos_skill_root),
                warnings=validated.warnings,
            )
        finally:
            archive_path.unlink(missing_ok=True)

    def delete_skill(self, *, name: str, root_dir: str | None = None) -> dict[str, bool]:
        registry = self._skill_registry(root_dir)
        try:
            skill = registry.get(name)
        except SkillNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        if skill.root_dir is None:
            raise HTTPException(status_code=403, detail="Only local .aethos skills can be deleted")
        if skill.source == "aethos_user":
            aethos_root = self._user_aethos_skill_root.resolve()
        elif skill.source == "aethos_project" and root_dir and root_dir.strip():
            aethos_root = (Path(root_dir).expanduser().resolve() / ".aethos" / "skills").resolve()
        else:
            raise HTTPException(status_code=403, detail="Only user or current-project .aethos skills can be deleted")
        target = skill.root_dir.resolve()
        try:
            target.relative_to(aethos_root)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Skill path is outside .aethos/skills") from exc
        shutil.rmtree(target)
        return {"ok": True}

    def list_mcp_servers(self, *, root_dir: str | None = None) -> MCPServersPayload:
        specs = self._mcp_servers_for(root_dir)
        runtime = MCPRuntime(specs)
        user_settings = self._settings_service.get_settings_for_source("user")
        user_mcp = user_settings.get("mcpServers") if isinstance(user_settings, dict) else {}
        user_settings_names = set(user_mcp) if isinstance(user_mcp, dict) else set()
        effective_settings = (
            self._settings_service.get_effective_settings(workspace_root=root_dir)
            if root_dir and root_dir.strip()
            else self._settings_service.get_effective_settings()
        )
        effective_mcp = effective_settings.get("mcpServers") if isinstance(effective_settings, dict) else {}
        effective_names = set(effective_mcp) if isinstance(effective_mcp, dict) else set()
        project_names: set[str] = set()
        local_names: set[str] = set()
        managed_settings = self._settings_service.get_settings_for_source("managed")
        managed_names = set(managed_settings.get("mcpServers", {})) if isinstance(managed_settings.get("mcpServers"), dict) else set()
        if root_dir and root_dir.strip():
            project_settings = self._settings_service.get_settings_for_source("project", workspace_root=root_dir)
            local_settings = self._settings_service.get_settings_for_source("local", workspace_root=root_dir)
            project_names = set(project_settings.get("mcpServers", {})) if isinstance(project_settings.get("mcpServers"), dict) else set()
            local_names = set(local_settings.get("mcpServers", {})) if isinstance(local_settings.get("mcpServers"), dict) else set()
        servers: list[MCPServerPayload] = []
        for spec in specs:
            tools: list[dict[str, Any]] = []
            resources: list[dict[str, Any]] = []
            prompts: list[dict[str, Any]] = []
            errors: list[str] = []
            status = "ok"
            try:
                tools = self._json_items(runtime.list_tools(spec.name), "tools")
            except Exception as exc:
                errors.append(f"tools: {exc}")
            try:
                resources = self._json_items(runtime.list_resources(spec.name), "resources")
            except Exception as exc:
                errors.append(f"resources: {exc}")
            try:
                prompts = self._json_items(runtime.list_prompts(spec.name), "prompts")
            except Exception as exc:
                errors.append(f"prompts: {exc}")
            if errors:
                status = "partial" if tools else "error"
            skill_prompts = [item for item in prompts if _is_mcp_skill_prompt(item)]
            transport = str(spec.connection.get("transport", "")) or None
            in_settings = spec.name in effective_names
            source = spec.source or ("settings" if in_settings else "env")
            scope = None
            if spec.name in local_names:
                scope = "local"
            elif spec.name in project_names:
                scope = "project"
            elif spec.name in user_settings_names:
                scope = "user"
            elif spec.name in managed_names:
                scope = "managed"
            elif source == "mcp_json":
                scope = "project"
            elif source == "env":
                scope = "env"
            servers.append(
                MCPServerPayload(
                    name=spec.name,
                    transport=transport,
                    url=str(spec.connection.get("url", "")) or None,
                    httpUrl=str(spec.connection.get("url", "")) or None,
                    auth_url=spec.auth_url,
                    has_instructions=bool(spec.instructions),
                    status=status,
                    error="; ".join(errors) if errors else None,
                    command=str(spec.connection.get("command", "")) or None,
                    args=list(spec.connection.get("args", [])),
                    source=source,
                    scope=scope,
                    can_remove=spec.name in user_settings_names,
                    tools=tools,
                    resources=resources,
                    prompts=prompts,
                    skill_prompts=skill_prompts,
                )
            )
        return MCPServersPayload(servers=servers)

    def get_mcp_instructions(self, *, root_dir: str | None = None) -> MCPInstructionsPayload:
        return MCPInstructionsPayload(
            instructions=build_mcp_instructions_section(self._mcp_servers_for(root_dir))
        )

    def refresh_mcp(self) -> MCPServersPayload:
        self._mcp_servers = get_mcp_servers(self._workspace, include_project_settings=False)
        return self.list_mcp_servers()

    def add_mcp_server(self, body: MCPServerInput, *, root_dir: str | None = None) -> MCPServersPayload:
        """Persist a new server to the selected settings scope and refresh the server list."""
        if body.transport not in _SUPPORTED_TRANSPORTS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported transport {body.transport!r}. Supported: {', '.join(sorted(_SUPPORTED_TRANSPORTS))}",
            )
        scope = self._normalize_mcp_scope(body.scope)
        if scope == "project" and (not root_dir or not root_dir.strip()):
            raise HTTPException(status_code=400, detail="Project MCP servers require root_dir")
        spec = MCPServerSpec(
            name=body.name,
            connection=body.to_connection(),
            auth_url=body.auth_url,
            instructions=body.instructions,
        )
        source = "project" if scope == "project" else "user"
        source_settings = self._settings_service.get_settings_for_source(
            source, workspace_root=root_dir
        )
        current_servers = (
            source_settings.get("mcpServers")
            if isinstance(source_settings.get("mcpServers"), dict)
            else {}
        )
        entry = dict(spec.connection)
        if spec.auth_url:
            entry["auth_url"] = spec.auth_url
        if spec.instructions:
            entry["instructions"] = spec.instructions
        self._settings_service.update_settings_for_source(
            source,
            {"mcpServers": {**current_servers, spec.name: entry}},
            workspace_root=root_dir,
        )
        if scope == "user":
            self._mcp_servers = self._mcp_servers_for()
        return self.list_mcp_servers(root_dir=root_dir)

    @staticmethod
    def _validate_provider(provider: str) -> str:
        value = provider.strip().lower()
        if value not in _SUPPORTED_CONNECTION_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unsupported connection provider: {provider}")
        return value

    def remove_mcp_server(self, name: str, *, scope: str = "user", root_dir: str | None = None) -> MCPServersPayload:
        """Remove *name* from the selected settings scope."""
        resolved_scope = self._normalize_mcp_scope(scope)
        if resolved_scope == "project" and (not root_dir or not root_dir.strip()):
            raise HTTPException(status_code=400, detail="Project MCP servers require root_dir")
        source = "project" if resolved_scope == "project" else "user"
        source_settings = self._settings_service.get_settings_for_source(source, workspace_root=root_dir)
        current_servers = source_settings.get("mcpServers")
        if not isinstance(current_servers, dict) or name not in current_servers:
            raise HTTPException(
                status_code=403,
                detail=f"Server {name!r} is not in {resolved_scope} settings and cannot be removed via the API.",
            )
        updated_servers = dict(current_servers)
        del updated_servers[name]
        self._settings_service.write_settings_for_source(
            source,
            {"mcpServers": updated_servers},
            workspace_root=root_dir,
        )
        if resolved_scope == "user":
            self._mcp_servers = self._mcp_servers_for()
        return self.list_mcp_servers(root_dir=root_dir)

    def get_mcp_json_config(self, *, scope: str = "user", root_dir: str | None = None) -> MCPJSONConfigPayload:
        resolved_scope = self._normalize_mcp_scope(scope)
        if resolved_scope == "project" and (not root_dir or not root_dir.strip()):
            raise HTTPException(status_code=400, detail="Project MCP config requires root_dir")
        source = "project" if resolved_scope == "project" else "user"
        path = self._settings_service.get_settings_file_path(source, workspace_root=root_dir)
        data = self._settings_service.get_settings_for_source(source, workspace_root=root_dir)
        mcp_servers = data.get("mcpServers") if isinstance(data.get("mcpServers"), dict) else {}
        return MCPJSONConfigPayload(
            path=str(path),
            content=json.dumps({"mcpServers": mcp_servers}, indent=2, ensure_ascii=False),
            scope=resolved_scope,
        )

    def update_mcp_json_config(
        self,
        body: MCPJSONConfigInput,
        *,
        scope: str = "user",
        root_dir: str | None = None,
    ) -> MCPJSONConfigPayload:
        resolved_scope = self._normalize_mcp_scope(scope)
        if resolved_scope == "project" and (not root_dir or not root_dir.strip()):
            raise HTTPException(status_code=400, detail="Project MCP config requires root_dir")
        try:
            parsed = json.loads(body.content)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="MCP config must be a JSON object.")
        mcp_servers = parsed.get("mcpServers")
        if mcp_servers is None:
            mcp_servers = {}
        if not isinstance(mcp_servers, dict):
            raise HTTPException(status_code=422, detail="mcpServers must be a JSON object.")
        validation = self._settings_service.validate_settings_content({"mcpServers": mcp_servers})
        if not validation.is_valid:
            raise HTTPException(status_code=422, detail="; ".join(validation.errors))
        source = "project" if resolved_scope == "project" else "user"
        self._settings_service.update_settings_for_source(
            source,
            {"mcpServers": mcp_servers},
            workspace_root=root_dir,
        )
        if resolved_scope == "user":
            self._mcp_servers = self._mcp_servers_for()
        return self.get_mcp_json_config(scope=resolved_scope, root_dir=root_dir)

    def list_connections(self, *, owner_user_id: str, root_dir: str | None = None) -> ConnectionListPayload:
        service = self._connection_service(root_dir)
        records = service.list_effective_connections(owner_user_id=owner_user_id)
        legacy_service = self._legacy_project_connection_service(root_dir)
        if legacy_service is not None:
            seen_ids = {item.id for item in records}
            records.extend(
                item
                for item in legacy_service.list_connections(owner_user_id=owner_user_id)
                if item.id not in seen_ids
            )
        connections = [
            ConnectionPayload(
                id=item.id,
                provider=item.provider,
                account_label=item.account_label,
                status=item.status,
                capabilities=item.capabilities,
                scopes=item.scopes,
                auth_type=item.auth_type,
                tools_enabled=item.tools_enabled,
                created_at=item.created_at,
                updated_at=item.updated_at,
                last_refresh_at=item.last_refresh_at,
                last_error=item.last_error,
                scope="project" if item.project_key != "user" else "user",
                effective=True,
            )
            for item in records
        ]
        return ConnectionListPayload(
            project_key=service.project_key,
            mode="project" if root_dir and root_dir.strip() else "general",
            connections=connections,
        )

    def begin_connection_authorization(
        self,
        *,
        root_dir: str | None = None,
        provider: str,
        owner_user_id: str,
        body: ConnectionAuthorizationInput,
    ) -> ConnectionAuthorizationPayload:
        service = self._connection_service(root_dir)
        started = service.begin_authorization(
            provider=self._validate_provider(provider),  # type: ignore[arg-type]
            owner_user_id=owner_user_id,
            redirect_to=body.redirect_to,
        )
        return ConnectionAuthorizationPayload(
            provider=started.provider,
            authorization_url=started.authorization_url,
            state=started.state,
        )

    def test_connection(self, *, connection_id: str, owner_user_id: str, root_dir: str | None = None) -> ConnectionTestPayload:
        try:
            payload = self._connection_service(root_dir).test_connection(
                connection_id=connection_id,
                owner_user_id=owner_user_id,
            )
        except HTTPException as exc:
            legacy_service = self._legacy_project_connection_service(root_dir)
            if exc.status_code != 404 or legacy_service is None:
                raise
            payload = legacy_service.test_connection(connection_id=connection_id, owner_user_id=owner_user_id)
        return ConnectionTestPayload(
            ok=bool(payload.get("ok")),
            provider=str(payload.get("provider", "")),
            label=str(payload.get("label")) if payload.get("label") is not None else None,
        )

    def delete_connection(self, *, connection_id: str, owner_user_id: str, root_dir: str | None = None) -> dict[str, bool]:
        deleted = self._connection_service(root_dir).revoke_connection(
            connection_id=connection_id,
            owner_user_id=owner_user_id,
        )
        if not deleted:
            legacy_service = self._legacy_project_connection_service(root_dir)
            deleted = bool(
                legacy_service
                and legacy_service.revoke_connection(connection_id=connection_id, owner_user_id=owner_user_id)
            )
        if not deleted:
            raise HTTPException(status_code=404, detail="Connection not found.")
        return {"ok": True}

    def update_connection_tools(
        self,
        *,
        root_dir: str | None = None,
        connection_id: str,
        owner_user_id: str,
        body: ConnectionToolsInput,
    ) -> ConnectionPayload:
        try:
            item = self._connection_service(root_dir).set_tools_enabled(
                connection_id=connection_id,
                owner_user_id=owner_user_id,
                enabled=body.enabled,
            )
        except HTTPException as exc:
            legacy_service = self._legacy_project_connection_service(root_dir)
            if exc.status_code != 404 or legacy_service is None:
                raise
            item = legacy_service.set_tools_enabled(
                connection_id=connection_id,
                owner_user_id=owner_user_id,
                enabled=body.enabled,
            )
        return ConnectionPayload(
            id=item.id,
            provider=item.provider,
            account_label=item.account_label,
            status=item.status,
            capabilities=item.capabilities,
            scopes=item.scopes,
            auth_type=item.auth_type,
            tools_enabled=item.tools_enabled,
            created_at=item.created_at,
            updated_at=item.updated_at,
            last_refresh_at=item.last_refresh_at,
            last_error=item.last_error,
            scope="project" if item.project_key != "user" else "user",
            effective=True,
        )

    def get_connection_scopes(self, *, connection_id: str, owner_user_id: str, root_dir: str | None = None) -> ConnectionScopesPayload:
        try:
            scopes = self._connection_service(root_dir).get_connection_scopes(
                connection_id=connection_id,
                owner_user_id=owner_user_id,
            )
        except HTTPException as exc:
            legacy_service = self._legacy_project_connection_service(root_dir)
            if exc.status_code != 404 or legacy_service is None:
                raise
            scopes = legacy_service.get_connection_scopes(connection_id=connection_id, owner_user_id=owner_user_id)
        return ConnectionScopesPayload(id=connection_id, scopes=scopes)

    @staticmethod
    def _json_items(raw: str, key: str) -> list[dict[str, Any]]:
        payload = json.loads(raw)
        items = payload.get(key, [])
        return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []

    def _validate_archive(self, archive_path: Path) -> _ValidatedArchive:
        warnings: list[str] = []
        try:
            archive = zipfile.ZipFile(archive_path)
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Skill package is not a valid zip archive") from exc

        with archive:
            skill_entries: list[PurePosixPath] = []
            for info in archive.infolist():
                path = PurePosixPath(info.filename.replace("\\", "/"))
                self._validate_archive_entry(path, info)
                if path.name == "SKILL.md":
                    skill_entries.append(path)

            if len(skill_entries) != 1:
                raise HTTPException(status_code=400, detail="Skill package must contain exactly one SKILL.md")

            skill_path = skill_entries[0]
            base_prefix = "" if len(skill_path.parts) == 1 else skill_path.parts[0]
            if base_prefix and len({entry.parts[0] for entry in skill_entries if entry.parts}) != 1:
                raise HTTPException(status_code=400, detail="SKILL.md must be at archive root or inside one top-level folder")
            raw = archive.read(str(skill_path)).decode("utf-8")
            frontmatter, _body = strip_frontmatter(raw)
            name = str(frontmatter.get("name", "")).strip() if frontmatter else ""
            description = str(frontmatter.get("description", "")).strip() if frontmatter else ""
            if not name or not description:
                raise HTTPException(status_code=400, detail="Skill SKILL.md requires name and description frontmatter")
            install_dir_name = self._safe_install_name(name)
            if install_dir_name != name:
                warnings.append(f"Skill install directory was normalized to '{install_dir_name}'.")
            return _ValidatedArchive(
                archive_path=archive_path,
                base_prefix=base_prefix,
                skill_name=name,
                install_dir_name=install_dir_name,
                warnings=warnings,
            )

    @staticmethod
    def _validate_archive_entry(path: PurePosixPath, info: zipfile.ZipInfo) -> None:
        if path.is_absolute() or ".." in path.parts or not str(path):
            raise HTTPException(status_code=400, detail=f"Unsafe path in skill package: {info.filename}")
        if any(part.startswith(".") for part in path.parts if part not in {"."}):
            raise HTTPException(status_code=400, detail=f"Hidden paths are not allowed in skill packages: {info.filename}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise HTTPException(status_code=400, detail=f"Symlinks are not allowed in skill packages: {info.filename}")

    @staticmethod
    def _safe_install_name(name: str) -> str:
        value = _SAFE_DIR_RE.sub("-", name.strip().lower()).strip(".-_")
        return value or "skill"

    @staticmethod
    def _extract_archive(validated: _ValidatedArchive, target: Path) -> None:
        with zipfile.ZipFile(validated.archive_path) as archive:
            for info in archive.infolist():
                source_path = PurePosixPath(info.filename.replace("\\", "/"))
                if info.is_dir():
                    continue
                if validated.base_prefix:
                    if not source_path.parts or source_path.parts[0] != validated.base_prefix:
                        continue
                    relative = PurePosixPath(*source_path.parts[1:])
                else:
                    relative = source_path
                if not str(relative):
                    continue
                destination = (target / Path(*relative.parts)).resolve()
                try:
                    destination.relative_to(target.resolve())
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=f"Unsafe path in skill package: {info.filename}") from exc
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
