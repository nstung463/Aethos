"""bash tool - run POSIX shell commands inside a supported backend."""

from __future__ import annotations

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src.backends.protocol import SandboxProtocol
from src.ai.permissions.evaluator import PermissionEvaluator
from src.ai.permissions.shell_policy import ShellPolicy
from src.ai.permissions.types import PermissionBehavior, PermissionContext, PermissionMode, PermissionSubject
from src.ai.tools.shell.exit_semantics import (
    DEFAULT_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
    SILENT_BASH_COMMANDS,
    interpret_bash_exit,
    is_silent_command,
    ms_to_seconds,
    truncate_output,
)
from src.ai.tools.shell.bash_provider import build_bash_read_hint, build_bash_wrapper
from src.ai.tools.shell.shared import SharedShellExecutionConfig, run_foreground_command, start_background_command


BASH_TOOL_DESCRIPTION = (
    "Execute a Bash command inside a POSIX-compatible backend workspace. "
    f"Default timeout: {DEFAULT_TIMEOUT_MS // 60_000} min. "
    "Use this for git, tests, package managers, scripts, and shell-based inspection. "
    "This tool runs non-interactively: avoid commands that expect a TTY or live input such as vim, less, top, watch, or tail -f. "
    "Use run_in_background for long-running commands when you do not need the result immediately; do not append '&' when using that parameter. "
    "Prefer dedicated Glob/Grep/ReadFile tools for file search and reading instead of shelling out."
)


class BashInput(BaseModel):
    command: str = Field(
        description=(
            "Bash command to execute inside the backend workspace. "
            "Examples: 'ls -la', 'pytest -q', 'python app.py'."
        )
    )
    description: str | None = Field(
        default=None,
        description=(
            "Brief description of what this command does in active voice. "
            "Used as the label in background task messages and logs. "
            "Examples: 'Run unit tests', 'Start dev server', 'Install dependencies'."
        ),
    )
    timeout: int | None = Field(
        default=None,
        description=(
            f"Timeout in milliseconds (max {MAX_TIMEOUT_MS:,} ms / "
            f"{MAX_TIMEOUT_MS // 60_000} minutes). "
            f"Defaults to {DEFAULT_TIMEOUT_MS:,} ms ({DEFAULT_TIMEOUT_MS // 60_000} minutes). "
            "Values under 1,000 ms are raised to 1 s."
        ),
    )
    run_in_background: bool = Field(
        default=False,
        description=(
            "Run the command in the background and return immediately. "
            "The output is written to a file inside the workspace — "
            "read it later with the bash or read_file tool. "
            "Only supported on local backends."
        ),
    )


def build_bash_tool(
    backend: SandboxProtocol,
    permission_context: PermissionContext | None = None,
) -> StructuredTool:
    """Build the bash tool when the backend supports POSIX shell execution."""
    policy = ShellPolicy()
    evaluator = PermissionEvaluator()

    approval_options = [
        {"id": "once", "label": "Approve once"},
        {"id": "thread_command", "label": "Allow this command in this thread"},
        {"id": "user_command", "label": "Always allow this command"},
    ]

    def _build_config(
        command: str,
        description: str | None,
        timeout: int | None,
    ) -> SharedShellExecutionConfig:
        return SharedShellExecutionConfig(
            command=command,
            wrapped_command=build_bash_wrapper(command),
            timeout_s=ms_to_seconds(timeout),
            description=description,
            read_output_hint=build_bash_read_hint,
        )

    def _bash(
        command: str,
        description: str | None = None,
        timeout: int | None = None,
        run_in_background: bool = False,
    ) -> str:
        if "bash" not in backend.supported_shells:
            return "Error: bash is not supported by the active backend."

        if permission_context is not None:
            decision = evaluator.evaluate(
                context=permission_context,
                subject=PermissionSubject.BASH,
                candidate=command,
                policy_decision=policy.check_bash(context=permission_context, command=command),
            )
            if decision.behavior is PermissionBehavior.ALLOW:
                pass
            elif decision.behavior is PermissionBehavior.DENY:
                return f"Permission denied: {decision.reason}"
            elif decision.behavior is PermissionBehavior.ASK:
                user_decision = interrupt({
                    "behavior": "ask",
                    "reason": decision.reason,
                    "subject": PermissionSubject.BASH.value,
                    "command": command,
                    "approval_options": approval_options,
                    "suggested_mode": PermissionMode.BYPASS_PERMISSIONS.value,
                    "suggestions": [s.value for s in (decision.suggestions or [])],
                })
                if not user_decision.get("approved", False):
                    return "Permission denied by user."

        config = _build_config(command=command, description=description, timeout=timeout)

        if run_in_background:
            return start_background_command(backend=backend, config=config)

        result = run_foreground_command(backend=backend, config=config)
        raw = result.output.strip()
        output = truncate_output(raw)
        if result.truncated:
            output = f"[Output truncated by backend]\n{output}"

        is_error, info_msg = interpret_bash_exit(command, result.exit_code)
        if is_error:
            return f"Exit code: {result.exit_code}\n{output}" if output else f"Command failed (exit {result.exit_code})"
        if result.exit_code != 0 and info_msg:
            return f"{info_msg}\n{output}".strip() if output else info_msg

        if not output:
            return "Done." if is_silent_command(command, SILENT_BASH_COMMANDS) else "(no output)"

        return output

    return StructuredTool.from_function(
        name="bash",
        func=_bash,
        description=BASH_TOOL_DESCRIPTION,
        args_schema=BashInput,
    )
