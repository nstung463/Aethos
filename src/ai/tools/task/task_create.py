"""task_create tool â€” create a new task record in the store."""
from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.ai.tools._store import ToolStore


class TaskCreateInput(BaseModel):
    subject: str = Field(description="A brief title for the task.")
    description: str = Field(description="What needs to be done.")
    active_form: Optional[str] = Field(default=None, description="Present continuous form shown while in_progress.")
    metadata: Optional[dict[str, Any]] = Field(default=None, description="Arbitrary metadata to attach.")
    blocked_by: Optional[list[str]] = Field(default=None, description="IDs of tasks that must complete before this one.")
    owner: Optional[str] = Field(default=None, description="Optional owner identifier.")


def build_task_create_tool(store: ToolStore) -> StructuredTool:
    def _create(
        subject: str,
        description: str,
        active_form: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        blocked_by: Optional[list[str]] = None,
        owner: Optional[str] = None,
    ) -> str:
        # Create with empty blocked_by; only add deps that pass validation.
        record = store.create_task(subject=subject, description=description,
                                    active_form=active_form, metadata=metadata,
                                    blocked_by=[], owner=owner)
        errors = []
        for dep_id in (blocked_by or []):
            err = store.add_dependency(record.id, dep_id)
            if err:
                # Invalid dep (not found etc.) — do NOT add to record.blocked_by.
                errors.append(err)
            elif store.has_cycle(record.id):
                dep = store.get_task(dep_id)
                if dep and record.id in dep.blocks:
                    dep.blocks.remove(record.id)
                if dep_id in record.blocked_by:
                    record.blocked_by.remove(dep_id)
                errors.append(f"Adding '{dep_id}' as blocker would create a cycle.")
        result: dict[str, Any] = {"task": {"id": record.id, "subject": record.subject}}
        if errors:
            result["warnings"] = errors
        return json.dumps(result)

    return StructuredTool.from_function(
        name="task_create",
        func=_create,
        description="Create a new task to track a unit of work. Returns the task ID.",
        args_schema=TaskCreateInput,
    )

