from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260618_0006"
down_revision = "20260618_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("store_app_metadata_drafts") as batch_op:
        batch_op.drop_constraint("uq_store_app_metadata_drafts_scope", type_="unique")
        batch_op.add_column(
            sa.Column(
                "content_set_id",
                sa.String(length=80),
                nullable=False,
                server_default="default",
            )
        )
        batch_op.add_column(
            sa.Column(
                "content_set_name",
                sa.String(length=120),
                nullable=False,
                server_default="默认上架内容",
            )
        )
        batch_op.create_unique_constraint(
            "uq_store_app_metadata_drafts_scope",
            [
                "developer_account_id",
                "app_id",
                "platform",
                "version",
                "locale",
                "content_set_id",
            ],
        )


def downgrade() -> None:
    with op.batch_alter_table("store_app_metadata_drafts") as batch_op:
        batch_op.drop_constraint("uq_store_app_metadata_drafts_scope", type_="unique")
        batch_op.create_unique_constraint(
            "uq_store_app_metadata_drafts_scope",
            ["developer_account_id", "app_id", "platform", "version", "locale"],
        )
        batch_op.drop_column("content_set_name")
        batch_op.drop_column("content_set_id")
