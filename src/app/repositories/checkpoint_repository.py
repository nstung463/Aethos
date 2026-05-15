"""Repository helpers for thread events and LangGraph checkpoints."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import Engine
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from src.app.db.models.checkpoints import ThreadCheckpointModel, ThreadCheckpointWriteModel, ThreadEventModel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CheckpointRepository:
    session_factory: sessionmaker[Session] | Engine

    def _session_factory(self) -> sessionmaker[Session]:
        if isinstance(self.session_factory, sessionmaker):
            return self.session_factory
        if isinstance(self.session_factory, Engine):
            return sessionmaker(bind=self.session_factory, autoflush=False, expire_on_commit=False, future=True)
        raise TypeError(f"Unsupported session factory type: {type(self.session_factory)!r}")

    def checkpoint_exists(
        self,
        *,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str | None,
    ) -> bool:
        if not checkpoint_id:
            return False
        with self._session_factory()() as session:
            stmt = (
                select(ThreadCheckpointModel.id)
                .where(
                    ThreadCheckpointModel.id == checkpoint_id,
                    ThreadCheckpointModel.thread_id == thread_id,
                    ThreadCheckpointModel.checkpoint_ns == checkpoint_ns,
                )
                .limit(1)
            )
            return session.scalar(stmt) is not None

    def read_checkpoint_by_id(
        self,
        *,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str | None,
    ) -> tuple[str, bytes] | None:
        if not checkpoint_id:
            return None
        with self._session_factory()() as session:
            row = session.scalar(
                select(ThreadCheckpointModel).where(
                    ThreadCheckpointModel.id == checkpoint_id,
                    ThreadCheckpointModel.thread_id == thread_id,
                    ThreadCheckpointModel.checkpoint_ns == checkpoint_ns,
                )
            )
            if row is None:
                return None
            return str(row.checkpoint_type), bytes(row.checkpoint_payload)

    def list_checkpoint_rows(
        self,
        config_thread_id: str | None,
        checkpoint_ns: str | None,
        checkpoint_id: str | None,
        before_id: str | None,
        limit: int | None,
    ) -> list[ThreadCheckpointModel]:
        with self._session_factory()() as session:
            stmt = select(ThreadCheckpointModel)
            if config_thread_id is not None:
                stmt = stmt.where(ThreadCheckpointModel.thread_id == config_thread_id)
            if checkpoint_ns is not None:
                stmt = stmt.where(ThreadCheckpointModel.checkpoint_ns == checkpoint_ns)
            if checkpoint_id is not None:
                stmt = stmt.where(ThreadCheckpointModel.id == checkpoint_id)
            if before_id is not None:
                stmt = stmt.where(ThreadCheckpointModel.id < before_id)
            stmt = stmt.order_by(ThreadCheckpointModel.created_at.desc(), ThreadCheckpointModel.id.desc())
            if limit is not None:
                stmt = stmt.limit(limit)
            return list(session.scalars(stmt).all())

    def get_max_seq_and_parent(self, *, thread_id: str) -> tuple[int, str | None]:
        with self._session_factory()() as session:
            max_seq = (
                session.scalar(select(func.coalesce(func.max(ThreadEventModel.seq), 0)).where(ThreadEventModel.thread_id == thread_id))
                or 0
            )
            parent = session.scalar(
                select(ThreadEventModel.id).where(ThreadEventModel.thread_id == thread_id).order_by(ThreadEventModel.seq.desc()).limit(1)
            )
            return int(max_seq), parent

    def message_exists(self, *, thread_id: str, fingerprint: str) -> bool:
        with self._session_factory()() as session:
            stmt = (
                select(ThreadEventModel.id)
                .where(
                    ThreadEventModel.thread_id == thread_id,
                    (ThreadEventModel.message_fingerprint == fingerprint)
                    | (ThreadEventModel.message_fingerprint.like(f"{fingerprint}:%")),
                )
                .limit(1)
            )
            return session.scalar(stmt) is not None

    def append_event_rows(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        with self._session_factory().begin() as session:
            for row in rows:
                existing = session.scalar(
                    select(ThreadEventModel.id).where(
                        ThreadEventModel.thread_id == row["thread_id"],
                        ThreadEventModel.message_fingerprint == row["message_fingerprint"],
                    )
                )
                if existing is not None:
                    continue
                session.add(ThreadEventModel(**row))

    def append_interruption_event(
        self,
        *,
        thread_id: str,
        run_id: str,
        reason: str,
        tool_use: bool,
    ) -> dict[str, Any] | None:
        with self._session_factory().begin() as session:
            existing = session.scalar(
                select(ThreadEventModel.id)
                .where(
                    ThreadEventModel.thread_id == thread_id,
                    ThreadEventModel.run_id == run_id,
                    ThreadEventModel.event_type == "interruption",
                )
                .limit(1)
            )
            if existing is not None:
                return None

            max_seq = (
                session.scalar(select(func.coalesce(func.max(ThreadEventModel.seq), 0)).where(ThreadEventModel.thread_id == thread_id))
                or 0
            )
            parent_uuid = session.scalar(
                select(ThreadEventModel.id).where(ThreadEventModel.thread_id == thread_id).order_by(ThreadEventModel.seq.desc()).limit(1)
            )
            event_id = str(uuid.uuid4())
            text_value = "[Request interrupted by user for tool use]" if tool_use else "[Request interrupted by user]"

            session.add(
                ThreadEventModel(
                    id=event_id,
                    thread_id=thread_id,
                    seq=int(max_seq) + 1,
                    parent_event_id=parent_uuid,
                    event_type="interruption",
                    message_json={"role": "user", "content": [{"type": "text", "text": text_value}]},
                    message_fingerprint=f"interruption:{run_id}",
                    checkpoint_id=None,
                    run_id=run_id,
                    interruption_reason=reason,
                    tool_use=tool_use,
                    is_sidechain=False,
                    session_id=thread_id,
                    user_type="external",
                    entrypoint="api",
                    cwd=str(Path.cwd()),
                )
            )

            return {
                "parentUuid": parent_uuid,
                "isSidechain": False,
                "type": "interruption",
                "message": {"role": "user", "content": [{"type": "text", "text": text_value}]},
                "uuid": event_id,
                "timestamp": _now_iso(),
                "sessionId": thread_id,
                "checkpointId": None,
                "messageFingerprint": f"interruption:{run_id}",
                "userType": "external",
                "entrypoint": "api",
                "cwd": str(Path.cwd()),
                "runId": run_id,
                "interruptionReason": reason,
                "toolUse": tool_use,
            }

    def insert_checkpoint(
        self,
        *,
        checkpoint_id: str,
        thread_id: str,
        checkpoint_ns: str,
        parent_checkpoint_id: str | None,
        checkpoint_type: str,
        checkpoint_payload: bytes,
        metadata_type: str,
        metadata_payload: bytes,
        new_versions_json: dict[str, Any],
    ) -> None:
        with self._session_factory().begin() as session:
            existing = session.scalar(
                select(ThreadCheckpointModel.id)
                .where(
                    ThreadCheckpointModel.id == checkpoint_id,
                    ThreadCheckpointModel.thread_id == thread_id,
                    ThreadCheckpointModel.checkpoint_ns == checkpoint_ns,
                )
                .limit(1)
            )
            if existing is not None:
                return
            session.add(
                ThreadCheckpointModel(
                    id=checkpoint_id,
                    thread_id=thread_id,
                    checkpoint_ns=checkpoint_ns,
                    parent_checkpoint_id=parent_checkpoint_id,
                    checkpoint_payload=checkpoint_payload,
                    checkpoint_type=checkpoint_type,
                    metadata_payload=metadata_payload,
                    metadata_type=metadata_type,
                    new_versions_json=new_versions_json,
                )
            )

    def insert_writes(self, entries: list[dict[str, Any]]) -> bool:
        if not entries:
            return True
        try:
            with self._session_factory().begin() as session:
                for entry in entries:
                    existing = session.get(
                        ThreadCheckpointWriteModel,
                        {
                            "checkpoint_id": entry["checkpoint_id"],
                            "task_id": entry["task_id"],
                            "idx": entry["idx"],
                        },
                    )
                    if existing is not None:
                        continue
                    session.add(ThreadCheckpointWriteModel(**entry))
        except IntegrityError:
            return False
        return True

    def get_checkpoint_with_writes(
        self,
        *,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str | None,
    ) -> tuple[ThreadCheckpointModel | None, list[ThreadCheckpointWriteModel]]:
        with self._session_factory()() as session:
            stmt = select(ThreadCheckpointModel).where(
                ThreadCheckpointModel.thread_id == thread_id,
                ThreadCheckpointModel.checkpoint_ns == checkpoint_ns,
            )
            if checkpoint_id is not None:
                stmt = stmt.where(ThreadCheckpointModel.id == checkpoint_id)
            stmt = stmt.order_by(ThreadCheckpointModel.created_at.desc(), ThreadCheckpointModel.id.desc()).limit(1)
            checkpoint = session.scalar(stmt)
            if checkpoint is None:
                return None, []

            writes = list(
                session.scalars(
                    select(ThreadCheckpointWriteModel)
                    .where(
                        ThreadCheckpointWriteModel.thread_id == thread_id,
                        ThreadCheckpointWriteModel.checkpoint_id == checkpoint.id,
                    )
                    .order_by(ThreadCheckpointWriteModel.created_at.asc(), ThreadCheckpointWriteModel.idx.asc())
                ).all()
            )
            return checkpoint, writes

    def get_full_message_entries(self, *, thread_id: str) -> list[dict[str, Any]]:
        with self._session_factory()() as session:
            rows = list(
                session.scalars(
                    select(ThreadEventModel)
                    .where(ThreadEventModel.thread_id == thread_id)
                    .order_by(ThreadEventModel.seq.asc(), ThreadEventModel.created_at.asc(), ThreadEventModel.id.asc())
                ).all()
            )

        entries: list[dict[str, Any]] = []
        for row in rows:
            entries.append(
                {
                    "parentUuid": row.parent_event_id,
                    "isSidechain": bool(row.is_sidechain),
                    "type": row.event_type,
                    "message": row.message_json if isinstance(row.message_json, dict) else {},
                    "uuid": row.id,
                    "timestamp": row.created_at.isoformat() if row.created_at is not None else _now_iso(),
                    "sessionId": row.session_id,
                    "checkpointId": row.checkpoint_id,
                    "messageFingerprint": row.message_fingerprint,
                    "userType": row.user_type,
                    "entrypoint": row.entrypoint,
                    "cwd": row.cwd,
                    **({"runId": row.run_id} if row.run_id is not None else {}),
                    **({"interruptionReason": row.interruption_reason} if row.interruption_reason is not None else {}),
                    **({"toolUse": bool(row.tool_use)} if row.tool_use is not None else {}),
                }
            )
        return entries


__all__ = ["CheckpointRepository"]
