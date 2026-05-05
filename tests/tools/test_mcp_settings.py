"""Tests for MCP server management via .ethos/settings.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.config import (
    MCPServerSpec,
    _load_mcp_from_settings,
    _parse_mcp_env_var,
    get_mcp_servers,
    remove_mcp_server_from_settings,
    save_mcp_server_to_settings,
)


# ---------------------------------------------------------------------------
# _load_mcp_from_settings
# ---------------------------------------------------------------------------

def test_load_from_settings_http_server(tmp_path: Path) -> None:
    (tmp_path / ".ethos").mkdir()
    (tmp_path / ".ethos" / "settings.json").write_text(
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


def test_load_from_settings_stdio_server(tmp_path: Path) -> None:
    (tmp_path / ".ethos").mkdir()
    (tmp_path / ".ethos" / "settings.json").write_text(
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
    (tmp_path / ".ethos").mkdir()
    (tmp_path / ".ethos" / "settings.json").write_text(
        json.dumps({"mcpServers": {"rt": {"transport": "websocket", "url": "ws://localhost:9000"}}}),
        encoding="utf-8",
    )

    servers = _load_mcp_from_settings(str(tmp_path))

    assert servers[0].connection["transport"] == "websocket"


def test_load_from_settings_returns_empty_when_file_missing(tmp_path: Path) -> None:
    assert _load_mcp_from_settings(str(tmp_path)) == []


def test_load_from_settings_returns_empty_when_mcp_servers_absent(tmp_path: Path) -> None:
    (tmp_path / ".ethos").mkdir()
    (tmp_path / ".ethos" / "settings.json").write_text(
        json.dumps({"otherKey": "value"}), encoding="utf-8"
    )

    assert _load_mcp_from_settings(str(tmp_path)) == []


def test_load_from_settings_silently_skips_malformed_json(tmp_path: Path) -> None:
    (tmp_path / ".ethos").mkdir()
    (tmp_path / ".ethos" / "settings.json").write_text("not json!!!", encoding="utf-8")

    # Should not raise — just return empty
    assert _load_mcp_from_settings(str(tmp_path)) == []


# ---------------------------------------------------------------------------
# save_mcp_server_to_settings
# ---------------------------------------------------------------------------

def test_save_creates_settings_file(tmp_path: Path) -> None:
    spec = MCPServerSpec(
        name="myserver",
        connection={"transport": "http", "url": "https://api.example.com/mcp"},
    )

    save_mcp_server_to_settings(str(tmp_path), spec)

    path = tmp_path / ".ethos" / "settings.json"
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

    data = json.loads((tmp_path / ".ethos" / "settings.json").read_text(encoding="utf-8"))
    entry = data["mcpServers"]["docs"]
    assert entry["auth_url"] == "https://example.com/login"
    assert entry["instructions"] == "Use for documentation."


def test_save_overwrites_existing_server(tmp_path: Path) -> None:
    spec_v1 = MCPServerSpec(name="s", connection={"transport": "http", "url": "https://v1.example.com"})
    spec_v2 = MCPServerSpec(name="s", connection={"transport": "http", "url": "https://v2.example.com"})

    save_mcp_server_to_settings(str(tmp_path), spec_v1)
    save_mcp_server_to_settings(str(tmp_path), spec_v2)

    data = json.loads((tmp_path / ".ethos" / "settings.json").read_text(encoding="utf-8"))
    assert data["mcpServers"]["s"]["url"] == "https://v2.example.com"


def test_save_preserves_other_servers(tmp_path: Path) -> None:
    spec_a = MCPServerSpec(name="a", connection={"transport": "http", "url": "https://a.example.com"})
    spec_b = MCPServerSpec(name="b", connection={"transport": "http", "url": "https://b.example.com"})

    save_mcp_server_to_settings(str(tmp_path), spec_a)
    save_mcp_server_to_settings(str(tmp_path), spec_b)

    data = json.loads((tmp_path / ".ethos" / "settings.json").read_text(encoding="utf-8"))
    assert "a" in data["mcpServers"]
    assert "b" in data["mcpServers"]


# ---------------------------------------------------------------------------
# remove_mcp_server_from_settings
# ---------------------------------------------------------------------------

def test_remove_existing_server(tmp_path: Path) -> None:
    spec = MCPServerSpec(name="docs", connection={"transport": "http", "url": "https://example.com"})
    save_mcp_server_to_settings(str(tmp_path), spec)

    removed = remove_mcp_server_from_settings(str(tmp_path), "docs")

    assert removed is True
    data = json.loads((tmp_path / ".ethos" / "settings.json").read_text(encoding="utf-8"))
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

    data = json.loads((tmp_path / ".ethos" / "settings.json").read_text(encoding="utf-8"))
    assert "a" in data["mcpServers"]
    assert "b" not in data["mcpServers"]
    assert "c" in data["mcpServers"]


# ---------------------------------------------------------------------------
# get_mcp_servers — merging env var + settings file
# ---------------------------------------------------------------------------

def test_get_mcp_servers_merges_env_and_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps({"env_server": {"transport": "http", "url": "https://env.example.com"}}),
    )
    monkeypatch.setenv("ETHOS_WORKSPACE", str(tmp_path))
    (tmp_path / ".ethos").mkdir()
    (tmp_path / ".ethos" / "settings.json").write_text(
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


def test_server_name_validator_rejects_double_underscore() -> None:
    from pydantic import ValidationError
    from src.app.modules.extensions.schemas import MCPServerInput

    with pytest.raises(ValidationError, match="__"):
        MCPServerInput(name="docs__v2", transport="http")


def test_server_name_validator_rejects_spaces() -> None:
    from pydantic import ValidationError
    from src.app.modules.extensions.schemas import MCPServerInput

    with pytest.raises(ValidationError):
        MCPServerInput(name="my server", transport="http")


def test_server_name_validator_accepts_valid_names() -> None:
    from src.app.modules.extensions.schemas import MCPServerInput

    for name in ("docs", "my-server", "server_v2", "GitHub"):
        inp = MCPServerInput(name=name, transport="http")
        assert inp.name == name


def test_get_mcp_servers_env_wins_on_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "ETHOS_MCP_SERVERS",
        json.dumps({"docs": {"transport": "http", "url": "https://env.example.com"}}),
    )
    (tmp_path / ".ethos").mkdir()
    (tmp_path / ".ethos" / "settings.json").write_text(
        json.dumps(
            {"mcpServers": {"docs": {"transport": "http", "url": "https://file.example.com"}}}
        ),
        encoding="utf-8",
    )

    servers = get_mcp_servers(str(tmp_path))

    assert len(servers) == 1
    assert servers[0].connection["url"] == "https://env.example.com"


def test_get_mcp_servers_merges_user_local_and_managed_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home-ethos"
    home.mkdir()
    managed = tmp_path / "managed-settings"
    (managed / "managed-settings.d").mkdir(parents=True)
    workspace = tmp_path / "workspace"
    (workspace / ".ethos").mkdir(parents=True)

    monkeypatch.setenv("ETHOS_CONFIG_HOME", str(home))
    monkeypatch.setenv("ETHOS_MANAGED_SETTINGS_DIR", str(managed))

    (home / "settings.json").write_text(
        json.dumps({"mcpServers": {"user": {"transport": "http", "url": "https://user.example.com"}}}),
        encoding="utf-8",
    )
    (workspace / ".ethos" / "settings.json").write_text(
        json.dumps({"mcpServers": {"shared": {"transport": "http", "url": "https://project.example.com"}}}),
        encoding="utf-8",
    )
    (workspace / ".ethos" / "settings.local.json").write_text(
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
