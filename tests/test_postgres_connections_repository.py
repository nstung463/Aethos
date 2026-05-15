from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from src.app.db.models.connections import (
    ConnectionAuditModel,
    ConnectionModel,
    ConnectionSecretModel,
    OAuthStateModel,
)
from src.app.features.extensions.connections_service import ConnectionService
from src.app.repositories.connection_repository import (
    ConnectionRepository,
    ConnectionRepositorySchemaUnavailableError,
)


def _prepare_schema(database_url: str) -> None:
    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            ConnectionModel.__table__.create(bind=conn, checkfirst=True)
            ConnectionSecretModel.__table__.create(bind=conn, checkfirst=True)
            ConnectionAuditModel.__table__.create(bind=conn, checkfirst=True)
            OAuthStateModel.__table__.create(bind=conn, checkfirst=True)
            conn.exec_driver_sql(
                "TRUNCATE TABLE connection_audit, connection_secrets, connections, oauth_states RESTART IDENTITY CASCADE"
            )
    finally:
        engine.dispose()


def test_postgres_connection_repository_round_trip_when_database_available() -> None:
    pytest.importorskip("psycopg")
    database_url = os.environ.get("AETHOS_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("AETHOS_TEST_DATABASE_URL is not configured for PostgreSQL connection repository testing")

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except OperationalError:
        pytest.skip("Configured PostgreSQL test database is not available")

    _prepare_schema(database_url)
    repo = ConnectionRepository(sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True))

    record = repo.save_connection(
        connection_id=None,
        provider="google-gmail",
        owner_user_id="user-a",
        project_key="project-a",
        account_label="work@example.com",
        status="active",
        capabilities=["gmail"],
        scopes=["scope:a"],
    )
    repo.save_secret(connection_id=record.id, ciphertext="ciphertext-1")
    repo.append_audit(
        connection_id=record.id,
        user_id="user-a",
        tool_name="gmail_search_messages",
        action_kind="read",
        status="ok",
        request_summary=json.dumps({"query": "from:alice"}),
    )

    loaded = repo.get_connection(connection_id=record.id, owner_user_id="user-a")
    listed = repo.list_connections(owner_user_id="user-a", project_key="project-a")
    default = repo.get_default_connection(provider="google-gmail", owner_user_id="user-a", project_key="project-a")
    state = repo.create_oauth_state(
        provider="google-gmail",
        user_id="user-a",
        project_key="project-a",
        workspace_root="W:/aethos",
        redirect_to="http://localhost/settings",
    )
    payload = repo.consume_oauth_state(state=state, provider="google-gmail")

    assert loaded is not None
    assert loaded.account_label == "work@example.com"
    assert len(listed) == 1
    assert default is not None
    assert repo.load_secret(connection_id=record.id) == "ciphertext-1"
    assert payload["workspace_root"] == "W:/aethos"
    assert payload["redirect_to"] == "http://localhost/settings"

    with engine.begin() as conn:
        audit_rows = conn.exec_driver_sql(
            "SELECT tool_name, status FROM connection_audit WHERE connection_id = %s",
            (record.id,),
        ).fetchall()
    assert len(audit_rows) == 1
    assert audit_rows[0][0] == "gmail_search_messages"
    assert audit_rows[0][1] == "ok"

    assert repo.delete_connection(connection_id=record.id, owner_user_id="user-a") is True
    assert repo.get_connection(connection_id=record.id, owner_user_id="user-a") is None
    assert repo.load_secret(connection_id=record.id) is None


def test_postgres_connection_repository_fails_fast_when_schema_missing() -> None:
    pytest.importorskip("psycopg")
    database_url = os.environ.get("AETHOS_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("AETHOS_TEST_DATABASE_URL is not configured for PostgreSQL connection repository testing")

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except OperationalError:
        pytest.skip("Configured PostgreSQL test database is not available")

    schema_name = f"schema_missing_{uuid.uuid4().hex}"
    with engine.begin() as conn:
        conn.exec_driver_sql(f'CREATE SCHEMA "{schema_name}"')

    isolated_engine = create_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
        connect_args={"options": f"-c search_path={schema_name}"},
    )
    try:
        with pytest.raises(ConnectionRepositorySchemaUnavailableError, match="Run database migrations"):
            ConnectionRepository(sessionmaker(bind=isolated_engine, autoflush=False, expire_on_commit=False, future=True))
    finally:
        isolated_engine.dispose()
        with engine.begin() as conn:
            conn.exec_driver_sql(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE')


def test_connection_service_for_oauth_state_rejects_expired_postgres_state(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("psycopg")
    database_url = os.environ.get("AETHOS_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("AETHOS_TEST_DATABASE_URL is not configured for PostgreSQL connection repository testing")

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except OperationalError:
        pytest.skip("Configured PostgreSQL test database is not available")

    _prepare_schema(database_url)
    repo = ConnectionRepository(sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True))
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            INSERT INTO oauth_states(state, provider, payload_json, expires_at, created_at)
            VALUES (%s, %s, %s::jsonb, NOW() - INTERVAL '1 minute', NOW())
            """,
            (
                "expired-state",
                "google-gmail",
                json.dumps({
                    "workspace_root": "W:/aethos",
                    "project_key": "project-a",
                    "user_id": "user-a",
                }),
            ),
        )

    monkeypatch.setenv("AETHOS_DATABASE_ENABLED", "true")
    monkeypatch.setenv("AETHOS_DATABASE_URL", database_url)

    with pytest.raises(HTTPException, match="invalid or unavailable"):
        ConnectionService.for_oauth_state(state="expired-state", provider="google-gmail")
