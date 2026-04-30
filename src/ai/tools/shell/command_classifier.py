"""Classify bash/shell commands for UI optimization and output collapsing.

Mirrors the semantic command analysis in claude-code-source BashTool.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


BASH_SEARCH_COMMANDS: frozenset[str] = frozenset({
    "find", "grep", "rg", "ag", "ack", "locate", "which", "whereis",
})

BASH_READ_COMMANDS: frozenset[str] = frozenset({
    "cat", "head", "tail", "less", "more", "wc", "stat", "file",
    "strings", "jq", "awk", "cut", "sort", "uniq", "tr", "sed",
    "diff", "comm", "xxd", "od",
})

BASH_LIST_COMMANDS: frozenset[str] = frozenset({
    "ls", "tree", "du", "df", "lsof", "ps",
})

BASH_NEUTRAL_COMMANDS: frozenset[str] = frozenset({
    "echo", "printf", "true", "false", ":", "pwd", "date",
    "id", "whoami", "hostname", "uname", "env", "printenv",
})

BASH_WRITE_COMMANDS: frozenset[str] = frozenset({
    "cp", "mv", "rm", "rmdir", "mkdir", "touch",
    "chmod", "chown", "ln", "install", "rsync",
})

# Commands that pipe operators: separate sub-commands
_PIPE_SPLIT = re.compile(r"[|;&]")


@dataclass
class BashClassification:
    is_search: bool = False
    is_read: bool = False
    is_list: bool = False
    is_write: bool = False
    should_collapse: bool = False
    collapse_threshold: int = 50


def _base_cmd(token: str) -> str:
    """Extract the base command name from a token (strip path prefixes)."""
    return token.strip().split()[0].split("/")[-1] if token.strip() else ""


def classify_bash_command(command: str) -> BashClassification:
    """Classify a bash command for output collapsing and UI hints.

    Splits pipelines and analyses each segment independently.
    """
    result = BashClassification()
    if not command or not command.strip():
        return result

    segments = _PIPE_SPLIT.split(command)
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        cmd = _base_cmd(seg)
        if not cmd or cmd in BASH_NEUTRAL_COMMANDS:
            continue
        if cmd in BASH_SEARCH_COMMANDS:
            result.is_search = True
        if cmd in BASH_READ_COMMANDS:
            result.is_read = True
        if cmd in BASH_LIST_COMMANDS:
            result.is_list = True
        if cmd in BASH_WRITE_COMMANDS:
            result.is_write = True

    result.should_collapse = result.is_search or result.is_list or result.is_read
    return result
