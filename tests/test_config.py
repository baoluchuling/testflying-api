from __future__ import annotations

from testflying_api.config import Settings


def test_settings_reads_connector_base_url_template(monkeypatch) -> None:
    monkeypatch.setenv(
        "TESTFLYING_CONNECTOR_BASE_URL_TEMPLATE",
        " http://connector-{account_id}:8100 ",
    )

    settings = Settings.from_environment()

    assert settings.connector_base_url_template == "http://connector-{account_id}:8100"


def test_settings_normalizes_blank_connector_base_url_template(monkeypatch) -> None:
    monkeypatch.setenv("TESTFLYING_CONNECTOR_BASE_URL_TEMPLATE", " ")

    settings = Settings.from_environment()

    assert settings.connector_base_url_template is None
