"""Shared subprocess execution lifecycle for local shell-backed backends.

This module centralizes subprocess lifecycle concerns for both foreground and
background shell execution without introducing shell-specific semantics.
"""

from __future__ import annotations

from collections import deque
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from src.backends.protocol import ExecuteResponse

DEFAULT_MAX_OUTPUT_CHARS = 120_000
TIMEOUT_EXIT_CODE = 124


class _TailBuffer:
    def __init__(self, limit: int) -> None:
        self.limit = max(0, limit)
        self._parts: deque[str] = deque()
        self._total = 0
        self.truncated = False

    def append(self, text: str) -> None:
        if not text:
            return
        if self.limit == 0:
            self.truncated = True
            return
        self._parts.append(text)
        self._total += len(text)
        while self._total > self.limit and self._parts:
            overflow = self._total - self.limit
            head = self._parts[0]
            if len(head) <= overflow:
                self._parts.popleft()
                self._total -= len(head)
            else:
                self._parts[0] = head[overflow:]
                self._total -= overflow
            self.truncated = True

    def text(self) -> str:
        return "".join(self._parts)


def _drain_stream(stream, buffer: _TailBuffer) -> None:
    if stream is None:
        return
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            buffer.append(chunk)
    finally:
        stream.close()


@dataclass(frozen=True)
class SubprocessExecutionConfig:
    command: str
    cwd: str
    env: dict[str, str]
    timeout_s: int
    stdin: int | None = subprocess.DEVNULL
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS


@dataclass(frozen=True)
class BackgroundExecutionConfig:
    command: str
    cwd: str
    env: dict[str, str]
    timeout_s: int
    output_file: Path
    stdin: int | None = subprocess.DEVNULL


def _cap_output(text: str, limit: int) -> tuple[str, bool]:
    if limit <= 0:
        return "", bool(text)
    if len(text) <= limit:
        return text, False
    return text[-limit:], True


def run_subprocess_command(config: SubprocessExecutionConfig) -> ExecuteResponse:
    """Execute one non-interactive subprocess command with runtime-owned lifecycle."""
    process: subprocess.Popen[str] | None = None
    try:
        process = subprocess.Popen(
            config.command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=config.cwd,
            env=config.env,
            stdin=config.stdin,
        )
        stdout_buffer = _TailBuffer(config.max_output_chars)
        stderr_buffer = _TailBuffer(config.max_output_chars)
        stdout_thread = threading.Thread(target=_drain_stream, args=(process.stdout, stdout_buffer), daemon=True)
        stderr_thread = threading.Thread(target=_drain_stream, args=(process.stderr, stderr_buffer), daemon=True)
        stdout_thread.start()
        stderr_thread.start()
        try:
            process.wait(timeout=config.timeout_s)
            exit_code = process.returncode if process.returncode is not None else 1
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=1)
            except Exception:
                pass
            stdout_thread.join(timeout=1)
            stderr_thread.join(timeout=1)
            return ExecuteResponse(
                output=f"Command timed out after {config.timeout_s}s",
                exit_code=TIMEOUT_EXIT_CODE,
                truncated=False,
            )

        stdout_thread.join(timeout=1)
        stderr_thread.join(timeout=1)

        output = stdout_buffer.text()
        stderr_text = stderr_buffer.text().strip()
        if stderr_text:
            output += f"\n<stderr>{stderr_text}</stderr>"

        truncated = stdout_buffer.truncated or stderr_buffer.truncated
        return ExecuteResponse(output=output, exit_code=exit_code, truncated=truncated)
    except Exception as exc:
        if process is not None:
            try:
                process.kill()
            except Exception:
                pass
        return ExecuteResponse(output=str(exc), exit_code=1, truncated=False)


def start_background_subprocess(config: BackgroundExecutionConfig) -> None:
    """Start a background subprocess and stream output directly to a log file."""

    def _worker() -> None:
        output_path = config.output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with output_path.open("w", encoding="utf-8") as handle:
                process = subprocess.Popen(
                    config.command,
                    shell=True,
                    stdout=handle,
                    stderr=handle,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=config.cwd,
                    env=config.env,
                    stdin=config.stdin,
                )
                try:
                    exit_code = process.wait(timeout=config.timeout_s)
                    handle.write(f"\n\nexit_code: {exit_code}\n")
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=1)
                    except Exception:
                        pass
                    handle.write(f"\n\nTask error: Command timed out after {config.timeout_s}s\n")
                    handle.write(f"exit_code: {TIMEOUT_EXIT_CODE}\n")
        except Exception as exc:
            try:
                output_path.write_text(f"Task error: {exc}\nexit_code: -1\n", encoding="utf-8")
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()
