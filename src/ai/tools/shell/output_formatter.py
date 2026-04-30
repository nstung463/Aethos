"""Format and optionally collapse large bash command output.

Mirrors the output-collapsing heuristic in claude-code-source BashTool:
commands that produce search/list/read output beyond the collapse_threshold
get summarised so the LLM doesn't have to process hundreds of raw lines.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.ai.tools.shell.command_classifier import BashClassification


@dataclass
class FormattedOutput:
    raw: str
    summary: str | None
    collapsed: bool
    line_count: int


def format_bash_output(
    output: str,
    classification: BashClassification,
    *,
    max_lines: int | None = None,
) -> FormattedOutput:
    """Return a FormattedOutput wrapping *output*.

    When *classification.should_collapse* is True and the output exceeds
    *classification.collapse_threshold* (or the *max_lines* override),
    a one-line summary is generated and *collapsed* is set to True so
    callers can decide whether to return the summary or the full text to
    the LLM.
    """
    lines = output.splitlines()
    line_count = len(lines)
    threshold = max_lines if max_lines is not None else classification.collapse_threshold

    if not classification.should_collapse or line_count <= threshold:
        return FormattedOutput(
            raw=output,
            summary=None,
            collapsed=False,
            line_count=line_count,
        )

    summary = _build_summary(output, lines, classification)
    return FormattedOutput(
        raw=output,
        summary=summary,
        collapsed=True,
        line_count=line_count,
    )


def _build_summary(output: str, lines: list[str], cls: BashClassification) -> str:
    """Produce a compact summary of *output* based on command type."""
    total = len(lines)
    non_empty = [l for l in lines if l.strip()]
    shown = lines[:5]
    tail = lines[-3:] if total > 8 else []

    if cls.is_list:
        return (
            f"[{total} lines] Listing output ({len(non_empty)} entries). "
            f"First entries: {', '.join(l.strip() for l in shown[:5] if l.strip())}"
        )

    if cls.is_search:
        matches = [l for l in lines if l.strip()]
        preview = matches[:5]
        return (
            f"[{total} lines, {len(matches)} matches] "
            + "; ".join(preview)
            + ("..." if len(matches) > 5 else "")
        )

    if cls.is_read:
        head_lines = "\n".join(shown)
        tail_note = f"\n... ({total - 8} more lines) ..." if tail else ""
        tail_lines = "\n".join(tail) if tail else ""
        return f"[{total} lines]\n{head_lines}{tail_note}\n{tail_lines}".strip()

    # generic fallback
    return f"[{total} lines] " + "\n".join(lines[:10]) + ("..." if total > 10 else "")
