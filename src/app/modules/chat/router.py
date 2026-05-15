"""Compatibility shim for the migrated chat feature.

Deprecated for one release cycle. Do not add new logic or imports here;
use ``src.app.features.chat.router`` instead.
"""

from src.app.features.chat.router import *  # noqa: F403
