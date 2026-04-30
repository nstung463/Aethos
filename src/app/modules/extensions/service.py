"""Service layer for project skills and MCP extension metadata."""

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
from src.ai.skills.registry import SkillDefinition, SkillNotFoundError, SkillRegistry, strip_frontmatter
from src.ai.tools.mcp import MCPRuntime
from src.app.modules.extensions.schemas import (
    MCPInstructionsPayload,
    MCPServerPayload,
    MCPServersPayload,
    SkillImportPayload,
    SkillListPayload,
    SkillPayload,
)
from src.config import MCPServerSpec, get_mcp_servers

_MAX_SKILL_PACKAGE_BYTES = 25 * 1024 * 1024
_SKILL_PACKAGE_SUFFIXES = {".zip", ".skill"}
_SAFE_DIR_RE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True)
class _ValidatedArchive:
    archive_path: Path
    base_prefix: str
    skill_name: str
    install_dir_name: str
    warnings: list[str]


def _safe_root(root_dir: str) -> Path:
    root = Path(root_dir).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Project root_dir is invalid: {root}")
    return root


def _skill_to_payload(skill: SkillDefinition, *, body: str | None = None, project_root: Path | None = None) -> SkillPayload:
    can_delete = False
    if project_root is not None and skill.path is not None and skill.source == "ethos":
        ethos_root = (project_root / ".ethos" / "skills").resolve()
        try:
            skill.path.resolve().relative_to(ethos_root)
            can_delete = True
        except ValueError:
            can_delete = False
    return SkillPayload(
        name=skill.name,
        description=skill.description,
        source=skill.source,
        loaded_from=skill.loaded_from,
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
    )


def _is_mcp_skill_prompt(item: dict[str, Any]) -> bool:
    if item.get("isSkill") is True:
        return True
    if item.get("kind") == "skill" or item.get("type") == "skill":
        return True
    metadata = item.get("_meta") or item.get("metadata") or {}
    if isinstance(metadata, dict):
        if metadata.get("skill") is True or metadata.get("claude_code_skill") is True:
            return True
        if metadata.get("ethos.skill") is True:
            return True
    tags = item.get("tags") or item.get("labels") or ()
    if isinstance(tags, (list, tuple, set)):
        return "skill" in {str(tag).lower() for tag in tags}
    return False


class ExtensionsService:
    def __init__(self, mcp_servers: list[MCPServerSpec] | None = None) -> None:
        self._mcp_servers = mcp_servers if mcp_servers is not None else get_mcp_servers()

    def list_skills(self, *, root_dir: str) -> SkillListPayload:
        root = _safe_root(root_dir)
        registry = SkillRegistry(root, mcp_runtime=MCPRuntime(self._mcp_servers))
        skills = [_skill_to_payload(skill, project_root=root) for skill in registry.discover()]
        return SkillListPayload(root_dir=str(root), skills=skills)

    def get_skill(self, *, root_dir: str, name: str) -> SkillPayload:
        root = _safe_root(root_dir)
        registry = SkillRegistry(root, mcp_runtime=MCPRuntime(self._mcp_servers))
        try:
            skill = registry.get(name)
        except SkillNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        body = None
        if skill.loaded_from == "local" and skill.path is not None:
            _frontmatter, body = strip_frontmatter(skill.path.read_text(encoding="utf-8"))
        return _skill_to_payload(skill, body=body, project_root=root)

    async def import_skill(
        self,
        *,
        root_dir: str,
        upload: UploadFile,
        overwrite: bool = False,
    ) -> SkillImportPayload:
        root = _safe_root(root_dir)
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
            target_root = root / ".ethos" / "skills"
            target = (target_root / validated.install_dir_name).resolve()
            if target.exists() and not overwrite:
                raise HTTPException(status_code=409, detail=f"Skill '{validated.install_dir_name}' already exists")

            target_root.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(target)
            target.mkdir(parents=True)
            self._extract_archive(validated, target)

            registry = SkillRegistry(root)
            skill = registry.get(validated.skill_name)
            return SkillImportPayload(
                skill=_skill_to_payload(skill, project_root=root),
                warnings=validated.warnings,
            )
        finally:
            archive_path.unlink(missing_ok=True)

    def delete_skill(self, *, root_dir: str, name: str) -> dict[str, bool]:
        root = _safe_root(root_dir)
        registry = SkillRegistry(root, mcp_runtime=MCPRuntime(self._mcp_servers))
        try:
            skill = registry.get(name)
        except SkillNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        ethos_root = (root / ".ethos" / "skills").resolve()
        if skill.source != "ethos" or skill.root_dir is None:
            raise HTTPException(status_code=403, detail="Only .ethos project skills can be deleted")
        target = skill.root_dir.resolve()
        try:
            target.relative_to(ethos_root)
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="Skill path is outside .ethos/skills") from exc
        shutil.rmtree(target)
        return {"ok": True}

    def list_mcp_servers(self) -> MCPServersPayload:
        runtime = MCPRuntime(self._mcp_servers)
        servers: list[MCPServerPayload] = []
        for spec in self._mcp_servers:
            tools: list[dict[str, Any]] = []
            resources: list[dict[str, Any]] = []
            prompts: list[dict[str, Any]] = []
            error = None
            status = "ok"
            try:
                tools = self._json_items(runtime.list_tools(spec.name), "tools")
                resources = self._json_items(runtime.list_resources(spec.name), "resources")
                prompts = self._json_items(runtime.list_prompts(spec.name), "prompts")
            except Exception as exc:
                status = "error"
                error = str(exc)
            skill_prompts = [item for item in prompts if _is_mcp_skill_prompt(item)]
            servers.append(
                MCPServerPayload(
                    name=spec.name,
                    transport=str(spec.connection.get("transport", "")) or None,
                    url=str(spec.connection.get("url", "")) or None,
                    auth_url=spec.auth_url,
                    has_instructions=bool(spec.instructions),
                    status=status,
                    error=error,
                    tools=tools,
                    resources=resources,
                    prompts=prompts,
                    skill_prompts=skill_prompts,
                )
            )
        return MCPServersPayload(servers=servers)

    def get_mcp_instructions(self) -> MCPInstructionsPayload:
        return MCPInstructionsPayload(instructions=build_mcp_instructions_section(self._mcp_servers))

    def refresh_mcp(self) -> MCPServersPayload:
        return self.list_mcp_servers()

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
                destination.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, destination.open("wb") as dest:
                    shutil.copyfileobj(source, dest)
