from __future__ import annotations

import asyncio
import mimetypes
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from src.app.core.settings import get_settings
from src.app.dependencies import (
    enforce_rate_limit,
    get_current_user,
    get_file_store,
    get_open_terminal_api_key,
    get_open_terminal_base_url,
    get_thread_store,
)
from src.app.modules.auth.repository import AuthUser
from src.app.modules.files.schemas import ContentUpdateRequest, ImportFromSandboxRequest
from src.app.services.file_store import FileStore
from src.app.services.rate_limiter import RateLimitRule
from src.app.services.thread_store import ThreadStore

router = APIRouter(prefix="/api/files", tags=["files"])


def _pick_local_directory_path() -> str | None:
    if os.name == "nt":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$dialog.Description = 'Select local project folder'; "
            "$dialog.ShowNewFolderButton = $false; "
            "if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            "Write-Output $dialog.SelectedPath }"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "Folder picker command failed.")
        return result.stdout.strip() or None

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - platform specific import
        raise RuntimeError("Folder picker is unavailable on this platform.") from exc

    root = tk.Tk()
    root.withdraw()
    selected = filedialog.askdirectory(title="Select local project folder")
    root.destroy()
    return selected or None


@router.post("/")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    store: FileStore = Depends(get_file_store),
    current_user: AuthUser = Depends(get_current_user),
):
    settings = get_settings()
    enforce_rate_limit(
        request=request,
        rule=RateLimitRule(
            scope="files_write",
            limit=settings.file_write_limit,
            window_seconds=settings.file_write_window_seconds,
        ),
        user=current_user,
    )
    suffix = Path(file.filename or "upload.bin").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        content = await file.read()
        if len(content) > settings.managed_file_max_bytes:
            raise HTTPException(status_code=413, detail="Uploaded file exceeds size limit")
        if store.total_usage_bytes(owner_user_id=current_user.id) + len(content) > settings.managed_file_total_bytes_per_user:
            raise HTTPException(status_code=413, detail="User file storage quota exceeded")
        temp.write(content)
        temp_path = Path(temp.name)

    try:
        record = store.save_upload(
            filename=file.filename or "upload.bin",
            content_type=file.content_type,
            source_path=temp_path,
            owner_user_id=current_user.id,
        )
        return record
    finally:
        temp_path.unlink(missing_ok=True)


@router.get("/")
async def list_files(
    store: FileStore = Depends(get_file_store),
    current_user: AuthUser = Depends(get_current_user),
):
    return {"data": store.list_files(owner_user_id=current_user.id)}


@router.get("/search")
async def search_files(
    filename: str = Query("*"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1),
    store: FileStore = Depends(get_file_store),
    current_user: AuthUser = Depends(get_current_user),
):
    needle = filename.strip("*").lower()
    items = store.list_files(owner_user_id=current_user.id)
    if needle:
        items = [item for item in items if needle in item.get("filename", "").lower()]
    return items[skip : skip + limit]


@router.post("/upload/dir")
async def upload_dir():
    return {"status": True}


@router.post("/select-local-folder")
async def select_local_folder(
    request: Request,
    current_user: AuthUser = Depends(get_current_user),
):
    settings = get_settings()
    enforce_rate_limit(
        request=request,
        rule=RateLimitRule(
            scope="files_write",
            limit=settings.file_write_limit,
            window_seconds=settings.file_write_window_seconds,
        ),
        user=current_user,
    )
    try:
        selected = await asyncio.to_thread(_pick_local_directory_path)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if not selected:
        raise HTTPException(status_code=400, detail="No folder selected")

    root_dir = Path(selected).expanduser().resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        raise HTTPException(status_code=400, detail=f"Selected folder is invalid: {root_dir}")

    return {"root_dir": str(root_dir)}


@router.post("/import-from-sandbox")
async def import_from_sandbox(
    request: Request,
    payload: ImportFromSandboxRequest,
    store: FileStore = Depends(get_file_store),
    base_url: str = Depends(get_open_terminal_base_url),
    api_key: str = Depends(get_open_terminal_api_key),
    current_user: AuthUser = Depends(get_current_user),
    thread_store: ThreadStore = Depends(get_thread_store),
):
    settings = get_settings()
    enforce_rate_limit(
        request=request,
        rule=RateLimitRule(
            scope="files_write",
            limit=settings.file_write_limit,
            window_seconds=settings.file_write_window_seconds,
        ),
        user=current_user,
    )
    if not thread_store.get_owned_thread(thread_id=payload.thread_id, user_id=current_user.id):
        raise HTTPException(status_code=404, detail="Thread not found")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(
            f"{base_url}/files/view",
            params={"path": payload.path},
            headers=headers,
        )
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Sandbox file not found")
        response.raise_for_status()
        if len(response.content) > settings.managed_file_max_bytes:
            raise HTTPException(status_code=413, detail="Imported file exceeds size limit")
        if (
            store.total_usage_bytes(owner_user_id=current_user.id) + len(response.content)
            > settings.managed_file_total_bytes_per_user
        ):
            raise HTTPException(status_code=413, detail="User file storage quota exceeded")
        filename = payload.filename or Path(payload.path).name or "artifact.bin"
        content_type = payload.content_type or response.headers.get("content-type")
        return store.import_bytes(
            filename=filename,
            content=response.content,
            content_type=content_type,
            owner_user_id=current_user.id,
            thread_id=payload.thread_id,
        )


@router.get("/{file_id}")
async def get_file(
    file_id: str,
    store: FileStore = Depends(get_file_store),
    current_user: AuthUser = Depends(get_current_user),
):
    record = store.get_file(file_id, owner_user_id=current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return record


@router.get("/{file_id}/content")
async def get_file_content(
    file_id: str,
    store: FileStore = Depends(get_file_store),
    current_user: AuthUser = Depends(get_current_user),
):
    record = store.get_file(file_id, owner_user_id=current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    media_type = record.get("meta", {}).get("content_type") or mimetypes.guess_type(record["filename"])[0]
    return FileResponse(path=record["path"], filename=record["filename"], media_type=media_type)


@router.get("/{file_id}/content/html")
async def get_file_content_html(
    file_id: str,
    store: FileStore = Depends(get_file_store),
    current_user: AuthUser = Depends(get_current_user),
):
    return await get_file_content(file_id=file_id, store=store, current_user=current_user)


@router.get("/{file_id}/process/status")
async def get_process_status(file_id: str):
    async def event_stream():
        yield 'data: {"ok": true}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/{file_id}/data/content/update")
async def update_file_content(
    file_id: str,
    payload: ContentUpdateRequest,
    store: FileStore = Depends(get_file_store),
    current_user: AuthUser = Depends(get_current_user),
):
    record = store.update_content(file_id, payload.content, owner_user_id=current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="File not found")
    return record


@router.delete("/{file_id}")
async def delete_file(
    file_id: str,
    store: FileStore = Depends(get_file_store),
    current_user: AuthUser = Depends(get_current_user),
):
    if not store.delete_file(file_id, owner_user_id=current_user.id):
        raise HTTPException(status_code=404, detail="File not found")
    return {"status": True}
