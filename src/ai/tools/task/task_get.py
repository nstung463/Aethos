"""task_get tool — retrieve a task by ID."""
from __future__ import annotations

import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from src.ai.tools._store import ToolStore


class TaskGetInput(BaseModel):
    task_id: str = Field(description="The ID of the task to retrieve.")


def build_task_get_tool(store: ToolStore) -> StructuredTool:
    def _get(task_id: str) -> str:
        record = store.get_task(task_id)
        if record is None:
            return f"Error: task '{task_id}' not found."

        blocker_details = []
        for bid in record.blocked_by:
            dep = store.get_task(bid)
            blocker_details.append({
                "id": bid,
                "subject": dep.subject if dep else "(unknown)",
                "status": dep.status.value if dep else "missing",
            })

        dependent_details = []
        for did in record.blocks:
            dep = store.get_task(did)
            dependent_details.append({
                "id": did,
                "subject": dep.subject if dep else "(unknown)",
                "status": dep.status.value if dep else "missing",
            })

        return json.dumps({
            "id": record.id,
            "subject": record.subject,
            "description": record.description,
            "status": record.status.value,
            "active_form": record.active_form,
            "metadata": record.metadata,
            "stopped": record.stopped,
            "owner": record.owner,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "blocked_by": record.blocked_by,
            "blocks": record.blocks,
            "blocker_details": blocker_details,
            "dependent_details": dependent_details,
        })

    return StructuredTool.from_function(
        name="task_get",
        func=_get,
        description="Get the current state of a task by its ID, including dependency details.",
        args_schema=TaskGetInput,
    )
