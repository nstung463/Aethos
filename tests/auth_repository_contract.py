from __future__ import annotations

from typing import Callable

from src.app.features.auth.types import AuthRepositoryProtocol


def exercise_auth_repository_contract(
    factory: Callable[[], AuthRepositoryProtocol],
) -> None:
    repo = factory()
    user, session = repo.create_guest_session(display_name="Contract User")

    loaded_user = repo.get_user(user.id)
    assert loaded_user is not None
    assert loaded_user.id == user.id
    assert loaded_user.display_name == "Contract User"

    loaded_session = repo.get_session(session.token)
    assert loaded_session is not None
    assert loaded_session.user_id == user.id

    saved = repo.update_permission_defaults(
        user_id=user.id,
        defaults={
            "mode": "acceptEdits",
            "working_directories": ["W:/aethos"],
            "rules": [{"tool": "shell", "decision": "allow"}],
        },
    )
    assert saved is not None
    assert repo.get_permission_defaults(user.id) == saved

    linked = repo.link_identity(
        user_id=user.id,
        provider="google",
        provider_subject="contract-subject",
        email="contract@example.com",
        profile={"email": "contract@example.com"},
    )
    assert linked.id == user.id

    identified_user = repo.find_identity(
        provider="google",
        provider_subject="contract-subject",
    )
    assert identified_user is not None
    assert identified_user.id == user.id

    created_user = repo.create_user_with_identity(
        provider="slack",
        provider_subject="contract-secondary",
        email="secondary@example.com",
        display_name="Secondary User",
        profile={"team": "qa"},
    )
    assert created_user.display_name == "Secondary User"

    secondary_identity = repo.find_identity(
        provider="slack",
        provider_subject="contract-secondary",
    )
    assert secondary_identity is not None
    assert secondary_identity.id == created_user.id

    assert repo.revoke_session(session.token) is True
    assert repo.get_session(session.token) is None
    assert repo.revoke_session(session.token) is False
