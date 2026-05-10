from __future__ import annotations

from pathlib import Path

from src.ai.agents import aethos as aethos_module
from src.backends.local import LocalBackend


class _FakeBackend:
    supported_shells = {"bash"}

    def __init__(self, root: Path | None = None) -> None:
        self.root = root


def test_create_aethos_agent_uses_unified_filesystem_builder_for_sandbox(workspace: Path, monkeypatch) -> None:
    backend = _FakeBackend()
    captured: dict[str, object] = {}

    def _fake_build_filesystem_tools(*, root_dir: str, backend=None, permission_context=None, media_block_support=None):
        captured["root_dir"] = root_dir
        captured["backend"] = backend
        captured["permission_context"] = permission_context
        captured["media_block_support"] = media_block_support
        return []

    monkeypatch.setattr(aethos_module, "build_filesystem_tools", _fake_build_filesystem_tools)
    monkeypatch.setattr(aethos_module, "build_bash_tool", lambda *args, **kwargs: "bash")
    monkeypatch.setattr(aethos_module, "build_powershell_tool", lambda *args, **kwargs: "powershell")
    monkeypatch.setattr(aethos_module, "build_mcp_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(aethos_module, "get_mcp_servers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(aethos_module, "build_task_tool", lambda **_kwargs: "task_tool")
    monkeypatch.setattr(aethos_module, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(aethos_module, "_build_default_middleware", lambda *_args, **_kwargs: [])

    result = aethos_module.create_aethos_agent(root_dir=str(workspace), backend=backend, model=object())

    assert captured["root_dir"] == str(workspace)
    assert captured["backend"] is backend
    assert captured["permission_context"] is None
    assert captured["media_block_support"] is None
    assert "task_tool" in result["tools"]


def test_create_aethos_agent_uses_backend_root_when_root_dir_is_omitted(
    workspace: Path,
    monkeypatch,
) -> None:
    backend_root = workspace / "project"
    backend_root.mkdir(parents=True, exist_ok=True)
    backend = _FakeBackend(root=backend_root)
    captured: dict[str, object] = {}

    def _fake_build_filesystem_tools(*, root_dir: str, backend=None, permission_context=None, media_block_support=None):
        captured["root_dir"] = root_dir
        captured["backend"] = backend
        captured["permission_context"] = permission_context
        captured["media_block_support"] = media_block_support
        return []

    monkeypatch.setattr(aethos_module, "build_filesystem_tools", _fake_build_filesystem_tools)
    monkeypatch.setattr(aethos_module, "build_bash_tool", lambda *args, **kwargs: "bash")
    monkeypatch.setattr(aethos_module, "build_powershell_tool", lambda *args, **kwargs: "powershell")
    monkeypatch.setattr(aethos_module, "build_mcp_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(aethos_module, "get_mcp_servers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(aethos_module, "build_task_tool", lambda **_kwargs: "task_tool")
    monkeypatch.setattr(aethos_module, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(aethos_module, "_build_default_middleware", lambda *_args, **_kwargs: [])

    aethos_module.create_aethos_agent(backend=backend, model=object())

    assert captured["root_dir"] == str(backend_root)


def test_create_aethos_agent_includes_skill_tool(workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr(aethos_module, "build_filesystem_tools", lambda **_kwargs: [])
    monkeypatch.setattr(aethos_module, "build_bash_tool", lambda *args, **kwargs: "bash")
    monkeypatch.setattr(aethos_module, "build_powershell_tool", lambda *args, **kwargs: "powershell")
    monkeypatch.setattr(aethos_module, "build_mcp_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(aethos_module, "get_mcp_servers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(aethos_module, "build_task_tool", lambda **_kwargs: "task_tool")
    monkeypatch.setattr(aethos_module, "create_agent", lambda **kwargs: kwargs)

    result = aethos_module.create_aethos_agent(root_dir=str(workspace), model=object())

    tool_names = [getattr(tool, "name", tool) for tool in result["tools"]]
    assert "skill" in tool_names
    assert "task_tool" in tool_names


def test_local_backend_includes_project_skills(workspace: Path, monkeypatch) -> None:
    skill_dir = workspace / ".aethos" / "skills" / "xlsx"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: xlsx\ndescription: Spreadsheet work\n---\nUse spreadsheet workflow.",
        encoding="utf-8",
    )
    backend = LocalBackend(root_dir=str(workspace))
    captured: dict[str, object] = {}

    def _fake_get_mcp_servers(*_args, **kwargs):
        captured["include_project_settings"] = kwargs.get("include_project_settings")
        return []

    monkeypatch.setattr(aethos_module, "build_filesystem_tools", lambda **_kwargs: [])
    monkeypatch.setattr(aethos_module, "build_powershell_tool", lambda *args, **kwargs: "powershell")
    monkeypatch.setattr(aethos_module, "build_mcp_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(aethos_module, "get_mcp_servers", _fake_get_mcp_servers)
    monkeypatch.setattr(aethos_module, "build_integration_tools", lambda **_kwargs: [])

    tools = aethos_module.build_aethos_tools(
        root_dir=str(workspace),
        backend=backend,
        model=object(),
        include_task_tool=False,
    )

    skill_tool = next(tool for tool in tools if getattr(tool, "name", None) == "skill")
    result = skill_tool.invoke({"skill": "xlsx", "args": ""})
    assert captured["include_project_settings"] is True
    assert "Use spreadsheet workflow." in result


def test_remote_backend_excludes_project_skills(workspace: Path, monkeypatch) -> None:
    backend = _FakeBackend(root=workspace)
    captured: dict[str, object] = {}

    def _fake_get_mcp_servers(*_args, **kwargs):
        captured["include_project_settings"] = kwargs.get("include_project_settings")
        return []

    monkeypatch.setattr(aethos_module, "build_filesystem_tools", lambda **_kwargs: [])
    monkeypatch.setattr(aethos_module, "build_bash_tool", lambda *args, **kwargs: "bash")
    monkeypatch.setattr(aethos_module, "build_mcp_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(aethos_module, "get_mcp_servers", _fake_get_mcp_servers)
    monkeypatch.setattr(aethos_module, "build_integration_tools", lambda **_kwargs: [])

    aethos_module.build_aethos_tools(
        root_dir=str(workspace),
        backend=backend,
        model=object(),
        include_task_tool=False,
    )

    assert captured["include_project_settings"] is False
