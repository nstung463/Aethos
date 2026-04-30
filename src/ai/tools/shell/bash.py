"""bash tool - run POSIX shell commands inside a supported backend."""

from __future__ import annotations

import shlex

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src.backends.protocol import SandboxProtocol
from src.ai.permissions.evaluator import PermissionEvaluator
from src.ai.permissions.shell_policy import ShellPolicy
from src.ai.permissions.types import PermissionBehavior, PermissionContext, PermissionMode, PermissionSubject
from src.ai.tools.shell.command_classifier import classify_bash_command
from src.ai.tools.shell.output_formatter import format_bash_output


class BashInput(BaseModel):
    command: str = Field(
        description=(
            "Bash command to execute inside the backend workspace. "
            "Examples: 'ls -la', 'pytest -q', 'python app.py'."
        )
    )
    timeout: int | None = Field(
        default=None,
        description="Maximum seconds to wait. Uses backend default when omitted.",
    )
    background: bool = Field(
        default=False,
        description="Reserved for future parity. Background execution is not supported in Ethos v1.",
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

    def _bash(command: str, timeout: int | None = None, background: bool = False) -> str:
        if "bash" not in backend.supported_shells:
            return "Error: bash is not supported by the active backend."
        if background:
            return "Error: background execution is not supported by the bash tool yet."

        if permission_context is not None:
            decision = evaluator.evaluate(
                context=permission_context,
                subject=PermissionSubject.BASH,
                candidate=command,
                policy_decision=policy.check_bash(context=permission_context, command=command),
            )
            if decision.behavior is PermissionBehavior.ALLOW:
                pass  # fall through to execution
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

        wrapped = f"bash -lc {shlex.quote(command)}"
        result = backend.execute(wrapped, timeout=timeout)
        output = result.output.strip()
        if result.exit_code != 0:
            return f"Exit code: {result.exit_code}\n{output}" if output else f"Command failed (exit {result.exit_code})"
        if not output:
            return "(no output)"

        # Always return full output to the agent; collapsing is a UI-only concern.
        classify_bash_command(command)  # side-effect-free; kept for future UI metadata
        return output

    return StructuredTool.from_function(
        name="bash",
        func=_bash,
        description=(
            "Execute a Bash command inside a POSIX-compatible backend workspace. "
            "Use for tests, scripts, package installation, or shell-based inspection."
        ),
        args_schema=BashInput,
    )
