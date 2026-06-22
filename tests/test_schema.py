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
        "store_app_metadata_drafts",
        "store_image_suites",
        "store_image_suite_locales",
        "store_preflight_checks",
        "store_sync_runs",
        "audit_logs",
    }.issubset(table_names)
    assert "install_tasks" not in table_names
    assert "sort_orders" not in table_names
    assert "notification_reads" not in table_names


def test_store_connector_is_unique_per_account() -> None:
    engine = create_engine_for_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    constraints = inspect(engine).get_unique_constraints("store_connectors")

    assert any(
        constraint["column_names"] == ["developer_account_id"] for constraint in constraints
    )


def test_store_metadata_drafts_include_image_settings() -> None:
    engine = create_engine_for_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("store_app_metadata_drafts")
    }

    assert "store_images_json" in columns


def test_store_image_suites_are_unique_per_app_scope() -> None:
    engine = create_engine_for_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    constraints = inspect(engine).get_unique_constraints("store_image_suites")

    assert any(
        constraint["column_names"] == [
            "developer_account_id",
            "app_id",
            "platform",
            "suite_id",
        ]
        for constraint in constraints
    )


def test_store_image_suite_locales_store_images_by_locale() -> None:
    engine = create_engine_for_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    columns = {
        column["name"]
        for column in inspect(engine).get_columns("store_image_suite_locales")
    }
    constraints = inspect(engine).get_unique_constraints("store_image_suite_locales")

    assert "store_images_json" in columns
    assert any(
        constraint["column_names"] == ["image_suite_id", "locale"] for constraint in constraints
    )
