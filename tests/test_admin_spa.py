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


def test_legacy_admin_pages_redirect_to_spa(client: TestClient) -> None:
    expected = {
        "/admin": "/admin-next",
        "/admin/apps": "/admin-next/apps",
        "/admin/uploads": "/admin-next/uploads",
        "/admin/builds": "/admin-next/builds",
        "/admin/devices": "/admin-next/devices",
        "/admin/notifications": "/admin-next/notifications",
        "/admin/app-logs": "/admin-next/app-logs",
        "/admin/store-reviews": "/admin-next/store-reviews",
        "/admin/api-docs": "/admin-next/api-docs",
        "/admin/developer-accounts": "/admin-next/accounts",
        "/admin/developer-accounts/new": "/admin-next/accounts/new",
        "/admin/developer-accounts/account-apple-enterprise": (
            "/admin-next/accounts/account-apple-enterprise"
        ),
        "/admin/developer-accounts/account-apple-enterprise/edit": (
            "/admin-next/accounts/account-apple-enterprise/edit"
        ),
        "/admin/developer-accounts/account-apple-enterprise/apps/app-insight-ios/store": (
            "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/store"
        ),
        "/admin/developer-accounts/account-apple-enterprise/apps/app-insight-ios/store-metadata": (
            "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/store"
        ),
        "/admin/developer-accounts/account-apple-enterprise/apps/app-insight-ios/release-notes": (
            "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/release-notes"
        ),
        (
            "/admin/developer-accounts/account-apple-enterprise/apps/app-insight-ios"
            "/store/connection"
        ): "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/connection",
        "/admin/developer-accounts/account-apple-enterprise/apps/app-insight-ios/store/marketing": (
            "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/marketing"
        ),
        (
            "/admin/developer-accounts/account-apple-enterprise/apps/app-insight-ios"
            "/store/marketing-pages/page-1"
        ): (
            "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios"
            "/marketing-pages/page-1"
        ),
    }

    for path, target in expected.items():
        response = client.get(path, headers=_admin_headers(), follow_redirects=False)

        assert response.status_code == 307
        assert response.headers["location"] == target


def test_legacy_admin_resource_routes_do_not_redirect(client: TestClient) -> None:
    for path in (
        "/admin/api-docs/store-management.md",
        "/admin/app-logs/events",
        "/admin/app-logs/qr.svg",
    ):
        response = client.get(path, headers=_admin_headers(), follow_redirects=False)

        assert response.status_code != 307


def test_admin_next_deep_routes_serve_spa_shell(client: TestClient) -> None:
    for path in (
        "/admin-next/accounts",
        "/admin-next/accounts/account-apple-enterprise",
        "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/store",
        "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/marketing",
        "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/connection",
        "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/release-notes",
        "/admin-next/accounts/account-apple-enterprise/apps/app-insight-ios/marketing-pages/page-1",
    ):
        response = client.get(path, headers=_admin_headers())

        assert response.status_code == 200
        assert "data-admin-app-root" in response.text
