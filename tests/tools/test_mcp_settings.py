"""Tests for MCP server management via .aethos/settings.json and .mcp.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from src.app.repositories.connection_repository import ConnectionRepository
from src.app.services.database import get_sqlalchemy_session_factory
from src.app.services.storage_paths import StoragePathsService
from src.config import (
    MCPServerSpec,
    _load_mcp_from_mcp_json,
    _load_mcp_from_settings,
    _parse_mcp_env_var,
    get_mcp_servers,
    read_mcp_json_config,
    remove_mcp_server_from_mcp_json,
    remove_mcp_server_from_settings,
    save_mcp_server_to_mcp_json,
    save_mcp_server_to_settings,
    write_mcp_json_config,
)


pytestmark = pytest.mark.usefixtures("postgres_database")


@pytest.fixture(autouse=True)
def _reset_connections_tables(postgres_database: str) -> None:
    del postgres_database
    repo = ConnectionRepository(get_sqlalchemy_session_factory())
    with repo.engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE connection_audit, connection_secrets, connections, oauth_states RESTART IDENTITY CASCADE"))


# ---------------------------------------------------------------------------
# _load_mcp_from_settings
# ---------------------------------------------------------------------------

def test_load_from_settings_http_server(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "docs": {
                        "transport": "http",
                        "url": "https://example.com/mcp",
                        "instructions": "Use for docs.",
                        "auth_url": "https://example.com/login",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = _load_mcp_from_settings(str(tmp_path))

    assert len(servers) == 1
    assert servers[0].name == "docs"
    assert servers[0].connection["transport"] == "http"
    assert servers[0].auth_url == "https://example.com/login"
    assert servers[0].instructions == "Use for docs."


def test_load_from_settings_accepts_google_workspace_http_url_oauth(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "drive": {
                        "httpUrl": "https://drivemcp.googleapis.com/mcp/v1",
                        "oauth": {
                            "enabled": True,
                            "clientId": "client-id",
                            "clientSecret": "client-secret",
                            "scopes": [
                                "https://www.googleapis.com/auth/drive.readonly",
                                "https://www.googleapis.com/auth/drive.file",
                            ],
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = _load_mcp_from_settings(str(tmp_path))

    assert len(servers) == 1
    assert servers[0].name == "drive"
    assert servers[0].connection["transport"] == "streamable_http"
    assert servers[0].connection["url"] == "https://drivemcp.googleapis.com/mcp/v1"
    assert servers[0].connection["oauth"]["enabled"] is True


def test_get_mcp_servers_filters_native_google_servers_when_tools_disabled(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "drive": {
                        "httpUrl": "https://drivemcp.googleapis.com/mcp/v1",
                        "oauth": {
                            "enabled": True,
                            "clientId": "client-id",
                            "clientSecret": "client-secret",
                            "scopes": [
                                "https://www.googleapis.com/auth/drive.readonly",
                            ],
                        },
                    },
                    "calendar": {
                        "httpUrl": "https://calendarmcp.googleapis.com/mcp/v1",
                        "oauth": {
                            "enabled": True,
                            "clientId": "client-id",
                            "clientSecret": "client-secret",
                            "scopes": [
                                "https://www.googleapis.com/auth/calendar.events.readonly",
                            ],
                        },
                    },
                    "docs": {
                        "transport": "http",
                        "url": "https://example.com/mcp",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    del user_scope_root
    repo = ConnectionRepository(get_sqlalchemy_session_factory())
    project_key = "user"
    repo.save_connection(
        connection_id=None,
        provider="google-drive",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="drive@example.com",
        status="active",
        capabilities=["drive"],
        scopes=["scope:a"],
        tools_enabled=True,
    )
    repo.save_connection(
        connection_id=None,
        provider="google-calendar",
        owner_user_id="user-a",
        project_key=project_key,
        account_label="calendar@example.com",
        status="active",
        capabilities=["calendar"],
        scopes=["scope:a"],
        tools_enabled=False,
    )

    servers = get_mcp_servers(str(tmp_path), owner_user_id="user-a")

    assert [server.name for server in servers] == ["drive", "docs"]


def test_get_mcp_servers_general_uses_user_settings_and_project_adds_overrides(tmp_path: Path) -> None:
    storage = StoragePathsService()
    user_settings_dir = storage.user_settings_dir()
    user_settings_dir.mkdir(parents=True, exist_ok=True)
    (user_settings_dir / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "slack": {
                        "transport": "http",
                        "url": "https://user.example/slack",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "docs": {
                        "transport": "http",
                        "url": "https://project.example/docs",
                    },
                    "slack": {
                        "transport": "http",
                        "url": "https://project.example/slack",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    general_servers = get_mcp_servers(str(tmp_path), include_project_settings=False)
    project_servers = get_mcp_servers(str(tmp_path), include_project_settings=True)

    assert {server.name for server in general_servers} == {"slack"}
    assert {server.name for server in project_servers} == {"docs", "slack"}
    assert next(server for server in general_servers if server.name == "slack").connection["url"] == "https://user.example/slack"
    assert next(server for server in project_servers if server.name == "slack").connection["url"] == "https://project.example/slack"


def test_get_mcp_servers_project_mode_keeps_native_servers_from_user_fallback(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "drive": {
                        "httpUrl": "https://drivemcp.googleapis.com/mcp/v1",
                        "oauth": {
                            "enabled": True,
                            "clientId": "client-id",
                            "clientSecret": "client-secret",
                            "scopes": ["https://www.googleapis.com/auth/drive.readonly"],
                        },
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    del user_scope_root
    repo = ConnectionRepository(get_sqlalchemy_session_factory())
    repo.save_connection(
        connection_id=None,
        provider="google-drive",
        owner_user_id="user-a",
        project_key="user",
        account_label="drive@example.com",
        status="active",
        capabilities=["drive"],
        scopes=["scope:a"],
        tools_enabled=True,
    )

    servers = get_mcp_servers(str(tmp_path), owner_user_id="user-a", include_project_settings=True)

    assert [server.name for server in servers] == ["drive"]

def test_get_mcp_servers_filters_native_microsoft_servers_when_tools_disabled(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "outlook-mail": {
                        "transport": "streamable_http",
                        "url": "https://graph.microsoft.com/mcp",
                        "oauth": {
                            "enabled": True,
                            "clientId": "client-id",
                            "clientSecret": "client-secret",
                            "scopes": ["Mail.Read", "Mail.Send"],
                        },
                    },
                    "outlook-calendar": {
                        "transport": "streamable_http",
                        "url": "https://graph.microsoft.com/mcp",
                        "oauth": {
                            "enabled": True,
                            "clientId": "client-id",
                            "clientSecret": "client-secret",
                            "scopes": ["Calendars.Read", "Calendars.ReadWrite"],
                        },
                    },
                    "docs": {
                        "transport": "http",
                        "url": "https://example.com/mcp",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    storage = StoragePathsService()
    user_scope_root = storage.user_settings_dir() / "__user_scope__"
    del user_scope_root
    repo = ConnectionRepository(get_sqlalchemy_session_factory())
    repo.save_connection(
        connection_id=None,
        provider="microsoft-outlook-mail",
        owner_user_id="user-a",
        project_key="user",
        account_label="mail@example.com",
        status="active",
        capabilities=["outlook_mail"],
        scopes=["scope:a"],
        tools_enabled=True,
    )
    repo.save_connection(
        connection_id=None,
        provider="microsoft-outlook-calendar",
        owner_user_id="user-a",
        project_key="user",
        account_label="calendar@example.com",
        status="active",
        capabilities=["outlook_calendar"],
        scopes=["scope:a"],
        tools_enabled=False,
    )

    servers = get_mcp_servers(str(tmp_path), owner_user_id="user-a")

    assert [server.name for server in servers] == ["outlook-mail", "docs"]


def test_load_from_settings_stdio_server(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "math": {
                        "transport": "stdio",
                        "command": "python",
                        "args": ["/srv/math.py"],
                        "env": {"PYTHONPATH": "/srv"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = _load_mcp_from_settings(str(tmp_path))

    assert servers[0].name == "math"
    assert servers[0].connection["command"] == "python"
    assert servers[0].connection["args"] == ["/srv/math.py"]
    assert servers[0].connection["env"] == {"PYTHONPATH": "/srv"}


def test_load_from_settings_websocket_server(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps({"mcpServers": {"rt": {"transport": "websocket", "url": "ws://localhost:9000"}}}),
        encoding="utf-8",
    )

    servers = _load_mcp_from_settings(str(tmp_path))

    assert servers[0].connection["transport"] == "websocket"


def test_load_from_settings_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert _load_mcp_from_settings(str(tmp_path)) == []


def test_load_from_settings_returns_empty_when_mcp_servers_absent(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps({"otherKey": "value"}), encoding="utf-8"
    )

    assert _load_mcp_from_settings(str(tmp_path)) == []


def test_load_from_settings_silently_skips_malformed_json(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text("not json!!!", encoding="utf-8")

    # Should not raise â€” just return empty
    assert _load_mcp_from_settings(str(tmp_path)) == []


def test_load_from_mcp_json_accepts_claude_style_stdio_server(tmp_path: Path) -> None:
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "command": "cmd",
                        "args": ["/c", "npx", "-y", "@modelcontextprotocol/server-github"],
                        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${TOKEN}"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = _load_mcp_from_mcp_json(str(tmp_path))

    assert len(servers) == 1
    assert servers[0].name == "github"
    assert servers[0].connection["transport"] == "stdio"
    assert servers[0].connection["command"] == "cmd"


# ---------------------------------------------------------------------------
# save_mcp_server_to_settings
# ---------------------------------------------------------------------------

def test_save_creates_settings_file(tmp_path: Path) -> None:
    spec = MCPServerSpec(
        name="myserver",
        connection={"transport": "http", "url": "https://api.example.com/mcp"},
    )

    save_mcp_server_to_settings(str(tmp_path), spec)

    path = tmp_path / ".aethos" / "settings.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "myserver" in data["mcpServers"]
    assert data["mcpServers"]["myserver"]["transport"] == "http"


def test_save_includes_optional_fields(tmp_path: Path) -> None:
    spec = MCPServerSpec(
        name="docs",
        connection={"transport": "http", "url": "https://example.com/mcp"},
        auth_url="https://example.com/login",
        instructions="Use for documentation.",
    )

    save_mcp_server_to_settings(str(tmp_path), spec)

    data = json.loads((tmp_path / ".aethos" / "settings.json").read_text(encoding="utf-8"))
    entry = data["mcpServers"]["docs"]
    assert entry["auth_url"] == "https://example.com/login"
    assert entry["instructions"] == "Use for documentation."


def test_save_overwrites_existing_server(tmp_path: Path) -> None:
    spec_v1 = MCPServerSpec(name="s", connection={"transport": "http", "url": "https://v1.example.com"})
    spec_v2 = MCPServerSpec(name="s", connection={"transport": "http", "url": "https://v2.example.com"})

    save_mcp_server_to_settings(str(tmp_path), spec_v1)
    save_mcp_server_to_settings(str(tmp_path), spec_v2)

    data = json.loads((tmp_path / ".aethos" / "settings.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["s"]["url"] == "https://v2.example.com"


def test_save_preserves_other_servers(tmp_path: Path) -> None:
    spec_a = MCPServerSpec(name="a", connection={"transport": "http", "url": "https://a.example.com"})
    spec_b = MCPServerSpec(name="b", connection={"transport": "http", "url": "https://b.example.com"})

    save_mcp_server_to_settings(str(tmp_path), spec_a)
    save_mcp_server_to_settings(str(tmp_path), spec_b)

    data = json.loads((tmp_path / ".aethos" / "settings.json").read_text(encoding="utf-8"))
    assert "a" in data["mcpServers"]
    assert "b" in data["mcpServers"]


def test_save_mcp_server_to_mcp_json_writes_claude_style_entry(tmp_path: Path) -> None:
    spec = MCPServerSpec(
        name="github",
        connection={"transport": "stdio", "command": "cmd", "args": ["/c", "npx", "-y", "pkg"]},
        instructions="Use for repository operations.",
    )

    save_mcp_server_to_mcp_json(str(tmp_path), spec)

    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    entry = data["mcpServers"]["github"]
    assert "transport" not in entry
    assert entry["command"] == "cmd"
    assert entry["instructions"] == "Use for repository operations."


def test_save_mcp_server_to_mcp_json_preserves_google_workspace_http_url(tmp_path: Path) -> None:
    spec = MCPServerSpec(
        name="calendar",
        connection={
            "transport": "streamable_http",
            "url": "https://calendarmcp.googleapis.com/mcp/v1",
            "oauth": {
                "enabled": True,
                "clientId": "client-id",
                "clientSecret": "client-secret",
                "scopes": [
                    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
                    "https://www.googleapis.com/auth/calendar.events.freebusy",
                    "https://www.googleapis.com/auth/calendar.events.readonly",
                ],
            },
        },
    )

    save_mcp_server_to_mcp_json(str(tmp_path), spec)

    data = json.loads((tmp_path / ".mcp.json").read_text(encoding="utf-8"))
    entry = data["mcpServers"]["calendar"]
    assert entry["httpUrl"] == "https://calendarmcp.googleapis.com/mcp/v1"
    assert "url" not in entry
    assert entry["oauth"]["enabled"] is True


def test_write_mcp_json_config_rejects_invalid_shape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="requires 'transport'"):
        write_mcp_json_config(
            str(tmp_path),
            {"mcpServers": {"broken": {"url": "https://example.com/mcp"}}},
        )


# ---------------------------------------------------------------------------
# remove_mcp_server_from_settings
# ---------------------------------------------------------------------------

def test_remove_existing_server(tmp_path: Path) -> None:
    spec = MCPServerSpec(name="docs", connection={"transport": "http", "url": "https://example.com"})
    save_mcp_server_to_settings(str(tmp_path), spec)

    removed = remove_mcp_server_from_settings(str(tmp_path), "docs")

    assert removed is True
    data = json.loads((tmp_path / ".aethos" / "settings.json").read_text(encoding="utf-8"))
    assert "docs" not in data["mcpServers"]


def test_remove_returns_false_when_not_present(tmp_path: Path) -> None:
    assert remove_mcp_server_from_settings(str(tmp_path), "ghost") is False


def test_remove_preserves_other_servers(tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        save_mcp_server_to_settings(
            str(tmp_path),
            MCPServerSpec(name=name, connection={"transport": "http", "url": f"https://{name}.example.com"}),
        )

    remove_mcp_server_from_settings(str(tmp_path), "b")

    data = json.loads((tmp_path / ".aethos" / "settings.json").read_text(encoding="utf-8"))
    assert "a" in data["mcpServers"]
    assert "b" not in data["mcpServers"]
    assert "c" in data["mcpServers"]


def test_remove_existing_server_from_mcp_json(tmp_path: Path) -> None:
    save_mcp_server_to_mcp_json(
        str(tmp_path),
        MCPServerSpec(name="docs", connection={"transport": "stdio", "command": "uvx"}),
    )

    removed = remove_mcp_server_from_mcp_json(str(tmp_path), "docs")

    assert removed is True
    assert read_mcp_json_config(str(tmp_path)) == {"mcpServers": {}}


# ---------------------------------------------------------------------------
# get_mcp_servers â€” merging env var + settings file
# ---------------------------------------------------------------------------

def test_get_mcp_servers_merges_env_and_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "AETHOS_MCP_SERVERS",
        json.dumps({"env_server": {"transport": "http", "url": "https://env.example.com"}}),
    )
    monkeypatch.setenv("AETHOS_WORKSPACE", str(tmp_path))
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "file_server": {"transport": "http", "url": "https://file.example.com"}
                }
            }
        ),
        encoding="utf-8",
    )

    servers = get_mcp_servers(str(tmp_path))
    names = [s.name for s in servers]

    assert "env_server" in names
    assert "file_server" in names


def test_get_mcp_servers_includes_mcp_json_servers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AETHOS_WORKSPACE", str(tmp_path))
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "github": {
                        "command": "cmd",
                        "args": ["/c", "npx", "-y", "@modelcontextprotocol/server-github"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    servers = get_mcp_servers(str(tmp_path))

    assert [server.name for server in servers] == ["github"]
    assert servers[0].source == "mcp_json"


def test_server_name_validator_rejects_double_underscore() -> None:
    from pydantic import ValidationError
    from src.app.features.extensions.schemas import MCPServerInput

    with pytest.raises(ValidationError, match="__"):
        MCPServerInput(name="docs__v2", transport="http")


def test_server_name_validator_rejects_spaces() -> None:
    from pydantic import ValidationError
    from src.app.features.extensions.schemas import MCPServerInput

    with pytest.raises(ValidationError):
        MCPServerInput(name="my server", transport="http")


def test_server_name_validator_accepts_valid_names() -> None:
    from src.app.features.extensions.schemas import MCPServerInput

    for name in ("docs", "my-server", "server_v2", "GitHub"):
        inp = MCPServerInput(name=name, transport="http")
        assert inp.name == name


def test_get_mcp_servers_env_wins_on_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "AETHOS_MCP_SERVERS",
        json.dumps({"docs": {"transport": "http", "url": "https://env.example.com"}}),
    )
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps(
            {"mcpServers": {"docs": {"transport": "http", "url": "https://file.example.com"}}}
        ),
        encoding="utf-8",
    )

    servers = get_mcp_servers(str(tmp_path))

    assert len(servers) == 1
    assert servers[0].connection["url"] == "https://env.example.com"


def test_get_mcp_servers_settings_override_mcp_json_on_duplicate(tmp_path: Path) -> None:
    (tmp_path / ".aethos").mkdir()
    (tmp_path / ".aethos" / "settings.json").write_text(
        json.dumps({"mcpServers": {"docs": {"transport": "http", "url": "https://settings.example.com"}}}),
        encoding="utf-8",
    )
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"docs": {"command": "uvx", "args": ["docs-server"]}}}),
        encoding="utf-8",
    )

    servers = get_mcp_servers(str(tmp_path))

    assert len(servers) == 1
    assert servers[0].source == "settings"
    assert servers[0].connection["url"] == "https://settings.example.com"


def test_get_mcp_servers_merges_user_local_and_managed_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home-aethos"
    home.mkdir()
    managed = tmp_path / "managed-settings"
    (managed / "managed-settings.d").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    (workspace / ".aethos").mkdir(parents=True)

    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(home))
    monkeypatch.setenv("AETHOS_MANAGED_SETTINGS_DIR", str(managed))

    (home / "settings.json").write_text(
        json.dumps({"mcpServers": {"user": {"transport": "http", "url": "https://user.example.com"}}}),
        encoding="utf-8",
    )
    (workspace / ".aethos" / "settings.json").write_text(
        json.dumps({"mcpServers": {"shared": {"transport": "http", "url": "https://project.example.com"}}}),
        encoding="utf-8",
    )
    (workspace / ".aethos" / "settings.local.json").write_text(
        json.dumps({"mcpServers": {"shared": {"transport": "http", "url": "https://local.example.com"}}}),
        encoding="utf-8",
    )
    (managed / "managed-settings.json").write_text(
        json.dumps({"mcpServers": {"managed": {"transport": "http", "url": "https://managed.example.com"}}}),
        encoding="utf-8",
    )

    servers = get_mcp_servers(str(workspace))
    by_name = {server.name: server for server in servers}

    assert by_name["user"].connection["url"] == "https://user.example.com"
    assert by_name["shared"].connection["url"] == "https://local.example.com"
    assert by_name["managed"].connection["url"] == "https://managed.example.com"

