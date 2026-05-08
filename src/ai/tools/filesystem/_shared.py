from __future__ import annotations

from langgraph.types import interrupt

from src.ai.filesystem import FilesystemService
from src.ai.permissions.evaluator import PermissionEvaluator
from src.ai.permissions.filesystem_policy import FilesystemPolicy
from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionContext,
    PermissionMode,
    PermissionSubject,
)
from src.app.services.settings import is_protected_aethos_path


def _approval_options(subject: PermissionSubject) -> list[dict[str, str]]:
    if subject is PermissionSubject.EDIT:
        return [
            {"id": "once", "label": "Approve once"},
            {"id": "thread_file", "label": "Allow this file in this thread"},
            {"id": "user_file", "label": "Always allow this file"},
        ]
    return [
        {"id": "once", "label": "Approve once"},
        {"id": "thread_file", "label": "Allow this file in this thread"},
        {"id": "user_file", "label": "Always allow this file"},
    ]


def _suggested_mode(subject: PermissionSubject) -> str:
    """Return the permission mode string to suggest for a filesystem subject (filesystem subjects only)."""
    if subject is PermissionSubject.EDIT:
        return PermissionMode.ACCEPT_EDITS.value
    return PermissionMode.BYPASS_PERMISSIONS.value


def permission_error(
    filesystem: FilesystemService,
    permission_context: PermissionContext | None,
    subject: PermissionSubject,
    path: str,
) -> str | None:
    """
    Check permission for a filesystem operation.

    Returns None if the operation is allowed.
    Returns an error string if the operation is denied.
    Calls interrupt() if the operation requires human approval — execution suspends
    here and resumes with the user's decision dict {"approved": bool}.
    """
    candidate, target = filesystem.resolve_permission_target(path)
    if subject is PermissionSubject.EDIT and is_protected_aethos_path(filesystem.root, target):
        return f"Permission denied: direct edits to protected Aethos config paths are not allowed ({candidate})."

    if permission_context is None:
        return None

    policy = FilesystemPolicy()
    evaluator = PermissionEvaluator()
    policy_decision = (
        policy.check_read(context=permission_context, target=target)
        if subject is PermissionSubject.READ
        else policy.check_edit(context=permission_context, target=target)
    )
    decision = evaluator.evaluate(
        context=permission_context,
        subject=subject,
        candidate=candidate,
        policy_decision=policy_decision,
    )

    if decision.behavior is PermissionBehavior.ALLOW:
        return None

    if decision.behavior is PermissionBehavior.ASK:
        user_decision = interrupt({
            "behavior": "ask",
            "reason": decision.reason,
            "subject": subject.value,
            "path": path,
            "approval_options": _approval_options(subject),
            "suggested_mode": _suggested_mode(subject),
            "suggestions": [s.value for s in (decision.suggestions or [])],
        })
        if user_decision.get("approved", False):
            return None
        return "Permission denied by user."

    # DENY — explicit policy decision, no human loop needed
    return f"Permission denied: {decision.reason}"
