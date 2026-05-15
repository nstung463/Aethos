"""Import all ORM models so metadata is complete when loaded."""

from src.app.db.models.auth import AuthIdentityModel, AuthSessionModel, UserModel
from src.app.db.models.checkpoints import ThreadCheckpointModel, ThreadCheckpointWriteModel, ThreadEventModel
from src.app.db.models.connections import ConnectionAuditModel, ConnectionModel, ConnectionSecretModel, OAuthStateModel
from src.app.db.models.threads import ProjectModel, ThreadModel, ThreadPermissionModel

__all__ = [
    "AuthIdentityModel",
    "AuthSessionModel",
    "ConnectionAuditModel",
    "ConnectionModel",
    "ConnectionSecretModel",
    "OAuthStateModel",
    "ProjectModel",
    "ThreadCheckpointModel",
    "ThreadCheckpointWriteModel",
    "ThreadEventModel",
    "ThreadModel",
    "ThreadPermissionModel",
    "UserModel",
]
