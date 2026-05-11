from __future__ import annotations

import json
from pathlib import Path

from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionContext,
    PermissionMode,
    PermissionRule,
    PermissionSource,
    PermissionSubject,
)
from src.ai.tools.session import PRESENT_OUTPUT_FILE_MARKER, build_present_output_file_tool, detect_artifact_type
from src.ai.tools.session.present_output_file import PresentOutputFileInput


def test_present_output_file_registers_managed_file(workspace: Path) -> None:
    report = workspace / "report.xlsx"
    report.write_bytes(b"xlsx bytes")
    tool = build_present_output_file_tool(workspace, owner_user_id="user_1")

    result = tool.invoke({"path": "report.xlsx", "title": "Q1 report", "description": "Final workbook"})
    payload = json.loads(result)

    assert payload[PRESENT_OUTPUT_FILE_MARKER] is True
    assert payload["message"] == "Presented output file: report.xlsx"
    artifact = payload["artifact"]
    assert artifact["filename"] == "report.xlsx"
    assert artifact["title"] == "Q1 report"
    assert artifact["description"] == "Final workbook"
    assert artifact["artifact_type"] == "spreadsheet"
    assert artifact["content_url"] == f"/api/files/{artifact['file_id']}/content"
    assert artifact["size"] == len(b"xlsx bytes")


def test_present_output_file_missing_file_returns_error(workspace: Path) -> None:
    tool = build_present_output_file_tool(workspace, owner_user_id="user_1")

    result = tool.invoke({"path": "missing.xlsx"})

    assert "does not exist" in result



def test_present_output_file_blocks_outside_workspace(workspace: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"pdf")
    tool = build_present_output_file_tool(workspace, owner_user_id="user_1")

    result = tool.invoke({"path": str(outside)})

    assert "Access denied" in result



def test_present_output_file_requires_authenticated_owner(workspace: Path) -> None:
    (workspace / "report.pdf").write_bytes(b"pdf")
    tool = build_present_output_file_tool(workspace)

    result = tool.invoke({"path": "report.pdf"})

    assert "requires an authenticated user session" in result



def test_present_output_file_respects_read_permissions(workspace: Path) -> None:
    (workspace / "secret.xlsx").write_bytes(b"secret")
    permission_context = PermissionContext(
        mode=PermissionMode.DEFAULT,
        workspace_root=workspace,
        working_directories=(workspace,),
        rules=(
            PermissionRule(
                subject=PermissionSubject.READ,
                behavior=PermissionBehavior.DENY,
                source=PermissionSource.SESSION,
                matcher="secret.xlsx",
            ),
        ),
    )
    tool = build_present_output_file_tool(
        workspace,
        owner_user_id="user_1",
        permission_context=permission_context,
    )

    result = tool.invoke({"path": "secret.xlsx"})

    assert "denied" in result.lower()


def test_detect_artifact_type_from_extension() -> None:
    assert detect_artifact_type("a.xlsx") == "spreadsheet"
    assert detect_artifact_type("a.pdf") == "pdf"
    assert detect_artifact_type("a.png") == "image"
    assert detect_artifact_type("a.csv") == "data"


def test_present_output_file_tool_description_guides_final_deliverables(workspace: Path) -> None:
    tool = build_present_output_file_tool(workspace, owner_user_id="user_1")

    assert "finished deliverables" in tool.description
    assert "Do not use it for temporary files" in tool.description
    assert "Call it once per final artifact version" in tool.description


def test_present_output_file_input_schema_descriptions_are_specific() -> None:
    schema = PresentOutputFileInput.model_fields

    assert "existing final output file" in (schema["path"].description or "")
    assert "Must point to a single file" in (schema["path"].description or "")
    assert "user-facing title" in (schema["title"].description or "")
    assert "one-sentence user-facing caption" in (schema["description"].description or "")
    assert "extension is ambiguous" in (schema["artifact_type"].description or "")
