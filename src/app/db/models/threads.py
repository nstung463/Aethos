"""ORM models for projects, threads, and permissions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, PrimaryKeyConstraint, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.db.base import Base


class ProjectModel(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    canonical_root: Mapped[str] = mapped_column(Text, nullable=False)
    original_root: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    threads: Mapped[list["ThreadModel"]] = relationship(back_populates="project")


class ThreadModel(Base):
    __tablename__ = "threads"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(Text, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True)
    workspace_root: Mapped[str | None] = mapped_column(Text, nullable=True)
    canonical_root: Mapped[str | None] = mapped_column(Text, nullable=True)
    backend: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'idle'"))
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("FALSE"))
    active_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_stop_run_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_stop_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_interrupted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    project: Mapped[ProjectModel | None] = relationship(back_populates="threads")
    permissions: Mapped[list["ThreadPermissionModel"]] = relationship(back_populates="thread", cascade="all, delete-orphan")


class ThreadPermissionModel(Base):
    __tablename__ = "thread_permissions"
    __table_args__ = (PrimaryKeyConstraint("thread_id", "user_id", name="pk_thread_permissions"),)

    thread_id: Mapped[str] = mapped_column(Text, ForeignKey("threads.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    overlay_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    thread: Mapped[ThreadModel] = relationship(back_populates="permissions")


__all__ = ["ProjectModel", "ThreadModel", "ThreadPermissionModel"]
