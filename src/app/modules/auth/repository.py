"""Persistence layer for auth data — per-user file structure."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


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


class AuthRepository:
    """
    File layout:
        root/
          <user_id>/
            profile.json                    # user info + permission_defaults
            sessions/
              <token_hash>.json             # session record with TTL
    """

    def __init__(
        self,
        root: Path,
        session_ttl_seconds: int = 30 * 24 * 60 * 60,
        legacy_root: Path | None = None,
    ) -> None:
        self.root = root
        self.ttl = session_ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

        # token_hash -> user_id in-memory index, built lazily
        self._index: dict[str, str] = {}
        self._index_lock = Lock()
        self._user_locks: dict[str, Lock] = {}
        self._users_lock = Lock()

        self._build_index()

        if legacy_root is not None:
            self._migrate_from_legacy(legacy_root)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _user_lock(self, user_id: str) -> Lock:
        with self._users_lock:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = Lock()
            return self._user_locks[user_id]

    def _user_dir(self, user_id: str) -> Path:
        return self.root / user_id

    def _profile_path(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "profile.json"

    def _sessions_dir(self, user_id: str) -> Path:
        return self._user_dir(user_id) / "sessions"

    def _session_path(self, user_id: str, token: str) -> Path:
        return self._sessions_dir(user_id) / f"{_hash_token(token)}.json"

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_json(self, path: Path, data: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)

    def _build_index(self) -> None:
        index: dict[str, str] = {}
        for session_file in self.root.glob("*/sessions/*.json"):
            user_id = session_file.parent.parent.name
            token_hash = session_file.stem
            index[token_hash] = user_id
        with self._index_lock:
            self._index = index

    def _index_add(self, token: str, user_id: str) -> None:
        with self._index_lock:
            self._index[_hash_token(token)] = user_id

    def _index_remove(self, token: str) -> None:
        with self._index_lock:
            self._index.pop(_hash_token(token), None)

    def _find_user_id_for_token(self, token: str) -> str | None:
        with self._index_lock:
            return self._index.get(_hash_token(token))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_guest_session(
        self, *, display_name: str | None = None
    ) -> tuple[AuthUser, AuthSession]:
        now = int(time.time())
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

        with self._user_lock(user.id):
            self._write_json(
                self._profile_path(user.id),
                {
                    "id": user.id,
                    "display_name": user.display_name,
                    "created_at": user.created_at,
                    "permission_defaults": {
                        "mode": None,
                        "working_directories": [],
                        "rules": [],
                    },
                },
            )
            self._write_json(
                self._session_path(user.id, session.token),
                {
                    "token": session.token,
                    "user_id": session.user_id,
                    "created_at": session.created_at,
                    "expires_at": session.expires_at,
                    "last_used_at": session.last_used_at,
                },
            )

        self._index_add(session.token, user.id)
        return user, session

    def get_session(self, token: str) -> AuthSession | None:
        user_id = self._find_user_id_for_token(token)
        if not user_id:
            return None

        path = self._session_path(user_id, token)
        with self._user_lock(user_id):
            raw = self._read_json(path)
            if not raw or raw.get("token") != token:
                self._index_remove(token)
                return None

            now = int(time.time())
            expires_at = int(raw.get("expires_at", 0))
            if expires_at and now > expires_at:
                path.unlink(missing_ok=True)
                self._index_remove(token)
                return None

            # Sliding expiry — extend on each use
            raw["last_used_at"] = now
            raw["expires_at"] = now + self.ttl
            self._write_json(path, raw)

            return AuthSession(
                token=str(raw["token"]),
                user_id=str(raw["user_id"]),
                created_at=int(raw["created_at"]),
                expires_at=int(raw["expires_at"]),
                last_used_at=int(raw["last_used_at"]),
            )

    def get_user(self, user_id: str) -> AuthUser | None:
        with self._user_lock(user_id):
            raw = self._read_json(self._profile_path(user_id))
        if not raw:
            return None
        return AuthUser(
            id=str(raw["id"]),
            display_name=str(raw["display_name"]),
            created_at=int(raw["created_at"]),
        )

    def get_permission_defaults(self, user_id: str) -> dict[str, Any]:
        with self._user_lock(user_id):
            raw = self._read_json(self._profile_path(user_id))
        defaults = raw.get("permission_defaults") if raw else None
        if not isinstance(defaults, dict):
            return {"mode": None, "working_directories": [], "rules": []}
        return {
            "mode": defaults.get("mode") if isinstance(defaults.get("mode"), str) else None,
            "working_directories": [
                item for item in (defaults.get("working_directories") or []) if isinstance(item, str)
            ],
            "rules": [
                item for item in (defaults.get("rules") or []) if isinstance(item, dict)
            ],
        }

    def update_permission_defaults(
        self, *, user_id: str, defaults: dict[str, Any]
    ) -> dict[str, Any] | None:
        path = self._profile_path(user_id)
        with self._user_lock(user_id):
            raw = self._read_json(path)
            if not raw:
                return None
            raw["permission_defaults"] = defaults
            self._write_json(path, raw)
        return defaults

    # ------------------------------------------------------------------
    # Migration from legacy auth.json
    # ------------------------------------------------------------------

    def _migrate_from_legacy(self, legacy_root: Path) -> None:
        legacy_file = legacy_root / "auth.json"
        migrated_flag = legacy_root / "auth.json.migrated"

        if not legacy_file.exists() or migrated_flag.exists():
            return

        try:
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
        except Exception:
            return

        users: dict[str, Any] = data.get("users", {})
        sessions: dict[str, Any] = data.get("sessions", {})
        now = int(time.time())

        for user_data in users.values():
            user_id = str(user_data.get("id", ""))
            if not user_id:
                continue
            profile_path = self._profile_path(user_id)
            if profile_path.exists():
                continue
            self._write_json(
                profile_path,
                {
                    "id": user_id,
                    "display_name": str(user_data.get("display_name", "Guest")),
                    "created_at": int(user_data.get("created_at", now)),
                    "permission_defaults": user_data.get(
                        "permission_defaults",
                        {"mode": None, "working_directories": [], "rules": []},
                    ),
                },
            )

        for session_data in sessions.values():
            token = str(session_data.get("token", ""))
            user_id = str(session_data.get("user_id", ""))
            if not token or not user_id:
                continue
            created_at = int(session_data.get("created_at", now))
            session_path = self._session_path(user_id, token)
            if session_path.exists():
                continue
            self._write_json(
                session_path,
                {
                    "token": token,
                    "user_id": user_id,
                    "created_at": created_at,
                    "expires_at": now + self.ttl,
                    "last_used_at": created_at,
                },
            )
            self._index_add(token, user_id)

        migrated_flag.write_text("migrated", encoding="utf-8")
