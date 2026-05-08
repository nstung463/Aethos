"""powershell tool - run PowerShell commands inside a supported backend."""

from __future__ import annotations

import base64
import threading
from pathlib import Path
from uuid import uuid4

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
    SILENT_PS_COMMANDS,
    interpret_ps_exit,
    is_silent_command,
    ms_to_seconds,
    truncate_output,
)


class PowerShellInput(BaseModel):
    command: str = Field(
        description=(
            "PowerShell command to execute inside the backend workspace. "
            "Examples: 'Get-ChildItem', 'pytest -q', 'Get-Content file.txt'."
        )
    )
    description: str | None = Field(
        default=None,
        description=(
            "Brief description of what this command does in active voice. "
            "Used as the label in background task messages and logs. "
            "Examples: 'List source files', 'Run unit tests'."
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
            "read it later with the powershell or read_file tool. "
            "Only supported on local backends."
        ),
    )


def _encode_powershell(command: str) -> str:
    return base64.b64encode(command.encode("utf-16le")).decode("ascii")


def build_powershell_tool(
    backend: SandboxProtocol,
    permission_context: PermissionContext | None = None,
) -> StructuredTool:
    """Build the PowerShell tool when the backend supports it."""
    policy = ShellPolicy()
    evaluator = PermissionEvaluator()

    approval_options = [
        {"id": "once", "label": "Approve once"},
        {"id": "thread_command", "label": "Allow this command in this thread"},
        {"id": "user_command", "label": "Always allow this command"},
    ]

    def _powershell(
        command: str,
        description: str | None = None,
        timeout: int | None = None,
        run_in_background: bool = False,
    ) -> str:
        if "powershell" not in backend.supported_shells:
            return "Error: powershell is not supported by the active backend."

        if permission_context is not None:
            decision = evaluator.evaluate(
                context=permission_context,
                subject=PermissionSubject.POWERSHELL,
                candidate=command,
                policy_decision=policy.check_powershell(context=permission_context, command=command),
            )
            if decision.behavior is PermissionBehavior.ALLOW:
                pass
            elif decision.behavior is PermissionBehavior.DENY:
                return f"Permission denied: {decision.reason}"
            elif decision.behavior is PermissionBehavior.ASK:
                user_decision = interrupt({
                    "behavior": "ask",
                    "reason": decision.reason,
                    "subject": PermissionSubject.POWERSHELL.value,
                    "command": command,
                    "approval_options": approval_options,
                    "suggested_mode": PermissionMode.BYPASS_PERMISSIONS.value,
                    "suggestions": [s.value for s in (decision.suggestions or [])],
                })
                if not user_decision.get("approved", False):
                    return "Permission denied by user."

        encoded = _encode_powershell(command)
        wrapped = f"powershell -NoProfile -EncodedCommand {encoded}"
        timeout_s = ms_to_seconds(timeout)

        if run_in_background:
            workspace_root = getattr(backend, "root", None)
            if workspace_root is None:
                return "Error: run_in_background is only supported on local backends."
            task_id = str(uuid4())[:8]
            output_file = Path(workspace_root) / f".aethos_bg_{task_id}.log"

            def _worker() -> None:
                try:
                    bg_result = backend.execute(wrapped, timeout=timeout_s)
                    content = f"exit_code: {bg_result.exit_code}\n---\n{bg_result.output}"
                except Exception as exc:
                    content = f"exit_code: -1\n---\nTask error: {exc}"
                try:
                    output_file.write_text(content, encoding="utf-8")
                except Exception:
                    pass

            threading.Thread(target=_worker, daemon=True).start()
            label = description or command
            return (
                f"Background task started (id: {task_id}): {label}\n"
                f"Output path: {output_file.as_posix()}\n"
                f"Check with: Get-Content '{output_file.as_posix()}'"
            )

        result = backend.execute(wrapped, timeout=timeout_s)
        raw = result.output.strip()
        output = truncate_output(raw)
        if result.truncated:
            output = f"[Output truncated by backend]\n{output}"

        is_error, info_msg = interpret_ps_exit(command, result.exit_code)
        if is_error:
            return f"Exit code: {result.exit_code}\n{output}" if output else f"Command failed (exit {result.exit_code})"
        if result.exit_code != 0 and info_msg:
            return f"{info_msg}\n{output}".strip() if output else info_msg

        if not output:
            return "Done." if is_silent_command(command, SILENT_PS_COMMANDS) else "(no output)"

        return output

    return StructuredTool.from_function(
        name="powershell",
        func=_powershell,
        description=(
            "Execute a PowerShell command inside a Windows-compatible backend workspace. "
            f"Default timeout: {DEFAULT_TIMEOUT_MS // 60_000} min. "
            "Use for Windows-native shell tasks and scripts."
        ),
        args_schema=PowerShellInput,
    )
