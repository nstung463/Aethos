from __future__ import annotations

from src.backends.protocol import ExecuteResponse
from src.backends.sandbox import BaseSandbox as CommandBackedBackend


class _FakeBackend(CommandBackedBackend):
    def __init__(self, shells: set[str], root=None) -> None:
        self._shells = shells
        self.calls: list[tuple[str, int | None]] = []
        # Optional workspace root — required for run_in_background
        if root is not None:
            self.root = root

    @property
    def id(self) -> str:
        return "fake"

    @property
    def supported_shells(self) -> set[str]:
        return self._shells

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        self.calls.append((command, timeout))
        return ExecuteResponse(output="ok", exit_code=0, truncated=False)

    def upload_files(self, files: list[tuple[str, bytes]]):  # pragma: no cover - not used here
        return []

    def download_files(self, paths: list[str]):  # pragma: no cover - not used here
        return []


def test_bash_tool_wraps_command_for_bash() -> None:
    from src.ai.tools.shell.bash import build_bash_tool

    backend = _FakeBackend({"bash"})
    tool = build_bash_tool(backend)

    # timeout is in milliseconds; 7000 ms → 7 seconds passed to backend
    result = tool.invoke({"command": "echo hello", "timeout": 7000})

    assert result == "ok"
    assert backend.calls == [("bash -lc 'echo hello'", 7)]


def test_bash_tool_rejects_unsupported_backend() -> None:
    from src.ai.tools.shell.bash import build_bash_tool

    tool = build_bash_tool(_FakeBackend({"powershell"}))

    result = tool.invoke({"command": "echo hello"})

    assert "not supported" in result.lower()


def test_powershell_tool_encodes_command() -> None:
    from src.ai.tools.shell.powershell import build_powershell_tool

    backend = _FakeBackend({"powershell"})
    tool = build_powershell_tool(backend)

    # timeout is in milliseconds; 3000 ms → 3 seconds passed to backend
    result = tool.invoke({"command": "Get-ChildItem", "timeout": 3000})

    assert result == "ok"
    command, timeout = backend.calls[0]
    assert command.startswith("powershell -NoProfile -EncodedCommand ")
    assert timeout == 3


def test_powershell_tool_starts_background_task(tmp_path) -> None:
    from src.ai.tools.shell.powershell import build_powershell_tool

    tool = build_powershell_tool(_FakeBackend({"powershell"}, root=tmp_path))

    result = tool.invoke({"command": "Get-ChildItem", "run_in_background": True})

    assert "background task started" in result.lower()
    assert "Get-ChildItem" in result


def test_powershell_tool_background_requires_local_backend() -> None:
    from src.ai.tools.shell.powershell import build_powershell_tool

    tool = build_powershell_tool(_FakeBackend({"powershell"}))  # no root → remote-like

    result = tool.invoke({"command": "Get-ChildItem", "run_in_background": True})

    assert "only supported on local backends" in result.lower()



def test_bash_blocks_network_command_in_default_mode(tmp_path):
    from unittest.mock import patch

    from src.ai.permissions.context import build_default_permission_context
    from src.ai.tools.shell.bash import build_bash_tool

    backend = _FakeBackend({"bash"})
    tool = build_bash_tool(backend, permission_context=build_default_permission_context(tmp_path))
    with patch("src.ai.tools.shell.bash.interrupt", return_value={"approved": False}):
        result = tool.invoke({"command": "curl https://example.com"})
    assert "permission" in result.lower()
    assert backend.calls == []


def test_bash_allows_read_only_command_in_default_mode(tmp_path):
    from src.ai.permissions.context import build_default_permission_context
    from src.ai.tools.shell.bash import build_bash_tool

    backend = _FakeBackend({"bash"})
    tool = build_bash_tool(backend, permission_context=build_default_permission_context(tmp_path))
    result = tool.invoke({"command": "pwd"})
    assert result == "ok"
    assert len(backend.calls) == 1


def test_bash_calls_interrupt_on_network_command(tmp_path) -> None:
    """bash tool must call interrupt() for networked commands, not return a string."""
    from pathlib import Path
    from unittest.mock import patch

    from src.ai.permissions.context import build_default_permission_context
    from src.ai.tools.shell.bash import build_bash_tool

    backend = _FakeBackend({"bash"})
    ctx = build_default_permission_context(workspace_root=tmp_path)
    tool = build_bash_tool(backend, permission_context=ctx)

    interrupted: list[dict] = []

    def _fake_interrupt(payload):
        interrupted.append(payload)
        return {"approved": False}

    with patch("src.ai.tools.shell.bash.interrupt", side_effect=_fake_interrupt):
        result = tool.invoke({"command": "curl https://example.com"})

    assert len(interrupted) == 1
    assert interrupted[0]["behavior"] == "ask"
    assert interrupted[0]["subject"] == "bash"
    assert interrupted[0]["approval_options"] == [
        {"id": "once", "label": "Approve once"},
        {"id": "thread_command", "label": "Allow this command in this thread"},
        {"id": "user_command", "label": "Always allow this command"},
    ]
    assert not backend.calls  # command was NOT executed


