from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from src.app.core.settings import get_settings

logger = logging.getLogger(__name__)

SettingSource = Literal["user", "project", "local", "managed"]

_LEGACY_PERMISSION_KEYS = {"mode", "working_directories", "workingDirectories", "rules"}
_PROTECTED_AETHOS_FILES = {"settings.json", "settings.local.json", "instructions.md"}
_PROTECTED_AETHOS_DIRS = {"skills", "agents", "commands"}


@dataclass(frozen=True)
class SettingsValidationResult:
    is_valid: bool
    normalized: dict[str, Any]
    errors: tuple[str, ...] = ()


def _deep_merge(base: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in incoming.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _unique_strings(values: Any) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    if not isinstance(values, list):
        return normalized
    for item in values:
        if not isinstance(item, str):
            continue
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized


def normalize_permission_profile(raw: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"mode": None, "working_directories": [], "rules": []}

    mode_value = raw.get("mode")
    mode = mode_value.strip() if isinstance(mode_value, str) and mode_value.strip() else None

    directories_value = raw.get("workingDirectories")
    if directories_value is None:
        directories_value = raw.get("working_directories")

    rules: list[dict[str, Any]] = []
    for item in raw.get("rules") or []:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject", "")).strip()
        behavior = str(item.get("behavior", "")).strip()
        matcher = item.get("matcher")
        if not subject or not behavior:
            continue
        rules.append(
            {
                "subject": subject,
                "behavior": behavior,
                "matcher": matcher.strip() if isinstance(matcher, str) and matcher.strip() else None,
            }
        )

    return {
        "mode": mode,
        "working_directories": _unique_strings(directories_value),
        "rules": rules,
    }


def permission_profile_to_settings(profile: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_permission_profile(profile)
    return {
        "mode": normalized["mode"],
        "workingDirectories": list(normalized["working_directories"]),
        "rules": list(normalized["rules"]),
    }


def _normalize_permission_settings(raw: dict[str, Any], *, preserve_missing: bool) -> dict[str, Any]:
    normalized = normalize_permission_profile(raw)
    settings: dict[str, Any] = {}
    if not preserve_missing or "mode" in raw:
        settings["mode"] = normalized["mode"]
    if not preserve_missing or "workingDirectories" in raw or "working_directories" in raw:
        settings["workingDirectories"] = list(normalized["working_directories"])
    if not preserve_missing or "rules" in raw:
        settings["rules"] = list(normalized["rules"])
    return settings


def extract_permission_profile(settings_data: dict[str, Any]) -> dict[str, Any]:
    permissions = settings_data.get("permissions")
    if isinstance(permissions, dict):
        return normalize_permission_profile(permissions)
    return {"mode": None, "working_directories": [], "rules": []}


def is_protected_aethos_path(workspace_root: Path, target: Path) -> bool:
    normalized_workspace = workspace_root.resolve()
    normalized_target = target.resolve()
    aethos_root = normalized_workspace / ".aethos"
    try:
        relative = normalized_target.relative_to(aethos_root)
    except ValueError:
        return False
    if not relative.parts:
        return False
    first = relative.parts[0].lower()
    if len(relative.parts) == 1 and first in _PROTECTED_AETHOS_FILES:
        return True
    return first in _PROTECTED_AETHOS_DIRS


class SettingsService:
    def __init__(
        self,
        *,
        config_home: Path | None = None,
        managed_settings_dir: Path | None = None,
    ) -> None:
        app_settings = get_settings()
        self.config_home = (
            Path(config_home).expanduser().resolve()
            if config_home is not None
            else app_settings.aethos_config_dir.expanduser().resolve()
        )
        self.managed_settings_dir = (
            Path(managed_settings_dir).expanduser().resolve()
            if managed_settings_dir is not None
            else app_settings.aethos_managed_settings_dir.expanduser().resolve()
        )

    def get_settings_file_path(
        self,
        source: SettingSource,
        *,
        workspace_root: str | Path | None = None,
    ) -> Path:
        if source == "user":
            return self.config_home / "settings.json"
        if source == "managed":
            return self.managed_settings_dir / "managed-settings.json"
        if workspace_root is None:
            raise ValueError(f"workspace_root is required for {source} settings")
        root = Path(workspace_root).expanduser().resolve()
        filename = "settings.json" if source == "project" else "settings.local.json"
        return root / ".aethos" / filename

    def get_managed_drop_in_dir(self) -> Path:
        return self.managed_settings_dir / "managed-settings.d"

    def validate_settings_content(self, content: str | bytes | dict[str, Any] | Any) -> SettingsValidationResult:
        if isinstance(content, dict):
            data = dict(content)
        else:
            try:
                text = content.decode("utf-8") if isinstance(content, bytes) else str(content)
                decoded = json.loads(text)
            except Exception as exc:
                return SettingsValidationResult(is_valid=False, normalized={}, errors=(str(exc),))
            if not isinstance(decoded, dict):
                return SettingsValidationResult(
                    is_valid=False,
                    normalized={},
                    errors=("Settings content must decode to a JSON object.",),
                )
            data = decoded

        normalized = self.normalize_settings_dict(data)
        errors: list[str] = []

        mcp_servers = normalized.get("mcpServers")
        if mcp_servers is not None and not isinstance(mcp_servers, dict):
            errors.append("mcpServers must be an object map.")

        permissions = normalized.get("permissions")
        if permissions is not None and not isinstance(permissions, dict):
            errors.append("permissions must be an object.")

        return SettingsValidationResult(
            is_valid=not errors,
            normalized=normalized if not errors else {},
            errors=tuple(errors),
        )

    def normalize_settings_dict(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {}

        normalized = dict(raw)

        if "permissions" in normalized and isinstance(normalized["permissions"], dict):
            normalized["permissions"] = _normalize_permission_settings(
                normalized["permissions"],
                preserve_missing=True,
            )
        elif any(key in normalized for key in _LEGACY_PERMISSION_KEYS):
            normalized["permissions"] = _normalize_permission_settings(normalized, preserve_missing=False)

        for key in _LEGACY_PERMISSION_KEYS:
            if key != "permissions":
                normalized.pop(key, None)

        return normalized

    def get_settings_for_source(
        self,
        source: SettingSource,
        *,
        workspace_root: str | Path | None = None,
    ) -> dict[str, Any]:
        if source == "managed":
            return self.load_managed_settings()

        path = self.get_settings_file_path(source, workspace_root=workspace_root)
        return self._read_settings_file(path, source=source)

    def get_effective_settings(
        self,
        *,
        workspace_root: str | Path | None = None,
    ) -> dict[str, Any]:
        merged = self.get_settings_for_source("user")
        if workspace_root is not None:
            merged = _deep_merge(merged, self.get_settings_for_source("project", workspace_root=workspace_root))
            merged = _deep_merge(merged, self.get_settings_for_source("local", workspace_root=workspace_root))
        return _deep_merge(merged, self.load_managed_settings())

    def load_managed_settings(self) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        base_path = self.get_settings_file_path("managed")
        merged = _deep_merge(merged, self._read_settings_file(base_path, source="managed"))

        drop_in_dir = self.get_managed_drop_in_dir()
        try:
            entries = sorted(
                path for path in drop_in_dir.iterdir()
                if path.is_file() and path.suffix.lower() == ".json" and not path.name.startswith(".")
            )
        except FileNotFoundError:
            return merged
        except OSError as exc:
            logger.warning("Failed to read managed settings drop-ins from %s: %s", drop_in_dir, exc)
            return merged

        for path in entries:
            merged = _deep_merge(merged, self._read_settings_file(path, source="managed"))
        return merged

    def update_settings_for_source(
        self,
        source: SettingSource,
        patch: dict[str, Any],
        *,
        workspace_root: str | Path | None = None,
    ) -> dict[str, Any]:
        if source == "managed":
            raise ValueError("Managed settings are read-only")

        validation = self.validate_settings_content(patch)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))

        path = self.get_settings_file_path(source, workspace_root=workspace_root)
        current = self.get_settings_for_source(source, workspace_root=workspace_root)
        updated = _deep_merge(current, validation.normalized)
        self._atomic_write_json(path, updated)
        return updated

    def write_settings_for_source(
        self,
        source: SettingSource,
        data: dict[str, Any],
        *,
        workspace_root: str | Path | None = None,
    ) -> dict[str, Any]:
        if source == "managed":
            raise ValueError("Managed settings are read-only")

        validation = self.validate_settings_content(data)
        if not validation.is_valid:
            raise ValueError("; ".join(validation.errors))

        path = self.get_settings_file_path(source, workspace_root=workspace_root)
        self._atomic_write_json(path, validation.normalized)
        return validation.normalized

    def _read_settings_file(self, path: Path, *, source: SettingSource) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to load %s settings from %s: %s", source, path, exc)
            return {}
        if not isinstance(raw, dict):
            logger.warning("Ignoring non-object %s settings from %s", source, path)
            return {}
        return self.normalize_settings_dict(raw)

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = tempfile.NamedTemporaryFile(
            mode="w",
            dir=path.parent,
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        )
        tmp = Path(fd.name)
        try:
            fd.write(json.dumps(data, indent=2, ensure_ascii=False))
            fd.flush()
            fd.close()
            tmp.replace(path)
        except Exception:
            fd.close()
            tmp.unlink(missing_ok=True)
            raise


def default_config_home() -> Path:
    return Path(os.getenv("AETHOS_CONFIG_HOME", str(get_settings().aethos_config_dir))).expanduser().resolve()


def default_managed_settings_dir() -> Path:
    return Path(
        os.getenv("AETHOS_MANAGED_SETTINGS_DIR", str(get_settings().aethos_managed_settings_dir))
    ).expanduser().resolve()
