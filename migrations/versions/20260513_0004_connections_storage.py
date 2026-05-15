"""Create PostgreSQL storage for native connections."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260513_0004"
down_revision = "20260513_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "connections" not in existing_tables:
        op.create_table(
            "connections",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column("owner_user_id", sa.Text(), nullable=False),
            sa.Column("project_key", sa.Text(), nullable=False),
            sa.Column("account_label", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column(
                "capabilities_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "scopes_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("auth_type", sa.Text(), nullable=False, server_default=sa.text("'oauth2'")),
            sa.Column("tools_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("last_refresh_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
        )
        op.create_index("ix_connections_owner_project_provider", "connections", ["owner_user_id", "project_key", "provider"])

    if "connection_secrets" not in existing_tables:
        op.create_table(
            "connection_secrets",
            sa.Column("connection_id", sa.Text(), sa.ForeignKey("connections.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("ciphertext", sa.Text(), nullable=False),
            sa.Column("key_version", sa.Text(), nullable=False, server_default=sa.text("'v1'")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        )

    if "connection_audit" not in existing_tables:
        op.create_table(
            "connection_audit",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("connection_id", sa.Text(), sa.ForeignKey("connections.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("tool_name", sa.Text(), nullable=False),
            sa.Column("action_kind", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False),
            sa.Column("request_summary", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("error", sa.Text(), nullable=True),
        )
        op.create_index("ix_connection_audit_connection_id", "connection_audit", ["connection_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "connection_audit" in existing_tables:
        op.drop_index("ix_connection_audit_connection_id", table_name="connection_audit")
        op.drop_table("connection_audit")
    if "connection_secrets" in existing_tables:
        op.drop_table("connection_secrets")
    if "connections" in existing_tables:
        op.drop_index("ix_connections_owner_project_provider", table_name="connections")
        op.drop_table("connections")
