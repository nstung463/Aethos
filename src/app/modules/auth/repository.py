"""Persistence layer for auth data backed by SQLite."""

from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from src.logger import get_logger

logger = get_logger(__name__)

DEFAULT_PERMISSION_DEFAULTS = {
    "mode": None,
    "working_directories": [],
    "rules": [],
}


@dataclass(frozen=True)
class AuthUser:
    id: str
    display_name: str
    created_at: int


@dataclass(frozen=True)
class AuthSession:
    token: str
    user_id: str
    created_at: int
    expires_at: int
    last_used_at: int


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:32]


def _now() -> int:
    return int(time.time())


class AuthRepository:
    """
    SQLite-backed auth storage with one-time import from legacy JSON files.

    Legacy file layout:
        root/
          <user_id>/
            profile.json
            sessions/
              <token_hash>.json
    """

    def __init__(
        self,
        root: Path,
        session_ttl_seconds: int = 30 * 24 * 60 * 60,
        session_refresh_interval_seconds: int = 5 * 60,
        legacy_root: Path | None = None,
        db_path: Path | None = None,
        migration_marker_path: Path | None = None,
    ) -> None:
        self.root = root
        self.ttl = session_ttl_seconds
        self.session_refresh_interval = max(0, session_refresh_interval_seconds)
        self.legacy_root = legacy_root
        self.root.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path or (self.root / "auth.db")
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._migration_marker_path = (
            migration_marker_path or self._db_path.with_suffix(".migration-complete")
        )
        self._migration_lock = Lock()

        self._init_db()
        self._migrate_once()

    # ------------------------------------------------------------------
    # SQLite helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    permission_defaults_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    token TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    last_used_at INTEGER NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_sessions_user_id
                    ON sessions(user_id);
                """
            )

    def _row_to_user(self, row: sqlite3.Row | None) -> AuthUser | None:
        if row is None:
            return None
        return AuthUser(
            id=str(row["id"]),
            display_name=str(row["display_name"]),
            created_at=int(row["created_at"]),
        )

    def _row_to_session(self, row: sqlite3.Row | None) -> AuthSession | None:
        if row is None:
            return None
        return AuthSession(
            token=str(row["token"]),
            user_id=str(row["user_id"]),
            created_at=int(row["created_at"]),
            expires_at=int(row["expires_at"]),
            last_used_at=int(row["last_used_at"]),
        )

    def _normalize_permission_defaults(self, defaults: Any) -> dict[str, Any]:
        if not isinstance(defaults, dict):
            defaults = {}
        return {
            "mode": defaults.get("mode") if isinstance(defaults.get("mode"), str) else None,
            "working_directories": [
                item for item in (defaults.get("working_directories") or []) if isinstance(item, str)
            ],
            "rules": [item for item in (defaults.get("rules") or []) if isinstance(item, dict)],
        }

    def _permission_defaults_to_json(self, defaults: Any) -> str:
        return json.dumps(self._normalize_permission_defaults(defaults), separators=(",", ":"))

    def _permission_defaults_from_json(self, raw: str | None) -> dict[str, Any]:
        if not raw:
            return dict(DEFAULT_PERMISSION_DEFAULTS)
        try:
            return self._normalize_permission_defaults(json.loads(raw))
        except Exception:
            return dict(DEFAULT_PERMISSION_DEFAULTS)

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _should_refresh_session(self, last_used_at: int, expires_at: int, now: int) -> bool:
        if self.session_refresh_interval <= 0:
            return True
        if now - last_used_at >= self.session_refresh_interval:
            return True
        return expires_at - now <= self.session_refresh_interval

    # ------------------------------------------------------------------
    # Migration helpers
    # ------------------------------------------------------------------

    def _migrate_once(self) -> None:
        if self._migration_marker_path.exists() and self._db_has_auth_rows():
            return

        with self._migration_lock:
            if self._migration_marker_path.exists() and self._db_has_auth_rows():
                return

            self._import_legacy_data()
            self._migration_marker_path.parent.mkdir(parents=True, exist_ok=True)
            self._migration_marker_path.write_text("complete", encoding="utf-8")

    def _db_has_auth_rows(self) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    EXISTS(SELECT 1 FROM users LIMIT 1) AS has_users,
                    EXISTS(SELECT 1 FROM sessions LIMIT 1) AS has_sessions
                """
            ).fetchone()
        if row is None:
            return False
        return bool(row["has_users"]) or bool(row["has_sessions"])

    def _import_legacy_data(self) -> None:
        with self._connect() as conn:
            if self.legacy_root is not None:
                self._import_legacy_auth_users(conn)
            self._import_legacy_user_files(conn)
            if self.legacy_root is not None:
                self._import_legacy_auth_sessions(conn)

    def _import_legacy_user_files(self, conn: sqlite3.Connection) -> None:
        if not self.root.exists():
            return

        known_user_ids: set[str] = set()
        for user_dir in self.root.iterdir():
            if not user_dir.is_dir():
                continue
            user_id = user_dir.name
            profile_path = user_dir / "profile.json"
            if profile_path.exists():
                profile = self._read_json(profile_path)
                if not profile:
                    logger.warning("Skipping malformed auth profile at %s", profile_path)
                elif str(profile.get("id") or user_id):
                    normalized_user_id = str(profile.get("id") or user_id)
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO users(id, display_name, created_at, permission_defaults_json)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            normalized_user_id,
                            str(profile.get("display_name", "Guest")),
                            int(profile.get("created_at", _now())),
                            self._permission_defaults_to_json(
                                profile.get("permission_defaults", DEFAULT_PERMISSION_DEFAULTS)
                            ),
                        ),
                    )
                    known_user_ids.add(normalized_user_id)

        for row in conn.execute("SELECT id FROM users").fetchall():
            known_user_ids.add(str(row["id"]))

        for user_dir in self.root.iterdir():
            if not user_dir.is_dir():
                continue
            user_id = user_dir.name
            sessions_dir = user_dir / "sessions"
            if user_id not in known_user_ids or not sessions_dir.exists():
                continue
            for session_path in sessions_dir.glob("*.json"):
                raw = self._read_json(session_path)
                if not raw:
                    logger.warning("Skipping malformed auth session at %s", session_path)
                    continue
                token = str(raw.get("token", ""))
                session_user_id = str(raw.get("user_id", user_id))
                if not token or session_user_id not in known_user_ids:
                    continue
                try:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO sessions(
                            token_hash, token, user_id, created_at, expires_at, last_used_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            _hash_token(token),
                            token,
                            session_user_id,
                            int(raw.get("created_at", _now())),
                            int(raw.get("expires_at", _now() + self.ttl)),
                            int(raw.get("last_used_at", raw.get("created_at", _now()))),
                        ),
                    )
                except Exception:
                    logger.warning("Skipping malformed auth session row at %s", session_path)

    def _read_legacy_auth_json(self) -> dict[str, Any] | None:
        legacy_file = self.legacy_root / "auth.json"
        if not legacy_file.exists():
            return None

        data = self._read_json(legacy_file)
        if not data:
            logger.warning("Skipping malformed legacy auth state at %s", legacy_file)
            return None

        users = data.get("users", {})
        sessions = data.get("sessions", {})
        if not isinstance(users, dict) or not isinstance(sessions, dict):
            logger.warning("Skipping malformed legacy auth state structure at %s", legacy_file)
            return None
        return data

    def _import_legacy_auth_users(self, conn: sqlite3.Connection) -> None:
        data = self._read_legacy_auth_json()
        if data is None:
            return

        now = _now()
        users = data.get("users", {})
        for user_data in users.values():
            if not isinstance(user_data, dict):
                continue
            user_id = str(user_data.get("id", ""))
            if not user_id:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO users(id, display_name, created_at, permission_defaults_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user_id,
                    str(user_data.get("display_name", "Guest")),
                    int(user_data.get("created_at", now)),
                    self._permission_defaults_to_json(
                        user_data.get("permission_defaults", DEFAULT_PERMISSION_DEFAULTS)
                    ),
                ),
            )

    def _import_legacy_auth_sessions(self, conn: sqlite3.Connection) -> None:
        data = self._read_legacy_auth_json()
        if data is None:
            return

        now = _now()
        sessions = data.get("sessions", {})
        known_user_ids = {str(row["id"]) for row in conn.execute("SELECT id FROM users").fetchall()}
        for session_data in sessions.values():
            if not isinstance(session_data, dict):
                continue
            token = str(session_data.get("token", ""))
            user_id = str(session_data.get("user_id", ""))
            if not token or user_id not in known_user_ids:
                continue
            created_at = int(session_data.get("created_at", now))
            conn.execute(
                """
                INSERT OR IGNORE INTO sessions(
                    token_hash, token, user_id, created_at, expires_at, last_used_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _hash_token(token),
                    token,
                    user_id,
                    created_at,
                    int(session_data.get("expires_at", now + self.ttl)),
                    int(session_data.get("last_used_at", created_at)),
                ),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_guest_session(
        self, *, display_name: str | None = None
    ) -> tuple[AuthUser, AuthSession]:
        now = _now()
        user = AuthUser(
            id=f"user_{uuid.uuid4().hex}",
            display_name=(display_name or "Guest").strip() or "Guest",
            created_at=now,
        )
        session = AuthSession(
            token=secrets.token_urlsafe(32),
            user_id=user.id,
            created_at=now,
            expires_at=now + self.ttl,
            last_used_at=now,
        )

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO users(id, display_name, created_at, permission_defaults_json)
                VALUES (?, ?, ?, ?)
                """,
                (
                    user.id,
                    user.display_name,
                    user.created_at,
                    self._permission_defaults_to_json(DEFAULT_PERMISSION_DEFAULTS),
                ),
            )
            conn.execute(
                """
                INSERT INTO sessions(token_hash, token, user_id, created_at, expires_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _hash_token(session.token),
                    session.token,
                    session.user_id,
                    session.created_at,
                    session.expires_at,
                    session.last_used_at,
                ),
            )

        return user, session

    def get_session(self, token: str) -> AuthSession | None:
        token_hash = _hash_token(token)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT token, user_id, created_at, expires_at, last_used_at
                FROM sessions
                WHERE token_hash = ?
                """,
                (token_hash,),
            ).fetchone()

            session = self._row_to_session(row)
            if session is None:
                return None
            if session.token != token:
                try:
                    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                except sqlite3.Error as exc:
                    logger.warning(
                        "Failed to delete mismatched auth session for token_hash=%s: %s",
                        token_hash,
                        exc,
                    )
                return None

            now = _now()
            if session.expires_at and now > session.expires_at:
                try:
                    conn.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash,))
                except sqlite3.Error as exc:
                    logger.warning(
                        "Failed to delete expired auth session for user_id=%s token_hash=%s: %s",
                        session.user_id,
                        token_hash,
                        exc,
                    )
                return None

            if not self._should_refresh_session(session.last_used_at, session.expires_at, now):
                return session

            try:
                updated = conn.execute(
                    """
                    UPDATE sessions
                    SET last_used_at = ?, expires_at = ?
                    WHERE token_hash = ?
                      AND token = ?
                      AND (
                        (? - last_used_at) >= ?
                        OR (expires_at - ?) <= ?
                      )
                    """,
                    (
                        now,
                        now + self.ttl,
                        token_hash,
                        token,
                        now,
                        self.session_refresh_interval,
                        now,
                        self.session_refresh_interval,
                    ),
                )
                if updated.rowcount:
                    return AuthSession(
                        token=session.token,
                        user_id=session.user_id,
                        created_at=session.created_at,
                        expires_at=now + self.ttl,
                        last_used_at=now,
                    )
            except sqlite3.Error as exc:
                logger.warning(
                    "Failed to refresh auth session metadata for user_id=%s token_hash=%s: %s",
                    session.user_id,
                    token_hash,
                    exc,
                )

            return session

    def get_user(self, user_id: str) -> AuthUser | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, display_name, created_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        return self._row_to_user(row)

    def get_permission_defaults(self, user_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT permission_defaults_json
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return dict(DEFAULT_PERMISSION_DEFAULTS)
        return self._permission_defaults_from_json(
            row["permission_defaults_json"]
            if "permission_defaults_json" in row.keys()
            else None
        )

    def update_permission_defaults(
        self, *, user_id: str, defaults: dict[str, Any]
    ) -> dict[str, Any] | None:
        normalized = self._normalize_permission_defaults(defaults)
        with self._connect() as conn:
            updated = conn.execute(
                """
                UPDATE users
                SET permission_defaults_json = ?
                WHERE id = ?
                """,
                (json.dumps(normalized, separators=(",", ":")), user_id),
            )
        if updated.rowcount == 0:
            return None
        return normalized
