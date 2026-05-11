from __future__ import annotations

import os
import subprocess
from pathlib import Path

from src.backends.local import LocalSandbox as LocalBackend


def test_run_subprocess_command_appends_stderr_output(monkeypatch) -> None:
    from src.backends.subprocess_runtime import SubprocessExecutionConfig, run_subprocess_command

    class _Proc:
        returncode = 0
        stdout = None
        stderr = None

        def __init__(self):
            from io import StringIO

            self.stdout = StringIO("stdout text")
            self.stderr = StringIO("stderr text")

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr("src.backends.subprocess_runtime.subprocess.Popen", lambda *a, **k: _Proc())

    result = run_subprocess_command(
        SubprocessExecutionConfig(
            command="echo hi",
            cwd="C:/tmp",
            env={},
            timeout_s=5,
        )
    )

    assert result.exit_code == 0
    assert result.output == "stdout text\n<stderr>stderr text</stderr>"
    assert result.truncated is False


def test_run_subprocess_command_timeout_returns_124(monkeypatch) -> None:
    from src.backends.subprocess_runtime import SubprocessExecutionConfig, run_subprocess_command

    class _Proc:
        returncode = None
        stdout = None
        stderr = None

        def __init__(self):
            from io import StringIO

            self.stdout = StringIO("")
            self.stderr = StringIO("")

        def wait(self, timeout=None):
            raise subprocess.TimeoutExpired(cmd="cmd", timeout=7)

        def kill(self):
            return None

    monkeypatch.setattr("src.backends.subprocess_runtime.subprocess.Popen", lambda *a, **k: _Proc())

    result = run_subprocess_command(
        SubprocessExecutionConfig(
            command="sleep 10",
            cwd="C:/tmp",
            env={},
            timeout_s=7,
        )
    )

    assert result.exit_code == 124
    assert result.output == "Command timed out after 7s"
    assert result.truncated is False


def test_run_subprocess_command_sets_truncated_when_output_exceeds_limit(monkeypatch) -> None:
    from src.backends.subprocess_runtime import SubprocessExecutionConfig, run_subprocess_command

    def _fake_popen(*args, **kwargs):
        class _Proc:
            returncode = 0
            stdout = None
            stderr = None

            def __init__(self):
                from io import StringIO

                self.stdout = StringIO("x" * 30)
                self.stderr = StringIO("")

            def wait(self, timeout=None):
                return 0

            def kill(self):
                return None

        return _Proc()

    monkeypatch.setattr("src.backends.subprocess_runtime.subprocess.Popen", _fake_popen)

    result = run_subprocess_command(
        SubprocessExecutionConfig(
            command="echo hi",
            cwd="C:/tmp",
            env={},
            timeout_s=5,
            max_output_chars=10,
        )
    )

    assert result.exit_code == 0
    assert result.truncated is True
    assert result.output == "x" * 10


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

    def _fake_run_subprocess_command(config):
        captured["config"] = config
        from src.backends.protocol import ExecuteResponse

        return ExecuteResponse(output="ok", exit_code=0, truncated=False)

    monkeypatch.setattr("src.backends.local._is_windows", lambda: True)
    monkeypatch.setattr("src.backends.local.run_subprocess_command", _fake_run_subprocess_command)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python3 -c \"print('hi')\"")

    assert result.exit_code == 0
    config = captured["config"]
    assert config.command == "python -c \"print('hi')\""
    assert config.timeout_s == 120
    assert config.stdin is subprocess.DEVNULL


def test_local_backend_execute_keeps_command_on_non_windows(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_subprocess_command(config):
        captured["config"] = config
        from src.backends.protocol import ExecuteResponse

        return ExecuteResponse(output="ok", exit_code=0, truncated=False)

    monkeypatch.setattr("src.backends.local._is_windows", lambda: False)
    monkeypatch.setattr("src.backends.local.run_subprocess_command", _fake_run_subprocess_command)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python3 -c \"print('hi')\"")

    assert result.exit_code == 0
    config = captured["config"]
    assert config.command == "python3 -c \"print('hi')\""
    assert config.timeout_s == 120
    assert config.stdin is subprocess.DEVNULL


def test_local_backend_execute_strips_virtualenv_by_default(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_subprocess_command(config):
        captured["config"] = config
        from src.backends.protocol import ExecuteResponse

        return ExecuteResponse(output="ok", exit_code=0, truncated=False)

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
    monkeypatch.setattr("src.backends.local.run_subprocess_command", _fake_run_subprocess_command)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python -c \"print('hi')\"")

    assert result.exit_code == 0
    env = captured["config"].env
    assert isinstance(env, dict)
    assert "VIRTUAL_ENV" not in env
    assert "VIRTUAL_ENV_PROMPT" not in env
    assert env["PATH"] == kept_path


def test_local_backend_execute_uses_shared_subprocess_runtime(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_subprocess_command(config):
        captured["config"] = config
        from src.backends.protocol import ExecuteResponse

        return ExecuteResponse(output="ok", exit_code=0, truncated=False)

    monkeypatch.setattr("src.backends.local.run_subprocess_command", _fake_run_subprocess_command)
    monkeypatch.setattr("src.backends.local._is_windows", lambda: False)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python3 -c \"print('hi')\"")

    assert result.exit_code == 0
    config = captured["config"]
    assert config.command == "python3 -c \"print('hi')\""
    assert config.cwd == str(workspace)
    assert isinstance(config.env, dict)
    assert config.timeout_s == 120
    assert config.stdin is subprocess.DEVNULL
    assert config.max_output_chars == 120_000


def test_local_backend_execute_strips_aethos_virtualenv_without_virtual_env_marker(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_run_subprocess_command(config):
        captured["config"] = config
        from src.backends.protocol import ExecuteResponse

        return ExecuteResponse(output="ok", exit_code=0, truncated=False)

    aethos_venv_scripts = str(Path(__file__).resolve().parents[1] / ".venv" / "Scripts")
    kept_path = str(workspace / "bin")
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PATH", os.pathsep.join([aethos_venv_scripts, kept_path]))
    monkeypatch.setattr("src.backends.local.run_subprocess_command", _fake_run_subprocess_command)
    backend = LocalBackend(str(workspace))

    result = backend.execute("python -c \"print('hi')\"")

    assert result.exit_code == 0
    env = captured["config"].env
    assert isinstance(env, dict)
    assert env["PATH"] == kept_path


def test_local_backend_start_background_execution_uses_runtime_streaming(workspace, monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_start_background_subprocess(config):
        captured["config"] = config

    monkeypatch.setattr("src.backends.local.start_background_subprocess", _fake_start_background_subprocess)
    backend = LocalBackend(str(workspace))
    output_file = workspace / "bg.log"

    backend.start_background_execution(
        command="python3 -c \"print('hi')\"",
        timeout=9,
        output_file=output_file,
    )

    config = captured["config"]
    assert config.command == "python -c \"print('hi')\""
    assert config.cwd == str(workspace)
    assert isinstance(config.env, dict)
    assert config.timeout_s == 9
    assert config.output_file == output_file
    assert config.stdin is subprocess.DEVNULL
