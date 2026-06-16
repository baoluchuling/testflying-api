from __future__ import annotations

from fastapi.testclient import TestClient

from testflying_api.app import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
