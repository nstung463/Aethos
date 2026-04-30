from __future__ import annotations

from pathlib import Path

from src.ai.tools.filesystem._sandbox import resolve


class WorkspacePathResolver:
    def __init__(self, root_dir: str | Path) -> None:
        self.root = Path(root_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def sanitize_input_path(self, path: str) -> str:
        stripped = path.strip()
        return stripped or "."

    def resolve_workspace_path(self, path: str, *, base: str | None = None) -> Path:
        path = self.sanitize_input_path(path)
        if not base or path.startswith("/"):
            return resolve(self.root, path)

        base_target = resolve(self.root, base)
        target = (base_target / path).resolve()
        try:
            target.relative_to(self.root)
        except ValueError as exc:
            raise PermissionError(
                f"Path '{path}' resolves outside the workspace root '{self.root}'. Access denied."
            ) from exc
        return target

    def to_display_path(self, target: Path) -> str:
        relative = target.relative_to(self.root)
        return "." if relative == Path(".") else relative.as_posix()

    def normalize_path(self, path: str, *, base: str | None = None) -> str:
        return self.to_display_path(self.resolve_workspace_path(path, base=base))

    def resolve_permission_target(self, path: str, *, base: str | None = None) -> tuple[str, Path]:
        target = self.resolve_workspace_path(path, base=base)
        return self.to_display_path(target), target

    def relative_to_base(self, display_path: str, base: str) -> str:
        if base == ".":
            return display_path
        base_display = self.normalize_path(base)
        if display_path == base_display:
            return "."
        prefix = f"{base_display}/"
        return display_path[len(prefix):] if display_path.startswith(prefix) else display_path
