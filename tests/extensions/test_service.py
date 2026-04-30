from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile

from src.app.modules.extensions.service import ExtensionsService
from src.config import MCPServerSpec


def _package(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _skill_md(name: str = "review") -> str:
    return f"---\nname: {name}\ndescription: Review code\n---\nFollow the workflow.\n"


def _upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


@pytest.mark.asyncio
async def test_import_skill_package_installs_to_ethos_skills(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_ethos_skill_root=workspace / "__no_user_ethos__")

    result = await service.import_skill(
        root_dir=str(workspace),
        upload=_upload("review.zip", _package({"SKILL.md": _skill_md()})),
    )

    assert result.skill.name == "review"
    assert result.skill.source == "ethos_project"
    assert (workspace / ".ethos" / "skills" / "review" / "SKILL.md").exists()
    assert service.list_skills(root_dir=str(workspace)).skills[0].name == "review"


@pytest.mark.asyncio
async def test_import_skill_package_rejects_path_traversal(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_ethos_skill_root=workspace / "__no_user_ethos__")

    with pytest.raises(HTTPException) as exc:
        await service.import_skill(
            root_dir=str(workspace),
            upload=_upload("bad.zip", _package({"../SKILL.md": _skill_md()})),
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_import_skill_package_rejects_duplicate_without_overwrite(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_ethos_skill_root=workspace / "__no_user_ethos__")
    package = _package({"SKILL.md": _skill_md()})
    await service.import_skill(root_dir=str(workspace), upload=_upload("review.zip", package))

    with pytest.raises(HTTPException) as exc:
        await service.import_skill(root_dir=str(workspace), upload=_upload("review.skill", package))

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_import_skill_package_rejects_invalid_frontmatter(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_ethos_skill_root=workspace / "__no_user_ethos__")

    with pytest.raises(HTTPException) as exc:
        await service.import_skill(
            root_dir=str(workspace),
            upload=_upload("bad.zip", _package({"SKILL.md": "---\nname: bad\n---\nBody"})),
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_skill_only_allows_ethos_source(workspace: Path) -> None:
    user_root = workspace / "__user_ethos__" / ".ethos" / "skills"
    service = ExtensionsService(mcp_servers=[], user_ethos_skill_root=user_root)
    await service.import_skill(
        root_dir=str(workspace),
        upload=_upload("review.zip", _package({"SKILL.md": _skill_md()})),
    )
    user_skill = user_root / "native"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text(
        "---\nname: native\ndescription: Native skill\n---\nBody",
        encoding="utf-8",
    )

    service.delete_skill(root_dir=str(workspace), name="review")
    assert not (workspace / ".ethos" / "skills" / "review").exists()
    with pytest.raises(HTTPException) as exc:
        service.delete_skill(root_dir=str(workspace), name="native")
    assert exc.value.status_code == 403


class _FakeMCPRuntime:
    def __init__(self, servers: list[MCPServerSpec]) -> None:
        self.servers = servers

    def list_tools(self, server: str | None = None) -> str:
        return json.dumps({"tools": [{"name": "ping", "server": server}]})

    def list_resources(self, server: str | None = None) -> str:
        return json.dumps({"resources": []})

    def list_prompts(self, server: str | None = None) -> str:
        return json.dumps(
            {
                "prompts": [
                    {"name": "generic", "server": server, "description": "Plain prompt"},
                    {"name": "review", "server": server, "description": "Skill prompt", "_meta": {"skill": True}},
                ]
            }
        )


def test_mcp_servers_expose_only_marked_skill_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.app.modules.extensions.service.MCPRuntime", _FakeMCPRuntime)
    service = ExtensionsService(
        mcp_servers=[MCPServerSpec(name="docs", connection={"transport": "stdio"}, instructions="Use docs")],
        user_ethos_skill_root=Path("__no_user_ethos__"),
    )

    payload = service.list_mcp_servers()

    assert [prompt["name"] for prompt in payload.servers[0].prompts] == ["generic", "review"]
    assert [prompt["name"] for prompt in payload.servers[0].skill_prompts] == ["review"]
