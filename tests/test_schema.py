from __future__ import annotations

from sqlalchemy import inspect

from testflying_api.database import create_engine_for_url
from testflying_api.schema import Base


def test_catalog_schema_contains_no_user_state_tables() -> None:
    engine = create_engine_for_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    table_names = set(inspect(engine).get_table_names())

    assert {
        "apps",
        "builds",
        "artifacts",
        "devices",
        "developer_accounts",
        "developer_account_apps",
        "notifications",
        "device_build_visibility",
        "store_connectors",
        "store_release_note_drafts",
        "store_preflight_checks",
        "store_sync_runs",
        "audit_logs",
    }.issubset(table_names)
    assert "install_tasks" not in table_names
    assert "sort_orders" not in table_names
    assert "notification_reads" not in table_names
