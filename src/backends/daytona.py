"""Daytona remote backend for Aethos."""

from __future__ import annotations

import os
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from src.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
from src.backends.sandbox import CommandBackedBackend
from src.logger import get_logger

logger = get_logger(__name__)


class DaytonaUnavailableError(RuntimeError):
    """Raised when the optional Daytona SDK is unavailable."""


def _raise_daytona_unavailable(exc: ModuleNotFoundError) -> None:
    if exc.name != "daytona":
        raise exc
    raise DaytonaUnavailableError(
        "daytona package not installed. Run: pip install 'aethos[daytona]'"
    ) from exc


class DaytonaBackend(CommandBackedBackend):
    """Daytona remote isolated backend."""

    def __init__(self, *, sandbox: object, timeout: int = 30 * 60) -> None:
        self._sandbox = sandbox
        self._default_timeout = timeout

    @property
    def id(self) -> str:
        return str(self._sandbox.id)  # type: ignore[attr-defined]

    @property
    def supported_shells(self) -> set[str]:
        return {"bash"}

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        effective_timeout = timeout if timeout is not None else self._default_timeout
        logger.debug("Executing command in Daytona sandbox (sandbox_id=%s)", self.id)
        try:
            result = self._sandbox.process.exec(command, timeout=effective_timeout)  # type: ignore[attr-defined]
        except Exception as exc:
            logger.exception("Daytona exec failed (sandbox_id=%s)", self.id)
            return ExecuteResponse(output=f"Daytona exec failed: {exc}", exit_code=1, truncated=False)

        return ExecuteResponse(output=result.result or "", exit_code=result.exit_code, truncated=False)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        try:
            from daytona import FileUpload
        except ImportError:
            return [FileUploadResponse(path=path, error="daytona not installed") for path, _ in files]

        responses: list[FileUploadResponse] = []
        upload_requests = []

        for path, content in files:
            if not path.startswith("/"):
                responses.append(FileUploadResponse(path=path, error="invalid_path: must be absolute"))
                continue
            upload_requests.append((path, FileUpload(source=content, destination=path)))
            responses.append(FileUploadResponse(path=path))

        if upload_requests:
            self._sandbox.fs.upload_files([request for _, request in upload_requests])  # type: ignore[attr-defined]

        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        try:
            from daytona import FileDownloadRequest
        except ImportError:
            return [FileDownloadResponse(path=path, error="daytona not installed") for path in paths]

        responses: list[FileDownloadResponse] = []
        valid_indices: list[int] = []
        download_requests: list[FileDownloadRequest] = []

        for index, path in enumerate(paths):
            if not path.startswith("/"):
                responses.append(FileDownloadResponse(path=path, error="invalid_path"))
                continue
            valid_indices.append(index)
            download_requests.append(FileDownloadRequest(source=path))
            responses.append(FileDownloadResponse(path=path))

        if download_requests:
            daytona_responses = self._sandbox.fs.download_files(download_requests)  # type: ignore[attr-defined]
            for index, response in zip(valid_indices, daytona_responses):
                if response.result is None:
                    responses[index] = FileDownloadResponse(path=paths[index], error="file_not_found")
                else:
                    responses[index] = FileDownloadResponse(path=paths[index], content=response.result)

        return responses


@dataclass(frozen=True)
class DaytonaBackendLease:
    backend: DaytonaBackend
    sandbox_name: str
    is_new: bool


def _run_setup_script(backend: DaytonaBackend, setup_script_path: str) -> None:
    if not os.path.exists(setup_script_path):
        logger.warning("Setup script not found: %s", setup_script_path)
        return
    with open(setup_script_path, encoding="utf-8") as file:
        script = file.read()
    logger.info("Running Daytona setup script: %s", setup_script_path)
    backend.execute(script)


def _get_daytona_client() -> object:
    try:
        from daytona import Daytona, DaytonaConfig
    except ModuleNotFoundError as exc:
        _raise_daytona_unavailable(exc)

    api_key = os.environ.get("DAYTONA_API_KEY")
    if not api_key:
        raise ValueError("DAYTONA_API_KEY environment variable not set")

    return Daytona(DaytonaConfig(api_key=api_key))