def test_bash_proceeds_after_interrupt_approval(tmp_path) -> None:
    from unittest.mock import patch

    from src.ai.permissions.context import build_default_permission_context
    from src.ai.tools.shell.bash import build_bash_tool

    backend = _FakeBackend({"bash"})
    ctx = build_default_permission_context(workspace_root=tmp_path)
    tool = build_bash_tool(backend, permission_context=ctx)

    with patch("src.ai.tools.shell.bash.interrupt", return_value={"approved": True}):
        result = tool.invoke({"command": "curl https://example.com"})

    assert backend.calls  # command WAS executed after approval
    assert "denied" not in result.lower()  # not a denial message


def test_bash_calls_interrupt_on_code_execution(tmp_path) -> None:
    """code_execution commands (python, node) must call interrupt() even in accept_edits mode."""
    from unittest.mock import patch

    from src.ai.permissions.context import build_default_permission_context
    from src.ai.permissions.types import PermissionMode
    from src.ai.tools.shell.bash import build_bash_tool

    backend = _FakeBackend({"bash"})
    ctx = build_default_permission_context(workspace_root=tmp_path, mode=PermissionMode.ACCEPT_EDITS)
    tool = build_bash_tool(backend, permission_context=ctx)

    interrupted: list[dict] = []

    def _fake_interrupt(payload):
        interrupted.append(payload)
        return {"approved": False}

    with patch("src.ai.tools.shell.bash.interrupt", side_effect=_fake_interrupt):
        tool.invoke({"command": "python script.py"})

    assert len(interrupted) == 1
    assert interrupted[0]["behavior"] == "ask"
    assert not backend.calls


# ── command_classifier ───────────────────────────────────────────────────────

def test_classifier_search_command() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    c = classify_bash_command("grep -r foo .")
    assert c.is_search
    assert not c.is_read
    assert c.should_collapse


def test_classifier_list_command() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    c = classify_bash_command("ls -la")
    assert c.is_list
    assert c.should_collapse


def test_classifier_read_command() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    c = classify_bash_command("cat README.md")
    assert c.is_read
    assert c.should_collapse


def test_classifier_write_command() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    c = classify_bash_command("rm -rf dist/")
    assert c.is_write
    assert not c.should_collapse


def test_classifier_neutral_command() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    c = classify_bash_command("echo hello")
    assert not c.is_search and not c.is_read and not c.is_list and not c.is_write
    assert not c.should_collapse


def test_classifier_pipeline() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    c = classify_bash_command("grep pattern file | sort | uniq")
    assert c.is_search
    assert c.is_read  # sort+uniq are read cmds
    assert c.should_collapse


def test_classifier_empty_command() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    c = classify_bash_command("")
    assert not c.should_collapse


def test_classifier_path_prefix_stripped() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    c = classify_bash_command("/usr/bin/find . -name '*.py'")
    assert c.is_search


# ── output_formatter ─────────────────────────────────────────────────────────

def test_formatter_no_collapse_below_threshold() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    from src.ai.tools.shell.output_formatter import format_bash_output

    cls = classify_bash_command("ls")
    output = "\n".join(f"file{i}.py" for i in range(10))
    result = format_bash_output(output, cls)
    assert not result.collapsed
    assert result.summary is None
    assert result.raw == output


def test_formatter_collapses_above_threshold() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    from src.ai.tools.shell.output_formatter import format_bash_output

    cls = classify_bash_command("ls")
    output = "\n".join(f"file{i}.py" for i in range(60))
    result = format_bash_output(output, cls)
    assert result.collapsed
    assert result.summary is not None
    assert "60" in result.summary or "lines" in result.summary.lower()


def test_formatter_no_collapse_for_write_command() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    from src.ai.tools.shell.output_formatter import format_bash_output

    cls = classify_bash_command("rm -rf dist/")
    output = "\n".join(f"removed {i}" for i in range(100))
    result = format_bash_output(output, cls)
    assert not result.collapsed


def test_formatter_max_lines_override() -> None:
    from src.ai.tools.shell.command_classifier import classify_bash_command
    from src.ai.tools.shell.output_formatter import format_bash_output

    cls = classify_bash_command("grep pattern file")
    output = "\n".join(f"match {i}" for i in range(10))
    result = format_bash_output(output, cls, max_lines=5)
    assert result.collapsed


