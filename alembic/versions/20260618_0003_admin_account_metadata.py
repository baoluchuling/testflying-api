from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260618_0003"
down_revision = "20260618_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_app_metadata_drafts",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column(
            "developer_account_id",
            sa.String(length=80),
            sa.ForeignKey("developer_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "app_id",
            sa.String(length=80),
            sa.ForeignKey("apps.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("version", sa.String(length=60), nullable=False),
        sa.Column("locale", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("subtitle", sa.String(length=160), nullable=False),
        sa.Column("keywords", sa.String(length=240), nullable=False),
        sa.Column("promotional_text", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("privacy_policy_url", sa.String(length=400), nullable=False),
        sa.Column("support_url", sa.String(length=400), nullable=False),
        sa.Column("marketing_url", sa.String(length=400), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "developer_account_id",
            "app_id",
            "platform",
            "version",
            "locale",
            name="uq_store_app_metadata_drafts_scope",
        ),
    )
    op.add_column(
        "store_sync_runs",
        sa.Column("metadata_draft_id", sa.String(length=80), nullable=True),
    )
    op.create_foreign_key(
        "fk_store_sync_runs_metadata_draft_id",
        "store_sync_runs",
        "store_app_metadata_drafts",
        ["metadata_draft_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_store_sync_runs_metadata_draft_id",
        "store_sync_runs",
        type_="foreignkey",
    )
    op.drop_column("store_sync_runs", "metadata_draft_id")
    op.drop_table("store_app_metadata_drafts")
