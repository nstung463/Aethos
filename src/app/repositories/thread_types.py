"""Thread metadata persistence contract used by chat and permission services."""

from __future__ import annotations

from typing import Any, Protocol


class ThreadRepositoryProtocol(Protocol):
    def create_thread(self, *, user_id: str) -> dict[str, Any]:
        ...

    def update_session_metadata(
        self,
        *,
        thread_id: str,
        user_id: str,
        workspace_root: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        ...

    def list_threads(self, *, user_id: str) -> list[dict[str, Any]]:
        ...

    def get_thread(self, thread_id: str, user_id: str) -> dict[str, Any] | None:
        ...

    def get_owned_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        ...

    def touch_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        ...

    def stop_run(self, *, thread_id: str, user_id: str, run_id: str, reason: str) -> dict[str, Any] | None:
        ...

    def update_thread_metadata(self, *, thread_id: str, user_id: str, **kwargs: Any) -> dict[str, Any] | None:
        ...

    def delete_thread(self, *, thread_id: str, user_id: str) -> bool:
        ...

    def get_permission_overlay(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        ...

    def update_permission_overlay(
        self,
        *,
        thread_id: str,
        user_id: str,
        overlay: dict[str, Any],
    ) -> dict[str, Any] | None:
        ...