def test_bash_tool_returns_full_output_regardless_of_size(tmp_path) -> None:
    from src.ai.tools.shell.bash import build_bash_tool
    from src.backends.protocol import ExecuteResponse

    big_output = "\n".join(f"file{i}.py" for i in range(60))

    class _BigBackend(_FakeBackend):
        def execute(self, command, *, timeout=None):
            self.calls.append((command, timeout))
            return ExecuteResponse(output=big_output, exit_code=0, truncated=False)

    tool = build_bash_tool(_BigBackend({"bash"}))
    result = tool.invoke({"command": "ls -la"})
    # Agent always receives full output; collapsing is a UI-only concern.
    assert result == big_output


# ── exit_semantics ───────────────────────────────────────────────────────────

def test_grep_exit_1_is_not_error() -> None:
    from src.ai.tools.shell.exit_semantics import interpret_bash_exit
    is_error, msg = interpret_bash_exit("grep pattern file.txt", 1)
    assert not is_error
    assert msg == "No matches found"


def test_grep_exit_2_is_error() -> None:
    from src.ai.tools.shell.exit_semantics import interpret_bash_exit
    is_error, msg = interpret_bash_exit("grep pattern file.txt", 2)
    assert is_error
    assert msg is None


def test_diff_exit_1_is_not_error() -> None:
    from src.ai.tools.shell.exit_semantics import interpret_bash_exit
    is_error, msg = interpret_bash_exit("diff a.txt b.txt", 1)
    assert not is_error
    assert msg == "Files differ"


def test_unknown_command_exit_nonzero_is_error() -> None:
    from src.ai.tools.shell.exit_semantics import interpret_bash_exit
    is_error, msg = interpret_bash_exit("python app.py", 1)
    assert is_error
    assert msg is None


def test_pipeline_exit_code_uses_last_segment() -> None:
    # 'cat file | grep pattern' exit 1 → semantics from grep (last), not cat (first)
    from src.ai.tools.shell.exit_semantics import interpret_bash_exit
    is_error, msg = interpret_bash_exit("cat file.txt | grep pattern", 1)
    assert not is_error
    assert msg == "No matches found"


def test_truncate_output_short_passthrough() -> None:
    from src.ai.tools.shell.exit_semantics import truncate_output
    text = "hello\nworld"
    assert truncate_output(text, max_chars=100) == text


def test_truncate_output_keeps_tail() -> None:
    from src.ai.tools.shell.exit_semantics import truncate_output
    lines = [f"line{i}" for i in range(1000)]
    text = "\n".join(lines)
    result = truncate_output(text, max_chars=100)
    assert "truncated" in result
    assert result.endswith(lines[-1])


def test_truncate_output_dropped_count_is_accurate() -> None:
    # dropped count must equal len(original) - MAX_CHARS, not be inflated by alignment
    from src.ai.tools.shell.exit_semantics import truncate_output
    # 200 chars of content; truncate to 100 → must report exactly 100 dropped
    text = "a" * 200
    result = truncate_output(text, max_chars=100)
    import re
    m = re.search(r"([\d,]+) chars truncated", result)
    assert m is not None
    dropped = int(m.group(1).replace(",", ""))
    assert dropped == 100


def test_is_silent_command_simple() -> None:
    from src.ai.tools.shell.exit_semantics import is_silent_command, SILENT_BASH_COMMANDS
    assert is_silent_command("rm file.txt", SILENT_BASH_COMMANDS)


def test_is_silent_command_compound_not_silent() -> None:
    # rm is silent, but echo after && produces output → whole command is NOT silent
    from src.ai.tools.shell.exit_semantics import is_silent_command, SILENT_BASH_COMMANDS
    assert not is_silent_command("rm file.txt && echo done", SILENT_BASH_COMMANDS)


def test_ms_to_seconds_converts() -> None:
    from src.ai.tools.shell.exit_semantics import ms_to_seconds
    assert ms_to_seconds(30_000) == 30
    assert ms_to_seconds(None) is None
    assert ms_to_seconds(500) == 1   # floor at 1 second
    assert ms_to_seconds(700_000) == 600  # capped at MAX_TIMEOUT_MS / 1000


def test_bash_tool_grep_no_match_shows_info_not_error() -> None:
    from src.ai.tools.shell.bash import build_bash_tool
    from src.backends.protocol import ExecuteResponse

    class _GrepBackend(_FakeBackend):
        def execute(self, command, *, timeout=None):
            self.calls.append((command, timeout))
            return ExecuteResponse(output="", exit_code=1, truncated=False)

    tool = build_bash_tool(_GrepBackend({"bash"}))
    result = tool.invoke({"command": "grep pattern file.txt"})
    assert result == "No matches found"
    assert "exit code" not in result.lower()


def test_bash_tool_silent_command_returns_done() -> None:
    from src.ai.tools.shell.bash import build_bash_tool
    from src.backends.protocol import ExecuteResponse

    class _SilentBackend(_FakeBackend):
        def execute(self, command, *, timeout=None):
            self.calls.append((command, timeout))
            return ExecuteResponse(output="", exit_code=0, truncated=False)

    tool = build_bash_tool(_SilentBackend({"bash"}))
    result = tool.invoke({"command": "rm old_file.txt"})
    assert result == "Done."


