from __future__ import annotations

from pathlib import Path

from src.app.services.settings import is_protected_aethos_path
from src.ai.permissions.suggestions import suggest_directory, suggest_mode
from src.ai.permissions.types import (
    PermissionBehavior,
    PermissionContext,
    PermissionDecision,
    PermissionMode,
)


class FilesystemPolicy:
    def _normalize(self, context: PermissionContext, target: Path) -> Path | None:
        resolved = target.resolve()
        try:
            resolved.relative_to(context.workspace_root)
        except ValueError:
            return None  # path escapes workspace
        return resolved

    def _in_working_dirs(self, context: PermissionContext, target: Path) -> bool:
        return any(
            target == working_dir or target.is_relative_to(working_dir)
            for working_dir in context.working_directories
        )

    def check_read(self, *, context: PermissionContext, target: Path) -> PermissionDecision:
        normalized = self._normalize(context, target)
        if normalized is None:
            return PermissionDecision(
                behavior=PermissionBehavior.DENY,
                reason="Path resolves outside workspace root",
            )
        if self._in_working_dirs(context, normalized):
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                reason="Read inside working directory",
            )
        return PermissionDecision(
            behavior=PermissionBehavior.ASK,
            reason="Read outside working directory",
            suggestions=(suggest_directory(normalized.parent),),
        )

    def check_edit(self, *, context: PermissionContext, target: Path) -> PermissionDecision:
        normalized = self._normalize(context, target)
        if normalized is None:
            return PermissionDecision(
                behavior=PermissionBehavior.DENY,
                reason="Path resolves outside workspace root",
            )
        if is_protected_aethos_path(context.workspace_root, normalized):
            return PermissionDecision(
                behavior=PermissionBehavior.DENY,
                reason="Direct edits to protected .aethos config paths are not allowed",
            )
        edit_modes = {PermissionMode.ACCEPT_EDITS, PermissionMode.BYPASS_PERMISSIONS}
        if context.mode in edit_modes and self._in_working_dirs(context, normalized):
            return PermissionDecision(
                behavior=PermissionBehavior.ALLOW,
                reason=f"Edit allowed by {context.mode.value} in working directory",
            )
        return PermissionDecision(
            behavior=PermissionBehavior.ASK,
            reason="Edit requires approval",
            suggestions=(suggest_mode("accept_edits"),),
        )
