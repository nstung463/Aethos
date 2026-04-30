"""Validation rules for task state transitions and dependency constraints."""
from __future__ import annotations

from src.ai.tools._store import TaskRecord, TaskStatus, ToolStore

_ALLOWED_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.IN_PROGRESS, TaskStatus.STOPPED},
    TaskStatus.IN_PROGRESS: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: {TaskStatus.PENDING},
    TaskStatus.STOPPED: {TaskStatus.PENDING},
}

_TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED}


def validate_transition(record: TaskRecord, new_status: TaskStatus) -> str | None:
    """Return an error message if the transition is invalid, else None."""
    allowed = _ALLOWED_TRANSITIONS.get(record.status, set())
    if new_status not in allowed:
        return (
            f"Cannot transition task '{record.id}' from '{record.status.value}' "
            f"to '{new_status.value}'."
        )
    return None


def validate_completion(record: TaskRecord, store: ToolStore) -> str | None:
    """Return an error if any blocker is unfinished when completing a task."""
    if record.blocked_by:
        for dep_id in record.blocked_by:
            dep = store.get_task(dep_id)
            if dep is None or dep.status not in _TERMINAL:
                blocker_status = dep.status.value if dep else "missing"
                return (
                    f"Cannot complete task '{record.id}': "
                    f"blocker '{dep_id}' is still '{blocker_status}'."
                )
    return None
