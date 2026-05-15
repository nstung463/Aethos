"""Skill discovery and rendering for Aethos agents."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_SOURCE_PRIORITY = {
    "aethos_project": 0,
    "aethos_user": 1,
}


class SkillNotFoundError(FileNotFoundError):
    """Raised when a skill cannot be found by name."""


@dataclass(frozen=True)
class SkillDefinition:
    """A discovered skill and its Claude-compatible metadata."""

    name: str
    description: str
    path: Path | None
    root_dir: Path | None
    source: str
    loaded_from: Literal["local", "mcp"] = "local"
    server: str | None = None
    remote_name: str | None = None
    when_to_use: str | None = None
    aliases: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    argument_hint: str | None = None
    arguments: tuple[str, ...] = ()
    model: str | None = None
    effort: str | None = None
    context: str | None = None
    agent: str | None = None
    paths: tuple[str, ...] = ()
    raw_frontmatter: dict[str, Any] = field(default_factory=dict)


def _as_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(part.strip() for part in value.split(",") if part.strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(str(part).strip() for part in value if str(part).strip())
    return (str(value).strip(),) if str(value).strip() else ()


def _normalize_skill_identifier(value: str) -> str:
    return value.strip().lstrip("/").lower()


def _is_mcp_skill_prompt(item: dict[str, Any]) -> bool:
    if item.get("isSkill") is True:
        return True
    if item.get("kind") == "skill" or item.get("type") == "skill":
        return True
    metadata = item.get("_meta") or item.get("metadata") or {}
    if isinstance(metadata, dict):
        if metadata.get("skill") is True:
            return True
        if metadata.get("claude_code_skill") is True:
            return True
        if metadata.get("aethos.skill") is True:
            return True
    tags = item.get("tags") or item.get("labels") or ()
    if isinstance(tags, (list, tuple, set)):
        return "skill" in {str(tag).lower() for tag in tags}
    return False


def _substitute_arguments(content: str, args: str, argument_names: tuple[str, ...]) -> str:
    final = content.replace("$ARGUMENTS", args)
    for index, name in enumerate(argument_names):
        parts = args.split()
        value = parts[index] if index < len(parts) else ""
        final = final.replace(f"${{{name}}}", value)
    return final


def strip_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Return parsed frontmatter and the markdown body without the YAML header."""

    match = _FRONTMATTER_RE.match(content)
    if not match:
        return {}, content.strip()

    try:
        data = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        logger.warning("YAML error in skill frontmatter: %s", exc)
        return {}, content[match.end() :].strip()

    if not isinstance(data, dict):
        return {}, content[match.end() :].strip()

    return data, content[match.end() :].strip()


