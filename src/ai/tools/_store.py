"""Shared in-memory store for todo lists and task records.

Mirrors the session-scoped task/todo state in claude-code-source.
Inject one ToolStore per agent session; pass it to all tool builders.
"""
from __future__ import annotations

import itertools
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


@dataclass
class TaskRecord:
    id: str
    subject: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    active_form: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    output: str = ""
    stopped: bool = False
    blocked_by: list[str] = field(default_factory=list)
    blocks: list[str] = field(default_factory=list)
    owner: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ToolStore:
    """Thread-safe in-memory store for todos and tasks."""

    _counter = itertools.count(1)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: dict[str, TaskRecord] = {}
        self._todos: list[dict[str, str]] = []

    # ── Tasks ──────────────────────────────────────────────────────────────

    def create_task(
        self,
        subject: str,
        description: str,
        active_form: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        blocked_by: Optional[list[str]] = None,
        owner: Optional[str] = None,
    ) -> TaskRecord:
        task_id = f"task-{next(self._counter)}"
        record = TaskRecord(
            id=task_id,
            subject=subject,
            description=description,
            active_form=active_form,
            metadata=metadata or {},
            blocked_by=list(blocked_by or []),
            owner=owner,
        )
        with self._lock:
            self._tasks[task_id] = record
        return record

    def get_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskRecord]:
        with self._lock:
            return list(self._tasks.values())

    def update_task(
        self,
        task_id: str,
        *,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[TaskStatus] = None,
        active_form: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> Optional[TaskRecord]:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return None
            if subject is not None:
                record.subject = subject
            if description is not None:
                record.description = description
            if status is not None:
                record.status = status
            if active_form is not None:
                record.active_form = active_form
            if metadata is not None:
                record.metadata.update(metadata)
            record.updated_at = datetime.now(timezone.utc).isoformat()
            return record

    def delete_task(self, task_id: str) -> bool:
        with self._lock:
            return self._tasks.pop(task_id, None) is not None

    def stop_task(self, task_id: str) -> Optional[TaskRecord]:
        with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.stopped = True
                record.status = TaskStatus.STOPPED
            return record

    def add_dependency(self, task_id: str, blocked_by_id: str) -> Optional[str]:
        """Link task_id as blocked by blocked_by_id. Returns error string or None."""
        with self._lock:
            task = self._tasks.get(task_id)
            dep = self._tasks.get(blocked_by_id)
            if task is None:
                return f"task '{task_id}' not found"
            if dep is None:
                return f"task '{blocked_by_id}' not found"
            if blocked_by_id not in task.blocked_by:
                task.blocked_by.append(blocked_by_id)
            if task_id not in dep.blocks:
                dep.blocks.append(task_id)
            return None

    def get_available_tasks(self) -> list[TaskRecord]:
        """Tasks with no unfinished blockers."""
        terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED}
        with self._lock:
            tasks = list(self._tasks.values())
        return [
            t for t in tasks
            if t.status == TaskStatus.PENDING
            and all(
                # Missing (deleted) blocker is treated as resolved, not as a permanent block.
                self._tasks.get(b) is None or self._tasks[b].status in terminal
                for b in t.blocked_by
            )
        ]

    def get_blocked_tasks(self) -> list[TaskRecord]:
        """Pending tasks that have at least one unfinished blocker."""
        terminal = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED}
        with self._lock:
            tasks = list(self._tasks.values())
        return [
            t for t in tasks
            if t.status == TaskStatus.PENDING and t.blocked_by
            and any(
                # Only count a blocker that still exists and hasn't finished.
                self._tasks.get(b) is not None and self._tasks[b].status not in terminal
                for b in t.blocked_by
            )
        ]

    def has_cycle(self, start_id: str) -> bool:
        """DFS cycle detection from start_id through blocked_by edges."""
        with self._lock:
            tasks = dict(self._tasks)

        visited: set[str] = set()
        path: set[str] = set()

        def dfs(tid: str) -> bool:
            if tid in path:
                return True
            if tid in visited:
                return False
            visited.add(tid)
            path.add(tid)
            record = tasks.get(tid)
            if record:
                for dep in record.blocked_by:
                    if dfs(dep):
                        return True
            path.discard(tid)
            return False

        return dfs(start_id)

    # ── Task output ────────────────────────────────────────────────────────

    def append_output(self, task_id: str, text: str) -> None:
        with self._lock:
            record = self._tasks.get(task_id)
            if record:
                record.output += text

    def get_output(self, task_id: str) -> str:
        with self._lock:
            record = self._tasks.get(task_id)
            return record.output if record else ""

    # ── Todos ──────────────────────────────────────────────────────────────

    def write_todos(self, todos: list[dict[str, str]]) -> None:
        with self._lock:
            self._todos = list(todos)

    def read_todos(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._todos)
