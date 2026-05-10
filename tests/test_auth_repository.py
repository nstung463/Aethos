from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.app.core.settings import get_settings
from src.app.dependencies import get_auth_repository
from src.app.modules.auth.repository import AuthRepository, _hash_token
from src.app.services.storage_paths import StoragePathsService


def test_auth_repository_defaults_to_config_home_users(tmp_path: Path, monkeypatch) -> None:
    config_home = tmp_path / "home-aethos"
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("AETHOS_USERS_DIR", raising=False)
    monkeypatch.delenv("AETHOS_SECURITY_STATE_DIR", raising=False)
    get_settings.cache_clear()
    get_auth_repository.cache_clear()

    repo = get_auth_repository()
    user, session = repo.create_guest_session(display_name="Storage Test")
    storage = StoragePathsService(get_settings())

    assert storage.auth_db_path().exists()
    assert repo.get_user(user.id) is not None
    assert repo.get_session(session.token) is not None


def test_get_session_skips_refresh_within_interval(tmp_path: Path) -> None:
    repo = AuthRepository(tmp_path / "users", session_refresh_interval_seconds=300)
    user, session = repo.create_guest_session(display_name="No Rewrite")

    loaded = repo.get_session(session.token)

    assert loaded is not None
    assert loaded.last_used_at == session.last_used_at
    assert loaded.expires_at == session.expires_at
    assert repo.get_user(user.id) is not None


