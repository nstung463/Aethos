"""Create PostgreSQL storage for thread events and checkpoints."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260513_0005"
down_revision = "20260513_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "thread_events" not in existing_tables:
        op.create_table(
            "thread_events",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("thread_id", sa.Text(), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("seq", sa.BigInteger(), nullable=False),
            sa.Column("parent_event_id", sa.Text(), sa.ForeignKey("thread_events.id", ondelete="SET NULL"), nullable=True),
            sa.Column("event_type", sa.Text(), nullable=False),
            sa.Column("message_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("message_fingerprint", sa.Text(), nullable=False),
            sa.Column("checkpoint_id", sa.Text(), nullable=True),
            sa.Column("run_id", sa.Text(), nullable=True),
            sa.Column("interruption_reason", sa.Text(), nullable=True),
            sa.Column("tool_use", sa.Boolean(), nullable=True),
            sa.Column("is_sidechain", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("session_id", sa.Text(), nullable=True),
            sa.Column("user_type", sa.Text(), nullable=True),
            sa.Column("entrypoint", sa.Text(), nullable=True),
            sa.Column("cwd", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        )
        op.create_index("ix_thread_events_thread_seq", "thread_events", ["thread_id", "seq"])
        op.create_unique_constraint("uq_thread_event_fingerprint", "thread_events", ["thread_id", "message_fingerprint"])
        op.execute(
            """
            CREATE UNIQUE INDEX uq_thread_interruption_event
            ON thread_events(thread_id, run_id, event_type)
            WHERE event_type = 'interruption'
            """
        )

    if "thread_checkpoints" not in existing_tables:
        op.create_table(
            "thread_checkpoints",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("thread_id", sa.Text(), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("checkpoint_ns", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("parent_checkpoint_id", sa.Text(), nullable=True),
            sa.Column("checkpoint_payload", sa.LargeBinary(), nullable=False),
            sa.Column("checkpoint_type", sa.Text(), nullable=False),
            sa.Column("metadata_payload", sa.LargeBinary(), nullable=False),
            sa.Column("metadata_type", sa.Text(), nullable=False),
            sa.Column(
                "new_versions_json",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        )
        op.create_index(
            "ix_thread_checkpoints_thread_ns_created",
            "thread_checkpoints",
            ["thread_id", "checkpoint_ns", "created_at"],
        )
        op.create_index(
            "ix_thread_checkpoints_thread_ns_id",
            "thread_checkpoints",
            ["thread_id", "checkpoint_ns", "id"],
        )

    if "thread_checkpoint_writes" not in existing_tables:
        op.create_table(
            "thread_checkpoint_writes",
            sa.Column("thread_id", sa.Text(), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
            sa.Column("checkpoint_id", sa.Text(), sa.ForeignKey("thread_checkpoints.id", ondelete="CASCADE"), nullable=False),
            sa.Column("task_id", sa.Text(), nullable=False),
            sa.Column("task_path", sa.Text(), nullable=False, server_default=sa.text("''")),
            sa.Column("idx", sa.Integer(), nullable=False),
            sa.Column("channel", sa.Text(), nullable=False),
            sa.Column("value_payload", sa.LargeBinary(), nullable=False),
            sa.Column("value_type", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
            sa.PrimaryKeyConstraint("checkpoint_id", "task_id", "idx", name="pk_thread_checkpoint_writes"),
        )
        op.create_index(
            "ix_thread_checkpoint_writes_thread_checkpoint",
            "thread_checkpoint_writes",
            ["thread_id", "checkpoint_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    if "thread_checkpoint_writes" in existing_tables:
        op.drop_index("ix_thread_checkpoint_writes_thread_checkpoint", table_name="thread_checkpoint_writes")
        op.drop_table("thread_checkpoint_writes")
    if "thread_checkpoints" in existing_tables:
        op.drop_index("ix_thread_checkpoints_thread_ns_id", table_name="thread_checkpoints")
        op.drop_index("ix_thread_checkpoints_thread_ns_created", table_name="thread_checkpoints")
        op.drop_table("thread_checkpoints")
    if "thread_events" in existing_tables:
        op.execute("DROP INDEX IF EXISTS uq_thread_interruption_event")
        op.drop_constraint("uq_thread_event_fingerprint", "thread_events", type_="unique")
        op.drop_index("ix_thread_events_thread_seq", table_name="thread_events")
        op.drop_table("thread_events")
