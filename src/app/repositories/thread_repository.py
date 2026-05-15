"""PostgreSQL thread repository backed by SQLAlchemy ORM sessions."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.orm import Session, sessionmaker

from src.app.db.models.threads import ProjectModel, ThreadModel, ThreadPermissionModel
from src.app.services.storage_paths import StoragePathsService


def _now() -> int:
    return int(time.time())


def _dt_from_epoch(value: int) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _epoch_from_dt(value: datetime | None) -> int | None:
    if value is None:
        return None
    return int(value.timestamp())


def _clean_overlay(overlay: Any) -> dict[str, Any]:
    if not isinstance(overlay, dict):
        return {"mode": None, "working_directories": [], "rules": []}
    return {
        "mode": overlay.get("mode") if isinstance(overlay.get("mode"), str) else None,
        "working_directories": [item for item in (overlay.get("working_directories") or []) if isinstance(item, str)],
        "rules": [item for item in (overlay.get("rules") or []) if isinstance(item, dict)],
    }


@dataclass(frozen=True)
class ThreadRepository:
    session_factory: sessionmaker[Session]
    storage: StoragePathsService

    @staticmethod
    def _normalized_overlay(overlay: dict[str, Any] | None) -> dict[str, Any]:
        return _clean_overlay(overlay)

    def _project_for_workspace(self, session: Session, workspace_root: str | Path | None) -> tuple[str, str, str] | None:
        if workspace_root is None:
            return None
        root = Path(workspace_root).expanduser().resolve()
        canonical_root = self.storage.project_identity_root(root)
        project_key = self.storage.project_key(canonical_root)
        project_id = f"proj_{project_key}"
        project = session.get(ProjectModel, project_id)
        if project is None:
            project = ProjectModel(
                id=project_id,
                project_key=project_key,
                canonical_root=str(canonical_root),
                original_root=str(root),
            )
            session.add(project)
        else:
            project.canonical_root = str(canonical_root)
            project.original_root = str(root)
            project.updated_at = datetime.now(timezone.utc)
        return project_id, str(root), str(canonical_root)

    def _row_to_record(self, thread: ThreadModel, overlay: dict[str, Any] | None = None) -> dict[str, Any]:
        permission_overlay = self._normalized_overlay(
            overlay if overlay is not None else (thread.permissions[0].overlay_json if thread.permissions else None)
        )
        return {
            "id": thread.id,
            "user_id": thread.user_id,
            "created_at": _epoch_from_dt(thread.created_at) or _now(),
            "updated_at": _epoch_from_dt(thread.updated_at) or _now(),
            "last_message_at": _epoch_from_dt(thread.last_message_at),
            "workspace_root": thread.workspace_root,
            "backend": thread.backend,
            "status": thread.status or "idle",
            "active_run_id": thread.active_run_id,
            "run_started_at": _epoch_from_dt(thread.run_started_at),
            "last_stop_run_id": thread.last_stop_run_id,
            "last_stop_reason": thread.last_stop_reason,
            "last_interrupted_at": _epoch_from_dt(thread.last_interrupted_at),
            "title": thread.title,
            "summary": thread.summary,
            "model": thread.model,
            "mode": thread.mode,
            "profile_id": thread.profile_id,
            "project": thread.project_label,
            "is_favorite": bool(thread.is_favorite),
            "permission_overlay": permission_overlay,
        }

    def _get_permission_overlay_model(
        self,
        session: Session,
        *,
        thread_id: str,
        user_id: str,
    ) -> ThreadPermissionModel | None:
        return session.get(ThreadPermissionModel, {"thread_id": thread_id, "user_id": user_id})

    def _get_thread_model(self, session: Session, *, thread_id: str, user_id: str) -> ThreadModel | None:
        return session.scalar(select(ThreadModel).where(ThreadModel.id == thread_id, ThreadModel.user_id == user_id))

    def create_thread(self, *, user_id: str) -> dict[str, Any]:
        now = _now()
        thread = ThreadModel(
            id=f"thread_{uuid.uuid4().hex}",
            user_id=user_id,
            status="idle",
            created_at=_dt_from_epoch(now),
            updated_at=_dt_from_epoch(now),
        )
        permission = ThreadPermissionModel(
            thread_id=thread.id,
            user_id=user_id,
            overlay_json=_clean_overlay(None),
            updated_at=_dt_from_epoch(now),
        )
        with self.session_factory.begin() as session:
            session.add(thread)
            session.add(permission)
            session.flush()
            return self._row_to_record(thread, permission.overlay_json)

    def get_thread(self, thread_id: str, user_id: str) -> dict[str, Any] | None:
        return self.get_owned_thread(thread_id=thread_id, user_id=user_id)

    def get_owned_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            thread = self._get_thread_model(session, thread_id=thread_id, user_id=user_id)
            if thread is None:
                return None
            permission = self._get_permission_overlay_model(session, thread_id=thread_id, user_id=user_id)
            overlay = permission.overlay_json if permission is not None else None
            return self._row_to_record(thread, overlay)

    def list_threads(self, *, user_id: str) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            rows = session.execute(
                select(ThreadModel, ThreadPermissionModel.overlay_json)
                .outerjoin(
                    ThreadPermissionModel,
                    and_(
                        ThreadPermissionModel.thread_id == ThreadModel.id,
                        ThreadPermissionModel.user_id == ThreadModel.user_id,
                    ),
                )
                .where(ThreadModel.user_id == user_id)
                .order_by(ThreadModel.updated_at.desc())
            ).all()
            return [self._row_to_record(thread, overlay) for thread, overlay in rows]

    def update_session_metadata(self, *, thread_id: str, user_id: str, workspace_root: str | None = None, backend: str | None = None, status: str | None = None, title: str | None = None, summary: str | None = None, last_message_at: int | None = None, active_run_id: str | None = None, run_started_at: int | None = None, last_stop_reason: str | None = None, last_interrupted_at: int | None = None, clear_active_run: bool = False, clear_stop_reason: bool = False) -> dict[str, Any] | None:
        now = _dt_from_epoch(_now())
        with self.session_factory.begin() as session:
            thread = self._get_thread_model(session, thread_id=thread_id, user_id=user_id)
            if thread is None:
                return None
            project_info = self._project_for_workspace(session, workspace_root) if workspace_root else None
            if project_info is not None:
                thread.project_id = project_info[0]
                thread.workspace_root = project_info[1]
                thread.canonical_root = project_info[2]
            if backend is not None:
                thread.backend = backend
            if status is not None:
                thread.status = status
            if title is not None:
                thread.title = title
            if summary is not None:
                thread.summary = summary
            if last_message_at is not None:
                thread.last_message_at = _dt_from_epoch(last_message_at)
            if clear_active_run:
                thread.active_run_id = None
                thread.run_started_at = None
            else:
                if active_run_id is not None:
                    thread.active_run_id = active_run_id
                if run_started_at is not None:
                    thread.run_started_at = _dt_from_epoch(run_started_at)
            if clear_stop_reason:
                thread.last_stop_reason = None
                thread.last_stop_run_id = None
                thread.last_interrupted_at = None
            else:
                if last_stop_reason is not None:
                    thread.last_stop_reason = last_stop_reason
                if last_interrupted_at is not None:
                    thread.last_interrupted_at = _dt_from_epoch(last_interrupted_at)
            thread.updated_at = now
        return self.get_owned_thread(thread_id=thread_id, user_id=user_id)

    def stop_run(self, *, thread_id: str, user_id: str, run_id: str, reason: str) -> dict[str, Any] | None:
        now = _dt_from_epoch(_now())
        with self.session_factory.begin() as session:
            thread = self._get_thread_model(session, thread_id=thread_id, user_id=user_id)
            if thread is None:
                return None
            active_run_id = thread.active_run_id
            already_stopped = active_run_id is None and thread.last_stop_run_id == run_id
            if active_run_id != run_id and not already_stopped:
                return None
            thread.status = "interrupted"
            thread.active_run_id = None
            thread.run_started_at = None
            thread.last_stop_run_id = run_id
            thread.last_stop_reason = "user_cancel" if "user_cancel" in {thread.last_stop_reason, reason} else reason
            thread.last_interrupted_at = now
            thread.updated_at = now
        return self.get_owned_thread(thread_id=thread_id, user_id=user_id)

    def update_thread_metadata(self, *, thread_id: str, user_id: str, title: str | None = None, summary: str | None = None, model: str | None = None, mode: str | None = None, profile_id: str | None = None, project: str | None = None, is_favorite: bool | None = None) -> dict[str, Any] | None:
        with self.session_factory.begin() as session:
            thread = self._get_thread_model(session, thread_id=thread_id, user_id=user_id)
            if thread is None:
                return None
            if title is not None:
                thread.title = title
            if summary is not None:
                thread.summary = summary
            if model is not None:
                thread.model = model
            if mode is not None:
                thread.mode = mode
            if profile_id is not None:
                thread.profile_id = profile_id
            if project is not None:
                thread.project_label = project
            if is_favorite is not None:
                thread.is_favorite = is_favorite
            thread.updated_at = datetime.now(timezone.utc)
        return self.get_owned_thread(thread_id=thread_id, user_id=user_id)

    def delete_thread(self, *, thread_id: str, user_id: str) -> bool:
        with self.session_factory.begin() as session:
            thread = self._get_thread_model(session, thread_id=thread_id, user_id=user_id)
            if thread is None:
                return False
            session.delete(thread)
            return True

    def touch_thread(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        with self.session_factory.begin() as session:
            thread = self._get_thread_model(session, thread_id=thread_id, user_id=user_id)
            if thread is None:
                return None
            thread.updated_at = datetime.now(timezone.utc)
        return self.get_owned_thread(thread_id=thread_id, user_id=user_id)

    def get_permission_overlay(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        with self.session_factory() as session:
            permission = self._get_permission_overlay_model(session, thread_id=thread_id, user_id=user_id)
            if permission is None:
                return None
            return self._normalized_overlay(permission.overlay_json)

    def update_permission_overlay(self, *, thread_id: str, user_id: str, overlay: dict[str, Any]) -> dict[str, Any] | None:
        normalized = self._normalized_overlay(overlay)
        with self.session_factory.begin() as session:
            thread = self._get_thread_model(session, thread_id=thread_id, user_id=user_id)
            if thread is None:
                return None
            permission = self._get_permission_overlay_model(session, thread_id=thread_id, user_id=user_id)
            if permission is None:
                permission = ThreadPermissionModel(thread_id=thread_id, user_id=user_id, overlay_json=normalized, updated_at=datetime.now(timezone.utc))
                session.add(permission)
            else:
                permission.overlay_json = normalized
                permission.updated_at = datetime.now(timezone.utc)
        return normalized


__all__ = ["ThreadRepository"]