def test_get_session_refreshes_when_near_expiry(tmp_path: Path) -> None:
    repo = AuthRepository(
        tmp_path / "users",
        session_ttl_seconds=600,
        session_refresh_interval_seconds=300,
    )
    _, session = repo.create_guest_session(display_name="Refresh")
    original_expires_at = session.expires_at

    with repo._connect() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET expires_at = ?, last_used_at = ?
            WHERE token_hash = ?
            """,
            (
                session.created_at + 10,
                session.created_at,
                _hash_token(session.token),
            ),
        )

    loaded = repo.get_session(session.token)

    assert loaded is not None
    assert loaded.expires_at > session.created_at + 10
    assert loaded.last_used_at >= session.last_used_at


def test_expired_session_is_rejected_and_deleted(tmp_path: Path) -> None:
    repo = AuthRepository(tmp_path / "users", session_ttl_seconds=600)
    _, session = repo.create_guest_session(display_name="Expired")

    with repo._connect() as conn:
        conn.execute(
            "UPDATE sessions SET expires_at = ? WHERE token_hash = ?",
            (session.created_at - 1, _hash_token(session.token)),
        )

    assert repo.get_session(session.token) is None
    with repo._connect() as conn:
        remaining = conn.execute(
            "SELECT 1 FROM sessions WHERE token_hash = ?",
            (_hash_token(session.token),),
        ).fetchone()
    assert remaining is None


def test_permission_defaults_round_trip_in_sqlite(tmp_path: Path) -> None:
    repo = AuthRepository(tmp_path / "users")
    user, _ = repo.create_guest_session(display_name="Permissions")

    saved = repo.update_permission_defaults(
        user_id=user.id,
        defaults={
            "mode": "acceptEdits",
            "working_directories": ["W:/aethos"],
            "rules": [{"tool": "shell", "decision": "allow"}],
        },
    )

    assert saved is not None
    assert repo.get_permission_defaults(user.id) == saved


def test_migrates_legacy_json_profile_and_session_once(tmp_path: Path) -> None:
    users_root = tmp_path / "users"
    user_id = "user_legacy"
    token = "legacy-token"
    user_dir = users_root / user_id
    (user_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (user_dir / "profile.json").write_text(
        json.dumps(
            {
                "id": user_id,
                "display_name": "Legacy User",
                "created_at": 100,
                "permission_defaults": {"mode": "default", "working_directories": [], "rules": []},
            }
        ),
        encoding="utf-8",
    )
    (user_dir / "sessions" / f"{_hash_token(token)}.json").write_text(
        json.dumps(
            {
                "token": token,
                "user_id": user_id,
                "created_at": 100,
                "expires_at": 4_102_444_800,
                "last_used_at": 150,
            }
        ),
        encoding="utf-8",
    )
    marker = tmp_path / "migrations" / "auth.migrated"

    repo = AuthRepository(users_root, db_path=tmp_path / "auth.db", migration_marker_path=marker)

    loaded = repo.get_session(token)
    assert loaded is not None
    assert loaded.user_id == user_id
    assert repo.get_user(user_id) is not None
    assert marker.exists()

    with (user_dir / "profile.json").open("w", encoding="utf-8") as fh:
        json.dump({"id": user_id, "display_name": "Changed", "created_at": 100}, fh)

    repo_again = AuthRepository(users_root, db_path=tmp_path / "auth.db", migration_marker_path=marker)
    loaded_user = repo_again.get_user(user_id)
    assert loaded_user is not None
    assert loaded_user.display_name == "Legacy User"


def test_migration_skips_malformed_legacy_files(tmp_path: Path) -> None:
    users_root = tmp_path / "users"
    user_dir = users_root / "user_bad"
    (user_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (user_dir / "profile.json").write_text("{not-json", encoding="utf-8")
    (user_dir / "sessions" / "broken.json").write_text("{not-json", encoding="utf-8")

    repo = AuthRepository(users_root, db_path=tmp_path / "auth.db", migration_marker_path=tmp_path / "migrated")

    assert repo.get_user("user_bad") is None
    with sqlite3.connect(tmp_path / "auth.db") as conn:
        session_count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    assert session_count == 0


def test_migration_imports_session_when_user_only_exists_in_auth_json(tmp_path: Path) -> None:
    users_root = tmp_path / "users"
    user_id = "user_from_auth_json"
    token = "json-backed-token"
    user_dir = users_root / user_id
    (user_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (user_dir / "profile.json").write_text("{not-json", encoding="utf-8")
    (user_dir / "sessions" / f"{_hash_token(token)}.json").write_text(
        json.dumps(
            {
                "token": token,
                "user_id": user_id,
                "created_at": 100,
                "expires_at": 4_102_444_800,
                "last_used_at": 150,
            }
        ),
        encoding="utf-8",
    )

    legacy_root = tmp_path / "security"
    legacy_root.mkdir(parents=True, exist_ok=True)
    (legacy_root / "auth.json").write_text(
        json.dumps(
            {
                "users": {
                    user_id: {
                        "id": user_id,
                        "display_name": "Recovered User",
                        "created_at": 100,
                    }
                },
                "sessions": {},
            }
        ),
        encoding="utf-8",
    )

    repo = AuthRepository(
        users_root,
        legacy_root=legacy_root,
        db_path=tmp_path / "auth.db",
        migration_marker_path=tmp_path / "migrated",
    )

    loaded = repo.get_session(token)
    assert loaded is not None
    assert loaded.user_id == user_id
    assert repo.get_user(user_id) is not None


def test_migration_retries_when_marker_exists_but_db_was_recreated(tmp_path: Path) -> None:
    users_root = tmp_path / "users"
    user_id = "user_retry"
    token = "retry-token"
    user_dir = users_root / user_id
    (user_dir / "sessions").mkdir(parents=True, exist_ok=True)
    (user_dir / "profile.json").write_text(
        json.dumps(
            {
                "id": user_id,
                "display_name": "Retry User",
                "created_at": 100,
                "permission_defaults": {"mode": None, "working_directories": [], "rules": []},
            }
        ),
        encoding="utf-8",
    )
    (user_dir / "sessions" / f"{_hash_token(token)}.json").write_text(
        json.dumps(
            {
                "token": token,
                "user_id": user_id,
                "created_at": 100,
                "expires_at": 4_102_444_800,
                "last_used_at": 150,
            }
        ),
        encoding="utf-8",
    )

    db_path = tmp_path / "auth.db"
    marker = tmp_path / "migrations" / "auth.migrated"
    repo = AuthRepository(users_root, db_path=db_path, migration_marker_path=marker)
    assert repo.get_session(token) is not None
    assert marker.exists()

    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM sessions")
        conn.execute("DELETE FROM users")

    repo_after_reset = AuthRepository(users_root, db_path=db_path, migration_marker_path=marker)
    loaded = repo_after_reset.get_session(token)
    assert loaded is not None
    assert loaded.user_id == user_id


def test_concurrent_get_session_calls_do_not_raise_or_invalidate(tmp_path: Path) -> None:
    repo = AuthRepository(tmp_path / "users", session_refresh_interval_seconds=0)
    _, session = repo.create_guest_session(display_name="Concurrent")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: repo.get_session(session.token), range(16)))

    assert all(result is not None for result in results)
    assert repo.get_session(session.token) is not None
