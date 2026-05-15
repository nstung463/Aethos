from __future__ import annotations

import asyncio
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from src.app.features.extensions.schemas import ConnectionAuthorizationInput, MCPJSONConfigInput, MCPServerInput
from src.app.features.extensions.service import ExtensionsService
from src.app.repositories.connection_repository import ConnectionRecord
from src.app.services.storage_paths import StoragePathsService
from src.config import MCPServerSpec


pytestmark = pytest.mark.usefixtures("disable_database")
from src.app.features.extensions.router import _connection_callback_html, _validated_redirect_to_or_none


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


def test_import_skill_package_installs_to_aethos_skills(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_aethos_skill_root=workspace / "__no_user_aethos__")

    result = asyncio.run(service.import_skill(upload=_upload("review.zip", _package({"SKILL.md": _skill_md()}))))

    assert result.skill.name == "review"
    assert result.skill.source == "aethos_user"
    assert (workspace / "__no_user_aethos__" / "review" / "SKILL.md").exists()
    assert service.list_skills().skills[0].name == "review"


def test_import_skill_package_rejects_path_traversal(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_aethos_skill_root=workspace / "__no_user_aethos__")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.import_skill(upload=_upload("bad.zip", _package({"../SKILL.md": _skill_md()}))))

    assert exc.value.status_code == 400


def test_import_skill_package_rejects_nested_path_traversal(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_aethos_skill_root=workspace / "__no_user_aethos__")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.import_skill(
                upload=_upload("bad.zip", _package({"nested/SKILL.md": _skill_md(), "nested/../escape.txt": "bad"}))
            )
        )

    assert exc.value.status_code == 400


def test_import_skill_package_rejects_duplicate_without_overwrite(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_aethos_skill_root=workspace / "__no_user_aethos__")
    package = _package({"SKILL.md": _skill_md()})
    asyncio.run(service.import_skill(upload=_upload("review.zip", package)))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.import_skill(upload=_upload("review.skill", package)))

    assert exc.value.status_code == 409


def test_import_skill_package_can_install_project_skill(workspace: Path) -> None:
    user_root = workspace / "__user_aethos__" / "skills"
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace), user_aethos_skill_root=user_root)

    result = asyncio.run(
        service.import_skill(
            upload=_upload("review.zip", _package({"SKILL.md": _skill_md("project-review")})),
            scope="project",
            root_dir=str(workspace),
        )
    )

    assert result.skill.source == "aethos_project"
    assert (workspace / ".aethos" / "skills" / "project-review" / "SKILL.md").exists()
    assert service.list_skills().skills == []
    assert service.list_skills(root_dir=str(workspace)).skills[0].name == "project-review"


def test_delete_skill_can_remove_project_skill(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))
    asyncio.run(
        service.import_skill(
            upload=_upload("review.zip", _package({"SKILL.md": _skill_md("project-review")})),
            scope="project",
            root_dir=str(workspace),
        )
    )

    result = service.delete_skill(name="project-review", root_dir=str(workspace))

    assert result == {"ok": True}
    assert service.list_skills(root_dir=str(workspace)).skills == []


def test_import_skill_package_rejects_project_scope_without_root_dir(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            service.import_skill(
                upload=_upload("review.zip", _package({"SKILL.md": _skill_md()})),
                scope="project",
            )
        )

    assert exc.value.status_code == 400


def test_import_skill_package_rejects_invalid_frontmatter(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], user_aethos_skill_root=workspace / "__no_user_aethos__")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.import_skill(upload=_upload("bad.zip", _package({"SKILL.md": "---\nname: bad\n---\nBody"}))))

    assert exc.value.status_code == 400


def test_delete_skill_only_allows_aethos_source(workspace: Path) -> None:
    user_root = workspace / "__user_aethos__" / ".aethos" / "skills"
    service = ExtensionsService(mcp_servers=[], user_aethos_skill_root=user_root)
    asyncio.run(service.import_skill(upload=_upload("review.zip", _package({"SKILL.md": _skill_md()}))))
    user_skill = user_root / "native"
    user_skill.mkdir(parents=True)
    (user_skill / "SKILL.md").write_text(
        "---\nname: native\ndescription: Native skill\n---\nBody",
        encoding="utf-8",
    )

    service.delete_skill(name="review")
    assert not (user_root / "review").exists()
    service.delete_skill(name="native")
    assert not user_skill.exists()


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


class _FakePartialMCPRuntime(_FakeMCPRuntime):
    def list_resources(self, server: str | None = None) -> str:
        raise RuntimeError("resource listing not supported")

    def list_prompts(self, server: str | None = None) -> str:
        raise RuntimeError("prompt listing not supported")


