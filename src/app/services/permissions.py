from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ai.permissions import (
    PermissionBehavior,
    PermissionContext,
    PermissionMode,
    PermissionRule,
    PermissionSource,
    PermissionSubject,
    add_rule,
    add_working_directory,
    build_default_permission_context,
    set_mode,
)
from src.app.modules.auth.repository import AuthRepository
from src.app.services.thread_store import ThreadStore

_EMPTY_PROFILE = {"mode": None, "working_directories": [], "rules": []}


def _unique_strings(values: list[Any] | tuple[Any, ...] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        if not isinstance(value, str):
            continue
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def normalize_permission_profile(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return dict(_EMPTY_PROFILE)

    mode_value = raw.get("mode")
    mode = None
    if isinstance(mode_value, str) and mode_value:
        mode = PermissionMode(mode_value).value

    rules: list[dict[str, Any]] = []
    for rule in raw.get("rules") or []:
        if not isinstance(rule, dict):
            continue
        subject = PermissionSubject(str(rule.get("subject", "")).strip()).value
        behavior = PermissionBehavior(str(rule.get("behavior", "")).strip()).value
        matcher_value = rule.get("matcher")
        rules.append(
            {
                "subject": subject,
                "behavior": behavior,
                "matcher": matcher_value if isinstance(matcher_value, str) and matcher_value.strip() else None,
            }
        )

    return {
        "mode": mode,
        "working_directories": _unique_strings(raw.get("working_directories")),
        "rules": rules,
    }


def merge_permission_profiles(*profiles: dict[str, Any]) -> dict[str, Any]:
    mode = None
    working_directories: list[str] = []
    rules: list[dict[str, Any]] = []
    seen_dirs: set[str] = set()

    for profile in profiles:
        normalized = normalize_permission_profile(profile)
        if normalized["mode"] is not None:
            mode = normalized["mode"]
        for directory in normalized["working_directories"]:
            if directory not in seen_dirs:
                seen_dirs.add(directory)
                working_directories.append(directory)
        rules.extend(normalized["rules"])

    return {"mode": mode, "working_directories": working_directories, "rules": rules}


def _append_rule(profile: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_permission_profile(profile)
    rules = list(normalized["rules"])
    if rule not in rules:
        rules.append(rule)
    normalized["rules"] = rules
    return normalized


class PermissionContextService:
    def __init__(self, auth_repo: AuthRepository, thread_store: ThreadStore) -> None:
        self._auth_repo = auth_repo
        self._thread_store = thread_store

    def get_user_defaults(self, *, user_id: str) -> dict[str, Any]:
        return normalize_permission_profile(self._auth_repo.get_permission_defaults(user_id))

    def update_user_defaults(self, *, user_id: str, profile: dict[str, Any]) -> dict[str, Any] | None:
        normalized = normalize_permission_profile(profile)
        saved = self._auth_repo.update_permission_defaults(user_id=user_id, defaults=normalized)
        return normalize_permission_profile(saved)

    def get_thread_overlay(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        overlay = self._thread_store.get_permission_overlay(thread_id=thread_id, user_id=user_id)
        if overlay is None:
            return None
        return normalize_permission_profile(overlay)

    def get_project_settings(self, *, workspace_root: Path | None) -> dict[str, Any]:
        return self._read_workspace_settings_profile(workspace_root=workspace_root, filename="settings.json")

    def get_local_settings(self, *, workspace_root: Path | None) -> dict[str, Any]:
        return self._read_workspace_settings_profile(workspace_root=workspace_root, filename="settings.local.json")

    def update_thread_overlay(self, *, thread_id: str, user_id: str, profile: dict[str, Any]) -> dict[str, Any] | None:
        normalized = normalize_permission_profile(profile)
        saved = self._thread_store.update_permission_overlay(thread_id=thread_id, user_id=user_id, overlay=normalized)
        if saved is None:
            return None
        return normalize_permission_profile(saved)

    def grant_rule_for_scope(
        self,
        *,
        user_id: str,
        thread_id: str,
        scope: str,
        subject: str,
        matcher: str,
    ) -> dict[str, Any] | None:
        rule = {
            "subject": PermissionSubject(subject).value,
            "behavior": PermissionBehavior.ALLOW.value,
            "matcher": matcher,
        }
        if scope == "thread":
            current = self.get_thread_overlay(thread_id=thread_id, user_id=user_id)
            if current is None:
                return None
            return self.update_thread_overlay(
                thread_id=thread_id,
                user_id=user_id,
                profile=_append_rule(current, rule),
            )
        if scope == "user":
            current = self.get_user_defaults(user_id=user_id)
            return self.update_user_defaults(
                user_id=user_id,
                profile=_append_rule(current, rule),
            )
        return None

    def get_thread_permissions_bundle(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        overlay = self.get_thread_overlay(thread_id=thread_id, user_id=user_id)
        if overlay is None:
            return None
        defaults = self.get_user_defaults(user_id=user_id)
        workspace_root = self._settings_workspace_root(
            thread_id=thread_id,
            user_id=user_id,
            fallback_workspace_root=None,
        )
        project = self.get_project_settings(workspace_root=workspace_root)
        local = self.get_local_settings(workspace_root=workspace_root)
        effective = merge_permission_profiles(defaults, project, local, overlay)
        return {"defaults": defaults, "overlay": overlay, "effective": effective}

    def promote_thread_permissions(self, *, thread_id: str, user_id: str) -> dict[str, Any] | None:
        bundle = self.get_thread_permissions_bundle(thread_id=thread_id, user_id=user_id)
        if bundle is None:
            return None
        promoted = merge_permission_profiles(bundle["defaults"], bundle["overlay"])
        return self.update_user_defaults(user_id=user_id, profile=promoted)

    def build_effective_context(
        self,
        *,
        user_id: str,
        thread_id: str,
        workspace_root: Path,
    ) -> PermissionContext | None:
        overlay = self.get_thread_overlay(thread_id=thread_id, user_id=user_id)
        if overlay is None:
            return None
        active_workspace_root = workspace_root.resolve()
        settings_workspace_root = self._settings_workspace_root(
            thread_id=thread_id,
            user_id=user_id,
            fallback_workspace_root=active_workspace_root,
        )
        defaults = self.get_user_defaults(user_id=user_id)
        project = self.get_project_settings(workspace_root=settings_workspace_root)
        local = self.get_local_settings(workspace_root=settings_workspace_root)
        profile = merge_permission_profiles(defaults, project, local, overlay)
        context = build_default_permission_context(workspace_root=active_workspace_root)

        mode_value = profile.get("mode")
        if isinstance(mode_value, str):
            context = set_mode(context, PermissionMode(mode_value))

        for directory in profile.get("working_directories", []):
            path = Path(directory)
            resolved = path.resolve() if path.is_absolute() else (workspace_root / path).resolve()
            context = add_working_directory(context, resolved)

        for rule in defaults.get("rules", []):
            context = add_rule(context, self._rule_from_profile(rule, PermissionSource.USER))
        for rule in project.get("rules", []):
            context = add_rule(context, self._rule_from_profile(rule, PermissionSource.PROJECT))
        for rule in local.get("rules", []):
            context = add_rule(context, self._rule_from_profile(rule, PermissionSource.LOCAL))
        for rule in overlay.get("rules", []):
            context = add_rule(context, self._rule_from_profile(rule, PermissionSource.SESSION))

        return context

    def _settings_workspace_root(
        self,
        *,
        thread_id: str,
        user_id: str,
        fallback_workspace_root: Path | None,
    ) -> Path | None:
        stored_workspace_root = self._resolve_workspace_root(thread_id=thread_id, user_id=user_id)
        if stored_workspace_root is not None:
            return stored_workspace_root
        if fallback_workspace_root is None:
            return None
        return fallback_workspace_root.resolve()

    def _resolve_workspace_root(self, *, thread_id: str, user_id: str) -> Path | None:
        thread = self._thread_store.get_owned_thread(thread_id=thread_id, user_id=user_id)
        if not thread:
            return None
        workspace_root = thread.get("workspace_root")
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            return None
        return Path(workspace_root).expanduser().resolve()

    @staticmethod
    def _workspace_settings_dir(workspace_root: Path | None) -> Path | None:
        if workspace_root is None:
            return None
        return workspace_root / ".ethos"

    def _read_workspace_settings_profile(
        self,
        *,
        workspace_root: Path | None,
        filename: str,
    ) -> dict[str, Any]:
        settings_dir = self._workspace_settings_dir(workspace_root)
        if settings_dir is None:
            return dict(_EMPTY_PROFILE)
        path = settings_dir / filename
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return dict(_EMPTY_PROFILE)
        try:
            return normalize_permission_profile(raw if isinstance(raw, dict) else None)
        except Exception:
            return dict(_EMPTY_PROFILE)

    @staticmethod
    def _rule_from_profile(rule: dict[str, Any], source: PermissionSource) -> PermissionRule:
        return PermissionRule(
            subject=PermissionSubject(str(rule["subject"])),
            behavior=PermissionBehavior(str(rule["behavior"])),
            source=source,
            matcher=rule.get("matcher"),
        )