def _wait_until_ready(sandbox: object, *, delete_on_failure: bool) -> None:
    for _ in range(90):
        try:
            ready = sandbox.process.exec("echo ready", timeout=5)  # type: ignore[attr-defined]
            if ready.exit_code == 0:
                return
        except Exception:
            pass
        time.sleep(2)

    if delete_on_failure:
        sandbox.delete()  # type: ignore[attr-defined]
    raise RuntimeError("Daytona sandbox failed to start within 180 seconds")


def get_or_create_daytona_backend(
    *,
    conversation_id: str,
    setup_script_path: str | None = None,
    auto_delete_interval: int = 10,
) -> DaytonaBackendLease:
    """Create or reuse a Daytona sandbox and return a ready backend."""
    try:
        from daytona import CreateSandboxBaseParams
        from daytona.common.errors import DaytonaError
    except ModuleNotFoundError as exc:
        _raise_daytona_unavailable(exc)

    logger.info("Creating or reusing Daytona sandbox (conversation_id=%s)", conversation_id)
    daytona = _get_daytona_client()
    sandbox_name = conversation_id

    is_new = False
    try:
        sandbox = daytona.create(
            params=CreateSandboxBaseParams(
                name=sandbox_name,
                auto_delete_interval=auto_delete_interval,
            )
        )
        is_new = True
        logger.info("Created new Daytona sandbox: %s", sandbox_name)
    except DaytonaError as exc:
        if "already exists" in str(exc):
            sandbox = daytona.get(sandbox_id_or_name=sandbox_name)
            logger.info("Reusing existing Daytona sandbox: %s", sandbox_name)
        else:
            raise

    _wait_until_ready(sandbox, delete_on_failure=is_new)
    backend = DaytonaBackend(sandbox=sandbox)
    logger.info("Daytona sandbox ready (sandbox_id=%s)", backend.id)

    if is_new:
        if setup_script_path is None:
            project_root = Path(__file__).resolve().parents[2]
            default_setup = project_root / "scripts" / "setup_daytona_sandbox.sh"
            if default_setup.exists():
                setup_script_path = str(default_setup)
        if setup_script_path:
            _run_setup_script(backend, setup_script_path)

    return DaytonaBackendLease(
        backend=backend,
        sandbox_name=sandbox_name,
        is_new=is_new,
    )


def delete_daytona_sandbox(*, sandbox_name: str) -> None:
    logger.info("Deleting Daytona sandbox: %s", sandbox_name)
    daytona = _get_daytona_client()
    sandbox = daytona.get(sandbox_id_or_name=sandbox_name)
    sandbox.delete()


@contextmanager
def create_daytona_sandbox(
    *,
    conversation_id: str,
    setup_script_path: str | None = None,
    output_dir: Path | None = None,
) -> Generator[DaytonaBackend, None, None]:
    """Create or reuse a Daytona sandbox for one-shot work."""
    if not os.environ.get("DAYTONA_API_KEY"):
        raise ValueError("DAYTONA_API_KEY environment variable not set")

    lease = get_or_create_daytona_backend(
        conversation_id=conversation_id,
        setup_script_path=setup_script_path,
    )
    backend = lease.backend

    try:
        yield backend
    finally:
        if output_dir:
            logger.info("Collecting output files to local dir: %s", output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            list_result = backend.execute("cd /tmp/OUTPUT_DIR && find . -type f 2>/dev/null | head -100")
            if list_result.exit_code == 0 and list_result.output.strip():
                rel_paths = [path.strip() for path in list_result.output.splitlines() if path.strip()]
                abs_paths = [f"/tmp/OUTPUT_DIR/{path.lstrip('./')}" for path in rel_paths]
                for response in backend.download_files(abs_paths):
                    if response.content is not None:
                        (output_dir / Path(response.path).name).write_bytes(response.content)
                        logger.debug("Downloaded output file: %s", response.path)
        delete_daytona_sandbox(sandbox_name=lease.sandbox_name)


# Backward-compatible alias while call sites migrate.
DaytonaSandbox = DaytonaBackend
