from __future__ import annotations

from dataclasses import replace

from fastapi.testclient import TestClient

from testflying_connector import main as connector_main
from testflying_connector.rate_limit import StoreRateLimitPolicy, parse_apple_user_hour_limit

app = connector_main.app


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev-connector-token"}


def _payload(version: str = "2.4.0") -> dict[str, object]:
    return {
        "developerAccountId": "account-apple-enterprise",
        "operation": "update_release_notes",
        "platform": "ios",
        "version": version,
        "locale": "zh-Hans",
        "app": {
            "appId": "app-aurora-ios",
            "bundleIdentifier": "com.internal.aurora",
            "storeAppId": "1234567890",
            "packageName": "com.internal.aurora",
        },
    }


def test_connector_requires_token() -> None:
    client = TestClient(app)

    response = client.post("/v1/preflight", json=_payload())

    assert response.status_code == 401


def test_connector_rejects_other_account() -> None:
    client = TestClient(app)
    payload = _payload()
    payload["developerAccountId"] = "account-other"

    response = client.post("/v1/preflight", headers=_headers(), json=payload)

    assert response.status_code == 403


def test_connector_preflight_reports_missing_version() -> None:
    client = TestClient(app)

    response = client.post("/v1/preflight", headers=_headers(), json=_payload("missing-2.4.1"))

    assert response.status_code == 200
    assert response.json()["canSync"] is False
    assert response.json()["reasonCode"] == "store_version_missing"


def test_connector_sync_run_succeeds() -> None:
    client = TestClient(app)
    payload = _payload()
    payload["runId"] = "sync-001"
    payload["releaseNotes"] = "修复已知问题。"

    response = client.post("/v1/sync-runs", headers=_headers(), json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"


def test_connector_metadata_sync_run_succeeds() -> None:
    client = TestClient(app)
    payload = _payload()
    payload["operation"] = "update_app_metadata"
    payload["runId"] = "sync-metadata-001"
    payload["metadata"] = {
        "title": "Aurora Mobile",
        "subtitle": "内部测试分发",
        "keywords": "internal,test",
        "promotionalText": "更稳定的测试体验。",
        "description": "用于内部测试包分发和回归验证。",
        "privacyPolicyUrl": "https://example.test/privacy",
        "supportUrl": "https://example.test/support",
        "marketingUrl": "",
    }

    response = client.post("/v1/sync-runs", headers=_headers(), json=payload)

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["message"] == "商店元数据已同步。"


def test_connector_lists_supported_locales() -> None:
    client = TestClient(app)

    response = client.get(
        "/v1/apps/app-aurora-ios/supported-locales",
        headers=_headers(),
        params={
            "developerAccountId": "account-apple-enterprise",
            "platform": "ios",
            "version": "2.4.0",
        },
    )

    assert response.status_code == 200
    assert response.json()["locales"] == ["zh-Hans", "en-US", "ja", "ko"]


def test_connector_rate_limits_google_requests() -> None:
    old_settings = connector_main.settings
    old_policy = connector_main.rate_limit_policy
    connector_main.settings = replace(
        old_settings,
        google_rate_limit_max_requests=2,
        google_rate_limit_window_seconds=60,
    )
    connector_main.rate_limit_policy = StoreRateLimitPolicy(connector_main.settings)
    connector_main.rate_limiter.reset()
    try:
        client = TestClient(app)
        payload = _payload()
        payload["platform"] = "android"
        payload["runId"] = "sync-rate-limit"
        payload["releaseNotes"] = "修复已知问题。"

        first_response = client.post("/v1/sync-runs", headers=_headers(), json=payload)
        second_response = client.post("/v1/sync-runs", headers=_headers(), json=payload)
        limited_response = client.post("/v1/sync-runs", headers=_headers(), json=payload)
        health_response = client.get("/health")

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert limited_response.status_code == 429
        assert int(limited_response.headers["retry-after"]) > 0
        assert health_response.status_code == 200
    finally:
        connector_main.settings = old_settings
        connector_main.rate_limit_policy = old_policy
        connector_main.rate_limiter.reset()


def test_apple_rate_limit_header_uses_safety_margin() -> None:
    policy = StoreRateLimitPolicy(
        replace(
            connector_main.settings,
            apple_rate_limit_fallback_max_requests=100,
            apple_rate_limit_safety_ratio=0.8,
        )
    )

    policy.record_apple_rate_limit_header("user-hour-lim:10;user-hour-rem:8;")
    rule = policy.rule_for_platform("ios")

    assert parse_apple_user_hour_limit("user-hour-lim:10;user-hour-rem:8;") == 10
    assert rule.max_requests == 8
    assert rule.window_seconds == 3600
