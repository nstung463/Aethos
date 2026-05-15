from __future__ import annotations

from unittest.mock import patch

from starlette.testclient import TestClient

from src.app import create_app


def _auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/auth/guest", json={})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_http_exception_includes_request_id_in_body_and_header() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/v1/tasks/title", json={"model": "aethos", "messages": []})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert response.json()["request_id"]
    assert response.headers["X-Request-ID"] == response.json()["request_id"]


def test_unhandled_exception_returns_traceable_payload() -> None:
    app = create_app()
    with patch(
        "src.app.features.auth.service.AuthService.create_guest_session",
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


