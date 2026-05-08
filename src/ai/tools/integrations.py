"""Native integration tools backed by the Connections service."""

from __future__ import annotations

from typing import Callable

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from src.ai.permissions.evaluator import PermissionEvaluator
from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
    PermissionSubject,
)
from src.app.services.connections import ConnectionService, WRITE_TOOL_NAMES


class _BaseConnectionInput(BaseModel):
    connection_id: str | None = Field(default=None, description="Optional connection ID. Uses the most recently updated active account when omitted.")


class GmailSearchInput(_BaseConnectionInput):
    query: str = Field(default="", description="Gmail search query.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of messages to return.")


class GmailGetInput(_BaseConnectionInput):
    message_id: str = Field(description="Gmail message ID.")


class GmailSendInput(_BaseConnectionInput):
    to: str = Field(description="Recipient email address.")
    subject: str = Field(description="Email subject.")
    body: str = Field(description="Plain text email body.")


class DriveSearchInput(_BaseConnectionInput):
    query: str = Field(default="", description="Drive search query. Defaults to non-trashed files.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of files to return.")


class DriveReadInput(_BaseConnectionInput):
    file_id: str = Field(description="Google Drive file ID.")


class CalendarListInput(_BaseConnectionInput):
    calendar_id: str = Field(default="primary", description="Calendar ID. Defaults to primary.")
    time_min: str | None = Field(default=None, description="Optional RFC3339 lower bound.")
    time_max: str | None = Field(default=None, description="Optional RFC3339 upper bound.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of events.")


class CalendarCreateInput(_BaseConnectionInput):
    title: str = Field(description="Event title.")
    start: str = Field(description="RFC3339 start datetime.")
    end: str = Field(description="RFC3339 end datetime.")
    calendar_id: str = Field(default="primary", description="Calendar ID. Defaults to primary.")
    description: str | None = Field(default=None, description="Optional event description.")
    attendees: list[str] = Field(default_factory=list, description="Optional attendee email addresses.")


class SheetsReadInput(_BaseConnectionInput):
    spreadsheet_id: str = Field(description="Google Sheets spreadsheet ID.")
    range: str = Field(description="A1 notation range.")


class SheetsAppendInput(_BaseConnectionInput):
    spreadsheet_id: str = Field(description="Google Sheets spreadsheet ID.")
    range: str = Field(description="A1 notation range to append into.")
    values: list[list[str]] = Field(description="Rows to append.")


class SlackListChannelsInput(_BaseConnectionInput):
    limit: int = Field(default=20, ge=1, le=100, description="Maximum number of channels to return.")


class SlackSearchMessagesInput(_BaseConnectionInput):
    query: str = Field(description="Slack search query.")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of matches to return.")


class SlackPostMessageInput(_BaseConnectionInput):
    channel: str = Field(description="Slack channel ID or name.")
    text: str = Field(description="Slack message text.")


def _candidate(provider: str, connection_id: str | None) -> str:
    return f"integration:{provider}:{connection_id or 'default'}"


def _check_integration_permission(
    *,
    permission_context: PermissionContext | None,
    provider: str,
    connection_id: str | None,
) -> str | None:
    if permission_context is None:
        return None
    evaluator = PermissionEvaluator()
    decision = evaluator.evaluate(
        context=permission_context,
        subject=PermissionSubject.INTEGRATION,
        candidate=_candidate(provider, connection_id),
        policy_decision=PermissionDecision(
            behavior=PermissionBehavior.PASSTHROUGH,
            reason="No matching integration permission rule or mode-based allow",
        ),
    )
    if decision.behavior is PermissionBehavior.ALLOW:
        return None
    if decision.behavior is PermissionBehavior.ASK:
        user_decision = interrupt(
            {
                "behavior": "ask",
                "reason": decision.reason,
                "subject": PermissionSubject.INTEGRATION.value,
                "source": _candidate(provider, connection_id),
                "suggested_mode": "bypass_permissions",
            }
        )
        if user_decision.get("approved", False):
            return None
        return "Permission denied by user."
    return f"Permission denied: {decision.reason}"


