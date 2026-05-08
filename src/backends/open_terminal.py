"""OpenTerminal remote backend for Aethos.

Provides OpenTerminalBackend that delegates execute/upload/download to a running
open-terminal HTTP service (github.com/open-webui/open-terminal).

Usage:
    backend = OpenTerminalBackend(
        base_url="http://localhost:8000",
        api_key="your-api-key",
    )
    result = backend.execute("echo hello")
    # → ExecuteResponse(output="hello", exit_code=0, ...)
"""

from __future__ import annotations

import time
import logging
from uuid import uuid4

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "httpx is required for OpenTerminalBackend. Install with: pip install 'aethos[open-terminal]'"
    ) from e

from src.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from src.backends.sandbox import CommandBackedBackend

logger = logging.getLogger(__name__)


def _join_output(entries: list[dict]) -> str:
    """Join log entries [{"type": "stdout", "data": "..."}] to a single string."""
    return "".join(e.get("data", "") for e in entries if isinstance(e, dict))


class OpenTerminalBackend(CommandBackedBackend):
    """Backend that delegates to an open-terminal HTTP service.

    The service must be running at base_url with OPEN_TERMINAL_API_KEY set.
    All filesystem and execute operations happen inside the service's container/process.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        api_key: str | None = None,
        user_id: str | None = None,
        timeout: int = 120,
    ) -> None:
        """Initialize OpenTerminalBackend.

        Args:
            base_url: open-terminal service URL (default: http://localhost:8000)
            api_key: OPEN_TERMINAL_API_KEY for Bearer token authentication
            user_id: OpenWebUI user ID (for multi-user mode; sent as X-User-Id header)
            timeout: Default timeout for execute commands in seconds (max 300)
        """
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key or ""
        self._timeout = min(timeout, 300)  # API limits to 300
        self._id = f"open-terminal-{uuid4().hex[:8]}"

        headers = {"Authorization": f"Bearer {self._api_key}"}
        if user_id:
            headers["X-User-Id"] = user_id

        self._client = httpx.Client(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout + 5,  # slightly longer than wait timeout
        )

        logger.info(
            "OpenTerminalBackend initialized (id=%s, url=%s, user_id=%s)",
            self._id,
            self._base_url,
            user_id,
        )

    @property
    def id(self) -> str:
        """Unique identifier for this sandbox instance."""
        return self._id

    @property
    def supported_shells(self) -> set[str]:
        return {"bash"}

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Execute a shell command inside the open-terminal service.

        The service's /execute endpoint is async by design. It starts a background
        process and returns immediately. We use the `wait` parameter to wait up to
        N seconds for completion. If still running, we poll for the result.

        Args:
            command: Shell command to run
            timeout: Override default timeout in seconds (max 300)

        Returns:
            ExecuteResponse with output and exit code
        """
        effective_timeout = (
            min(timeout, 300) if timeout is not None else self._timeout
        )

        logger.debug("Executing command (timeout=%d): %s", effective_timeout, command)

        try:
            resp = self._client.post(
                "/execute",
                json={"command": command},
                params={"wait": effective_timeout},
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            output = f"Command timed out after {effective_timeout}s"
            logger.warning(output)
            return ExecuteResponse(output=output, exit_code=1, truncated=False)
        except httpx.HTTPStatusError as e:
            output = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
            logger.warning("HTTP error executing command: %s", output)
            return ExecuteResponse(output=output, exit_code=1, truncated=False)
        except httpx.HTTPError as e:
            output = f"HTTP error: {str(e)}"
            logger.warning("HTTP error: %s", output)
            return ExecuteResponse(output=output, exit_code=1, truncated=False)

        # Join output entries
        output = _join_output(data.get("output", []))

        # If still running after wait, poll for completion
        status = data.get("status", "running")
        if status == "running":
            process_id = data["id"]
            next_offset = data.get("next_offset", 0)
            logger.debug("Process still running (id=%s), polling", process_id)
            poll_data = self._poll_until_done(process_id, next_offset)
            additional_output = _join_output(poll_data.get("output", []))
            output += additional_output
            status = poll_data.get("status", "error")
            data = poll_data

        # Determine exit code
        exit_code = data.get("exit_code")
        if exit_code is None:
            exit_code = 0 if status == "done" else 1

        truncated = data.get("truncated", False)

        logger.debug(
            "Command executed (exit_code=%d, truncated=%s, status=%s)",
            exit_code,
            truncated,
            status,
        )

        return ExecuteResponse(
            output=output,
            exit_code=exit_code,
            truncated=truncated,
        )

    def _poll_until_done(
        self, process_id: str, offset: int = 0, max_wait: float = 60
    ) -> dict:
        """Poll process status until done or timeout.

        Args:
            process_id: Process ID from execute response
            offset: Output offset to start polling from
            max_wait: Maximum seconds to wait for completion

        Returns:
            Final response dict with status, exit_code, and accumulated output
        """
        deadline = time.time() + max_wait
        all_output = []

        while time.time() < deadline:
            remaining = min(10.0, deadline - time.time())
            if remaining <= 0:
                break

            try:
                resp = self._client.get(
                    f"/execute/{process_id}/status",
                    params={"wait": remaining, "offset": offset},
                )
                resp.raise_for_status()
                data = resp.json()
            except httpx.HTTPError as e:
                logger.warning("Error polling process %s: %s", process_id, e)
                return {
                    "status": "error",
                    "exit_code": 1,
                    "output": all_output,
                }

            output_entries = data.get("output", [])
            all_output.extend(output_entries)
            offset = data.get("next_offset", offset)

            status = data.get("status", "running")
            if status != "running":
                data["output"] = all_output
                return data

        # Timed out — return partial result
        logger.warning("Poll timeout for process %s", process_id)
        return {
            "status": "running",
            "exit_code": None,
            "output": all_output,
        }

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files into the open-terminal service.

        Uses POST /files/write with JSON body for simplicity. Converts bytes to string
        using UTF-8 with replacement of undecodable bytes.

        Args:
            files: List of (path, content_bytes) tuples

        Returns:
            List of FileUploadResponse per file
        """
        responses: list[FileUploadResponse] = []

        for path, content in files:
            try:
                # Decode bytes to string safely
                text_content = content.decode("utf-8", errors="replace")

                resp = self._client.post(
                    "/files/write",
                    json={"path": path, "content": text_content},
                )
                resp.raise_for_status()
                logger.debug("Uploaded file: %s (%d bytes)", path, len(content))
                responses.append(FileUploadResponse(path=path, error=None))
            except httpx.HTTPStatusError as e:
                error = f"HTTP {e.response.status_code}: {e.response.text[:100]}"
                logger.warning("Failed to upload %s: %s", path, error)
                responses.append(FileUploadResponse(path=path, error=error))
            except httpx.HTTPError as e:
                error = str(e)
                logger.warning("Failed to upload %s: %s", path, error)
                responses.append(FileUploadResponse(path=path, error=error))

        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from the open-terminal service.

        Handles both text files (JSON response with content field) and binary files
        (raw binary response for images, etc.).

        Args:
            paths: List of file paths to download

        Returns:
            List of FileDownloadResponse per file
        """
        responses: list[FileDownloadResponse] = []

        for path in paths:
            try:
                resp = self._client.get(
                    "/files/read",
                    params={"path": path},
                )

                if resp.status_code == 404:
                    responses.append(
                        FileDownloadResponse(path=path, error="file_not_found")
                    )
                    continue

                resp.raise_for_status()

                # Check content type to determine response format
                content_type = resp.headers.get("content-type", "")
                if "json" in content_type or "application/json" in content_type:
                    # Text file response
                    data = resp.json()
                    content_str = data.get("content", "")
                    content_bytes = content_str.encode("utf-8")
                else:
                    # Binary response (images, etc.)
                    content_bytes = resp.content

                logger.debug("Downloaded file: %s (%d bytes)", path, len(content_bytes))
                responses.append(FileDownloadResponse(path=path, content=content_bytes))

            except httpx.HTTPStatusError as e:
                error = f"HTTP {e.response.status_code}"
                logger.warning("Failed to download %s: %s", path, error)
                responses.append(FileDownloadResponse(path=path, error=error))
            except httpx.HTTPError as e:
                error = str(e)
                logger.warning("Failed to download %s: %s", path, error)
                responses.append(FileDownloadResponse(path=path, error=error))
            except Exception as e:
                error = str(e)
                logger.warning("Unexpected error downloading %s: %s", path, error)
                responses.append(FileDownloadResponse(path=path, error=error))

        return responses

    def __del__(self):
        """Cleanup: close the HTTP client."""
        try:
            self._client.close()
        except Exception:
            pass


# Backward-compatible alias while call sites migrate.
OpenTerminalSandbox = OpenTerminalBackend
