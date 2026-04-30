"""Tests for task management tools (TaskCreate/Get/List/Update/Stop/Output)."""
from __future__ import annotations

import json
import pytest
from src.ai.tools._store import ToolStore, TaskStatus
from src.ai.tools.task import (
    build_task_create_tool, build_task_get_tool, build_task_list_tool,
    build_task_update_tool, build_task_stop_tool, build_task_output_tool,
)


@pytest.fixture()
def store() -> ToolStore:
    return ToolStore()


def test_task_create_returns_id_and_subject(store: ToolStore) -> None:
    tool = build_task_create_tool(store)
    result = json.loads(tool.invoke({"subject": "Run tests", "description": "Execute pytest"}))
    assert "id" in result["task"]
    assert result["task"]["subject"] == "Run tests"


def test_task_create_stores_in_store(store: ToolStore) -> None:
    tool = build_task_create_tool(store)
    result = json.loads(tool.invoke({"subject": "X", "description": "Y"}))
    assert store.get_task(result["task"]["id"]) is not None


def test_task_create_with_active_form(store: ToolStore) -> None:
    tool = build_task_create_tool(store)
    result = json.loads(tool.invoke({"subject": "Build", "description": "compile", "active_form": "Building..."}))
    record = store.get_task(result["task"]["id"])
    assert record.active_form == "Building..."


def test_task_get_existing(store: ToolStore) -> None:
    record = store.create_task(subject="S", description="D")
    tool = build_task_get_tool(store)
    result = json.loads(tool.invoke({"task_id": record.id}))
    assert result["id"] == record.id
    assert result["status"] == "pending"


def test_task_get_missing(store: ToolStore) -> None:
    tool = build_task_get_tool(store)
    result = tool.invoke({"task_id": "no-such-task"})
    assert "not found" in result.lower()


def test_task_list_empty(store: ToolStore) -> None:
    tool = build_task_list_tool(store)
    result = json.loads(tool.invoke({}))
    assert result["tasks"] == []


def test_task_list_returns_all(store: ToolStore) -> None:
    store.create_task(subject="A", description="a")
    store.create_task(subject="B", description="b")
    tool = build_task_list_tool(store)
    result = json.loads(tool.invoke({}))
    assert len(result["tasks"]) == 2


def test_task_update_status(store: ToolStore) -> None:
    record = store.create_task(subject="S", description="D")
    tool = build_task_update_tool(store)
    result = json.loads(tool.invoke({"task_id": record.id, "status": "in_progress"}))
    assert result["status"] == "in_progress"
    assert store.get_task(record.id).status == TaskStatus.IN_PROGRESS


def test_task_update_subject(store: ToolStore) -> None:
    record = store.create_task(subject="Old", description="D")
    tool = build_task_update_tool(store)
    result = json.loads(tool.invoke({"task_id": record.id, "subject": "New"}))
    assert result["subject"] == "New"


def test_task_update_deleted_removes_task(store: ToolStore) -> None:
    record = store.create_task(subject="Del", description="me")
    tool = build_task_update_tool(store)
    tool.invoke({"task_id": record.id, "status": "deleted"})
    assert store.get_task(record.id) is None


def test_task_update_missing(store: ToolStore) -> None:
    tool = build_task_update_tool(store)
    result = tool.invoke({"task_id": "ghost", "status": "completed"})
    assert "not found" in result.lower()


def test_task_stop_marks_stopped(store: ToolStore) -> None:
    record = store.create_task(subject="S", description="D")
    tool = build_task_stop_tool(store)
    result = json.loads(tool.invoke({"task_id": record.id}))
    assert result["stopped"] is True
    assert store.get_task(record.id).status == TaskStatus.STOPPED


def test_task_stop_missing(store: ToolStore) -> None:
    tool = build_task_stop_tool(store)
    result = tool.invoke({"task_id": "nope"})
    assert "not found" in result.lower()


def test_task_output_returns_accumulated(store: ToolStore) -> None:
    record = store.create_task(subject="Cmd", description="run it")
    store.append_output(record.id, "stdout line1\n")
    store.append_output(record.id, "stdout line2\n")
    tool = build_task_output_tool(store)
    result = tool.invoke({"task_id": record.id})
    assert "stdout line1" in result
    assert "stdout line2" in result


def test_task_output_missing_task(store: ToolStore) -> None:
    tool = build_task_output_tool(store)
    result = tool.invoke({"task_id": "x"})
    assert "not found" in result.lower()


def test_task_output_empty(store: ToolStore) -> None:
    record = store.create_task(subject="Q", description="quiet")
    tool = build_task_output_tool(store)
    result = tool.invoke({"task_id": record.id})
    assert result == "(no output yet)"


# ── dependency graph ──────────────────────────────────────────────────────────

def test_task_create_with_blocked_by(store: ToolStore) -> None:
    dep = store.create_task(subject="Dep", description="prereq")
    tool = build_task_create_tool(store)
    result = json.loads(tool.invoke({
        "subject": "Child", "description": "needs dep", "blocked_by": [dep.id]
    }))
    assert "warnings" not in result
    child = store.get_task(result["task"]["id"])
    assert dep.id in child.blocked_by
    assert child.id in store.get_task(dep.id).blocks


