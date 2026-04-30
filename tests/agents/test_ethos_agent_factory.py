from __future__ import annotations

from pathlib import Path

from src.ai.agents import ethos as ethos_module


class _FakeBackend:
    supported_shells = {"bash"}

    def __init__(self, root: Path | None = None) -> None:
        self.root = root


def test_create_ethos_agent_uses_unified_filesystem_builder_for_sandbox(workspace: Path, monkeypatch) -> None:
    backend = _FakeBackend()
    captured: dict[str, object] = {}

    def _fake_build_filesystem_tools(*, root_dir: str, backend=None, permission_context=None, media_block_support=None):
        captured["root_dir"] = root_dir
        captured["backend"] = backend
        captured["permission_context"] = permission_context
        captured["media_block_support"] = media_block_support
        return []

    monkeypatch.setattr(ethos_module, "build_filesystem_tools", _fake_build_filesystem_tools)
    monkeypatch.setattr(ethos_module, "build_bash_tool", lambda *args, **kwargs: "bash")
    monkeypatch.setattr(ethos_module, "build_powershell_tool", lambda *args, **kwargs: "powershell")
    monkeypatch.setattr(ethos_module, "build_mcp_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ethos_module, "get_mcp_servers", lambda: [])
    monkeypatch.setattr(ethos_module, "build_task_tool", lambda **_kwargs: "task_tool")
    monkeypatch.setattr(ethos_module, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(ethos_module, "_build_default_middleware", lambda *_args, **_kwargs: [])

    result = ethos_module.create_ethos_agent(root_dir=str(workspace), backend=backend, model=object())

    assert captured["root_dir"] == str(workspace)
    assert captured["backend"] is backend
    assert captured["permission_context"] is None
    assert captured["media_block_support"] is None
    assert "task_tool" in result["tools"]


def test_create_ethos_agent_uses_backend_root_when_root_dir_is_omitted(
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

    monkeypatch.setattr(ethos_module, "build_filesystem_tools", _fake_build_filesystem_tools)
    monkeypatch.setattr(ethos_module, "build_bash_tool", lambda *args, **kwargs: "bash")
    monkeypatch.setattr(ethos_module, "build_powershell_tool", lambda *args, **kwargs: "powershell")
    monkeypatch.setattr(ethos_module, "build_mcp_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ethos_module, "get_mcp_servers", lambda: [])
    monkeypatch.setattr(ethos_module, "build_task_tool", lambda **_kwargs: "task_tool")
    monkeypatch.setattr(ethos_module, "create_agent", lambda **kwargs: kwargs)
    monkeypatch.setattr(ethos_module, "_build_default_middleware", lambda *_args, **_kwargs: [])

    ethos_module.create_ethos_agent(backend=backend, model=object())

    assert captured["root_dir"] == str(backend_root)


def test_create_ethos_agent_includes_skill_tool(workspace: Path, monkeypatch) -> None:
    monkeypatch.setattr(ethos_module, "build_filesystem_tools", lambda **_kwargs: [])
    monkeypatch.setattr(ethos_module, "build_bash_tool", lambda *args, **kwargs: "bash")
    monkeypatch.setattr(ethos_module, "build_powershell_tool", lambda *args, **kwargs: "powershell")
    monkeypatch.setattr(ethos_module, "build_mcp_tools", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(ethos_module, "get_mcp_servers", lambda: [])
    monkeypatch.setattr(ethos_module, "build_task_tool", lambda **_kwargs: "task_tool")
    monkeypatch.setattr(ethos_module, "create_agent", lambda **kwargs: kwargs)

    result = ethos_module.create_ethos_agent(root_dir=str(workspace), model=object())

    tool_names = [getattr(tool, "name", tool) for tool in result["tools"]]
    assert "skill" in tool_names
    assert "task_tool" in tool_names
