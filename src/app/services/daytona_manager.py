from __future__ import annotations

import os
import time
from dataclasses import dataclass
from threading import Lock

from src.backends.daytona import DaytonaSandbox as DaytonaBackend, delete_daytona_sandbox, get_or_create_daytona_backend
from src.logger import get_logger

logger = get_logger(__name__)


@dataclass
class _SandboxSession:
    backend: DaytonaBackend
    sandbox_name: str
    last_used_at: float


class DaytonaSessionManager:
    """Keeps one Daytona sandbox alive per frontend session id."""

    def __init__(self, *, idle_ttl_seconds: int = 600) -> None:
        self._idle_ttl_seconds = idle_ttl_seconds
        self._lock = Lock()
        self._sessions: dict[str, _SandboxSession] = {}

    def get_backend(self, session_id: str) -> DaytonaBackend:
        now = time.time()
        expired: list[tuple[str, str]] = []

        with self._lock:
            for existing_session_id, session in list(self._sessions.items()):
                if now - session.last_used_at > self._idle_ttl_seconds:
                    expired.append((existing_session_id, session.sandbox_name))
                    del self._sessions[existing_session_id]

            current = self._sessions.get(session_id)
            if current is not None:
                current.last_used_at = now
                return current.backend

        self._delete_expired(expired)

        lease = get_or_create_daytona_backend(
            conversation_id=session_id,
            auto_delete_interval=max(1, int(self._idle_ttl_seconds / 60)),
        )
        session = _SandboxSession(
            backend=lease.backend,
            sandbox_name=lease.sandbox_name,
            last_used_at=now,
        )
        with self._lock:
            current = self._sessions.get(session_id)
            if current is not None:
                current.last_used_at = now
                delete_daytona_sandbox(sandbox_name=session.sandbox_name)
                return current.backend
            self._sessions[session_id] = session
        return session.backend

    def shutdown(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for session in sessions:
            try:
                delete_daytona_sandbox(sandbox_name=session.sandbox_name)
            except Exception:
                logger.exception("Failed to delete Daytona sandbox during shutdown: %s", session.sandbox_name)

    def _delete_expired(self, expired: list[tuple[str, str]]) -> None:
        for session_id, sandbox_name in expired:
            try:
                logger.info("Expiring Daytona sandbox for session_id=%s", session_id)
                delete_daytona_sandbox(sandbox_name=sandbox_name)
            except Exception:
                logger.exception("Failed to delete expired Daytona sandbox: %s", sandbox_name)


def build_daytona_session_manager() -> DaytonaSessionManager:
    ttl = int(os.getenv("AETHOS_DAYTONA_IDLE_TTL_SECONDS", "600"))
    return DaytonaSessionManager(idle_ttl_seconds=max(60, ttl))
