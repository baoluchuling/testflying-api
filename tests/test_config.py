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


def test_settings_reads_translation_configuration(monkeypatch) -> None:
    monkeypatch.setenv("TESTFLYING_TRANSLATION_PROVIDER", "openai")
    monkeypatch.setenv("TESTFLYING_TRANSLATION_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("TESTFLYING_TRANSLATION_OPENAI_BASE_URL", "https://llm.example.test/v1")
    monkeypatch.setenv("TESTFLYING_TRANSLATION_OPENAI_MODEL", "translation-model")

    settings = Settings.from_environment()

    assert settings.translation_provider == "openai"
    assert settings.translation_openai_api_key == "test-key"
    assert settings.translation_openai_base_url == "https://llm.example.test/v1"
    assert settings.translation_openai_model == "translation-model"
