"""ask_user tool — ask the user structured questions with selectable options.

Mirrors AskUserQuestionTool from claude-code-source.
Two execution modes:
  - use_interrupt=True  (LangGraph/API): suspends via langgraph.types.interrupt(),
    resumes when the host provides Command(resume={"answers": {...}, "notes": {...}}).
  - use_interrupt=False (CLI/test): reads from input_fn (default: stdin).
"""
from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

from langchain_core.tools import StructuredTool
from langgraph.types import interrupt
from pydantic import BaseModel, Field, model_validator


class QuestionOption(BaseModel):
    label: str = Field(description="Short display label (1–5 words).")
    description: str = Field(description="Explanation of the option.")
    preview: Optional[str] = Field(
        default=None,
        description=(
            "Optional preview content (monospace markdown, ASCII art, code snippet). "
            "Use for visual comparisons: UI mockups, layout diagrams, code variants."
        ),
    )


class Question(BaseModel):
    question: str = Field(description="The question to ask (end with '?').")
    header: str = Field(description="Short chip label (max 20 chars).")
    options: List[QuestionOption] = Field(description="2–4 options for the user to choose from.")
    multi_select: bool = Field(default=False, description="Allow multiple selections.")

    @model_validator(mode="after")
    def _validate(self) -> "Question":
        if not (2 <= len(self.options) <= 4):
            raise ValueError("Each question must have 2–4 options.")
        labels = [o.label for o in self.options]
        if len(labels) != len(set(labels)):
            raise ValueError(f"Option labels must be unique in question '{self.question}'.")
        return self


class AskUserInput(BaseModel):
    questions: List[Question] = Field(description="1–4 questions to ask the user.")
    metadata: Optional[Dict[str, str]] = Field(
        default=None,
        description="Optional metadata for tracking context (e.g. source: 'architecture-decision').",
    )

    @model_validator(mode="after")
    def _validate(self) -> "AskUserInput":
        if not (1 <= len(self.questions) <= 4):
            raise ValueError("Provide 1–4 questions.")
        texts = [q.question for q in self.questions]
        if len(texts) != len(set(texts)):
            raise ValueError("Question texts must be unique.")
        return self


class AnnotationData(BaseModel):
    preview: str = Field(default="", description="The preview content of the selected option.")
    notes: str = Field(default="", description="Optional user notes about the selection.")


class AskUserOutput(BaseModel):
    questions: List[Question]
    answers: Dict[str, str] = Field(description="Maps question text → selected label(s).")
    annotations: Dict[str, AnnotationData] = Field(
        description="Maps question text → selected preview + notes."
    )
    metadata: Optional[Dict[str, str]] = None


def _default_input(prompt: str) -> str:
    return input(prompt)


def _ask_cli(
    questions: List[Question],
    input_fn: Callable[[str], str],
    metadata: Optional[Dict[str, str]] = None,
) -> str:
    """Collect answers via stdin/input_fn. Returns AskUserOutput as JSON."""
    answers: Dict[str, str] = {}
    annotations: Dict[str, AnnotationData] = {}

    for q in questions:
        opts = q.options
        lines = [f"\n[{q.header}] {q.question}"]
        for i, opt in enumerate(opts):
            preview_hint = f"\n     Preview:\n{opt.preview}" if opt.preview else ""
            lines.append(f"  {i}) {opt.label} — {opt.description}{preview_hint}")
        lines.append("Enter comma-separated numbers:" if q.multi_select else "Enter number:")
        prompt = "\n".join(lines) + "\n> "
        raw = input_fn(prompt).strip()

        if q.multi_select:
            indices = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
            chosen_indices = [i for i in indices if 0 <= i < len(opts)]
            selected_labels = [opts[i].label for i in chosen_indices]
            answers[q.question] = ",".join(selected_labels)
            previews = [opts[i].preview for i in chosen_indices if opts[i].preview]
            joined_preview = "\n---\n".join(previews)
            notes = ""
            if previews:
                notes = input_fn("Add notes? (press Enter to skip): ").strip()
            annotations[q.question] = AnnotationData(preview=joined_preview, notes=notes)
        else:
            idx = int(raw) if raw.isdigit() else 0
            idx = max(0, min(idx, len(opts) - 1))
            answers[q.question] = opts[idx].label
            selected_preview = opts[idx].preview or ""
            notes = ""
            if selected_preview:
                notes = input_fn("Add notes? (press Enter to skip): ").strip()
            annotations[q.question] = AnnotationData(preview=selected_preview, notes=notes)

    return AskUserOutput(
        questions=questions,
        answers=answers,
        annotations=annotations,
        metadata=metadata,
    ).model_dump_json()


def _ask_interrupt(
    questions: List[Question],
    metadata: Optional[Dict[str, str]] = None,
) -> str:
    """Suspend via LangGraph interrupt(); resume payload: {"answers": {...}, "notes": {...}}."""
    resume = interrupt({
        "behavior": "ask_user",
        "questions": [q.model_dump() for q in questions],
        "metadata": metadata,
    })

    raw_answers: Dict[str, str] = resume.get("answers", {}) if isinstance(resume, dict) else {}
    raw_notes: Dict[str, str] = resume.get("notes", {}) if isinstance(resume, dict) else {}

    annotations: Dict[str, AnnotationData] = {}
    for q in questions:
        selected_label = raw_answers.get(q.question, "")
        selected_opt = next((o for o in q.options if o.label == selected_label), None)
        annotations[q.question] = AnnotationData(
            preview=selected_opt.preview if selected_opt and selected_opt.preview else "",
            notes=raw_notes.get(q.question, ""),
        )

    return AskUserOutput(
        questions=questions,
        answers=raw_answers,
        annotations=annotations,
        metadata=metadata,
    ).model_dump_json()


def build_ask_user_tool(
    input_fn: Optional[Callable[[str], str]] = None,
    use_interrupt: bool = False,
) -> StructuredTool:
    """Build ask_user tool.

    Args:
        input_fn: Custom input function for CLI/test mode (default: stdin).
        use_interrupt: When True, suspend via LangGraph interrupt() instead of stdin.
    """
    fn = input_fn or _default_input

    def _dispatch(questions: List[Question], metadata: Optional[Dict[str, str]] = None) -> str:
        if use_interrupt:
            return _ask_interrupt(questions, metadata)
        return _ask_cli(questions, fn, metadata)

    return StructuredTool.from_function(
        name="ask_user",
        func=_dispatch,
        description=(
            "Ask the user structured questions with selectable options. "
            "Each question must have 2–4 options and may include a 'preview' (markdown/ASCII art) "
            "for visual comparison of layouts, code variants, or design options. "
            "Returns the user's selections as JSON with 'answers' and 'annotations'."
        ),
        args_schema=AskUserInput,
    )
