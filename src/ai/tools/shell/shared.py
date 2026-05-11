"""Shared execution helpers for shell tools.

Phase 1 alignment note:
- Shared lifecycle here is intentionally limited to execution plumbing inspired by
  openclaude's ShellCommand/provider split.
- Shell-specific wrapping, exit semantics, and user-facing contracts stay in each tool.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from src.backends.protocol import ExecuteResponse
from src.backends.protocol import SandboxProtocol


@dataclass(frozen=True)
class SharedShellExecutionResult:
    """Normalized foreground execution result before shell-specific interpretation."""

    output: str
    exit_code: int
    truncated: bool


@dataclass(frozen=True)
class SharedShellExecutionConfig:
    """Shared lifecycle config with shell-specific callbacks kept outside this module."""

    command: str
    wrapped_command: str
    timeout_s: int | None
    description: str | None
    read_output_hint: Callable[[Path], str]


def run_foreground_command(
    backend: SandboxProtocol,
    config: SharedShellExecutionConfig,
) -> SharedShellExecutionResult:
    """Execute one wrapped shell command in the foreground."""
    result = backend.execute(config.wrapped_command, timeout=config.timeout_s)
    return SharedShellExecutionResult(
        output=result.output,
        exit_code=result.exit_code,
        truncated=result.truncated,
    )


def start_background_command(
    backend: SandboxProtocol,
    config: SharedShellExecutionConfig,
) -> str:
    """Start a background command and persist its result to a workspace log file."""
    workspace_root = getattr(backend, "root", None)
    if workspace_root is None:
        return "Error: run_in_background is only supported on local backends."

    task_id = str(uuid4())[:8]
    output_file = Path(workspace_root) / f".aethos_bg_{task_id}.log"

    start_background = getattr(backend, "start_background_execution", None)
    if callable(start_background):
        start_background(command=config.wrapped_command, timeout=config.timeout_s, output_file=output_file)
    else:
        def _worker() -> None:
            try:
                bg_result: ExecuteResponse = backend.execute(config.wrapped_command, timeout=config.timeout_s)
                content = f"exit_code: {bg_result.exit_code}\n---\n{bg_result.output}"
            except Exception as exc:
                content = f"exit_code: -1\n---\nTask error: {exc}"
            try:
                output_file.write_text(content, encoding="utf-8")
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()
    label = config.description or config.command
    return (
        f"Background task started (id: {task_id}): {label}\n"
        f"Output path: {output_file.as_posix()}\n"
        f"Check with: {config.read_output_hint(output_file)}"
    )
