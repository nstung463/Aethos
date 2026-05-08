"""Application package for Aethos backend."""


def create_app():
    from src.app.bootstrap import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]
