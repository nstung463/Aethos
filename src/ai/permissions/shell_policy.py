from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from types import MappingProxyType

from src.ai.permissions.powershell_policy import classify_powershell_command
from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
    PermissionMode,
)


_CMD_SEP = re.compile(r"\|\|?|&&|;")
_ENV_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

_READ_ONLY_COMMANDS = frozenset(
    {
        "pwd",
        "ls",
        "cat",
        "rg",
        "grep",
        "find",
        "git",
        "echo",
        "printf",
        "head",
        "tail",
        "wc",
        "sort",
        "uniq",
        "which",
        "where",
        "type",
    }
)

_READ_ONLY_GIT_SUBCOMMANDS = frozenset(
    {
        "status",
        "log",
        "diff",
        "show",
        "reflog",
        "rev-parse",
        "rev-list",
        "describe",
        "merge-base",
        "blame",
        "ls-files",
        "remote",
        "ls-remote",
        "shortlog",
    }
)

_NETWORK_COMMANDS = frozenset(
    {
        "curl",
        "wget",
        "pip",
        "pip3",
        "npm",
        "pnpm",
        "yarn",
        "uv",
        "apt",
        "apt-get",
        "brew",
        "gh",
        "docker",
        "git",
    }
)

_DESTRUCTIVE_COMMANDS = frozenset(
    {
        "rm",
        "del",
        "format",
        "mkfs",
        "dd",
        "shred",
    }
)

_PRIVILEGED_COMMANDS = frozenset(
    {
        "sudo",
        "su",
        "doas",
        "pkexec",
        "eval",
        "exec",
        "bash",
        "sh",
        "pwsh",
        "powershell",
    }
)

_CODE_EXECUTION_COMMANDS = frozenset(
    {
        "python",
        "python3",
        "node",
        "ruby",
        "perl",
    }
)

_WRITE_COMMANDS = frozenset(
    {
        "tee",
        "mkdir",
        "touch",
        "cp",
        "mv",
        "install",
    }
)

_SAFE_WRAPPERS = frozenset({"env", "command", "builtin", "noglob", "timeout"})
_GIT_GLOBAL_FLAGS_WITH_VALUE = frozenset(
    {
        "-C",
        "-c",
        "--git-dir",
        "--work-tree",
        "--namespace",
        "--exec-path",
        "--config-env",
    }
)

_NETWORK_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "pip": frozenset({"install", "download", "wheel"}),
    "pip3": frozenset({"install", "download", "wheel"}),
    "npm": frozenset({"install", "ci", "update", "publish"}),
    "pnpm": frozenset({"install", "update", "add"}),
    "yarn": frozenset({"install", "add", "upgrade"}),
    "uv": frozenset({"add", "sync", "pip"}),
    "git": frozenset({"clone", "fetch", "pull", "push"}),
    "docker": frozenset({"pull", "push", "login", "logout", "build"}),
}

_DESTRUCTIVE_PATTERNS = (
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\b"),
)

_REDIRECT_PATTERN = re.compile(r"(?:^|[\s;&|])(?:\d*>>?|&>>?)")
_HEREDOC_PATTERN = re.compile(r"<<-?\s*\S+")
_FIND_EXEC_PATTERN = re.compile(r"\bfind\b.*\s-exec\b")


@dataclass(frozen=True)
class _ParsedCommand:
    base_command: str
    subcommand: str | None
    tokens: tuple[str, ...]


