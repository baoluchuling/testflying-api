from __future__ import annotations

from base64 import b64encode

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.seed import seed_demo_catalog
from tests.fixtures import make_android_apk_bytes


def _admin_headers(password: str = "dev-token") -> dict[str, str]:
    token = b64encode(f"admin:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_admin_requires_basic_auth(client: TestClient) -> None:
    response = client.get("/admin")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_admin_dashboard_renders_seeded_catalog(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.get("/admin", headers=_admin_headers())

    assert response.status_code == 200
    assert "testflying 管理后台" in response.text
    assert "总览" in response.text
    assert "Aurora Mobile" in response.text
    assert "Apple 开发者账号即将到期" in response.text


def test_admin_resource_pages_render_seeded_catalog(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    pages = {
        "/admin/apps": "Aurora Mobile",
        "/admin/builds": "2.4.0",
        "/admin/devices": "iPhone 15 Pro",
        "/admin/developer-accounts": "Internal Distribution Team",
        "/admin/notifications": "Apple 开发者账号即将到期",
        "/admin/uploads": "上传构建",
    }
    for path, expected_text in pages.items():
        response = client.get(path, headers=_admin_headers())

        assert response.status_code == 200
        assert expected_text in response.text


def test_admin_upload_page_uses_auto_metadata_and_progress(client: TestClient) -> None:
    response = client.get("/admin/uploads", headers=_admin_headers())

    assert response.status_code == 200
    assert "包信息自动解析" in response.text
    assert "data-upload-progress" in response.text
    assert "name=\"appName\"" in response.text
    assert "name=\"packageName\"" not in response.text
    assert "name=\"buildNumber\"" not in response.text


def test_admin_upload_android_package_creates_build(client: TestClient) -> None:
    response = client.post(
        "/admin/uploads",
        headers=_admin_headers(),
        data={
            "platform": "android",
            "environment": "development",
            "changelog": "后台上传冒烟测试",
        },
        files={
            "file": (
                "admin.apk",
                make_android_apk_bytes(),
                "application/vnd.android.package-archive",
            )
        },
    )

    assert response.status_code == 200
    assert "上传成功" in response.text
    assert "Auto Parsed" in response.text
    assert "downloadUrl" in response.text

    builds_response = client.get("/admin/builds", headers=_admin_headers())
    assert builds_response.status_code == 200
    assert "Auto Parsed" in builds_response.text
    assert "4.5.6" in builds_response.text
