"""Tests for user interaction tools."""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest


# ── ask_user: CLI mode ────────────────────────────────────────────────────────

def test_ask_user_single_select() -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    tool = build_ask_user_tool(input_fn=lambda q: "0")
    result = json.loads(tool.invoke({
        "questions": [{
            "question": "Pick one?",
            "header": "Choice",
            "options": [
                {"label": "A", "description": "Option A"},
                {"label": "B", "description": "Option B"},
            ]
        }]
    }))
    assert result["answers"]["Pick one?"] == "A"


def test_ask_user_multi_select() -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    tool = build_ask_user_tool(input_fn=lambda q: "0,1")
    result = json.loads(tool.invoke({
        "questions": [{
            "question": "Pick all?",
            "header": "Multi",
            "options": [
                {"label": "X", "description": "Option X"},
                {"label": "Y", "description": "Option Y"},
                {"label": "Z", "description": "Option Z"},
            ],
            "multi_select": True,
        }]
    }))
    assert result["answers"]["Pick all?"] == "X,Y"


def test_ask_user_annotations_populated() -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    tool = build_ask_user_tool(input_fn=lambda q: "1")
    result = json.loads(tool.invoke({
        "questions": [{
            "question": "Which layout?",
            "header": "Layout",
            "options": [
                {"label": "Side-by-side", "description": "Two columns", "preview": "┌─┬─┐\n│A│B│\n└─┴─┘"},
                {"label": "Stacked", "description": "One column", "preview": "┌───┐\n│ A │\n├───┤\n│ B │\n└───┘"},
            ],
        }]
    }))
    assert result["answers"]["Which layout?"] == "Stacked"
    assert result["annotations"]["Which layout?"]["preview"] == "┌───┐\n│ A │\n├───┤\n│ B │\n└───┘"
    assert "notes" in result["annotations"]["Which layout?"]


def test_ask_user_preview_shown_in_prompt() -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    prompts_seen: list[str] = []
    tool = build_ask_user_tool(input_fn=lambda q: (prompts_seen.append(q), "0")[1])
    tool.invoke({
        "questions": [{
            "question": "Compare?",
            "header": "Cmp",
            "options": [
                {"label": "A", "description": "desc A", "preview": "PREVIEW_A"},
                {"label": "B", "description": "desc B"},
            ],
        }]
    })
    assert any("PREVIEW_A" in p for p in prompts_seen)


def test_ask_user_multi_select_annotations_have_preview() -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    tool = build_ask_user_tool(input_fn=lambda q: "0,1")
    result = json.loads(tool.invoke({
        "questions": [{
            "question": "Select all?",
            "header": "All",
            "options": [
                {"label": "X", "description": "x", "preview": "PX"},
                {"label": "Y", "description": "y", "preview": "PY"},
            ],
            "multi_select": True,
        }]
    }))
    ann = result["annotations"]["Select all?"]
    assert "PX" in ann["preview"]
    assert "PY" in ann["preview"]


def test_ask_user_option_count_validation() -> None:
    from src.ai.tools.interaction.ask_user import Question, QuestionOption
    with pytest.raises(Exception):
        Question(
            question="Q?",
            header="H",
            options=[QuestionOption(label="only one", description="d")],
        )


def test_ask_user_question_count_validation() -> None:
    from src.ai.tools.interaction.ask_user import AskUserInput, Question, QuestionOption
    with pytest.raises(Exception):
        AskUserInput(questions=[])


def test_ask_user_unique_option_labels_validation() -> None:
    from src.ai.tools.interaction.ask_user import Question, QuestionOption
    with pytest.raises(Exception, match="unique"):
        Question(
            question="Q?",
            header="H",
            options=[
                QuestionOption(label="Same", description="a"),
                QuestionOption(label="Same", description="b"),
            ],
        )


def test_ask_user_unique_question_texts_validation() -> None:
    from src.ai.tools.interaction.ask_user import AskUserInput, Question, QuestionOption
    opts = [
        QuestionOption(label="A", description="a"),
        QuestionOption(label="B", description="b"),
    ]
    with pytest.raises(Exception, match="unique"):
        AskUserInput(questions=[
            Question(question="Same?", header="H1", options=opts),
            Question(question="Same?", header="H2", options=opts),
        ])


def test_ask_user_metadata_passed_through() -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    tool = build_ask_user_tool(input_fn=lambda q: "0")
    result = json.loads(tool.invoke({
        "questions": [{
            "question": "Which?",
            "header": "H",
            "options": [
                {"label": "A", "description": "a"},
                {"label": "B", "description": "b"},
            ],
        }],
        "metadata": {"source": "architecture-decision"},
    }))
    assert result["metadata"] == {"source": "architecture-decision"}


