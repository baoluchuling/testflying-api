from __future__ import annotations

from base64 import b64encode

from fastapi.testclient import TestClient


def _admin_headers(password: str = "dev-token") -> dict[str, str]:
    token = b64encode(f"admin:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_admin_next_requires_basic_auth(client: TestClient) -> None:
    response = client.get("/admin-next")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_admin_next_serves_react_shell(client: TestClient) -> None:
    response = client.get("/admin-next", headers=_admin_headers())

    assert response.status_code == 200
    assert "data-admin-app-root" in response.text
    assert "testflying" in response.text


def test_admin_next_spa_fallback_serves_nested_routes(client: TestClient) -> None:
    response = client.get("/admin-next/store-reviews", headers=_admin_headers())

    assert response.status_code == 200
    assert "data-admin-app-root" in response.text


def test_legacy_admin_still_available_during_rebuild(client: TestClient) -> None:
    response = client.get("/admin", headers=_admin_headers())

    assert response.status_code == 200
    assert "data-admin-main" in response.text
    assert "testflying 管理后台" in response.text
