from __future__ import annotations

from unittest.mock import AsyncMock, patch

from starlette.testclient import TestClient

from src.app import create_app
from src.app.core.settings import get_settings


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/guest", json={})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_default_cors_origins_are_allowlisted() -> None:
    settings = get_settings()
    assert "*" not in (settings.cors_allow_origins or [])


def test_guest_session_creation_is_rate_limited(monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_AUTH_GUEST_SESSION_LIMIT", "1")
    with TestClient(create_app()) as client:
        first = client.post("/auth/guest", json={})
        second = client.post("/auth/guest", json={})

    assert first.status_code == 200
    assert second.status_code == 429
    assert 1 <= int(second.headers["Retry-After"]) <= 60


def test_terminal_creation_is_rate_limited(monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_TERMINAL_CREATE_LIMIT", "1")
    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        thread = client.post("/v1/threads", headers=headers).json()
        with patch("src.app.modules.terminals.router._proxy", new_callable=AsyncMock, return_value={"ok": True}):
            first = client.post(f"/api/terminals/{thread['id']}/api/terminals", headers=headers, json={})
            second = client.post(f"/api/terminals/{thread['id']}/api/terminals", headers=headers, json={})

    assert first.status_code == 200
    assert second.status_code == 429


def test_file_upload_rejects_oversized_payload(monkeypatch) -> None:
    monkeypatch.setenv("AETHOS_MANAGED_FILE_MAX_BYTES", "4")
    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        response = client.post(
            "/api/files/",
            headers=headers,
            files={"file": ("large.txt", b"12345", "text/plain")},
        )

    assert response.status_code == 413
    assert response.json()["detail"] == "Uploaded file exceeds size limit"
