from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from starlette.testclient import TestClient

from src.app import create_app
from src.app.dependencies import get_thread_store
from src.app.modules.files.schemas import ImportFromSandboxRequest


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/guest", json={})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_files_are_scoped_to_current_user() -> None:
    with TestClient(create_app()) as client:
        headers_a = _auth_headers(client)
        headers_b = _auth_headers(client)

        upload = client.post(
            "/api/files/",
            headers=headers_a,
            files={"file": ("hello.txt", b"hello world", "text/plain")},
        )
        assert upload.status_code == 200
        file_id = upload.json()["id"]

        mine = client.get("/api/files/", headers=headers_a)
        assert mine.status_code == 200
        assert [item["id"] for item in mine.json()["data"]] == [file_id]

        other = client.get(f"/api/files/{file_id}", headers=headers_b)
        assert other.status_code == 404


def test_files_all_route_is_removed() -> None:
    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        response = client.get("/api/files/all", headers=headers)
        assert response.status_code == 404


def test_import_request_accepts_thread_id_and_legacy_sandbox_id() -> None:
    assert ImportFromSandboxRequest.model_validate({"thread_id": "thread-1", "path": "/tmp/a.txt"}).thread_id == "thread-1"
    assert ImportFromSandboxRequest.model_validate({"sandbox_id": "thread-2", "path": "/tmp/a.txt"}).thread_id == "thread-2"


def test_import_from_sandbox_rejects_other_users_thread() -> None:
    with TestClient(create_app()) as client:
        headers_a = _auth_headers(client)
        headers_b = _auth_headers(client)
        thread = client.post("/v1/threads", headers=headers_a).json()

        response = client.post(
            "/api/files/import-from-sandbox",
            headers=headers_b,
            json={"thread_id": thread["id"], "path": "/tmp/out.txt"},
        )

    assert response.status_code == 404


def test_select_local_folder_returns_selected_path() -> None:
    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        with patch("src.app.modules.files.router._pick_local_directory_path", return_value=str(Path.cwd())):
            response = client.post("/api/files/select-local-folder", headers=headers)

    assert response.status_code == 200
    assert response.json()["root_dir"] == str(Path.cwd().resolve())


def test_select_local_folder_returns_400_when_user_cancels() -> None:
    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        with patch("src.app.modules.files.router._pick_local_directory_path", return_value=None):
            response = client.post("/api/files/select-local-folder", headers=headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "No folder selected"


def test_import_from_sandbox_local_backend_does_not_touch_daytona(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    artifact = workspace / "report.txt"
    artifact.write_text("hello", encoding="utf-8")

    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        thread = client.post("/v1/threads", headers=headers).json()
        client.app.state.daytona_manager = SimpleNamespace(
            get_backend=lambda _thread_id: (_ for _ in ()).throw(AssertionError("Daytona should not be used for local imports")),
            shutdown=lambda: None,
        )
        get_thread_store().update_session_metadata(
            thread_id=thread["id"],
            user_id=thread["user_id"],
            workspace_root=str(workspace),
            backend="local",
            status="idle",
        )

        response = client.post(
            "/api/files/import-from-sandbox",
            headers=headers,
            json={"thread_id": thread["id"], "path": "report.txt"},
        )

    assert response.status_code == 200
    assert response.json()["filename"] == "report.txt"


def test_import_from_sandbox_rejects_unknown_backend(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        thread = client.post("/v1/threads", headers=headers).json()
        get_thread_store().update_session_metadata(
            thread_id=thread["id"],
            user_id=thread["user_id"],
            workspace_root=str(workspace),
            backend="legacy",
            status="idle",
        )

        response = client.post(
            "/api/files/import-from-sandbox",
            headers=headers,
            json={"thread_id": thread["id"], "path": "report.txt"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported thread backend for file import: legacy"
