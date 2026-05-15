from __future__ import annotations

from starlette.testclient import TestClient

from src.app import create_app


def test_connection_callback_returns_400_for_invalid_oauth_state(postgres_database: str) -> None:
    del postgres_database

    with TestClient(create_app(), raise_server_exceptions=False) as client:
        response = client.get(
            "/v1/extensions/connections/google-drive/callback",
            params={"code": "auth-code", "state": "missing-state"},
        )

    assert response.status_code == 400
    assert "OAuth state is invalid or unavailable." in response.text