def test_ask_user_output_is_ask_user_output_model() -> None:
    from src.ai.tools.interaction.ask_user import AskUserOutput, AnnotationData
    out = AskUserOutput(
        questions=[],
        answers={"Q?": "A"},
        annotations={"Q?": AnnotationData(preview="p", notes="n")},
    )
    assert out.answers["Q?"] == "A"
    assert out.annotations["Q?"].preview == "p"
    assert out.annotations["Q?"].notes == "n"


def test_ask_user_notes_prompted_when_preview_exists(capsys) -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    inputs = iter(["0", "great choice"])
    tool = build_ask_user_tool(input_fn=lambda q: next(inputs))
    result = json.loads(tool.invoke({
        "questions": [{
            "question": "Style?",
            "header": "Style",
            "options": [
                {"label": "Dark", "description": "dark mode", "preview": "████"},
                {"label": "Light", "description": "light mode"},
            ],
        }]
    }))
    assert result["answers"]["Style?"] == "Dark"
    assert result["annotations"]["Style?"]["notes"] == "great choice"
    assert result["annotations"]["Style?"]["preview"] == "████"


# ── ask_user: interrupt mode ──────────────────────────────────────────────────

def test_ask_user_interrupt_mode_calls_interrupt() -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    resume_payload = {"answers": {"Layout?": "Dark"}}
    with patch("src.ai.tools.interaction.ask_user.interrupt", return_value=resume_payload) as mock_interrupt:
        tool = build_ask_user_tool(use_interrupt=True)
        result = json.loads(tool.invoke({
            "questions": [{
                "question": "Layout?",
                "header": "Theme",
                "options": [
                    {"label": "Light", "description": "Light mode"},
                    {"label": "Dark", "description": "Dark mode"},
                ],
            }]
        }))

    mock_interrupt.assert_called_once()
    payload = mock_interrupt.call_args[0][0]
    assert payload["behavior"] == "ask_user"
    assert len(payload["questions"]) == 1
    assert result["answers"]["Layout?"] == "Dark"


def test_ask_user_interrupt_mode_annotations_from_resume() -> None:
    from src.ai.tools.interaction.ask_user import build_ask_user_tool

    resume_payload = {"answers": {"Q?": "B"}}
    with patch("src.ai.tools.interaction.ask_user.interrupt", return_value=resume_payload):
        tool = build_ask_user_tool(use_interrupt=True)
        result = json.loads(tool.invoke({
            "questions": [{
                "question": "Q?",
                "header": "H",
                "options": [
                    {"label": "A", "description": "a", "preview": "PA"},
                    {"label": "B", "description": "b", "preview": "PB"},
                ],
            }]
        }))

    assert result["annotations"]["Q?"]["preview"] == "PB"


# ── structured_output ─────────────────────────────────────────────────────────

def test_structured_output_returns_json_string() -> None:
    from src.ai.tools.interaction.structured_output import structured_output_tool
    data = {"name": "test", "value": 42}
    result = structured_output_tool.invoke(data)
    assert json.loads(result) == data


def test_structured_output_nested() -> None:
    from src.ai.tools.interaction.structured_output import structured_output_tool
    data = {"items": [1, 2, 3], "meta": {"count": 3}}
    result = structured_output_tool.invoke(data)
    assert json.loads(result)["items"] == [1, 2, 3]


# ── send_user_message: CLI mode ───────────────────────────────────────────────

def test_send_user_message_returns_ack() -> None:
    from src.ai.tools.interaction.send_user_message import build_send_user_message_tool

    received = []
    tool = build_send_user_message_tool(output_fn=received.append)
    result = tool.invoke({"message": "Hello from agent"})
    assert received == ["Hello from agent"]
    assert result == "Message sent."


# ── send_user_message: interrupt mode ────────────────────────────────────────

def test_send_user_message_interrupt_mode_calls_interrupt() -> None:
    from src.ai.tools.interaction.send_user_message import build_send_user_message_tool

    with patch("src.ai.tools.interaction.send_user_message.interrupt", return_value=None) as mock_interrupt:
        tool = build_send_user_message_tool(use_interrupt=True)
        result = tool.invoke({"message": "Progress update"})

    mock_interrupt.assert_called_once_with({"behavior": "notify", "message": "Progress update"})
    assert result == "Message sent."


def test_send_user_message_interrupt_mode_does_not_call_output_fn() -> None:
    from src.ai.tools.interaction.send_user_message import build_send_user_message_tool

    received = []
    with patch("src.ai.tools.interaction.send_user_message.interrupt", return_value=None):
        tool = build_send_user_message_tool(output_fn=received.append, use_interrupt=True)
        tool.invoke({"message": "Should not print"})

    assert received == []
