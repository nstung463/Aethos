"""Aethos CLI entrypoint and LangGraph graph factory."""

from __future__ import annotations

from src.ai.agents.aethos import create_aethos_agent
from src.config import get_model, get_workspace


def create_graph():
    """Return the default compiled Aethos agent graph."""
    return create_aethos_agent(root_dir=get_workspace(), model=get_model())


def main() -> None:
    """Build the default graph so local entrypoint checks can import it."""
    create_graph()


if __name__ == "__main__":
    main()
