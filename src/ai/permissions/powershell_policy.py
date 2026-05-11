from __future__ import annotations

import base64
import re
from dataclasses import dataclass


_CMD_SEP = re.compile(r"\|\|?|&&|;")

# Common aliases (normalized lowercase)
_ALIASES = {
    "gci": "get-childitem",
    "ls": "get-childitem",
    "dir": "get-childitem",
    "gc": "get-content",
    "cat": "get-content",
    "gi": "get-item",
    "gl": "get-location",
    "pwd": "get-location",
    "sl": "set-location",
    "cd": "set-location",
    "chdir": "set-location",
    "ri": "remove-item",
    "del": "remove-item",
    "rd": "remove-item",
    "mi": "move-item",
    "ci": "copy-item",
    "ni": "new-item",
    "rni": "rename-item",
    "iwr": "invoke-webrequest",
    "irm": "invoke-restmethod",
    "iex": "invoke-expression",
}

_READ_ONLY_CMDLETS = frozenset(
    {
        "get-childitem",
        "get-content",
        "get-item",
        "get-location",
        "get-process",
        "get-service",
        "get-date",
        "select-string",
        "compare-object",
        "test-path",
        "select-object",
        "sort-object",
        "group-object",
        "where-object",
        "format-table",
        "format-list",
        "format-wide",
        "format-custom",
        "measure-object",
        "out-string",
    }
)

_WRITE_CMDLETS = frozenset(
    {
        "set-content",
        "out-file",
        "add-content",
        "new-item",
        "copy-item",
        "move-item",
        "rename-item",
        "set-itemproperty",
        "remove-item",
        "clear-content",
    }
)

_NETWORK_CMDLETS = frozenset({"invoke-webrequest", "invoke-restmethod"})

_PRIVILEGED_OR_ESCAPE = frozenset(
    {
        "invoke-expression",
        "start-process",
        "runas",
        "powershell",
        "pwsh",
    }
)

_DOWNLOAD_EXEC_COMBOS = (
    ("invoke-webrequest", "invoke-expression"),
    ("invoke-restmethod", "invoke-expression"),
)

_ENCODED_PARAM = re.compile(r"-(?:e|enc|encodedcommand)\b", re.IGNORECASE)
_REDIRECT_PATTERN = re.compile(r"(?:^|[\s;&|])(?:\d*>>?|&>>?)")


@dataclass(frozen=True)
class PowerShellClassification:
    classification: str


def _split_segments(command: str) -> list[str]:
    return [segment.strip() for segment in _CMD_SEP.split(command) if segment.strip()]


def _extract_first_token(segment: str) -> str:
    stripped = segment.strip()
    if not stripped:
        return ""
    if stripped.startswith("&"):
        stripped = stripped[1:].lstrip()
    if stripped.startswith(("'", '"')):
        q = stripped[0]
        end = stripped.find(q, 1)
        token = stripped[1:end] if end > 0 else stripped[1:]
    else:
        token = stripped.split()[0]
    token = token.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if token.lower().endswith(".exe"):
        token = token[:-4]
    return token.lower()


def _canonical_name(token: str) -> str:
    return _ALIASES.get(token, token)


def _all_command_names(command: str) -> list[str]:
    names: list[str] = []
    for segment in _split_segments(command):
        token = _extract_first_token(segment)
        if token:
            names.append(_canonical_name(token))
    return names


def _contains_encoded_execution(command: str) -> bool:
    lowered = command.lower()
    if "-encodedcommand" in lowered:
        return True
    if _ENCODED_PARAM.search(command) and ("pwsh" in lowered or "powershell" in lowered):
        return True
    # base64-ish payload indicator for common encoded invocations
    return bool(re.search(r"[A-Za-z0-9+/]{40,}={0,2}", command)) and ("encoded" in lowered)


def classify_powershell_command(command: str) -> PowerShellClassification:
    stripped = command.strip()
    if not stripped:
        return PowerShellClassification("workspace_write")

    names = _all_command_names(stripped)
    lowered = stripped.lower()

    if _contains_encoded_execution(stripped):
        return PowerShellClassification("privileged_or_escape")

    if any(name in _PRIVILEGED_OR_ESCAPE for name in names):
        return PowerShellClassification("privileged_or_escape")

    for downloader, executor in _DOWNLOAD_EXEC_COMBOS:
        if downloader in names and executor in names:
            return PowerShellClassification("privileged_or_escape")

    if any(name in _NETWORK_CMDLETS for name in names):
        return PowerShellClassification("networked")

    if any(name == "remove-item" for name in names):
        return PowerShellClassification("destructive")

    if _REDIRECT_PATTERN.search(stripped):
        return PowerShellClassification("workspace_write")

    if any(name in _WRITE_CMDLETS for name in names):
        return PowerShellClassification("workspace_write")

    if names and all(name in _READ_ONLY_CMDLETS for name in names):
        return PowerShellClassification("read_only")

    # External executable fallback: retain conservative default
    if re.match(r"^[a-z0-9_.-]+", lowered):
        return PowerShellClassification("workspace_write")

    return PowerShellClassification("workspace_write")
