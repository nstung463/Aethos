from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.backends.local import LocalSandbox as LocalBackend


def test_local_backend_read_uses_native_filesystem(workspace) -> None:
    (workspace / "hello.txt").write_text("line1\nline2\n", encoding="utf-8")
    backend = LocalBackend(str(workspace))
    backend.execute = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("execute should not be used"))  # type: ignore[method-assign]

    result = backend.read("hello.txt")

    assert result.error is None
    assert "line1" in (result.content or "")


def test_local_backend_write_uses_native_filesystem(workspace) -> None:
    backend = LocalBackend(str(workspace))
    backend.execute = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("execute should not be used"))  # type: ignore[method-assign]

    result = backend.write("nested/file.txt", "hello")

    assert result.error is None
    assert (workspace / "nested" / "file.txt").read_text(encoding="utf-8") == "hello"


def test_local_backend_edit_uses_native_filesystem(workspace) -> None:
    (workspace / "code.py").write_text("x = 1\ny = 2\n", encoding="utf-8")
    backend = LocalBackend(str(workspace))
    backend.execute = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("execute should not be used"))  # type: ignore[method-assign]

    result = backend.edit("code.py", "x = 1", "x = 99")

    assert result.error is None
    assert (workspace / "code.py").read_text(encoding="utf-8") == "x = 99\ny = 2\n"


def test_local_backend_glob_uses_native_filesystem(workspace) -> None:
    (workspace / "a.py").write_text("", encoding="utf-8")
    (workspace / "b.txt").write_text("", encoding="utf-8")
    subdir = workspace / "sub"
    subdir.mkdir()
    (subdir / "c.py").write_text("", encoding="utf-8")
    backend = LocalBackend(str(workspace))
    backend.execute = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("execute should not be used"))  # type: ignore[method-assign]

    result = backend.glob("**/*.py", ".")

    assert sorted(result) == ["a.py", "sub/c.py"]


def test_local_backend_grep_uses_native_filesystem(workspace) -> None:
    (workspace / "a.py").write_text("hello\nworld\n", encoding="utf-8")
    (workspace / "b.txt").write_text("hello\n", encoding="utf-8")
    backend = LocalBackend(str(workspace))
    backend.execute = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("execute should not be used"))  # type: ignore[method-assign]

    result = backend.grep("hello", ".", "*.py")

    assert result == [{"path": "a.py", "line": 1, "text": "hello"}]


def test_local_backend_supported_shells_windows(workspace, monkeypatch) -> None:
    monkeypatch.setattr("src.backends.local._is_windows", lambda: True)
    backend = LocalBackend(str(workspace))

    assert backend.supported_shells == {"powershell"}


def test_local_backend_supported_shells_non_windows(workspace, monkeypatch) -> None:
    monkeypatch.setattr("src.backends.local._is_windows", lambda: False)
    backend = LocalBackend(str(workspace))

    assert backend.supported_shells == {"bash"}


def test_local_backend_execute_normalizes_python3_on_windows(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("src.backends.local._is_windows", lambda: True)
    monkeypatch.setattr("src.backends.local.subprocess.run", _fake_run)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python3 -c \"print('hi')\"")

    assert result.exit_code == 0
    assert captured["command"] == "python -c \"print('hi')\""
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["stdin"] is subprocess.DEVNULL


def test_local_backend_execute_keeps_command_on_non_windows(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("src.backends.local._is_windows", lambda: False)
    monkeypatch.setattr("src.backends.local.subprocess.run", _fake_run)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python3 -c \"print('hi')\"")

    assert result.exit_code == 0
    assert captured["command"] == "python3 -c \"print('hi')\""
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
    assert captured["stdin"] is subprocess.DEVNULL


def test_local_backend_execute_strips_virtualenv_by_default(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    virtual_env = str(workspace / ".venv")
    kept_path = str(workspace / "bin")
    path_value = os.pathsep.join(
        [
            str(workspace / ".venv" / "Scripts"),
            kept_path,
            str(workspace / ".venv"),
        ]
    )
    monkeypatch.setenv("VIRTUAL_ENV", virtual_env)
    monkeypatch.setenv("VIRTUAL_ENV_PROMPT", "(.venv)")
    monkeypatch.setenv("PATH", path_value)
    monkeypatch.setattr("src.backends.local.subprocess.run", _fake_run)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python -c \"print('hi')\"")

    assert result.exit_code == 0
    env = captured["env"]
    assert isinstance(env, dict)
    assert "VIRTUAL_ENV" not in env
    assert "VIRTUAL_ENV_PROMPT" not in env
    assert env["PATH"] == kept_path


def test_local_backend_execute_strips_aethos_virtualenv_without_virtual_env_marker(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run(command, **kwargs):
        captured.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    aethos_venv_scripts = str(Path(__file__).resolve().parents[1] / ".venv" / "Scripts")
    kept_path = str(workspace / "bin")
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([aethos_venv_scripts, kept_path]))
    monkeypatch.setattr("src.backends.local.subprocess.run", _fake_run)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python -c \"print('hi')\"")

    assert result.exit_code == 0
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["PATH"] == kept_path
