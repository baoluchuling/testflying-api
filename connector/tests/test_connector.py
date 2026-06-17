from __future__ import annotations

from fastapi.testclient import TestClient

from testflying_connector.main import app


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
    detail_response = client.get("/v1/sync-runs/sync-001", headers=_headers())

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "succeeded"
