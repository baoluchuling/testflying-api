from __future__ import annotations

from fastapi.testclient import TestClient

from testflying_api.app import create_app


client = TestClient(create_app())


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_workspace_returns_client_contract_shape() -> None:
    response = client.get(
        "/v1/test-distribution/workspace",
        headers={
            "Authorization": "Bearer token-123",
            "X-Device-ID": "device-456",
            "X-Client-Platform": "ios",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["apps"] == []
    assert body["builds"] == []
    assert body["developerAccounts"] == []
    assert body["installTasks"] == []
    assert body["sortOrder"] == {"buildIds": []}
    assert body["devices"][0]["id"] == "device-456"
    assert body["devices"][0]["platform"] == "ios"
    assert body["profile"]["role"] == "authenticated"
