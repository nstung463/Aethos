"""Exit-code semantics and output utilities for shell tools.

Many commands use non-zero exit codes for informational reasons:
- grep/rg exits 1 when no matches found (not an error)
- diff exits 1 when files differ (not an error)
This module maps base command names to semantic rules so the agent
gets accurate context instead of spurious "error" messages.
"""
from __future__ import annotations

import re

MAX_OUTPUT_CHARS = 30_000
DEFAULT_TIMEOUT_MS = 120_000   # 2 minutes, matches Claude Code
MAX_TIMEOUT_MS = 600_000       # 10 minutes

# Commands that produce no stdout on success — return "Done." instead of "(no output)"
SILENT_BASH_COMMANDS: frozenset[str] = frozenset({
    "mv", "cp", "rm", "mkdir", "rmdir", "chmod", "chown", "chgrp",
    "touch", "ln", "cd", "export", "unset", "wait",
})

SILENT_PS_COMMANDS: frozenset[str] = frozenset({
    "Move-Item", "mi",
    "Copy-Item", "ci",
    "Remove-Item", "ri", "del", "rd",
    "New-Item", "ni",
    "Set-Location", "sl", "cd", "chdir",
    "Set-ItemProperty",
    "Rename-Item", "rni",
})

# Neutral commands whose presence doesn't affect the read/silent classification
_NEUTRAL_COMMANDS: frozenset[str] = frozenset({
    "echo", "printf", "true", "false", ":", "pwd", "date",
    "id", "whoami", "hostname", "uname", "Write-Host", "Write-Output",
})

# Maps command name → (error_threshold, info_message_at_non_error_exit).
# Exit codes strictly below the threshold are informational, not errors.
_BASH_SEMANTICS: dict[str, tuple[int, str]] = {
    # grep/rg: 0=matches found, 1=no matches, 2+=error
    "grep":  (2, "No matches found"),
    "rg":    (2, "No matches found"),
    # find: 1=some dirs inaccessible (partial result), 2+=error
    "find":  (2, "Some directories were inaccessible"),
    # diff: 0=identical, 1=files differ, 2+=error
    "diff":  (2, "Files differ"),
    # test/[: 0=true, 1=false, 2+=error
    "test":  (2, "Condition is false"),
    "[":     (2, "Condition is false"),
}

# Only external executables are listed here — native PS cmdlets exit 0 always.
# Select-String, Compare-Object, Test-Path all exit 0 regardless of result;
# their output (empty collection) is the signal, not the exit code.
_PS_SEMANTICS: dict[str, tuple[int, str]] = {
    # findstr (Windows built-in, like grep): exit 1 = no matches
    "findstr": (2, "No matches found"),
    # robocopy: exits 0-7 are all success/informational bitmasks, 8+ = error
    "robocopy": (8, "Robocopy completed (informational exit code)"),
    # External grep/rg called from PS have the same semantics as bash
    "grep": (2, "No matches found"),
    "rg":   (2, "No matches found"),
    "diff": (2, "Files differ"),
}

# Splits on ||, &&, |, ; — preserving operators as tokens for context-aware analysis.
_OP_PATTERN = re.compile(r"(\|\||&&|[|;])")
# Splits discarding operators — used when we only need the segments.
_CMD_SEP = re.compile(r"\|\|?|&&|;")


def _split_segments(command: str) -> list[str]:
    """Split a compound command into segments, discarding operators."""
    return [s.strip() for s in _CMD_SEP.split(command) if s.strip()]


def _split_with_operators(command: str) -> list[str]:
    """Split into alternating [segment, operator, segment, ...] token list.

    Operators (||, &&, |, ;) are preserved as separate tokens so callers can
    inspect the operator that precedes each command segment.
    """
    return [t.strip() for t in _OP_PATTERN.split(command) if t.strip()]


def _extract_base(segment: str) -> str:
    """Extract the bare command name from a single command segment."""
    token = segment.strip().split()[0] if segment.strip() else ""
    token = token.rsplit("/", 1)[-1]   # strip Unix path prefix
    token = token.rsplit("\\", 1)[-1]  # strip Windows path prefix
    # strip extension (rg.exe → rg), but preserve dotfile names (.bashrc)
    if "." in token and not token.startswith("."):
        token = token.rsplit(".", 1)[0]
    return token


def ms_to_seconds(ms: int | None) -> int | None:
    """Convert a millisecond timeout to seconds for the backend.

    Clamps to [1, MAX_TIMEOUT_MS/1000]. Returns None when ms is None
    (backend will use its own default).
    """
    if ms is None:
        return None
    return max(1, min(ms, MAX_TIMEOUT_MS) // 1000)


def interpret_bash_exit(command: str, exit_code: int) -> tuple[bool, str | None]:
    """Return (is_error, info_message).

    Uses the LAST pipeline segment to determine semantics, because that is
    the segment whose exit code propagates (e.g. 'cat f | grep p' → 'grep').
    info_message is set when exit_code != 0 but is informational (not an error).
    """
    if exit_code == 0:
        return False, None
    segments = _split_segments(command)
    last_base = _extract_base(segments[-1]) if segments else _extract_base(command)
    sem = _BASH_SEMANTICS.get(last_base)
    if sem is None:
        return True, None
    threshold, msg = sem
    return (False, msg) if exit_code < threshold else (True, None)


def interpret_ps_exit(command: str, exit_code: int) -> tuple[bool, str | None]:
    """Same as interpret_bash_exit but for PowerShell command semantics."""
    if exit_code == 0:
        return False, None
    segments = _split_segments(command)
    last_base = _extract_base(segments[-1]) if segments else _extract_base(command)
    sem = _PS_SEMANTICS.get(last_base)
    if sem is None:
        return True, None
    threshold, msg = sem
    return (False, msg) if exit_code < threshold else (True, None)


def is_silent_command(command: str, silent_set: frozenset[str]) -> bool:
    """Return True only if every meaningful segment is a known silent command.

    Mirrors Claude Code's isSilentBashCommand logic: neutral commands (echo,
    printf, etc.) are only ignored when they follow '||' — where they act as
    error-handler fallbacks, not primary output producers.

    Examples:
        'rm file'               → True   (single silent command)
        'rm file || echo error' → True   (echo after || is a fallback, ignored)
        'rm file && echo done'  → False  (echo after && produces output)
        'rm a | wc -c'          → False  (wc is not silent)
    """
    tokens = _split_with_operators(command)
    has_meaningful = False
    last_op: str | None = None
    for token in tokens:
        if token in ("||", "&&", "|", ";"):
            last_op = token
            continue
        base = _extract_base(token)
        if not base:
            continue
        # Neutral commands after || are error-handler fallbacks — skip them.
        if last_op == "||" and base in _NEUTRAL_COMMANDS:
            continue
        has_meaningful = True
        if base not in silent_set:
            return False
    return has_meaningful


def truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """Truncate output to max_chars, keeping the tail.

    Tail truncation keeps the end of build/test output which is usually
    the summary (most useful part). The dropped-char count is calculated
    before line-boundary alignment so the header is accurate.
    """
    if len(output) <= max_chars:
        return output
    base_dropped = len(output) - max_chars  # accurate count before alignment
    kept = output[-max_chars:]
    nl = kept.find("\n")
    if nl > 0:
        kept = kept[nl + 1:]
    return f"[{base_dropped:,} chars truncated from start]\n{kept}"