def test_task_create_blocked_by_missing_dep_reports_warning(store: ToolStore) -> None:
    tool = build_task_create_tool(store)
    result = json.loads(tool.invoke({
        "subject": "X", "description": "y", "blocked_by": ["no-such-task"]
    }))
    assert "warnings" in result
    assert any("not found" in w for w in result["warnings"])


def test_task_create_cycle_detection(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    store.add_dependency(b.id, a.id)  # B blocked_by A

    tool = build_task_create_tool(store)
    result = json.loads(tool.invoke({
        "subject": "A2", "description": "tries to cycle", "blocked_by": [b.id]
    }))
    # The new task uses b as blocker, but b is already blocked by a.
    # No direct cycle here (new task → b → a) — fine. Test a real cycle:
    # Make a cycle by having a blocked_by the new task (if it were added back).
    # Instead, manually create the cycle scenario:
    c = store.create_task(subject="C", description="c")
    store.add_dependency(c.id, a.id)  # C blocked_by A
    err = store.add_dependency(a.id, c.id)  # A blocked_by C → cycle A→C→A
    assert err is None  # add_dependency itself doesn't detect cycle
    assert store.has_cycle(a.id)  # cycle detection via DFS


def test_store_get_available_tasks(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    store.add_dependency(b.id, a.id)  # B blocked_by A

    available = store.get_available_tasks()
    ids = [t.id for t in available]
    assert a.id in ids
    assert b.id not in ids  # B is blocked


def test_store_get_blocked_tasks(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    store.add_dependency(b.id, a.id)

    blocked = store.get_blocked_tasks()
    assert any(t.id == b.id for t in blocked)


def test_store_blocked_task_becomes_available_when_dep_completes(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    store.add_dependency(b.id, a.id)

    store.update_task(a.id, status=None)  # no status change yet
    assert any(t.id == b.id for t in store.get_blocked_tasks())

    from src.ai.tools._store import TaskStatus
    store.update_task(a.id, status=TaskStatus.COMPLETED)
    available = store.get_available_tasks()
    assert any(t.id == b.id for t in available)


def test_task_update_add_blocked_by(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    tool = build_task_update_tool(store)
    result = json.loads(tool.invoke({"task_id": b.id, "add_blocked_by": [a.id]}))
    assert a.id in result["blocked_by"]
    assert "warnings" not in result


def test_task_update_add_blocks(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    tool = build_task_update_tool(store)
    result = json.loads(tool.invoke({"task_id": a.id, "add_blocks": [b.id]}))
    assert b.id in result["blocks"]


def test_task_update_cannot_complete_with_pending_blocker(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    store.add_dependency(b.id, a.id)
    store.update_task(b.id, status=None)  # keep pending

    tool = build_task_update_tool(store)
    # First transition to in_progress (required before completed)
    tool.invoke({"task_id": b.id, "status": "in_progress"})
    result = tool.invoke({"task_id": b.id, "status": "completed"})
    assert "error" in result.lower()
    assert "blocker" in result.lower() or "blocked" in result.lower()


def test_task_update_can_complete_when_blocker_done(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    store.add_dependency(b.id, a.id)

    from src.ai.tools._store import TaskStatus
    store.update_task(a.id, status=TaskStatus.COMPLETED)
    store.update_task(b.id, status=TaskStatus.IN_PROGRESS)

    tool = build_task_update_tool(store)
    result = json.loads(tool.invoke({"task_id": b.id, "status": "completed"}))
    assert result["status"] == "completed"


def test_task_update_invalid_transition(store: ToolStore) -> None:
    record = store.create_task(subject="S", description="D")
    tool = build_task_update_tool(store)
    # Cannot go from pending directly to completed
    result = tool.invoke({"task_id": record.id, "status": "completed"})
    assert "error" in result.lower()


def test_task_get_includes_blocker_details(store: ToolStore) -> None:
    a = store.create_task(subject="Prereq", description="must finish first")
    b = store.create_task(subject="Dependent", description="needs a")
    store.add_dependency(b.id, a.id)

    tool = build_task_get_tool(store)
    result = json.loads(tool.invoke({"task_id": b.id}))
    assert len(result["blocker_details"]) == 1
    assert result["blocker_details"][0]["subject"] == "Prereq"


def test_task_list_groups_correctly(store: ToolStore) -> None:
    a = store.create_task(subject="A", description="a")
    b = store.create_task(subject="B", description="b")
    store.add_dependency(b.id, a.id)

    from src.ai.tools._store import TaskStatus
    store.update_task(a.id, status=TaskStatus.IN_PROGRESS)

    tool = build_task_list_tool(store)
    result = json.loads(tool.invoke({}))
    assert result["summary"]["active"] == 1
    assert result["summary"]["blocked"] == 1
    assert len(result["active"]) == 1
    assert len(result["blocked"]) == 1

