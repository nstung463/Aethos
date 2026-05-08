from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from src.app.modules.extensions.schemas import ConnectionAuthorizationInput, MCPJSONConfigInput, MCPServerInput
from src.app.modules.extensions.service import ExtensionsService
from src.app.services.connections import ConnectionRecord
from src.config import MCPServerSpec
from src.app.modules.extensions.router import _connection_callback_html, _validated_redirect_to_or_none


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


def test_add_mcp_server_persists_to_mcp_json(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    payload = service.add_mcp_server(
        MCPServerInput(
            name="github",
            transport="stdio",
            command="cmd",
            args=["/c", "npx"],
            instructions="Use for repo tasks.",
        )
    )

    assert payload.servers[0].name == "github"
    data = json.loads((workspace / ".mcp.json").read_text(encoding="utf-8"))
    assert "github" in data["mcpServers"]
    assert "transport" not in data["mcpServers"]["github"]


def test_get_and_update_mcp_json_config(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    initial = service.get_mcp_json_config()
    assert initial.path.endswith(".mcp.json")
    assert "\"mcpServers\"" in initial.content

    updated = service.update_mcp_json_config(
        MCPJSONConfigInput(
            content=json.dumps({"mcpServers": {"docs": {"command": "uvx", "args": ["docs-server"]}}}),
        )
    )

    assert "\"docs\"" in updated.content
    assert json.loads((workspace / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["docs"]["command"] == "uvx"


def test_list_skills_does_not_include_generated_aliases(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_ethos_skill_root=workspace / "__no_user_ethos__")
    skill_dir = workspace / ".ethos" / "skills" / "spreadsheets"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Spreadsheets\ndescription: Create spreadsheet files (.xlsx, .csv)\n---\nBody",
        encoding="utf-8",
    )

    payload = service.list_skills(root_dir=str(workspace))

    assert payload.skills[0].name == "Spreadsheets"
    assert payload.skills[0].aliases == []


class _FakeConnectionService:
    project_key = "project-key"

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def list_connections(self, *, owner_user_id: str) -> list[ConnectionRecord]:
        assert owner_user_id == "user-a"
        return [
            ConnectionRecord(
                id="conn_1",
                provider="google-gmail",
                owner_user_id=owner_user_id,
                project_key=self.project_key,
                account_label="work@example.com",
                status="active",
                capabilities=["gmail"],
                scopes=["scope:a"],
                auth_type="oauth2",
                tools_enabled=True,
                created_at=1,
                updated_at=2,
                last_refresh_at=2,
                last_error=None,
            )
        ]

    def begin_authorization(self, *, provider: str, owner_user_id: str, redirect_to: str | None = None):
        assert provider == "google-gmail"
        assert owner_user_id == "user-a"
        assert redirect_to == "http://localhost/ui"
        from src.app.services.connections import AuthorizationStart

        return AuthorizationStart(provider="google-gmail", authorization_url="https://accounts.google.com/o/oauth2/auth", state="oauth-state")


def test_list_connections_maps_payload(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> None:
    monkeypatch.setattr("src.app.modules.extensions.service.ConnectionService", _FakeConnectionService)
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    payload = service.list_connections(root_dir=str(workspace), owner_user_id="user-a")

    assert payload.project_key == "project-key"
    assert payload.connections[0].provider == "google-gmail"
    assert payload.connections[0].account_label == "work@example.com"


def test_begin_connection_authorization_validates_provider(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> None:
    monkeypatch.setattr("src.app.modules.extensions.service.ConnectionService", _FakeConnectionService)
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    payload = service.begin_connection_authorization(
        root_dir=str(workspace),
        provider="google-gmail",
        owner_user_id="user-a",
        body=ConnectionAuthorizationInput(redirect_to="http://localhost/ui"),
    )

    assert payload.provider == "google-gmail"
    assert payload.state == "oauth-state"

    with pytest.raises(HTTPException) as exc:
        service.begin_connection_authorization(
            root_dir=str(workspace),
            provider="dropbox",
            owner_user_id="user-a",
            body=ConnectionAuthorizationInput(redirect_to=None),
        )
    assert exc.value.status_code == 400


def _request_with_headers(headers: dict[str, str]) -> Request:
    raw_headers = [(key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in headers.items()]
    return Request({"type": "http", "headers": raw_headers})


def test_validated_redirect_to_allows_same_origin_absolute_url() -> None:
    request = _request_with_headers({"origin": "http://localhost:5173"})

    result = _validated_redirect_to_or_none(request, "http://localhost:5173/settings/extensions")

    assert result == "http://localhost:5173/settings/extensions"


def test_validated_redirect_to_rejects_cross_origin_url() -> None:
    request = _request_with_headers({"origin": "http://localhost:5173"})

    with pytest.raises(HTTPException) as exc:
        _validated_redirect_to_or_none(request, "https://evil.example/steal")

    assert exc.value.status_code == 400


def test_validated_redirect_to_allows_root_relative_path() -> None:
    request = _request_with_headers({})

    assert _validated_redirect_to_or_none(request, "/settings/extensions") == "/settings/extensions"


def test_connection_callback_html_escapes_account_label() -> None:
    html_doc = _connection_callback_html(
        account_label='<img src=x onerror="alert(1)">',
        redirect_to="http://localhost:3000/app",
    )

    assert '<img src=x onerror="alert(1)">' not in html_doc
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in html_doc
    assert 'postMessage({ type: \'ethos-connections-updated\' }, window.location.origin)' in html_doc