def test_bash_tool_compound_silent_plus_echo_is_not_done() -> None:
    # 'rm f && echo done' exits 0 with output — not "Done.", returns the actual output
    from src.ai.tools.shell.bash import build_bash_tool
    from src.backends.protocol import ExecuteResponse

    class _Backend(_FakeBackend):
        def execute(self, command, *, timeout=None):
            self.calls.append((command, timeout))
            return ExecuteResponse(output="done", exit_code=0, truncated=False)

    tool = build_bash_tool(_Backend({"bash"}))
    result = tool.invoke({"command": "rm old_file.txt && echo done"})
    assert result == "done"


def test_bash_tool_background_writes_output_path(tmp_path) -> None:
    from src.ai.tools.shell.bash import build_bash_tool

    tool = build_bash_tool(_FakeBackend({"bash"}, root=tmp_path))
    result = tool.invoke({"command": "pytest -q", "run_in_background": True})
    assert "Background task started" in result
    assert "Output path:" in result
    assert "ethos_bg_" in result


def test_bash_tool_background_requires_local_backend() -> None:
    from src.ai.tools.shell.bash import build_bash_tool

    tool = build_bash_tool(_FakeBackend({"bash"}))  # no root → remote-like
    result = tool.invoke({"command": "pytest -q", "run_in_background": True})
    assert "only supported on local backends" in result.lower()


def test_bash_tool_background_returns_task_id(tmp_path) -> None:
    from src.ai.tools.shell.bash import build_bash_tool

    tool = build_bash_tool(_FakeBackend({"bash"}, root=tmp_path))
    result = tool.invoke({"command": "pytest -q", "run_in_background": True})
    assert "background task started" in result.lower()
    assert "pytest" in result


def test_bash_tool_description_param_accepted() -> None:
    from src.ai.tools.shell.bash import build_bash_tool

    backend = _FakeBackend({"bash"})
    tool = build_bash_tool(backend)
    result = tool.invoke({
        "command": "echo hello",
        "description": "Print greeting to stdout",
    })
    assert result == "ok"


def test_bash_tool_timeout_in_ms_converts_to_seconds() -> None:
    from src.ai.tools.shell.bash import build_bash_tool

    backend = _FakeBackend({"bash"})
    tool = build_bash_tool(backend)
    tool.invoke({"command": "echo hello", "timeout": 30_000})
    _, timeout_s = backend.calls[0]
    assert timeout_s == 30


def test_bash_tool_truncates_large_output() -> None:
    from src.ai.tools.shell.bash import build_bash_tool
    from src.backends.protocol import ExecuteResponse

    huge = "x" * 100_000

    class _HugeBackend(_FakeBackend):
        def execute(self, command, *, timeout=None):
            self.calls.append((command, timeout))
            return ExecuteResponse(output=huge, exit_code=0, truncated=False)

    tool = build_bash_tool(_HugeBackend({"bash"}))
    result = tool.invoke({"command": "cat bigfile.log"})
    assert len(result) < len(huge)
    assert "truncated" in result


def test_bash_tool_backend_truncated_flag_prepends_note() -> None:
    from src.ai.tools.shell.bash import build_bash_tool
    from src.backends.protocol import ExecuteResponse

    class _TruncBackend(_FakeBackend):
        def execute(self, command, *, timeout=None):
            self.calls.append((command, timeout))
            return ExecuteResponse(output="partial output", exit_code=0, truncated=True)

    tool = build_bash_tool(_TruncBackend({"bash"}))
    result = tool.invoke({"command": "cat huge.log"})
    assert "[Output truncated by backend]" in result
    assert "partial output" in result


# ── powershell tests (existing) ───────────────────────────────────────────────

def test_powershell_calls_interrupt_on_network_command(tmp_path) -> None:
    from unittest.mock import patch

    from src.ai.permissions.context import build_default_permission_context
    from src.ai.tools.shell.powershell import build_powershell_tool

    backend = _FakeBackend({"powershell"})
    ctx = build_default_permission_context(workspace_root=tmp_path)
    tool = build_powershell_tool(backend, permission_context=ctx)

    interrupted: list[dict] = []

    def _fake_interrupt(payload):
        interrupted.append(payload)
        return {"approved": False}

    with patch("src.ai.tools.shell.powershell.interrupt", side_effect=_fake_interrupt):
        result = tool.invoke({"command": "Invoke-WebRequest https://example.com"})

    assert len(interrupted) == 1
    assert interrupted[0]["behavior"] == "ask"
    assert interrupted[0]["subject"] == "powershell"
    assert not backend.calls