def test_mcp_servers_expose_only_marked_skill_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.app.features.extensions.service.MCPRuntime", _FakeMCPRuntime)
    service = ExtensionsService(
        mcp_servers=[MCPServerSpec(name="docs", connection={"transport": "stdio"}, instructions="Use docs")],
        user_aethos_skill_root=Path("__no_user_aethos__"),
    )

    payload = service.list_mcp_servers()

    assert [prompt["name"] for prompt in payload.servers[0].prompts] == ["generic", "review"]
    assert [prompt["name"] for prompt in payload.servers[0].skill_prompts] == ["review"]


def test_mcp_servers_mark_partial_when_non_tool_sections_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.app.features.extensions.service.MCPRuntime", _FakePartialMCPRuntime)
    service = ExtensionsService(
        mcp_servers=[MCPServerSpec(name="docs", connection={"transport": "stdio"}, instructions="Use docs")],
        user_aethos_skill_root=Path("__no_user_aethos__"),
    )

    payload = service.list_mcp_servers()

    assert payload.servers[0].status == "partial"
    assert payload.servers[0].tools[0]["name"] == "ping"
    assert payload.servers[0].resources == []
    assert payload.servers[0].prompts == []
    assert "resources:" in (payload.servers[0].error or "")
    assert "prompts:" in (payload.servers[0].error or "")


