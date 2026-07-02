from __future__ import annotations


def admin_next_redirect_path(path: str) -> str | None:
    """Map legacy visible admin page URLs to the React admin shell routes."""
    if path == "/admin" or path == "/admin/":
        return "/admin-next"
    if not path.startswith("/admin/"):
        return None

    if _is_legacy_admin_resource(path):
        return None

    static_pages = {
        "/admin/apps": "/admin-next/apps",
        "/admin/uploads": "/admin-next/uploads",
        "/admin/builds": "/admin-next/builds",
        "/admin/devices": "/admin-next/devices",
        "/admin/notifications": "/admin-next/notifications",
        "/admin/app-logs": "/admin-next/app-logs",
        "/admin/store-reviews": "/admin-next/store-reviews",
        "/admin/api-docs": "/admin-next/api-docs",
    }
    if path in static_pages:
        return static_pages[path]

    account_prefix = "/admin/developer-accounts"
    if path == account_prefix:
        return "/admin-next/accounts"
    if path.startswith(f"{account_prefix}/"):
        return _account_admin_next_path(path.removeprefix(f"{account_prefix}/"))

    return None


def _is_legacy_admin_resource(path: str) -> bool:
    resource_paths = {
        "/admin/app-logs/events",
        "/admin/app-logs/qr.svg",
        "/admin/api-docs/store-management.md",
    }
    if path in resource_paths:
        return True
    return path.startswith("/admin/api/") or path.startswith("/admin/artifacts/")


def _account_admin_next_path(relative: str) -> str | None:
    parts = [part for part in relative.strip("/").split("/") if part]
    if not parts:
        return "/admin-next/accounts"
    if parts == ["new"]:
        return "/admin-next/accounts/new"

    account_id = parts[0]
    if len(parts) == 1:
        return f"/admin-next/accounts/{account_id}"
    if parts[1] == "edit":
        return f"/admin-next/accounts/{account_id}/edit"
    if len(parts) < 4 or parts[1] != "apps":
        return f"/admin-next/accounts/{account_id}"

    app_id = parts[2]
    app_path = parts[3:]
    if not app_path:
        return f"/admin-next/accounts/{account_id}"

    first = app_path[0]
    if first == "release-notes":
        return f"/admin-next/accounts/{account_id}/apps/{app_id}/release-notes"

    if first == "store":
        return _store_admin_next_path(account_id=account_id, app_id=app_id, tail=app_path[1:])

    if first == "store-metadata":
        return _store_metadata_admin_next_path(
            account_id=account_id,
            app_id=app_id,
            tail=app_path[1:],
        )

    return f"/admin-next/accounts/{account_id}/apps/{app_id}/store"


def _store_admin_next_path(account_id: str, app_id: str, tail: list[str]) -> str:
    base = f"/admin-next/accounts/{account_id}/apps/{app_id}"
    if not tail:
        return f"{base}/store"
    if tail[0] == "connection":
        return f"{base}/connection"
    if tail[0] == "marketing":
        return f"{base}/marketing"
    if tail[0] == "marketing-pages":
        if len(tail) >= 2:
            return f"{base}/marketing-pages/{tail[1]}"
        return f"{base}/marketing"
    return f"{base}/store"


def _store_metadata_admin_next_path(account_id: str, app_id: str, tail: list[str]) -> str:
    base = f"/admin-next/accounts/{account_id}/apps/{app_id}"
    if tail and tail[0] == "marketing-pages":
        if len(tail) >= 2:
            return f"{base}/marketing-pages/{tail[1]}"
        return f"{base}/marketing"
    return f"{base}/store"
