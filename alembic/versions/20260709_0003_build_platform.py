from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260709_0003"
down_revision = "20260702_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("builds") as batch_op:
        batch_op.alter_column("version", existing_type=sa.String(length=60), nullable=True)
        batch_op.alter_column("build_number", existing_type=sa.String(length=80), nullable=True)
        batch_op.add_column(
            sa.Column(
                "requested_environment",
                sa.String(length=30),
                nullable=False,
                server_default="development",
            )
        )
        batch_op.add_column(
            sa.Column("source", sa.String(length=30), nullable=False, server_default="upload")
        )
        batch_op.add_column(
            sa.Column(
                "lifecycle_status",
                sa.String(length=40),
                nullable=False,
                server_default="succeeded",
            )
        )
        batch_op.add_column(sa.Column("git_url", sa.String(length=800), nullable=True))
        batch_op.add_column(sa.Column("git_ref", sa.String(length=240), nullable=True))
        batch_op.add_column(sa.Column("commit_sha", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("runner_id", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("runner_labels_json", sa.JSON(), nullable=True))
        batch_op.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("failure_classification", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(sa.Column("failure_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("human_action", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("duration_seconds", sa.Integer(), nullable=True))

    _upgrade_artifacts()


def downgrade() -> None:
    _downgrade_artifacts()

    with op.batch_alter_table("builds") as batch_op:
        for column in [
            "duration_seconds",
            "finished_at",
            "started_at",
            "human_action",
            "failure_summary",
            "failure_classification",
            "attempt_count",
            "runner_labels_json",
            "runner_id",
            "commit_sha",
            "git_ref",
            "git_url",
            "lifecycle_status",
            "source",
            "requested_environment",
        ]:
            batch_op.drop_column(column)
        batch_op.alter_column("build_number", existing_type=sa.String(length=80), nullable=False)
        batch_op.alter_column("version", existing_type=sa.String(length=60), nullable=False)


def _upgrade_artifacts() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _drop_artifacts_build_id_unique_postgresql()

    with op.batch_alter_table("artifacts", recreate="always") as batch_op:
        batch_op.add_column(
            sa.Column("artifact_type", sa.String(length=30), nullable=False, server_default="package")
        )
        batch_op.add_column(sa.Column("metadata_json", sa.JSON(), nullable=True))


def _downgrade_artifacts() -> None:
    with op.batch_alter_table("artifacts", recreate="always") as batch_op:
        batch_op.drop_column("metadata_json")
        batch_op.drop_column("artifact_type")
        batch_op.create_unique_constraint("uq_artifacts_build_id", ["build_id"])


def _drop_artifacts_build_id_unique_postgresql() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            old_constraint_name text;
        BEGIN
            SELECT con.conname
            INTO old_constraint_name
            FROM pg_constraint con
            JOIN pg_class rel ON rel.oid = con.conrelid
            WHERE rel.relname = 'artifacts'
              AND con.contype = 'u'
              AND (
                SELECT array_agg(att.attname::text ORDER BY keys.ordinality)
                FROM unnest(con.conkey) WITH ORDINALITY AS keys(attnum, ordinality)
                JOIN pg_attribute att
                  ON att.attrelid = rel.oid
                 AND att.attnum = keys.attnum
              ) = ARRAY['build_id']::text[];

            IF old_constraint_name IS NOT NULL THEN
                EXECUTE format('ALTER TABLE artifacts DROP CONSTRAINT %I', old_constraint_name);
            END IF;
        END
        $$;
        """
    )