def _confirm_write(*, tool_name: str, provider: str, payload: dict[str, object], account_hint: str | None) -> str | None:
    user_decision = interrupt(
        {
            "behavior": "ask",
            "reason": f"Approval required before {tool_name} sends a write request to {provider}.",
            "subject": PermissionSubject.INTEGRATION.value,
            "tool_name": tool_name,
            "source": account_hint or provider,
            "path": _candidate(provider, str(payload.get("connection_id")) if payload.get("connection_id") else None),
            "suggested_mode": "bypass_permissions",
        }
    )
    if user_decision.get("approved", False):
        return None
    return "Permission denied by user."


def _build_tool(
    *,
    name: str,
    description: str,
    provider: str,
    workspace_root: str,
    owner_user_id: str | None,
    permission_context: PermissionContext | None,
    input_model: type[BaseModel],
) -> StructuredTool:
    def _run(**kwargs: object) -> str:
        if not owner_user_id:
            return "This integration tool requires an authenticated user session."
        payload = dict(kwargs)
        connection_id = payload.get("connection_id")
        resolved_connection_id = connection_id if isinstance(connection_id, str) and connection_id.strip() else None
        error = _check_integration_permission(
            permission_context=permission_context,
            provider=provider,
            connection_id=resolved_connection_id,
        )
        if error is not None:
            return error
        if name in WRITE_TOOL_NAMES:
            confirmation_error = _confirm_write(
                tool_name=name,
                provider=provider,
                payload=payload,
                account_hint=resolved_connection_id,
            )
            if confirmation_error is not None:
                return confirmation_error
        service = ConnectionService(workspace_root=workspace_root)
        return service.perform_tool(
            provider=provider,  # type: ignore[arg-type]
            tool_name=name,
            owner_user_id=owner_user_id,
            connection_id=resolved_connection_id,
            payload=payload,
        )

    return StructuredTool.from_function(
        name=name,
        func=_run,
        description=description,
        args_schema=input_model,
    )


def build_integration_tools(
    *,
    root_dir: str,
    owner_user_id: str | None,
    permission_context: PermissionContext | None = None,
) -> list[StructuredTool]:
    service = ConnectionService(workspace_root=root_dir)
    available = {
        item.provider
        for item in (service.list_effective_connections(owner_user_id=owner_user_id) if owner_user_id else [])
        if item.status == "active" and item.tools_enabled
    }
    tools: list[StructuredTool] = []

    def add(
        name: str,
        description: str,
        provider: str,
        input_model: type[BaseModel],
    ) -> None:
        tools.append(
            _build_tool(
                name=name,
                description=description,
                provider=provider,
                workspace_root=root_dir,
                owner_user_id=owner_user_id,
                permission_context=permission_context,
                input_model=input_model,
            )
        )

    gmail_provider = "google-gmail" if "google-gmail" in available else ("google" if "google" in available else None)
    drive_provider = "google-drive" if "google-drive" in available else ("google" if "google" in available else None)
    calendar_provider = "google-calendar" if "google-calendar" in available else ("google" if "google" in available else None)
    sheets_provider = "google-sheets" if "google-sheets" in available else ("google" if "google" in available else None)

    if gmail_provider:
        add("gmail_search_messages", "Search Gmail messages using the connected Google account.", gmail_provider, GmailSearchInput)
        add("gmail_get_message", "Read a Gmail message by ID.", gmail_provider, GmailGetInput)
        add("gmail_send_message", "Send a plain text Gmail message after explicit approval.", gmail_provider, GmailSendInput)
    if drive_provider:
        add("drive_search_files", "Search Google Drive files.", drive_provider, DriveSearchInput)
        add("drive_read_file", "Read or export a Google Drive file by ID.", drive_provider, DriveReadInput)
    if calendar_provider:
        add("calendar_list_events", "List Google Calendar events.", calendar_provider, CalendarListInput)
        add("calendar_create_event", "Create a Google Calendar event after explicit approval.", calendar_provider, CalendarCreateInput)
    if sheets_provider:
        add("sheets_read_values", "Read values from a Google Sheet range.", sheets_provider, SheetsReadInput)
        add("sheets_append_values", "Append values to a Google Sheet after explicit approval.", sheets_provider, SheetsAppendInput)
    if "slack" in available:
        add("slack_list_channels", "List Slack channels for the connected workspace.", "slack", SlackListChannelsInput)
        add("slack_search_messages", "Search Slack messages.", "slack", SlackSearchMessagesInput)
        add("slack_post_message", "Post a Slack message after explicit approval.", "slack", SlackPostMessageInput)

    return tools


__all__ = ["build_integration_tools"]
