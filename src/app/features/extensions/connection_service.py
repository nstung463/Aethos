"""Small factories around the heavier native-connections service.

This file exists to give route handlers a clearly named entrypoint for the
OAuth callback path without exposing the full service construction details.
"""

from __future__ import annotations

from src.app.features.extensions.connections_service import ConnectionService, ProviderName


def build_oauth_state_connection_service(*, provider: ProviderName, state: str) -> ConnectionService:
    """Build a connection service bound to a validated OAuth callback state."""
    return ConnectionService.for_oauth_state(provider=provider, state=state)


def for_oauth_state_service(*, provider: ProviderName, state: str) -> ConnectionService:
    """Backward-compatible alias for older imports."""
    return build_oauth_state_connection_service(provider=provider, state=state)


__all__ = ["build_oauth_state_connection_service", "for_oauth_state_service"]
