from langchain_core.messages import AIMessage

from src.app.features.chat.adapters import to_lc_messages
from src.app.features.chat.schemas import Message


def test_to_lc_messages_preserves_assistant_reasoning_blocks() -> None:
    messages = [
        Message(role="assistant", content="Final answer", reasoning_content="Hidden chain of thought"),
    ]

    result = to_lc_messages(messages)

    assert len(result) == 1
    assert isinstance(result[0], AIMessage)
    assert result[0].content == "Final answer"
    assert result[0].additional_kwargs["reasoning_content"] == "Hidden chain of thought"


def test_to_lc_messages_keeps_reasoning_only_assistant_messages() -> None:
    messages = [
        Message(role="assistant", content="", reasoning_content="Need to preserve this for provider replay"),
    ]

    result = to_lc_messages(messages)

    assert len(result) == 1
    assert isinstance(result[0], AIMessage)
    assert result[0].content == ""
    assert result[0].additional_kwargs["reasoning_content"] == "Need to preserve this for provider replay"