class SkillRegistry:
    """Discover, resolve, and render local SKILL.md files."""

    def __init__(
        self,
        root_dir: str | Path,
        mcp_runtime: Any | None = None,
        *,
        user_aethos_skill_root: str | Path | None = None,
        include_project_skills: bool = True,
    ) -> None:
        self.root_dir = Path(root_dir).resolve()
        self.mcp_runtime = mcp_runtime
        self.user_aethos_skill_root = (
            Path(user_aethos_skill_root).expanduser().resolve()
            if user_aethos_skill_root is not None
            else self.default_user_aethos_skill_root()
        )
        self.include_project_skills = include_project_skills
        self._skills: dict[str, SkillDefinition] | None = None

    @staticmethod
    def default_user_aethos_skill_root() -> Path:
        return (Path.home() / ".aethos" / "skills").resolve()

    @property
    def skill_roots(self) -> tuple[tuple[str, Path], ...]:
        roots: list[tuple[str, Path]] = []
        if self.include_project_skills:
            roots.append(("aethos_project", self.root_dir / ".aethos" / "skills"))
        roots.append(("aethos_user", self.user_aethos_skill_root))
        return tuple(roots)

    def discover(self, include_mcp: bool = True) -> list[SkillDefinition]:
        """Discover skills, caching the result for this registry instance."""

        if include_mcp:
            if self._skills is None:
                self._skills = self._discover_uncached(include_mcp=True)
            return list(self._skills.values())
        return list(self._discover_uncached(include_mcp=False).values())

    def get(self, name: str) -> SkillDefinition:
        """Return a skill by exact frontmatter name."""

        normalized = _normalize_skill_identifier(name)
        skills = self._skills if self._skills is not None else {skill.name: skill for skill in self.discover()}
        for skill in skills.values():
            if _normalize_skill_identifier(skill.name) == normalized:
                return skill
            if normalized in {_normalize_skill_identifier(alias) for alias in skill.aliases}:
                return skill
        raise SkillNotFoundError(f"Skill '{normalized}' not found")

    def render_listing(self, max_chars: int | None = None) -> str:
        """Render a compact discovery listing for the system prompt."""

        lines = []
        for skill in self.discover():
            description = skill.description
            if skill.when_to_use:
                description = f"{description} - {skill.when_to_use}"
            if skill.aliases:
                alias_text = ", ".join(f"/{alias}" for alias in skill.aliases)
                description = f"{description} (aliases: {alias_text})"
            lines.append(f"- {skill.name}: {description}")

        listing = "\n".join(lines)
        if max_chars is not None and len(listing) > max_chars:
            return listing[: max(0, max_chars - 1)].rstrip() + "..."
        return listing

    def render_skill_prompt(self, name: str, args: str = "") -> str:
        """Render full skill instructions."""

        skill = self.get(name)
        if skill.loaded_from == "mcp":
            return self._render_mcp_skill_prompt(skill, args)
        if skill.path is None:
            raise FileNotFoundError(f"Skill '{skill.name}' has no local SKILL.md path")
        content = skill.path.read_text(encoding="utf-8")
        _frontmatter, body = strip_frontmatter(content)
        body = _substitute_arguments(body, args, skill.arguments)
        if skill.root_dir is not None:
            skill_dir = str(skill.root_dir).replace("\\", "/")
            body = body.replace("${CLAUDE_SKILL_DIR}", skill_dir)
        return self._format_skill_prompt(skill, body, args)

    def _discover_uncached(self, *, include_mcp: bool) -> dict[str, SkillDefinition]:
        skills: dict[str, SkillDefinition] = {}

        for source, root in self.skill_roots:
            if not root.exists():
                continue
            for skill_md in sorted(root.glob("*/SKILL.md")):
                definition = self._parse_skill(skill_md, source)
                if definition is None:
                    continue

                existing = skills.get(definition.name)
                if existing is not None:
                    if _SOURCE_PRIORITY[definition.source] >= _SOURCE_PRIORITY[existing.source]:
                        logger.warning(
                            "Ignoring duplicate skill '%s' from %s; already loaded from %s",
                            definition.name,
                            definition.path,
                            existing.path,
                        )
                        continue
                    logger.warning(
                        "Replacing duplicate skill '%s' from %s with higher-priority %s",
                        definition.name,
                        existing.path,
                        definition.path,
                    )

                skills[definition.name] = definition

        if include_mcp:
            for definition in self._discover_mcp_skills():
                if definition.name in skills:
                    logger.warning("Ignoring duplicate MCP skill '%s'", definition.name)
                    continue
                skills[definition.name] = definition

        return skills

    def _discover_mcp_skills(self) -> list[SkillDefinition]:
        if self.mcp_runtime is None:
            return []
        try:
            raw = self.mcp_runtime.list_prompts()
        except Exception as exc:
            logger.warning("Could not list MCP prompts as skills: %s", exc)
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("Could not parse MCP prompt list: %s", exc)
            return []

        prompts = payload.get("prompts", [])
        if not isinstance(prompts, list):
            return []

        definitions: list[SkillDefinition] = []
        for item in prompts:
            if not isinstance(item, dict):
                continue
            if not _is_mcp_skill_prompt(item):
                continue
            server = _as_string(item.get("server"))
            remote_name = _as_string(item.get("name"))
            if not server or not remote_name:
                continue
            name = f"mcp:{server}:{remote_name}"
            description = _as_string(item.get("description")) or f"MCP prompt {remote_name} from {server}"
            definitions.append(
                SkillDefinition(
                    name=name,
                    description=description,
                    path=None,
                    root_dir=None,
                    source="mcp",
                    loaded_from="mcp",
                    server=server,
                    remote_name=remote_name,
                    raw_frontmatter=dict(item),
                )
            )
        return definitions

    def _parse_skill(self, skill_md: Path, source: str) -> SkillDefinition | None:
        try:
            content = skill_md.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read skill %s: %s", skill_md, exc)
            return None

        frontmatter, _body = strip_frontmatter(content)
        if not frontmatter:
            logger.warning("No valid YAML frontmatter in %s", skill_md)
            return None

        name = _as_string(frontmatter.get("name"))
        description = _as_string(frontmatter.get("description"))
        if not name or not description:
            logger.warning("Skill %s is missing required name or description", skill_md)
            return None

        return SkillDefinition(
            name=name,
            description=description,
            path=skill_md,
            root_dir=skill_md.parent,
            source=source,
            loaded_from="local",
            when_to_use=_as_string(frontmatter.get("when_to_use")),
            aliases=tuple(
                alias
                for alias in (
                    _normalize_skill_identifier(value)
                    for value in (
                        _as_string_tuple(frontmatter.get("aliases"))
                        or _as_string_tuple(frontmatter.get("alias"))
                    )
                )
                if alias and alias != _normalize_skill_identifier(name)
            ),
            allowed_tools=_as_string_tuple(frontmatter.get("allowed-tools")),
            argument_hint=_as_string(frontmatter.get("argument-hint")),
            arguments=_as_string_tuple(frontmatter.get("arguments")),
            model=_as_string(frontmatter.get("model")),
            effort=_as_string(frontmatter.get("effort")),
            context=_as_string(frontmatter.get("context")),
            agent=_as_string(frontmatter.get("agent")),
            paths=_as_string_tuple(frontmatter.get("paths")),
            raw_frontmatter=dict(frontmatter),
        )

    def _render_mcp_skill_prompt(self, skill: SkillDefinition, args: str) -> str:
        if self.mcp_runtime is None or not skill.server or not skill.remote_name:
            raise FileNotFoundError(f"MCP skill '{skill.name}' is not available")
        content = self.mcp_runtime.get_prompt(skill.server, skill.remote_name, {"arguments": args} if args else None)
        return self._format_skill_prompt(skill, content, args)

    def _format_skill_prompt(self, skill: SkillDefinition, body: str, args: str) -> str:
        if skill.loaded_from == "mcp":
            prompt = f"MCP skill source: {skill.server}:{skill.remote_name}\n\n{body}"
        else:
            prompt = f"Base directory for this skill: {skill.root_dir}\n\n{body}"
        notes = []
        if args:
            notes.append(f"Skill arguments: {args}")
        if skill.allowed_tools:
            notes.append(
                "This skill requests additional tool permissions: "
                + ", ".join(skill.allowed_tools)
                + ". These are guidance only in Aethos skills v1 and do not bypass existing permissions."
            )
        if skill.context == "fork":
            notes.append(
                "Forked skill execution is not supported in Aethos skills v1. "
                "Follow these instructions inline unless the task requires isolated execution."
            )
        if notes:
            prompt = prompt + "\n\n" + "\n".join(notes)

        return prompt
