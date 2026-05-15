from __future__ import annotations

from src.app.services.context_status import build_context_status, context_window_for_model


def test_context_status_reports_loaded_instruction_files(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("Use project conventions.", encoding="utf-8")
    (tmp_path / "AGENTS.md").write_text("Remember local preferences.", encoding="utf-8")

    status = build_context_status(
        root_dir=str(tmp_path),
        model="gpt-5",
        messages=[{"role": "user", "content": "hello"}],
        context_window=None,
        mcp_servers=[],
    )

    names = {item["name"] for item in status["activated_rules"]}
    category_keys = {item["key"] for item in status["categories"]}
    assert names == {"CLAUDE.md", "AGENTS.md"}
    assert {"system_prompt", "environment", "memory", "tools", "free"}.issubset(category_keys)
    assert status["context_window"] == 256_000
    assert status["used_tokens"] > 0
    assert len(status["grid_rows"]) == 10
    assert all(len(row) == 10 for row in status["grid_rows"])
    assert status["is_estimated"] is True
    memory_rule = next(item for item in status["activated_rules"] if item["name"] == "AGENTS.md")
    memory_category = next(item for item in status["categories"] if item["key"] == "memory")
    assert memory_rule["tokens"] <= memory_category["tokens"]


def test_context_status_reports_auto_memory_file(tmp_path, monkeypatch):
    config_home = tmp_path / "home-aethos"
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(config_home))
    from src.app.core.settings import get_settings

    get_settings.cache_clear()
    memory_path = (
        config_home
        / "projects"
        / "tmp-pytest-project"
        / "memory"
        / "MEMORY.md"
    )
    memory_path.parent.mkdir(parents=True)
    memory_path.write_text("Remember storage layout decisions.", encoding="utf-8")
    monkeypatch.setattr(
        "src.app.services.context_status.StoragePathsService.memory_file",
        lambda self, root=None: memory_path,
    )

    status = build_context_status(
        root_dir=str(tmp_path),
        model="gpt-5",
        messages=[],
        context_window=None,
        mcp_servers=[],
    )

    memory_rules = [item for item in status["activated_rules"] if item["source"] == "memory"]
    assert any(item["path"] == str(memory_path) for item in memory_rules)


def test_tools_estimated_suggestion_requires_context_ratio(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("Use project conventions.", encoding="utf-8")
    small_window_status = build_context_status(
        root_dir=str(tmp_path),
        model="gpt-5",
        messages=[],
        context_window=50_000,
        mcp_servers=[],
    )
    large_window_status = build_context_status(
        root_dir=str(tmp_path),
        model="gemini-2.5-pro",
        messages=[],
        context_window=1_000_000,
        mcp_servers=[],
    )
    small_titles = {item["title_key"] for item in small_window_status["suggestions"]}
    large_titles = {item["title_key"] for item in large_window_status["suggestions"]}
    assert "context.suggestions.toolsEstimated.title" in small_titles
    assert "context.suggestions.toolsEstimated.title" not in large_titles


def test_context_window_has_provider_defaults():
    assert context_window_for_model("claude-sonnet-4") == 200_000
    assert context_window_for_model("gpt-4o") == 128_000
    assert context_window_for_model("gemini-2.5-pro") == 1_000_000


def test_context_window_override_wins():
    assert context_window_for_model("custom-model", override=64_000) == 64_000