class ShellPolicy:
    def _split_segments(self, command: str) -> list[str]:
        return [segment.strip() for segment in _CMD_SEP.split(command) if segment.strip()]

    def _tokenize(self, command: str) -> list[str]:
        try:
            return shlex.split(command, posix=True)
        except ValueError:
            return command.strip().split()

    def _strip_safe_wrappers(self, tokens: list[str]) -> list[str]:
        remaining = list(tokens)
        changed = True
        while remaining and changed:
            changed = False
            while remaining and _ENV_ASSIGNMENT.match(remaining[0]):
                remaining.pop(0)
                changed = True
            if remaining and remaining[0] in _SAFE_WRAPPERS:
                wrapper = remaining.pop(0)
                changed = True
                if wrapper == "timeout":
                    while remaining and remaining[0].startswith("-"):
                        flag = remaining.pop(0)
                        if flag in {"-k", "--kill-after", "-s", "--signal"} and remaining:
                            remaining.pop(0)
                    if remaining and not remaining[0].startswith("-"):
                        remaining.pop(0)
                if wrapper == "env":
                    while remaining and remaining[0].startswith("-"):
                        flag = remaining.pop(0)
                        if flag in {"-u", "--unset"} and remaining and "=" not in flag:
                            remaining.pop(0)
        return remaining

    def _extract_subcommand(self, tokens: list[str]) -> str | None:
        if not tokens:
            return None
        if tokens[0].lower() != "git":
            return tokens[1].lower() if len(tokens) > 1 and not tokens[1].startswith("-") else None

        i = 1
        while i < len(tokens):
            token = tokens[i]
            if token.startswith("-"):
                if token in _GIT_GLOBAL_FLAGS_WITH_VALUE and i + 1 < len(tokens):
                    i += 2
                    continue
                if any(token.startswith(prefix + "=") for prefix in _GIT_GLOBAL_FLAGS_WITH_VALUE if prefix.startswith("--")):
                    i += 1
                    continue
                i += 1
                continue
            return token.lower()
        return None

    def _parse_segment(self, segment: str) -> _ParsedCommand | None:
        tokens = self._strip_safe_wrappers(self._tokenize(segment))
        if not tokens:
            return None
        base = tokens[0].rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if base.endswith(".exe"):
            base = base[:-4]
        subcommand = self._extract_subcommand(tokens)
        return _ParsedCommand(base_command=base.lower(), subcommand=subcommand.lower() if subcommand else None, tokens=tuple(tokens))

    def _is_workspace_write(self, command: str, parsed: _ParsedCommand | None) -> bool:
        if _REDIRECT_PATTERN.search(command) or _HEREDOC_PATTERN.search(command):
            return True
        if parsed is None:
            return False
        if parsed.base_command in _WRITE_COMMANDS:
            return True
        if parsed.base_command == "git" and parsed.subcommand in {"apply", "checkout", "restore", "switch", "branch"}:
            return True
        if parsed.base_command == "find" and _FIND_EXEC_PATTERN.search(command):
            return True
        return False

    def _classify_segment(self, segment: str) -> str:
        parsed = self._parse_segment(segment)
        if parsed is None:
            return "workspace_write"

        if parsed.base_command in _PRIVILEGED_COMMANDS:
            if parsed.base_command in {"bash", "sh", "pwsh", "powershell"} and parsed.subcommand not in {"-lc", "-c", "-command"}:
                return "privileged_or_escape"
            if parsed.base_command in {"sudo", "su", "doas", "pkexec", "eval", "exec"}:
                return "privileged_or_escape"

        if parsed.base_command in _CODE_EXECUTION_COMMANDS:
            return "code_execution"

        if any(pattern.search(segment) for pattern in _DESTRUCTIVE_PATTERNS):
            return "destructive"

        if parsed.base_command in _DESTRUCTIVE_COMMANDS:
            return "destructive"

        if parsed.base_command in _NETWORK_COMMANDS:
            if parsed.base_command in _NETWORK_SUBCOMMANDS:
                if parsed.subcommand in _NETWORK_SUBCOMMANDS[parsed.base_command]:
                    return "networked"
                if parsed.base_command == "git" and parsed.subcommand in _READ_ONLY_GIT_SUBCOMMANDS:
                    return "read_only"
                if parsed.base_command == "docker" and parsed.subcommand in {"ps", "images", "inspect", "logs"}:
                    return "read_only"
                if parsed.base_command in {"git", "docker"}:
                    return "workspace_write"
            else:
                return "networked"

        if self._is_workspace_write(segment, parsed):
            return "workspace_write"

        if parsed.base_command == "git":
            return "read_only" if parsed.subcommand in _READ_ONLY_GIT_SUBCOMMANDS else "workspace_write"

        if parsed.base_command == "find" and parsed.subcommand == "-exec":
            return "workspace_write"

        if parsed.base_command in _READ_ONLY_COMMANDS:
            return "read_only"

        return "workspace_write"

    def _classify_bash(self, command: str) -> str:
        segment_classes = [self._classify_segment(segment) for segment in self._split_segments(command)]
        if not segment_classes:
            return "workspace_write"
        priority = (
            "privileged_or_escape",
            "networked",
            "destructive",
            "code_execution",
            "workspace_write",
            "read_only",
        )
        for classification in priority:
            if classification in segment_classes:
                return classification
        return "workspace_write"

    def check_bash(self, *, context: PermissionContext, command: str) -> PermissionDecision:
        classification = self._classify_bash(command)
        return self._decision_for_classification(context=context, classification=classification, shell_name="bash")

    def check_powershell(self, *, context: PermissionContext, command: str) -> PermissionDecision:
        classification = classify_powershell_command(command).classification
        return self._decision_for_classification(context=context, classification=classification, shell_name="powershell")

    def _decision_for_classification(
        self, *, context: PermissionContext, classification: str, shell_name: str
    ) -> PermissionDecision:
        if classification == "read_only":
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                reason=f"{shell_name} read-only command",
                metadata=MappingProxyType({"classification": classification}),
            )

        if classification in {"privileged_or_escape", "networked", "destructive", "code_execution"}:
            return PermissionDecision(
                behavior=PermissionBehavior.ASK,
                reason=f"{shell_name} command classified as {classification}",
                metadata=MappingProxyType({"classification": classification}),
            )

        if context.mode is PermissionMode.ACCEPT_EDITS:
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                reason=f"{shell_name} workspace write allowed by accept_edits",
                metadata=MappingProxyType({"classification": classification}),
            )

        return PermissionDecision(
            behavior=PermissionBehavior.ASK,
            reason=f"{shell_name} command classified as {classification}",
            metadata=MappingProxyType({"classification": classification}),
        )
