"""task_update tool — update task fields or delete a task.

Status 'deleted' is a special action that removes the task (mirrors TS).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.ai.tools._store import TaskStatus, ToolStore
from src.ai.tools.task.task_validation import validate_completion, validate_transition


class TaskUpdateInput(BaseModel):
    task_id: str = Field(description="The ID of the task to update.")
    subject: Optional[str] = Field(default=None, description="New subject.")
    description: Optional[str] = Field(default=None, description="New description.")
    active_form: Optional[str] = Field(default=None, description="New active form text.")
    status: Optional[str] = Field(
        default=None,
        description="New status: 'pending', 'in_progress', 'completed', 'failed', 'stopped', or 'deleted'.",
    )
    metadata: Optional[dict[str, Any]] = Field(default=None, description="Metadata to merge.")
    add_blocked_by: Optional[list[str]] = Field(default=None, description="Task IDs to add as blockers.")
    add_blocks: Optional[list[str]] = Field(default=None, description="Task IDs that this task should block.")


def build_task_update_tool(store: ToolStore) -> StructuredTool:
    def _update(
        task_id: str,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        active_form: Optional[str] = None,
        status: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        add_blocked_by: Optional[list[str]] = None,
        add_blocks: Optional[list[str]] = None,
    ) -> str:
        if status == "deleted":
            deleted = store.delete_task(task_id)
            if not deleted:
                return f"Error: task '{task_id}' not found."
            return json.dumps({"deleted": True, "task_id": task_id})

        record = store.get_task(task_id)
        if record is None:
            return f"Error: task '{task_id}' not found."

        parsed_status: Optional[TaskStatus] = None
        if status is not None:
            try:
                parsed_status = TaskStatus(status)
            except ValueError:
                return f"Error: unknown status '{status}'."

            err = validate_transition(record, parsed_status)
            if err:
                return f"Error: {err}"

            if parsed_status == TaskStatus.COMPLETED:
                err = validate_completion(record, store)
                if err:
                    return f"Error: {err}"

        # Handle dependency additions
        dep_errors = []
        for dep_id in (add_blocked_by or []):
            err = store.add_dependency(task_id, dep_id)
            if err:
                dep_errors.append(err)
            elif store.has_cycle(task_id):
                dep = store.get_task(dep_id)
                if dep and task_id in dep.blocks:
                    dep.blocks.remove(task_id)
                if dep_id in record.blocked_by:
                    record.blocked_by.remove(dep_id)
                dep_errors.append(f"Adding '{dep_id}' as blocker would create a cycle.")

        for dep_id in (add_blocks or []):
            err = store.add_dependency(dep_id, task_id)
            if err:
                dep_errors.append(err)
            elif store.has_cycle(dep_id):
                if dep_id in record.blocks:
                    record.blocks.remove(dep_id)
                dep = store.get_task(dep_id)
                if dep and task_id in dep.blocked_by:
                    dep.blocked_by.remove(task_id)
                dep_errors.append(f"Adding '{dep_id}' as dependent would create a cycle.")

        record = store.update_task(
            task_id,
            subject=subject,
            description=description,
            status=parsed_status,
            active_form=active_form,
            metadata=metadata,
        )

        result: dict[str, Any] = {
            "id": record.id,
            "subject": record.subject,
            "status": record.status.value,
            "blocked_by": record.blocked_by,
            "blocks": record.blocks,
        }
        if dep_errors:
            result["warnings"] = dep_errors
        return json.dumps(result)

    return StructuredTool.from_function(
        name="task_update",
        func=_update,
        description=(
            "Update a task's fields. Use status='deleted' to remove the task. "
            "Use add_blocked_by/add_blocks to manage dependencies."
        ),
        args_schema=TaskUpdateInput,
    )
