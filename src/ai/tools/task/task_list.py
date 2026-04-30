"""task_list tool — list all tasks grouped by availability."""
from __future__ import annotations

import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from src.ai.tools._store import TaskStatus, ToolStore

_TERMINAL = {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED}


class TaskListInput(BaseModel):
    pass


def build_task_list_tool(store: ToolStore) -> StructuredTool:
    def _list() -> str:
        records = store.list_tasks()

        def _row(r):
            return {
                "id": r.id,
                "subject": r.subject,
                "status": r.status.value,
                "blocked_by": r.blocked_by,
                "blocks": r.blocks,
            }

        available, blocked, active, done = [], [], [], []
        for r in records:
            if r.status == TaskStatus.IN_PROGRESS:
                active.append(_row(r))
            elif r.status in _TERMINAL:
                done.append(_row(r))
            elif r.blocked_by and any(
                (dep := store.get_task(b)) is None or dep.status not in _TERMINAL
                for b in r.blocked_by
            ):
                blocked.append(_row(r))
            else:
                available.append(_row(r))

        return json.dumps({
            "tasks": [_row(r) for r in records],
            "summary": {
                "available": len(available),
                "active": len(active),
                "blocked": len(blocked),
                "done": len(done),
            },
            "available": available,
            "active": active,
            "blocked": blocked,
            "done": done,
        })

    return StructuredTool.from_function(
        name="task_list",
        func=_list,
        description="List all tasks grouped into available, active, blocked, and done.",
        args_schema=TaskListInput,
    )