def test_add_mcp_server_persists_to_mcp_json(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    service.add_mcp_server(
        MCPServerInput(
            name="github",
            transport="stdio",
            command="cmd",
            args=["/c", "npx"],
            instructions="Use for repo tasks.",
        )
    )

    data = json.loads((workspace.parent / "home-aethos" / "settings.json").read_text(encoding="utf-8"))
    assert "github" in data["mcpServers"]
    assert data["mcpServers"]["github"]["transport"] == "stdio"


def test_add_mcp_server_can_persist_to_project_settings(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    payload = service.add_mcp_server(
        MCPServerInput(
            name="powerbi",
            transport="stdio",
            command="powerbi-modeling-mcp.exe",
            instructions="Use for project analytics.",
            scope="project",
        ),
        root_dir=str(workspace),
    )

    assert payload.servers[0].name == "powerbi"
    data = json.loads((workspace / ".aethos" / "settings.json").read_text(encoding="utf-8"))
    assert "powerbi" in data["mcpServers"]
    assert data["mcpServers"]["powerbi"]["command"] == "powerbi-modeling-mcp.exe"


def test_get_and_update_mcp_json_config(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    initial = service.get_mcp_json_config()
    assert initial.path.endswith("settings.json")
    assert "\"mcpServers\"" in initial.content

    updated = service.update_mcp_json_config(
        MCPJSONConfigInput(
            content=json.dumps({"mcpServers": {"docs": {"command": "uvx", "args": ["docs-server"]}}}),
        )
    )

    assert "\"docs\"" in updated.content
    assert json.loads((workspace.parent / "home-aethos" / "settings.json").read_text(encoding="utf-8"))["mcpServers"]["docs"]["command"] == "uvx"


def test_get_and_update_project_mcp_json_config(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    initial = service.get_mcp_json_config(scope="project", root_dir=str(workspace))
    assert initial.path.endswith(".aethos\\settings.json")
    assert initial.scope == "project"

    updated = service.update_mcp_json_config(
        MCPJSONConfigInput(
            content=json.dumps({"mcpServers": {"docs": {"command": "uvx", "args": ["project-docs-server"]}}}),
        ),
        scope="project",
        root_dir=str(workspace),
    )

    assert updated.scope == "project"
    assert "\"docs\"" in updated.content
    assert json.loads((workspace / ".aethos" / "settings.json").read_text(encoding="utf-8"))["mcpServers"]["docs"]["command"] == "uvx"


def test_remove_project_mcp_server_updates_project_settings(workspace: Path) -> None:
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))
    service.add_mcp_server(
        MCPServerInput(
            name="docs",
            transport="stdio",
            command="uvx",
            scope="project",
        ),
        root_dir=str(workspace),
    )

    payload = service.remove_mcp_server("docs", scope="project", root_dir=str(workspace))

    data = json.loads((workspace / ".aethos" / "settings.json").read_text(encoding="utf-8"))
    assert data["mcpServers"] == {}
    assert all(server.name != "docs" for server in payload.servers)


def test_list_skills_does_not_include_generated_aliases(workspace: Path) -> None:
    user_root = workspace / "__no_user_aethos__"
    service = ExtensionsService(mcp_servers=[], user_aethos_skill_root=user_root)
    skill_dir = user_root / "spreadsheets"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: Spreadsheets\ndescription: Create spreadsheet files (.xlsx, .csv)\n---\nBody",
        encoding="utf-8",
    )

    payload = service.list_skills()

    assert payload.skills[0].name == "Spreadsheets"
    assert payload.skills[0].aliases == []


class _FakeConnectionService:
    project_key = "user"
    scope = "user"

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def list_effective_connections(self, *, owner_user_id: str) -> list[ConnectionRecord]:
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

    def list_connections(self, *, owner_user_id: str) -> list[ConnectionRecord]:
        assert owner_user_id == "user-a"
        return []

    def begin_authorization(self, *, provider: str, owner_user_id: str, redirect_to: str | None = None):
        assert provider == "google-gmail"
        assert owner_user_id == "user-a"
        assert redirect_to == "http://localhost/ui"
        from src.app.features.extensions.connections_service import AuthorizationStart

        return AuthorizationStart(provider="google-gmail", authorization_url="https://accounts.google.com/o/oauth2/auth", state="oauth-state")


def test_list_connections_maps_payload(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> None:
    monkeypatch.setattr("src.app.features.extensions.service.ConnectionService", _FakeConnectionService)
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    payload = service.list_connections(owner_user_id="user-a", root_dir=str(workspace))

    assert payload.project_key == "user"
    assert payload.mode == "project"
    assert payload.connections[0].provider == "google-gmail"
    assert payload.connections[0].account_label == "work@example.com"
    assert payload.connections[0].scope == "user"
    assert payload.connections[0].effective is True


def test_list_connections_uses_effective_service_results_only(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> None:
    monkeypatch.setattr("src.app.features.extensions.service.ConnectionService", _FakeConnectionService)
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    payload = service.list_connections(owner_user_id="user-a", root_dir=str(workspace))

    assert payload.project_key == "user"
    assert [item.id for item in payload.connections] == ["conn_1"]
    assert payload.connections[0].scope == "user"


def test_begin_connection_authorization_validates_provider(monkeypatch: pytest.MonkeyPatch, workspace: Path) -> None:
    monkeypatch.setattr("src.app.features.extensions.service.ConnectionService", _FakeConnectionService)
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    payload = service.begin_connection_authorization(
        provider="google-gmail",
        owner_user_id="user-a",
        body=ConnectionAuthorizationInput(redirect_to="http://localhost/ui"),
    )

    assert payload.provider == "google-gmail"
    assert payload.state == "oauth-state"

    with pytest.raises(HTTPException) as exc:
        service.begin_connection_authorization(
            provider="dropbox",
            owner_user_id="user-a",
            body=ConnectionAuthorizationInput(redirect_to=None),
        )
    assert exc.value.status_code == 400


def test_list_skills_marks_user_skill_overridden_by_project(workspace: Path) -> None:
    user_root = workspace / "__user_aethos__" / "skills"
    project_root = workspace / ".aethos" / "skills"
    for root, description in (
        (user_root / "git-helper", "User skill"),
        (project_root / "git-helper", "Project override"),
    ):
        root.mkdir(parents=True, exist_ok=True)
        (root / "SKILL.md").write_text(
            f"---\nname: git-helper\ndescription: {description}\n---\nBody",
            encoding="utf-8",
        )

    service = ExtensionsService(mcp_servers=[], workspace=str(workspace), user_aethos_skill_root=user_root)

    general = service.list_skills()
    project = service.list_skills(root_dir=str(workspace))

    assert [skill.source for skill in general.skills if skill.name == "git-helper"] == ["aethos_user"]
    assert [skill.source for skill in project.skills if skill.name == "git-helper"] == ["aethos_project"]
    assert all(not skill.overridden_by_project for skill in general.skills)


def test_project_override_names_uses_frontmatter_name_not_directory_name(workspace: Path) -> None:
    project_root = workspace / ".aethos" / "skills" / "folder-name-only"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "SKILL.md").write_text(
        "---\nname: git-helper\ndescription: Project override\n---\nBody",
        encoding="utf-8",
    )
    service = ExtensionsService(mcp_servers=[], workspace=str(workspace))

    assert service._project_override_names(str(workspace)) == {"git-helper"}


def test_list_mcp_servers_marks_managed_scope_in_general_mode(workspace: Path) -> None:
    managed_settings_dir = workspace.parent / "managed-settings"
    managed_settings_dir.mkdir(parents=True, exist_ok=True)
    (managed_settings_dir / "managed-settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "managed-docs": {
                        "transport": "http",
                        "url": "https://managed.example/mcp",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    service = ExtensionsService(mcp_servers=None, workspace=str(workspace))

    payload = service.list_mcp_servers()

    assert payload.servers[0].name == "managed-docs"
    assert payload.servers[0].scope == "managed"


def _request_with_headers(headers: dict[str, str]) -> Request:
    raw_headers = [(key.lower().encode("latin-1"), value.encode("latin-1")) for key, value in headers.items()]
    return Request({"type": "http", "headers": raw_headers})


def test_validated_redirect_to_allows_same_origin_absolute_url() -> None:
    request = _request_with_headers({"origin": "http://localhost:3000"})

    result = _validated_redirect_to_or_none(request, "http://localhost:3000/settings/extensions")

    assert result == "http://localhost:3000/settings/extensions"


def test_validated_redirect_to_rejects_cross_origin_url() -> None:
    request = _request_with_headers({"origin": "http://localhost:3000"})

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
    assert 'postMessage({ type: \'aethos-connections-updated\' }, window.location.origin)' in html_doc

