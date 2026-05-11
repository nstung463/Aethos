"""PowerShell execution provider helpers.

Phase 2 keeps this provider focused on shell-specific wrapping so the shared
execution layer can own lifecycle concerns without flattening semantics.
"""

from __future__ import annotations

import base64
from pathlib import Path


def encode_powershell(command: str) -> str:
    return base64.b64encode(command.encode("utf-16le")).decode("ascii")


def build_powershell_wrapper(command: str) -> str:
    encoded = encode_powershell(command)
    return f"powershell -NoProfile -NonInteractive -EncodedCommand {encoded}"


def build_powershell_read_hint(path: Path) -> str:
    return f"Get-Content '{path.as_posix()}'"
