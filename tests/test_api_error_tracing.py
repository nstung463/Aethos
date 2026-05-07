from __future__ import annotations

from unittest.mock import patch

import httpx
from starlette.testclient import TestClient

from src.app import create_app


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/guest", json={})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_http_exception_includes_request_id_in_body_and_header() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/tasks/title", json={"model": "ethos", "messages": []})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert response.json()["request_id"]
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_unhandled_exception_returns_traceable_payload() -> None:
    app = create_app()
    with patch(
        "src.app.modules.auth.service.AuthService.create_guest_session",
        side_effect=RuntimeError("repository write failed"),
    ):
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post("/auth/guest", json={})

    assert response.status_code == 500
    body = response.json()
    assert body["detail"] == "Internal server error while handling POST /auth/guest"
    assert body["error_type"] == "RuntimeError"
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]


def test_terminal_proxy_error_returns_specific_detail() -> None:
    async def _raise_connect_error(*args, **kwargs):
        request = httpx.Request("GET", "http://localhost:8000/files/list?directory=/tmp")
        raise httpx.ConnectError("connection refused", request=request)

    with TestClient(create_app()) as client:
        headers = _auth_headers(client)
        thread_response = client.post("/v1/threads", headers=headers)
        assert thread_response.status_code == 200
        thread_id = thread_response.json()["id"]

        with patch("httpx.AsyncClient.request", side_effect=_raise_connect_error):
            response = client.get(
                f"/api/terminals/{thread_id}/files/list",
                params={"directory": "/tmp"},
                headers=headers,
            )

    assert response.status_code == 502
    body = response.json()
    assert "Failed to proxy terminal request GET /files/list" in body["detail"]
    assert "connection refused" in body["detail"]
    assert body["request_id"]
    assert response.headers["X-Request-ID"] == body["request_id"]
