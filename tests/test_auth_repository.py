from __future__ import annotations

from pathlib import Path

from src.app.core.settings import get_settings
from src.app.dependencies import get_auth_repository


def test_auth_repository_defaults_to_config_home_users(tmp_path: Path, monkeypatch) -> None:
    config_home = tmp_path / "home-aethos"
    monkeypatch.setenv("AETHOS_CONFIG_HOME", str(config_home))
    monkeypatch.delenv("AETHOS_USERS_DIR", raising=False)
    monkeypatch.delenv("AETHOS_SECURITY_STATE_DIR", raising=False)
    get_settings.cache_clear()
    get_auth_repository.cache_clear()

    repo = get_auth_repository()
    user, session = repo.create_guest_session(display_name="Storage Test")

    assert (config_home / "users" / user.id / "profile.json").exists()
    assert any((config_home / "users" / user.id / "sessions").glob("*.json"))
    assert repo.get_session(session.token) is not None
