"""Aethos execution backends.

Backends abstract where code executes and where files live.

- LocalBackend   — subprocess + pathlib on the local machine (default)
- DaytonaBackend — remote isolated container via Daytona SDK
"""

from src.backends.local import LocalBackend, LocalSandbox
from src.backends.protocol import (
    EditResult,
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
    SandboxProtocol,
)

__all__ = [
    "LocalBackend",
    "LocalSandbox",
    "SandboxProtocol",
    "ExecuteResponse",
    "FileDownloadResponse",
    "FileUploadResponse",
    "EditResult",
]
