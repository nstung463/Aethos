from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from src.app.features.auth.postgres_repository import PostgresAuthRepository
from src.app.repositories.auth_repository import _hash_token
from tests.auth_repository_contract import exercise_auth_repository_contract


def _require_test_engine() -> Engine:
    pytest.importorskip("psycopg")
    database_url = os.environ.get("AETHOS_TEST_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("AETHOS_TEST_DATABASE_URL is not configured for PostgreSQL contract testing")

    engine = create_engine(database_url, future=True, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except OperationalError:
        pytest.skip("Configured PostgreSQL test database is not available")
    return engine


def _reset_auth_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS oauth_states")
        conn.exec_driver_sql("DROP TABLE IF EXISTS auth_sessions")
        conn.exec_driver_sql("DROP TABLE IF EXISTS auth_identities")
        conn.exec_driver_sql("DROP TABLE IF EXISTS users")
        conn.exec_driver_sql(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                permission_defaults JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE auth_identities (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider TEXT NOT NULL,
                provider_subject TEXT NOT NULL,
                email TEXT NULL,
                profile JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_auth_identities_provider_subject UNIQUE (provider, provider_subject)
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE auth_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                session_token_hash TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                last_used_at TIMESTAMPTZ NOT NULL,
                revoked_at TIMESTAMPTZ NULL,
                ip TEXT NULL,
                user_agent TEXT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE oauth_states (
                state TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                expires_at TIMESTAMPTZ NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def test_postgres_auth_repository_contract_when_database_available() -> None:
    engine = _require_test_engine()
    _reset_auth_schema(engine)

    exercise_auth_repository_contract(lambda: PostgresAuthRepository(engine=engine))


def test_postgres_auth_repository_refreshes_session_when_near_expiry() -> None:
    engine = _require_test_engine()
    _reset_auth_schema(engine)
    repo = PostgresAuthRepository(
        engine=engine,
        session_ttl_seconds=600,
        session_refresh_interval_seconds=300,
    )

    _, session = repo.create_guest_session(display_name="Refresh")

    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            UPDATE auth_sessions
            SET expires_at = to_timestamp(%s), last_used_at = to_timestamp(%s)
            WHERE session_token_hash = %s
            """,
            (session.created_at + 10, session.created_at, _hash_token(session.token)),
        )

    loaded = repo.get_session(session.token)

    assert loaded is not None
    assert loaded.expires_at > session.created_at + 10
    assert loaded.last_used_at >= session.last_used_at
