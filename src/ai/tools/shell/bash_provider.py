"""Bash execution provider helpers.

Phase 7 alignment note:
- This module keeps bash-specific wrapping separate from shared execution
  lifecycle helpers, following the provider split used in openclaude.
- Pipeline/stdin redirect behavior is aligned here in conservative,
  traceable steps rather than by copying openclaude's full shell-quote stack.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path


_WINDOWS_NULL_REDIRECT = re.compile(r"(\d?&?>+\s*)[Nn][Uu][Ll](?=\s|$|[|&;)\n])")
_HEREDOC_PATTERN = re.compile(r"<<-?\s*(?:(['\"]?)(\w+)\1|\\(\w+))")
_STDIN_REDIRECT_PATTERN = re.compile(r"(?:^|[\s;&|])<(?![<(])\s*\S+")
_SHELL_VAR_PATTERN = re.compile(r"\$[A-Za-z_{]")
_CONTROL_STRUCTURE_PATTERN = re.compile(r"\b(for|while|until|if|case|select)\s")
_SINGLE_QUOTE_MULTILINE = re.compile(r"'(?:[^'\\]|\\.)*\n(?:[^'\\]|\\.)*'")
_DOUBLE_QUOTE_MULTILINE = re.compile(r'"(?:[^"\\]|\\.)*\n(?:[^"\\]|\\.)*"')


def rewrite_windows_null_redirect(command: str) -> str:
    """Normalize Windows CMD null redirects for POSIX bash environments.

    openclaude defends against `2>nul` because Git Bash treats `nul` as a
    literal filename instead of the Windows null device. We adopt the same
    intent here without pulling in the full shell-quoting stack yet.
    """
    return _WINDOWS_NULL_REDIRECT.sub(r"\1/dev/null", command)


def contains_heredoc(command: str) -> bool:
    """Return True when the command appears to use a heredoc."""
    if re.search(r"\d\s*<<\s*\d", command):
        return False
    if re.search(r"\[\[\s*\d+\s*<<\s*\d+\s*\]\]", command):
        return False
    if re.search(r"\$\(\(.*<<.*\)\)", command):
        return False
    return bool(_HEREDOC_PATTERN.search(command))


def contains_multiline_string(command: str) -> bool:
    """Return True when quoted strings span real newlines."""
    return bool(_SINGLE_QUOTE_MULTILINE.search(command) or _DOUBLE_QUOTE_MULTILINE.search(command))


def has_stdin_redirect(command: str) -> bool:
    """Return True when the command already provides its own stdin redirect."""
    return bool(_STDIN_REDIRECT_PATTERN.search(command))


def should_add_stdin_redirect(command: str) -> bool:
    """Mirror openclaude's non-interactive intent for bash commands.

    We add `< /dev/null` when the command does not already define stdin and is
    not using a heredoc. This keeps commands non-interactive without breaking
    explicit stdin behavior.
    """
    return not contains_heredoc(command) and not has_stdin_redirect(command)


def _first_unquoted_pipe(command: str) -> int:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(command):
        if escaped:
            escaped = False
            continue
        if char == "\\" and not in_single:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "|" and not in_single and not in_double:
            prev_char = command[index - 1] if index > 0 else ""
            next_char = command[index + 1] if index + 1 < len(command) else ""
            if prev_char == "|" or next_char == "|":
                continue
            return index
    return -1


def rearrange_pipe_command(command: str) -> str | None:
    """Move `< /dev/null` onto the first pipeline segment when safe.

    openclaude uses this to avoid stdin redirect changing pipeline behavior.
    Here we apply a conservative subset and fall back when syntax is complex.
    """
    if "|" not in command:
        return None
    if "`" in command or "$(" in command:
        return None
    if _SHELL_VAR_PATTERN.search(command):
        return None
    if _CONTROL_STRUCTURE_PATTERN.search(command):
        return None
    if contains_multiline_string(command):
        return None
    if "\n" in command:
        return None

    pipe_index = _first_unquoted_pipe(command)
    if pipe_index <= 0:
        return None

    first = command[:pipe_index].rstrip()
    rest = command[pipe_index:].lstrip()
    if not first or not rest:
        return None
    return f"{first} < /dev/null {rest}"


def build_bash_wrapper(command: str) -> str:
    """Wrap a command for explicit bash execution.

    Intentional divergence from openclaude: Aethos uses `bash -lc` directly
    rather than `eval ...` inside a larger shell command. Because of that, the
    optional stdin redirect can safely live outside the quoted command string
    and still apply to the shell process as a whole.
    """
    normalized = rewrite_windows_null_redirect(command)
    if should_add_stdin_redirect(normalized):
        rearranged = rearrange_pipe_command(normalized)
        if rearranged is not None:
            return f"bash -lc {shlex.quote(rearranged)}"
        return f"bash -lc {shlex.quote(normalized)} < /dev/null"
    return f"bash -lc {shlex.quote(normalized)}"


def build_bash_read_hint(path: Path) -> str:
    """Return a bash-native command for reading a background log file."""
    return f"cat {path.as_posix()}"
