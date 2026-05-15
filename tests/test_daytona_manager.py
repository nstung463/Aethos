from __future__ import annotations

from src.app.services.daytona_manager import DaytonaSessionManager


class _Backend:
    def __init__(self, identifier: str) -> None:
        self.id = identifier


def test_manager_reuses_backend_for_same_session(monkeypatch) -> None:
    created: list[str] = []

    def fake_get_or_create_daytona_backend(*, conversation_id: str, auto_delete_interval: int):
        created.append(f"{conversation_id}:{auto_delete_interval}")
        return type(
            "Lease",
            (),
            {
                "backend": _Backend(conversation_id),
                "sandbox_name": conversation_id,
            },
        )()

    monkeypatch.setattr(
        "src.app.services.daytona_manager.get_or_create_daytona_backend",
        fake_get_or_create_daytona_backend,
    )
    monkeypatch.setattr("src.app.services.daytona_manager.delete_daytona_sandbox", lambda *, sandbox_name: None)

    manager = DaytonaSessionManager(idle_ttl_seconds=600)

    first = manager.get_backend("session-a")
    second = manager.get_backend("session-a")

    assert first is second
    assert created == ["session-a:10"]


def test_manager_expires_old_session(monkeypatch) -> None:
    deleted: list[str] = []
    current_time = {"value": 1000.0}

    def fake_time() -> float:
        return current_time["value"]

    def fake_get_or_create_daytona_backend(*, conversation_id: str, auto_delete_interval: int):
        return type(
            "Lease",
            (),
            {
                "backend": _Backend(conversation_id),
                "sandbox_name": conversation_id,
            },
        )()

    monkeypatch.setattr("src.app.services.daytona_manager.time.time", fake_time)
    monkeypatch.setattr(
        "src.app.services.daytona_manager.get_or_create_daytona_backend",
        fake_get_or_create_daytona_backend,
    )
    monkeypatch.setattr(
        "src.app.services.daytona_manager.delete_daytona_sandbox",
        lambda *, sandbox_name: deleted.append(sandbox_name),
    )

    manager = DaytonaSessionManager(idle_ttl_seconds=60)
    manager.get_backend("session-a")

    current_time["value"] = 1061.0
    manager.get_backend("session-b")

    assert deleted == ["session-a"]

