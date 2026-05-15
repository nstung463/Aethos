"""Create thread metadata and oauth state tables."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260513_0003"
down_revision = "20260513_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "projects" not in existing_tables:
        op.create_table(
            "projects",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("project_key", sa.Text(), nullable=False, unique=True),
            sa.Column("canonical_root", sa.Text(), nullable=False),
            sa.Column("original_root", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        )

    if "threads" not in existing_tables:
        op.create_table(
            "threads",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("project_id", sa.Text(), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
            sa.Column("workspace_root", sa.Text(), nullable=True),
            sa.Column("canonical_root", sa.Text(), nullable=True),
            sa.Column("backend", sa.Text(), nullable=True),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'idle'")),
            sa.Column("title", sa.Text(), nullable=True),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("model", sa.Text(), nullable=True),
            sa.Column("mode", sa.Text(), nullable=True),
            sa.Column("profile_id", sa.Text(), nullable=True),
            sa.Column("project_label", sa.Text(), nullable=True),
            sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("active_run_id", sa.Text(), nullable=True),
            sa.Column("run_started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_stop_run_id", sa.Text(), nullable=True),
            sa.Column("last_stop_reason", sa.Text(), nullable=True),
            sa.Column("last_interrupted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        )
        op.create_index("ix_threads_user_id", "threads", ["user_id"])
        op.create_index("ix_threads_project_id", "threads", ["project_id"])

    if "thread_permissions" not in existing_tables:
        op.create_table(
            "thread_permissions",
            sa.Column("thread_id", sa.Text(), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column(
                "overlay_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.PrimaryKeyConstraint("thread_id", "user_id", name="pk_thread_permissions"),
        )

    if "oauth_states" not in existing_tables:
        op.create_table(
            "oauth_states",
            sa.Column("state", sa.Text(), primary_key=True),
            sa.Column("provider", sa.Text(), nullable=False),
            sa.Column(
                "payload_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "oauth_states" in existing_tables:
        op.drop_table("oauth_states")
    if "thread_permissions" in existing_tables:
        op.drop_table("thread_permissions")
    if "threads" in existing_tables:
        op.drop_index("ix_threads_project_id", table_name="threads")
        op.drop_index("ix_threads_user_id", table_name="threads")
        op.drop_table("threads")
    if "projects" in existing_tables:
        op.drop_table("projects")
