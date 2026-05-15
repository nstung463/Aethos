"""ORM models for thread events and checkpoints."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, PrimaryKeyConstraint, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.app.db.base import Base


class ThreadEventModel(Base):
    __tablename__ = "thread_events"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    thread_id: Mapped[str] = mapped_column(Text, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True)
    seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parent_event_id: Mapped[str | None] = mapped_column(Text, ForeignKey("thread_events.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    message_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    message_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    interruption_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_use: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_sidechain: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    entrypoint: Mapped[str | None] = mapped_column(Text, nullable=True)
    cwd: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class ThreadCheckpointModel(Base):
    __tablename__ = "thread_checkpoints"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    thread_id: Mapped[str] = mapped_column(Text, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True)
    checkpoint_ns: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    parent_checkpoint_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    checkpoint_payload: Mapped[bytes] = mapped_column(nullable=False)
    checkpoint_type: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_payload: Mapped[bytes] = mapped_column(nullable=False)
    metadata_type: Mapped[str] = mapped_column(Text, nullable=False)
    new_versions_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


class ThreadCheckpointWriteModel(Base):
    __tablename__ = "thread_checkpoint_writes"
    __table_args__ = (PrimaryKeyConstraint("checkpoint_id", "task_id", "idx", name="pk_thread_checkpoint_writes"),)

    thread_id: Mapped[str] = mapped_column(Text, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    checkpoint_id: Mapped[str] = mapped_column(Text, ForeignKey("thread_checkpoints.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[str] = mapped_column(Text, nullable=False)
    task_path: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    value_payload: Mapped[bytes] = mapped_column(nullable=False)
    value_type: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))


__all__ = ["ThreadCheckpointModel", "ThreadCheckpointWriteModel", "ThreadEventModel"]
