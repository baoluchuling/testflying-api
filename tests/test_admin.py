from __future__ import annotations

import json
import re
import shutil
import subprocess
from base64 import b64encode
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.schema import (
    App,
    DeveloperAccount,
    StoreAppMetadataDraft,
    StoreConnector,
    StoreImageSuite,
    StoreImageSuiteLocale,
    StoreMarketingPage,
    StoreMarketingPageLocale,
    StorePreflightCheck,
    StoreReleaseNoteDraft,
    StoreSyncRun,
)
from testflying_api.seed import seed_demo_catalog
from testflying_api.store_sync import CURRENT_METADATA_VERSION, supported_locales_for_app
from tests.fixtures import make_android_apk_bytes, make_png_header_bytes


def _admin_headers(password: str = "dev-token") -> dict[str, str]:
    token = b64encode(f"admin:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


LEGACY_JINJA_PAGE_REASON = "旧 Jinja 管理页已迁移为 /admin-next React SPA"


def _assert_admin_spa_shell(response) -> None:
    assert response.status_code == 200
    assert 'data-admin-app-root' in response.text
    assert "/assets/index-" in response.text
    assert "/static/admin/admin.css" not in response.text


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
    api_response = client.get("/admin/api/dashboard", headers=_admin_headers())

    _assert_admin_spa_shell(response)
    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload["recentBuilds"]
    assert payload["recentNotifications"][0]["title"] == "Apple 开发者账号即将到期"


def test_admin_shell_supports_inline_navigation_and_upload_dock(client: TestClient) -> None:
    response = client.get("/admin", headers=_admin_headers())
    bootstrap = client.get("/admin/api/bootstrap", headers=_admin_headers())

    _assert_admin_spa_shell(response)
    assert bootstrap.status_code == 200
    assert bootstrap.json()["navItems"][0]["path"] == "/admin-next"


def test_admin_shell_versions_static_css(client: TestClient) -> None:
    response = client.get("/admin", headers=_admin_headers())

    _assert_admin_spa_shell(response)


def test_admin_api_docs_page_renders_public_store_api(client: TestClient) -> None:
    response = client.get("/admin/api-docs", headers=_admin_headers())
    api_response = client.get("/admin/api/api-docs", headers=_admin_headers())

    _assert_admin_spa_shell(response)
    assert api_response.status_code == 200
    assert api_response.json()["downloadUrl"] == "/admin/api-docs/store-management.md"


def test_admin_api_docs_markdown_download(client: TestClient) -> None:
    response = client.get("/admin/api-docs/store-management.md", headers=_admin_headers())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert 'filename="testflying-store-management-api.md"' in response.headers[
        "content-disposition"
    ]
    assert "# testflying 商店连接对外 API" in response.text
    assert "第三方电脑或外部系统调用" in response.text
    assert "/v1/connectors" not in response.text


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_inline_script_has_valid_syntax(client: TestClient, tmp_path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("node is required to check admin inline script syntax")

    response = client.get("/admin/app-logs", headers=_admin_headers())
    assert response.status_code == 200
    start = response.text.rfind("<script>")
    end = response.text.rfind("</script>")
    assert start != -1
    assert end > start
    script_path = tmp_path / "admin.js"
    script_path.write_text(response.text[start + len("<script>") : end])

    subprocess.run([node, "--check", str(script_path)], check=True)


def test_admin_health_check_renders_inline_status(client: TestClient) -> None:
    response = client.get("/admin", headers=_admin_headers())
    bootstrap = client.get("/admin/api/bootstrap", headers=_admin_headers())

    _assert_admin_spa_shell(response)
    assert bootstrap.status_code == 200
    assert bootstrap.json()["health"] == {"state": "idle", "label": "未检查"}


def test_admin_health_check_status_has_distinct_colors(client: TestClient) -> None:
    response = client.get("/static/admin/admin.css")

    assert response.status_code == 200
    assert '.health-status[data-state="checking"]' in response.text
    assert "border-color: #f59e0b" in response.text
    assert '.health-status[data-state="ok"]' in response.text
    assert "border-color: #22c55e" in response.text
    assert '.health-status[data-state="error"]' in response.text
    assert "border-color: #ef4444" in response.text


def test_admin_connector_deploy_commands_are_readable(client: TestClient) -> None:
    response = client.get("/static/admin/admin.css")

    assert response.status_code == 200
    assert ".deploy-step pre" in response.text
    assert "background: white" in response.text
    assert "color: var(--text)" in response.text
    assert ".deploy-step code" in response.text
    assert "color: inherit" in response.text


def test_admin_api_docs_uses_full_main_width(client: TestClient) -> None:
    response = client.get("/static/admin/admin.css")

    assert response.status_code == 200
    assert ".api-docs-main {\n  max-width: none;\n}" in response.text
    assert ".api-docs-main {\n  max-width: 1480px;\n}" not in response.text


def test_admin_store_metadata_focus_layout_css_contract(client: TestClient) -> None:
    response = client.get("/static/admin/admin.css")

    assert response.status_code == 200
    assert ".sidebar {" in response.text
    assert "width: 184px" in response.text
    assert ".main {" in response.text
    assert "margin-left: 184px" in response.text
    assert ".admin-route-loading" in response.text
    assert "left: 208px" in response.text
    assert ".store-metadata-main" in response.text
    assert "max-width: 1262px" not in response.text
    assert ".store-metadata-main .toolbar" in response.text
    assert "justify-content: space-between" in response.text
    assert ".store-metadata-main .content-set-picker" in response.text
    assert "flex: 0 0 184px" in response.text
    assert "width: 184px" in response.text
    assert "max-width: 184px" in response.text
    assert ".store-metadata-main .language-picker" in response.text
    assert "flex: 0 0 138px" in response.text
    assert ".store-metadata-main .sync-item" in response.text
    assert "grid-template-columns: 26px minmax(0, 1fr) 8px auto 14px" in response.text
    assert "grid-template-columns: 232px minmax(0, 1fr) 252px" in response.text
    assert "grid-template-columns: 220px minmax(0, 1fr) 232px" in response.text
    assert "grid-template-columns: 184px minmax(0, 1fr) 252px" not in response.text
    assert "grid-template-columns: 180px minmax(0, 1fr) 232px" not in response.text
    assert ".store-metadata-main .editor" in response.text
    assert "min-height: 608px" in response.text
    assert "height: 168px" in response.text
    assert ".store-metadata-main .locale-row" in response.text
    assert "height: 64px" in response.text
    assert ".store-workspace-main .metadata-readonly-strip" in response.text
    assert ".metadata-sync-history-panel" not in response.text
    assert ".store-metadata-main .image-locale-row" in response.text
    assert ".store-image-lightbox" in response.text
    assert "place-items: stretch" in response.text
    assert ".store-image-lightbox-panel" in response.text
    assert "width: 100vw" in response.text
    assert "height: 100vh" in response.text
    assert "border-radius: 0" in response.text
    assert "repeat(auto-fill, minmax(240px, 1fr))" in response.text
    assert ".store-metadata-main .history-link" not in response.text
    assert ".store-section-tabs" not in response.text
    assert ".store-section-panel" not in response.text

    final_guard_index = response.text.rfind("Store metadata final conflict guards")
    assert final_guard_index != -1
    for selector in (
        ".store-metadata-main .toolbar-left",
        ".store-metadata-main .content-set-picker",
        ".store-metadata-main .language-picker",
        ".store-metadata-main .metadata-preflight-chip.blocked",
        ".store-metadata-main .main-input",
        ".store-metadata-main .locale-row",
    ):
        assert response.text.rfind(selector) > final_guard_index


def test_admin_marketing_page_layout_css_prevents_horizontal_overflow(
    client: TestClient,
) -> None:
    response = client.get("/static/admin/admin.css")

    assert response.status_code == 200
    assert "Marketing page layout guard" in response.text
    assert ".marketing-page-main {" in response.text
    assert "width: auto" in response.text
    assert "overflow-x: hidden" in response.text
    assert "padding: 28px 28px 150px" in response.text
    assert ".marketing-page-main .store-workspace-grid" in response.text
    assert "grid-template-columns: 220px minmax(0, 1fr) 278px" in response.text
    assert "gap: 14px" in response.text
    assert ".marketing-page-main .sync-item" in response.text
    assert "grid-template-columns: 22px minmax(0, 1fr) 7px 14px" in response.text
    assert "min-height: 44px" in response.text
    assert ".marketing-page-main .rail-section" in response.text
    assert "padding: 10px 8px" in response.text
    assert ".marketing-page-main .marketing-settings" in response.text
    assert "padding: 18px 18px 20px" in response.text
    assert ".marketing-page-main .marketing-readonly-field" in response.text
    assert ".marketing-page-main .editor-pane + .editor-pane" in response.text
    assert "scroll-margin-top: 18px" in response.text
    assert "gap: 12px" in response.text
    assert ".marketing-page-main .editor-icon svg" in response.text
    assert "width: 19px" in response.text
    assert "height: 19px" in response.text
    assert ".marketing-page-main .focus-completion" in response.text
    assert "display: inline-flex" in response.text
    assert ".marketing-page-main .store-workspace-bottom" in response.text
    assert "max-width: calc(100vw - 236px)" in response.text
    assert "@media (max-width: 1180px) and (min-width: 981px)" in response.text
    assert "grid-template-columns: 220px minmax(0, 1fr)" in response.text
    assert "max-width: calc(100vw - 240px)" in response.text
    assert "@media (max-width: 980px)" in response.text
    assert "max-width: calc(100vw - 28px)" in response.text


def test_admin_store_marketing_list_matches_resource_demo_contract(
    client: TestClient,
) -> None:
    response = client.get("/static/admin/admin.css")

    assert response.status_code == 200
    assert ".store-management-nav" not in response.text
    assert ".store-management-tab" not in response.text
    assert ".store-management-page," in response.text
    assert ".store-marketing-page {" in response.text
    assert "max-width: 1320px" not in response.text
    assert "width: 100%" in response.text
    assert ".store-management-resource-layout" in response.text
    assert "grid-template-columns: 280px minmax(0, 1fr)" in response.text
    assert ".store-default-page .store-metadata-form" in response.text
    assert ".store-management-page .resource-link.active" in response.text
    assert "box-shadow: inset 0 0 0 1px #1473f8" in response.text
    assert ".store-marketing-main .table-card" in response.text
    assert ".store-marketing-table th" in response.text
    assert "background: #f8fafd" in response.text
    assert ".store-marketing-table .page-name" in response.text
    assert ".store-marketing-main .badge.warn" in response.text


def test_admin_resource_pages_render_seeded_catalog(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    pages = [
        "/admin/apps",
        "/admin/builds",
        "/admin/devices",
        "/admin/app-logs",
        "/admin/developer-accounts",
        "/admin/notifications",
        "/admin/uploads",
    ]
    for path in pages:
        response = client.get(path, headers=_admin_headers())

        _assert_admin_spa_shell(response)


def test_admin_upload_page_uses_auto_metadata_and_progress(client: TestClient) -> None:
    response = client.get("/admin/uploads", headers=_admin_headers())
    api_response = client.get("/admin/api/uploads", headers=_admin_headers())

    _assert_admin_spa_shell(response)
    assert api_response.status_code == 200
    assert "accounts" in api_response.json()


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
    assert "解析结果" in response.text
    assert "Auto Parsed" in response.text
    assert "com.example.autoparse" in response.text
    assert "4.5.6" in response.text
    assert "321" in response.text
    assert "downloadUrl" in response.text
    assert "未绑定" in response.text

    builds_response = client.get("/admin/api/builds", headers=_admin_headers())
    assert builds_response.status_code == 200
    payload = builds_response.json()
    assert any(item["app"]["name"] == "Auto Parsed" for item in payload["builds"])
    assert any(item["version"] == "4.5.6" for item in payload["builds"])


def test_admin_developer_account_detail_renders_store_sync_entry(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise",
        headers=_admin_headers(),
    )
    api_response = client.get(
        "/admin/api/developer-accounts/account-apple-enterprise",
        headers=_admin_headers(),
    )

    _assert_admin_spa_shell(response)
    assert api_response.status_code == 200
    payload = api_response.json()
    assert payload["connector"]["name"] == "Internal Store Connector"
    assert [item["name"] for item in payload["apps"]] == ["Aurora Mobile", "Insight Desk"]
    assert payload["apps"][0]["storePath"].startswith("/admin-next/accounts/")
    assert payload["apps"][0]["marketingPath"].endswith("/marketing")
    assert payload["apps"][0]["releaseNotesPath"].endswith("/release-notes")


def test_admin_can_create_and_edit_developer_account(
    client: TestClient,
    db_session: Session,
) -> None:
    new_page = client.get("/admin/developer-accounts/new", headers=_admin_headers())

    _assert_admin_spa_shell(new_page)

    create_response = client.post(
        "/admin/developer-accounts",
        headers=_admin_headers(),
        data={
            "accountId": "account-new-team",
            "teamName": "New Store Team",
            "expiresAt": "2026-12-31 23:59",
            "status": "ok",
            "renewalActionLabel": "去续费",
        },
    )

    account = db_session.get(DeveloperAccount, "account-new-team")
    assert create_response.status_code == 200
    assert "开发者账号已保存" in create_response.text
    assert account is not None
    assert account.team_name == "New Store Team"

    edit_page = client.get(
        "/admin/developer-accounts/account-new-team/edit",
        headers=_admin_headers(),
    )
    _assert_admin_spa_shell(edit_page)

    edit_response = client.post(
        "/admin/developer-accounts/account-new-team",
        headers=_admin_headers(),
        data={
            "teamName": "Renamed Store Team",
            "expiresAt": "2027-01-31 23:59",
            "status": "renewal_due",
            "renewalActionLabel": "立即续费",
        },
    )

    db_session.refresh(account)
    assert edit_response.status_code == 200
    assert "开发者账号已更新" in edit_response.text
    assert account.team_name == "Renamed Store Team"
    assert account.status == "renewal_due"
    assert account.renewal_action_label == "立即续费"


def test_admin_upload_can_bind_package_to_developer_account(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/uploads",
        headers=_admin_headers(),
        data={
            "platform": "android",
            "environment": "development",
            "developerAccountId": "account-apple-enterprise",
            "changelog": "绑定账号上传",
        },
        files={
            "file": (
                "admin.apk",
                make_android_apk_bytes(),
                "application/vnd.android.package-archive",
            )
        },
    )

    app = db_session.query(App).filter_by(bundle_identifier="com.example.autoparse").one()
    assert response.status_code == 200
    assert "Internal Distribution Team" in response.text
    assert "商店标识" in response.text
    assert app.developer_account_id == "account-apple-enterprise"
    assert app.store_package_name == "com.example.autoparse"


def test_admin_account_detail_can_bind_update_and_unbind_app(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    upload_response = client.post(
        "/admin/uploads",
        headers=_admin_headers(),
        data={
            "platform": "android",
            "environment": "development",
            "changelog": "待绑定 App",
        },
        files={
            "file": (
                "admin.apk",
                make_android_apk_bytes(),
                "application/vnd.android.package-archive",
            )
        },
    )
    assert upload_response.status_code == 200
    uploaded_app = db_session.query(App).filter_by(bundle_identifier="com.example.autoparse").one()
    app_id = uploaded_app.id

    bind_response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/apps",
        headers=_admin_headers(),
        data={
            "appId": app_id,
            "storeAppId": "",
            "storePackageName": "com.example.autoparse",
        },
    )

    db_session.expire_all()
    app = db_session.get(App, app_id)
    assert bind_response.status_code == 200
    assert "App 已绑定到账号" in bind_response.text
    assert app is not None
    assert app.developer_account_id == "account-apple-enterprise"

    settings_response = client.post(
        f"/admin/developer-accounts/account-apple-enterprise/apps/{app_id}/settings",
        headers=_admin_headers(),
        data={
            "storePackageName": "com.example.autoparse.store",
        },
    )
    db_session.expire_all()
    app = db_session.get(App, app_id)
    assert app is not None
    assert settings_response.status_code == 200
    assert "商店标识已保存" in settings_response.text
    assert app.store_app_id is None
    assert app.store_package_name == "com.example.autoparse.store"

    unbind_response = client.post(
        f"/admin/developer-accounts/account-apple-enterprise/apps/{app_id}/unbind",
        headers=_admin_headers(),
    )
    db_session.expire_all()
    app = db_session.get(App, app_id)
    assert app is not None
    assert unbind_response.status_code == 200
    assert "App 已解绑" in unbind_response.text
    assert app.developer_account_id is None
    assert app.store_app_id is None


def test_admin_rejects_store_identifier_for_wrong_platform(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    ios_response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/apps/app-aurora-ios/settings",
        headers=_admin_headers(),
        data={
            "storePackageName": "com.example.ios.invalid",
        },
    )
    android_upload = client.post(
        "/admin/uploads",
        headers=_admin_headers(),
        data={
            "platform": "android",
            "environment": "development",
            "changelog": "待绑定 App",
        },
        files={
            "file": (
                "admin.apk",
                make_android_apk_bytes(),
                "application/vnd.android.package-archive",
            )
        },
    )
    android_app = db_session.query(App).filter_by(bundle_identifier="com.example.autoparse").one()
    android_bind_response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/apps",
        headers=_admin_headers(),
        data={
            "appId": android_app.id,
            "storeAppId": "1234567890",
        },
    )

    assert android_upload.status_code == 200
    assert ios_response.status_code == 422
    assert "iOS App 只能填写 App Store Connect App ID" in ios_response.text
    assert android_bind_response.status_code == 422
    assert "Android App 只能填写 Google Play package name" in android_bind_response.text


def test_admin_can_update_connector_settings(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector",
        headers=_admin_headers(),
        data={
            "name": "Account A Connector",
            "baseUrl": "http://connector-a:8100",
            "authToken": "new-token",
        },
    )

    assert response.status_code == 200
    assert "Connector 已保存" in response.text
    assert "Account A Connector" in response.text
    assert "http://connector-a:8100" in response.text
    assert db_session.query(StoreConnector).count() == 1


def test_admin_account_detail_auto_checks_connector(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    connector = db_session.query(StoreConnector).one()
    connector.status = "unknown"
    connector.last_checked_at = None
    db_session.commit()

    response = client.get(
        "/admin/api/developer-accounts/account-apple-enterprise",
        headers=_admin_headers(),
    )

    db_session.refresh(connector)
    assert response.status_code == 200
    assert response.json()["connector"]["status"] == "ok"
    assert connector.status == "ok"
    assert connector.last_checked_at is not None


def test_admin_account_detail_reuses_recent_connector_check(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    connector = db_session.query(StoreConnector).one()
    connector.status = "error"
    connector.last_checked_at = datetime.now(UTC)
    db_session.commit()

    response = client.get(
        "/admin/api/developer-accounts/account-apple-enterprise",
        headers=_admin_headers(),
    )

    db_session.refresh(connector)
    assert response.status_code == 200
    assert response.json()["connector"]["status"] == "error"
    assert connector.status == "error"


def test_admin_can_check_connector_manually(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    connector = db_session.query(StoreConnector).one()
    connector.status = "unknown"
    connector.last_checked_at = None
    db_session.commit()

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector/check",
        headers=_admin_headers(),
    )

    db_session.refresh(connector)
    assert response.status_code == 200
    assert "Connector 连接正常" in response.text
    assert "data-connector-check-result" in response.text
    assert "connector-inline-status success" in response.text
    assert "alert success" not in response.text
    assert connector.status == "ok"
    assert connector.last_checked_at is not None


def test_admin_can_generate_connector_url_from_account_template(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    db_session.query(StoreConnector).delete()
    db_session.commit()
    client.app.state.settings = replace(
        client.app.state.settings,
        connector_base_url_template="http://connector-{account_id}:8100",
    )

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector",
        headers=_admin_headers(),
        data={
            "name": "Generated Connector",
            "baseUrl": "",
            "authToken": "new-token",
        },
    )

    db_session.expire_all()
    connector = db_session.query(StoreConnector).one()
    expected_base_url = "http://connector-account-apple-enterprise:8100"
    assert response.status_code == 200
    assert "Connector 已保存" in response.text
    assert connector.base_url == expected_base_url
    assert expected_base_url in response.text


def test_admin_can_generate_windows_active_connector_package(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector/windows-package",
        headers=_admin_headers(),
        data={
            "appleIssuerId": "issuer-123",
            "appleKeyId": "",
        },
        files={
            "applePrivateKey": (
                "AuthKey_ABC123.p8",
                b"-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----",
                "application/octet-stream",
            ),
        },
    )

    connector = db_session.query(StoreConnector).one()
    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        config = json.loads(archive.read("config.json").decode("utf-8"))
        install_script = archive.read("install.ps1").decode("utf-8")
        update_script = archive.read("update.ps1").decode("utf-8")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "config.json" in names
    assert "install.ps1" in names
    assert "update.ps1" in names
    assert "README.txt" in names
    assert "secrets/apple/AuthKey_ABC123.p8" in names
    assert config["accountId"] == "account-apple-enterprise"
    assert config["storeMode"] == "live"
    assert config["centerUrl"] == "https://dist.example.test"
    assert config["apple"]["issuerId"] == "issuer-123"
    assert config["apple"]["keyId"] == "ABC123"
    assert connector.base_url == "active://account-apple-enterprise"
    assert connector.auth_token == config["connectorToken"]
    assert "TESTFLYING_CONNECTOR_CONFIG_PATH" in install_script
    stopped_run_script = (
        '`$ErrorActionPreference = "Stop"\n`$env:TESTFLYING_CONNECTOR_CONFIG_PATH'
    )
    assert stopped_run_script not in install_script
    assert "exit `$LASTEXITCODE" in install_script
    assert "schtasks.exe /Query" in install_script
    assert "System32\\WindowsPowerShell\\v1.0\\powershell.exe" in install_script
    assert "Failed to create scheduled task" in install_script
    assert "Failed to start scheduled task" in install_script
    assert "testflying-connector-updater" in update_script
    assert "testflying-connector-windows-amd64-*.zip" in update_script
    assert "$InstalledUpdater = \"$Root\\update.ps1\"" in update_script
    assert "Copy-Item -Force $MyInvocation.MyCommand.Path $InstalledUpdater" in update_script
    assert "Copy-Item -Force $Exe.FullName $CurrentExe" in update_script
    assert "config.json" in update_script
    assert 'Copy-Item -Force "$PSScriptRoot\\config.json"' not in update_script
    assert "secrets" not in update_script
    install_script.encode("ascii")
    update_script.encode("ascii")


def test_admin_can_generate_windows_active_connector_package_without_store_credentials(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector/windows-package",
        headers=_admin_headers(),
        data={},
    )

    connector = db_session.query(StoreConnector).one()
    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        config = json.loads(archive.read("config.json").decode("utf-8"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "config.json" in names
    assert "install.ps1" in names
    assert "update.ps1" in names
    assert "README.txt" in names
    assert not any(name.startswith("secrets/apple/") for name in names)
    assert not any(name.startswith("secrets/google/") for name in names)
    assert config["accountId"] == "account-apple-enterprise"
    assert config["storeMode"] == "live"
    assert config["centerUrl"] == "https://dist.example.test"
    assert "apple" not in config
    assert "google" not in config
    assert connector.base_url == "active://account-apple-enterprise"
    assert connector.auth_token == config["connectorToken"]


def test_admin_windows_active_connector_package_can_include_google_credentials(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector/windows-package",
        headers=_admin_headers(),
        data={
            "appleIssuerId": "issuer-123",
            "appleKeyId": "",
        },
        files=[
            (
                "applePrivateKey",
                (
                    "AuthKey_ABC123.p8",
                    b"-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----",
                    "application/octet-stream",
                ),
            ),
            (
                "googleServiceAccount",
                (
                    "service-account.json",
                    b'{"client_email":"robot@example.test","private_key":"key"}',
                    "application/json",
                ),
            ),
        ],
    )

    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        config = json.loads(archive.read("config.json").decode("utf-8"))

    assert response.status_code == 200
    assert "secrets/apple/AuthKey_ABC123.p8" in names
    assert "secrets/google/service-account.json" in names
    assert config["apple"]["issuerId"] == "issuer-123"
    assert config["apple"]["keyId"] == "ABC123"
    assert config["google"]["serviceAccountJsonPath"].endswith(
        r"\secrets\google\service-account.json"
    )


def test_admin_windows_active_connector_package_accepts_google_json_text(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector/windows-package",
        headers=_admin_headers(),
        data={
            "googleServiceAccountJson": json.dumps(
                {
                    "type": "service_account",
                    "client_email": "robot@example.test",
                    "private_key": "key",
                }
            ),
        },
    )

    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        config = json.loads(archive.read("config.json").decode("utf-8"))
        google_secret = json.loads(
            archive.read("secrets/google/service-account.json").decode("utf-8")
        )

    assert response.status_code == 200
    assert "secrets/google/service-account.json" in names
    assert config["google"]["serviceAccountJsonPath"].endswith(
        r"\secrets\google\service-account.json"
    )
    assert google_secret["client_email"] == "robot@example.test"


def test_admin_windows_active_connector_package_accepts_split_google_credentials(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector/windows-package",
        headers=_admin_headers(),
        data={
            "googleClientEmail": "robot@example.test",
            "googlePrivateKey": (
                "-----BEGIN PRIVATE KEY-----\\n"
                "key-content\\n"
                "-----END PRIVATE KEY-----"
            ),
        },
    )

    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        config = json.loads(archive.read("config.json").decode("utf-8"))
        google_secret = json.loads(
            archive.read("secrets/google/service-account.json").decode("utf-8")
        )

    assert response.status_code == 200
    assert "secrets/google/service-account.json" in names
    assert config["google"]["serviceAccountJsonPath"].endswith(
        r"\secrets\google\service-account.json"
    )
    assert google_secret["client_email"] == "robot@example.test"
    assert google_secret["private_key"] == (
        "-----BEGIN PRIVATE KEY-----\n"
        "key-content\n"
        "-----END PRIVATE KEY-----"
    )
    assert google_secret["token_uri"] == "https://oauth2.googleapis.com/token"


def test_admin_windows_active_connector_package_rejects_partial_google_split_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise/connector/windows-package",
        headers=_admin_headers(),
        data={
            "googlePrivateKey": "-----BEGIN PRIVATE KEY-----\nkey\n-----END PRIVATE KEY-----",
        },
    )

    assert response.status_code == 422
    assert "Google Play 拆分凭据需要同时填写 client_email 和 private_key" in response.text


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_release_notes_page_runs_cached_preflight(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    path = (
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/release-notes"
    )
    first_response = client.get(path, headers=_admin_headers())
    second_response = client.get(path, headers=_admin_headers())

    checks = db_session.query(StorePreflightCheck).all()
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert "商店状态正常" in first_response.text
    assert "商店版本已创建且允许修改，可以同步到商店。" in first_response.text
    assert "5 分钟缓存" in first_response.text
    assert "缓存" in second_response.text
    assert len(checks) == 1


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_preflight_uses_friendly_blocked_copy(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/release-notes?version=missing-2.4.0",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert "商店版本还没有创建" in response.text
    assert "testflying 后台构建可以存在，但商店后台还没有对应版本" in response.text
    assert "请先在 App Store Connect 创建这个商店版本" in response.text
    assert "store_version_missing" in response.text
    assert "商店中还没有创建 missing-2.4.0" not in response.text


def test_admin_release_notes_save_uses_target_version(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/release-notes",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "locale": "en-US",
            "releaseNotes": "Fix known issues.",
        },
    )

    draft = db_session.query(StoreReleaseNoteDraft).one()
    assert response.status_code == 200
    assert draft.version == "2.4.0"
    assert draft.version != CURRENT_METADATA_VERSION
    assert draft.release_notes == "Fix known issues."


def test_admin_release_notes_save_and_sync_creates_records(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    path = (
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/release-notes/sync"
    )
    response = client.post(
        path,
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "syncScopes": ["metadata"],
            "locale": "zh-Hans",
            "releaseNotes": "修复已知问题，优化安装体验。",
        },
    )

    draft = db_session.query(StoreReleaseNoteDraft).one()
    run = db_session.query(StoreSyncRun).one()
    assert response.status_code == 200
    assert "版本说明已同步" in response.text
    assert draft.release_notes == "修复已知问题，优化安装体验。"
    assert run.status == "succeeded"


def test_admin_store_metadata_save_and_sync_creates_records(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    path = (
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/sync"
    )
    response = client.post(
        path,
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "syncScopes": ["metadata"],
            "locale": "zh-Hans",
            "locales": ["zh-Hans", "en-US", "ja", "ko"],
            "keywords": ["internal,test", "", "internal,ja", "internal,ko"],
            "promotionalText": [
                "更稳定的测试体验。",
                "",
                "より安定したテスト体験。",
                "더 안정적인 테스트 경험.",
            ],
            "description": [
                "用于内部测试包分发和回归验证。",
                "",
                "内部テスト配布と回帰検証に使います。",
                "내부 테스트 배포와 회귀 검증에 사용합니다.",
            ],
            "featureGraphicUrl": ["https://cdn.example.test/feature.png", "", "", ""],
            "phoneScreenshots": [
                "https://cdn.example.test/phone-1.png\nhttps://cdn.example.test/phone-2.png",
                "",
                "https://cdn.example.test/ja-phone.png",
                "",
            ],
            "tabletScreenshots": ["https://cdn.example.test/tablet.png", "", "", ""],
        },
    )

    drafts = db_session.query(StoreAppMetadataDraft).order_by(StoreAppMetadataDraft.locale).all()
    runs = db_session.query(StoreSyncRun).order_by(StoreSyncRun.started_at.asc()).all()
    assert response.status_code == 200
    assert "商店元数据已同步 4 个语言" in response.text
    assert {draft.locale for draft in drafts} == {"zh-Hans", "en-US", "ja", "ko"}
    zh_hans_draft = next(draft for draft in drafts if draft.locale == "zh-Hans")
    en_us_draft = next(draft for draft in drafts if draft.locale == "en-US")
    assert zh_hans_draft.title == "Aurora Mobile"
    assert zh_hans_draft.version == CURRENT_METADATA_VERSION
    assert zh_hans_draft.subtitle == ""
    assert zh_hans_draft.description == "用于内部测试包分发和回归验证。"
    assert en_us_draft.keywords == ""
    assert en_us_draft.promotional_text == "更稳定的测试体验。"
    assert en_us_draft.description == "用于内部测试包分发和回归验证。"
    assert zh_hans_draft.content_set_id == "default"
    assert zh_hans_draft.content_set_name == "默认上架内容"
    assert "app_icon_url" not in zh_hans_draft.store_images_json
    assert zh_hans_draft.store_images_json["phone_screenshots"]["urls"] == [
        "https://cdn.example.test/phone-1.png",
        "https://cdn.example.test/phone-2.png",
    ]
    assert en_us_draft.store_images_json["feature_graphic_url"]["urls"] == [
        "https://cdn.example.test/feature.png"
    ]
    assert "note" not in en_us_draft.store_images_json
    assert [run.operation for run in runs[-4:]] == ["update_app_metadata"] * 4
    assert {run.locale for run in runs[-4:]} == {"zh-Hans", "en-US", "ja", "ko"}
    assert {run.status for run in runs[-4:]} == {"succeeded"}
    assert all(run.sync_scopes_json == {"scopes": ["metadata"]} for run in runs[-4:])
    assert all(run.payload_snapshot_json.get("metadata") for run in runs[-4:])


def test_admin_store_metadata_sync_requires_selected_scope(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/sync",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "locale": "en-US",
            "locales": ["en-US"],
            "keywords": ["internal,test"],
            "promotionalText": ["Faster internal installs."],
            "description": ["Internal distribution metadata for testing installs."],
            "featureGraphicUrl": [""],
            "phoneScreenshots": [""],
            "tabletScreenshots": [""],
        },
    )

    assert response.status_code == 422
    assert "请至少勾选一个要同步的内容" in response.text
    assert db_session.query(StoreAppMetadataDraft).count() == 0
    assert db_session.query(StoreSyncRun).count() == 0


def test_admin_store_metadata_sync_can_send_store_images_without_copy_payload(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/sync",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "syncScopes": ["store_images"],
            "locale": "en-US",
            "locales": ["en-US"],
            "keywords": ["internal,test"],
            "promotionalText": ["Faster internal installs."],
            "description": ["Internal distribution metadata for testing installs."],
            "featureGraphicUrl": [""],
            "phoneScreenshots": ["https://cdn.example.test/phone-1.png"],
            "tabletScreenshots": [""],
        },
    )

    run = db_session.query(StoreSyncRun).one()
    payload_metadata = run.payload_snapshot_json["metadata"]
    assert response.status_code == 200
    assert "已同步 1 个任务" in response.text
    assert run.sync_scopes_json == {"scopes": ["store_images"]}
    assert "storeImages" in payload_metadata
    assert payload_metadata["storeImages"]["phone_screenshots"]["urls"] == [
        "https://cdn.example.test/phone-1.png"
    ]
    assert "keywords" not in payload_metadata
    assert "promotionalText" not in payload_metadata
    assert "description" not in payload_metadata


def test_admin_store_metadata_sync_rejects_too_short_description(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/sync",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "syncScopes": ["metadata"],
            "locale": "en-US",
            "locales": ["en-US"],
            "keywords": ["internal,test"],
            "promotionalText": ["Faster internal installs."],
            "description": ["fix bugs"],
            "featureGraphicUrl": [""],
            "phoneScreenshots": [""],
            "tabletScreenshots": [""],
        },
    )

    assert response.status_code == 422
    assert "en-US 的 Description（描述） 太短" in response.text
    assert "至少需要 10 个字符，当前 8 个字符" in response.text
    assert db_session.query(StoreAppMetadataDraft).count() == 0
    assert db_session.query(StoreSyncRun).count() == 0


def test_admin_store_metadata_sync_ignores_submitted_keywords(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/sync",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "syncScopes": ["metadata"],
            "locale": "en-US",
            "locales": ["en-US"],
            "keywords": ["x" * 101],
            "promotionalText": ["Faster internal installs."],
            "description": [
                "Internal distribution metadata for testing installs before release."
            ],
            "featureGraphicUrl": [""],
            "phoneScreenshots": [""],
            "tabletScreenshots": [""],
        },
    )

    draft = db_session.query(StoreAppMetadataDraft).one()
    run = db_session.query(StoreSyncRun).one()
    assert response.status_code == 200
    assert draft.keywords == ""
    assert "keywords" not in run.payload_snapshot_json["metadata"]


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_store_metadata_uploads_store_images_into_content_set(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    path = (
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata"
    )
    response = client.post(
        path,
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "locale": "en-US",
            "contentSetId": "summer-launch",
            "contentSetName": "暑期活动投放",
            "locales": ["en-US"],
            "keywords": ["internal,test"],
            "promotionalText": [""],
            "description": ["Internal app distribution testing."],
            "featureGraphicUrl": [""],
            "phoneScreenshots": [""],
            "tabletScreenshots": [""],
        },
        files=[
            (
                "storeImageFiles__phone_screenshots__en-US",
                ("phone-1.png", make_png_header_bytes(1290, 2796), "image/png"),
            ),
            (
                "storeImageFiles__phone_screenshots__en-US",
                ("phone-2.png", make_png_header_bytes(1320, 2868), "image/png"),
            ),
        ],
    )

    draft = db_session.query(StoreAppMetadataDraft).one()
    phone_assets = draft.store_images_json["phone_screenshots"]["assets"]
    assert response.status_code == 200
    assert "商店元数据草稿已保存 1 个语言" in response.text
    assert "暑期活动投放" not in response.text
    assert draft.version == CURRENT_METADATA_VERSION
    assert draft.content_set_id == "default"
    assert draft.content_set_name == "默认上架内容"
    assert "app_icon_url" not in draft.store_images_json
    assert [asset["fileName"] for asset in phone_assets] == ["phone-1.png", "phone-2.png"]

    page = client.get(
        path + "?version=2.4.0&content_set_id=summer-launch",
        headers=_admin_headers(),
    )
    assert page.status_code == 200
    assert "当前商店内容" not in page.text
    assert "phone-1.png" in page.text
    assert "data-store-image-preview-image" in page.text
    assert 'src="/admin/artifacts/store-assets/' in page.text
    assert 'name="storeImageDelete"' in page.text
    assert "https://dist.example.test/artifacts/store-assets/" not in page.text
    assert 'data-width="1290"' in page.text
    assert 'data-height="2796"' in page.text
    assert "style=\"aspect-ratio:" in page.text
    assert "1290 x 2796" in page.text

    proxy_response = client.get(
        f"/admin/artifacts/{phone_assets[0]['storageKey']}",
        headers=_admin_headers(),
    )
    assert proxy_response.status_code == 200
    assert proxy_response.headers["content-type"] == "image/png"
    assert proxy_response.content.startswith(b"\x89PNG")

    delete_response = client.post(
        path + "/store-images/delete",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "locale": "en-US",
            "contentSetId": "summer-launch",
            "storeImageDelete": json.dumps(
                {
                    "locale": "en-US",
                    "slot": "phone_screenshots",
                    "storageKey": phone_assets[0]["storageKey"],
                }
            ),
        },
    )

    db_session.expire_all()
    updated_draft = db_session.query(StoreAppMetadataDraft).one()
    updated_draft_assets = updated_draft.store_images_json["phone_screenshots"]["assets"]
    assert delete_response.status_code == 200
    assert "已删除中心后台的商店图" in delete_response.text
    assert [asset["fileName"] for asset in updated_draft_assets] == ["phone-2.png"]
    assert db_session.query(StoreImageSuiteLocale).count() == 0
    assert phone_assets[0]["storageKey"] not in delete_response.text
    assert "phone-1.png" not in delete_response.text
    assert "phone-2.png" in delete_response.text
    deleted_proxy_response = client.get(
        f"/admin/artifacts/{phone_assets[0]['storageKey']}",
        headers=_admin_headers(),
    )
    assert deleted_proxy_response.status_code == 404


def test_admin_store_metadata_rejects_invalid_store_image_dimensions(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "locale": "en-US",
            "contentSetId": "summer-launch",
            "contentSetName": "暑期活动投放",
            "locales": ["en-US"],
            "keywords": ["internal,test"],
            "promotionalText": [""],
            "description": ["Internal app distribution testing."],
            "featureGraphicUrl": [""],
            "phoneScreenshots": [""],
            "tabletScreenshots": [""],
        },
        files=[
            (
                "storeImageFiles__phone_screenshots__en-US",
                ("bad-phone.png", make_png_header_bytes(1080, 2400), "image/png"),
            ),
        ],
    )

    assert response.status_code == 422
    assert "Apple 要求精确尺寸" in response.text
    assert db_session.query(StoreAppMetadataDraft).count() == 0


def test_admin_store_metadata_content_set_creation_persists(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    path = (
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata"
    )
    response = client.post(
        path + "/content-sets",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "locale": "en-US",
            "contentSetId": "holiday-copy",
            "contentSetName": "节日投放",
            "locales": ["en-US", "zh-Hant"],
            "keywords": ["internal,test", ""],
            "promotionalText": ["Faster internal installs.", ""],
            "description": ["Internal distribution metadata.", ""],
            "featureGraphicUrl": ["", ""],
            "phoneScreenshots": ["https://cdn.example.test/phone.png", ""],
            "tabletScreenshots": ["", ""],
        },
    )

    suites = db_session.query(StoreImageSuite).all()
    suite_locales = (
        db_session.query(StoreImageSuiteLocale).order_by(StoreImageSuiteLocale.locale).all()
    )
    assert response.status_code == 200
    assert response.json()["id"] == "holiday-copy"
    assert response.json()["name"] == "节日投放"
    assert db_session.query(StoreAppMetadataDraft).count() == 0
    assert db_session.query(StoreReleaseNoteDraft).count() == 0
    assert len(suites) == 1
    assert suites[0].suite_id == "holiday-copy"
    assert suites[0].suite_name == "节日投放"
    assert {item.locale for item in suite_locales} == {"en-US", "zh-Hant"}
    zh_hant = next(item for item in suite_locales if item.locale == "zh-Hant")
    assert zh_hant.store_images_json["phone_screenshots"]["urls"] == [
        "https://cdn.example.test/phone.png"
    ]

    page = client.get(
        path + "?content_set_id=holiday-copy",
        headers=_admin_headers(),
    )
    assert page.status_code == 200
    assert "节日投放" not in page.text
    assert "holiday-copy" not in page.text
    assert "商店图套件库" not in page.text


def test_admin_store_metadata_content_set_creation_allows_empty_metadata(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/content-sets",
        headers=_admin_headers(),
        data={
            "version": "2.4.0",
            "locale": "en-US",
            "contentSetId": "blank-image-suite",
            "contentSetName": "空白商店图套件",
            "locales": ["en-US"],
            "keywords": [""],
            "promotionalText": [""],
            "description": [""],
            "releaseNotes": [""],
            "featureGraphicUrl": [""],
            "phoneScreenshots": [""],
            "tabletScreenshots": [""],
        },
    )

    assert response.status_code == 200
    assert response.json()["id"] == "blank-image-suite"
    assert response.json()["name"] == "空白商店图套件"
    assert db_session.query(StoreAppMetadataDraft).count() == 0
    assert db_session.query(StoreReleaseNoteDraft).count() == 0
    suite = db_session.query(StoreImageSuite).one()
    suite_locale = db_session.query(StoreImageSuiteLocale).one()
    assert suite.suite_id == "blank-image-suite"
    assert suite_locale.locale == "en-US"


def test_admin_store_metadata_translation_requires_configured_provider(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/translations",
        headers=_admin_headers(),
        json={
            "field": "description",
            "sourceLocale": "en-US",
            "targetLocales": ["zh-Hant"],
            "text": "Internal distribution metadata.",
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "translation_not_configured"
    assert "翻译服务未配置" in response.json()["message"]


def test_admin_store_metadata_translation_returns_generated_locales(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    client.app.state.settings = replace(
        client.app.state.settings,
        translation_provider="mock",
    )

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/translations",
        headers=_admin_headers(),
        json={
            "field": "description",
            "sourceLocale": "en-US",
            "targetLocales": ["zh-Hant", "fr-FR", "en-US"],
            "text": "Internal distribution metadata.",
        },
    )

    assert response.status_code == 200
    assert response.json()["translations"] == {
        "zh-Hant": "Internal distribution metadata. [zh-Hant]",
        "fr-FR": "Internal distribution metadata. [fr-FR]",
    }


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_store_metadata_page_lists_supported_locales(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert 'name="locales" value="zh-Hans"' in response.text
    assert 'name="locales" value="en-US"' in response.text
    assert 'name="locales" value="ja"' in response.text
    assert 'name="locales" value="ko"' in response.text
    assert "源文案语言" in response.text
    assert 'value="en-US" required readonly' in response.text
    assert "全部语言对照" not in response.text
    assert "单语言编辑" not in response.text
    assert "data-language-view" not in response.text
    assert "翻译所有文案项" in response.text
    assert "requestMetadataTranslation" in response.text
    assert "syncMetadataWorkspace" in response.text
    assert "data-store-metadata-sync-submit" in response.text
    assert "data-store-sync-confirm" in response.text
    assert "buildStoreSyncPlan" in response.text
    assert "确认目标版本、语言和勾选的同步内容" in response.text
    assert "未接入翻译服务前" not in response.text
    assert "当前商店内容" not in response.text
    assert "同步历史" not in response.text
    assert "data-store-section-tab" not in response.text
    assert "data-store-section-panel" not in response.text
    assert "data-store-section-jump" not in response.text
    assert "营销页面控制台" not in response.text
    assert "/store/marketing" in response.text
    assert (
        "/developer-accounts/account-apple-enterprise/apps/app-aurora-ios/store/connection"
        in response.text
    )
    assert 'href="/admin/developer-accounts/account-apple-enterprise"' not in response.text
    assert "section=history" not in response.text
    assert "sync-scope-card" not in response.text
    assert "同步到商店前会打开确认清单" in response.text
    assert "同步范围只在确认弹窗里选择" in response.text
    assert "新建套件" not in response.text
    assert "复制当前套" not in response.text
    assert "商店图套件库" not in response.text
    assert "store-management-page store-default-page" in response.text
    assert (
        "resource-layout store-management-resource-layout store-default-resource-layout"
        in response.text
    )
    assert (
        'class="resource-link active" href="/admin/developer-accounts/'
        'account-apple-enterprise/apps/app-aurora-ios/store" aria-current="page"'
        in response.text
    )
    assert "setSection(document" not in response.text
    assert "store-management-nav" not in response.text
    assert "store-management-tab" not in response.text
    assert "card toolbar" in response.text
    assert "workspace" in response.text
    assert "main-input" in response.text
    assert "data-current-metadata-editor" in response.text
    assert "card rail" in response.text
    assert "data-sync-item-select" in response.text
    assert "data-sync-item-panel" in response.text
    assert "class=\"side\"" in response.text
    assert "class=\"checks\"" in response.text
    assert "class=\"check" in response.text
    assert "按版本和同步时间保存快照" not in response.text
    assert "class=\"card rail\"" in response.text
    assert "class=\"sync-item" in response.text
    assert "class=\"card editor\"" in response.text
    assert "class=\"locale-row\"" in response.text
    assert "class=\"image-locale-row store-image-locale-row\"" in response.text
    assert "商店图" in response.text
    assert "App Store Connect 默认商店页" in response.text
    assert 'data-sync-item-key="keywords"' not in response.text
    assert 'data-field="keywords"' not in response.text
    assert 'name="keywords"' not in response.text
    assert "宣传文本" in response.text
    assert "描述" in response.text
    assert "data-translate-field" in response.text
    assert "data-translate-store-image" in response.text
    assert "replaceContentSetUrl" in response.text
    assert "批量上传手机截图" in response.text
    assert "批量上传平板截图" in response.text
    assert "标题" not in response.text
    assert "副标题" not in response.text
    assert "隐私政策 URL" not in response.text
    assert "支持 URL" not in response.text
    assert "营销 URL" not in response.text
    assert "App 图标" not in response.text
    assert "素材备注" not in response.text
    assert "手机截图" in response.text
    assert "平板截图" in response.text
    assert "Feature graphic（功能宣传图）" not in response.text
    assert "Google Play Console 同步" not in response.text
    assert "storeImageFiles__feature_graphic" not in response.text
    assert "data-store-image-input" in response.text
    assert "data-store-image-zone" in response.text
    assert "data-store-image-track" in response.text
    assert "store-image-add-card" in response.text
    assert "data-store-image-requirement" in response.text
    assert "data-store-image-validation" in response.text
    assert "data-store-image-preview-all" in response.text
    assert "data-store-image-lightbox" in response.text
    assert "openStoreImageLightbox" in response.text
    assert "closeStoreImageLightbox" in response.text
    assert "readStoreImageDimensions" in response.text
    assert "validateStoreImageInspection" in response.text
    assert "filterValidStoreImageFiles" in response.text
    assert "图片未通过校验，已拒绝添加" in response.text
    assert "messageNode.title = message || ''" in response.text
    assert "Apple 要求精确尺寸" in response.text
    assert re.search(
        r'name="storeImageFiles__phone_screenshots__en-US"[^>]*multiple',
        response.text,
        re.DOTALL,
    )
    assert re.search(
        r'name="storeImageFiles__tablet_screenshots__en-US"[^>]*multiple',
        response.text,
        re.DOTALL,
    )
    assert "snapshotStoreImageFiles(input)" in response.text
    assert "appendStoreImageFiles(input, validFiles" in response.text
    assert "uniqueStoreImageFiles([...existing, ...files])" in response.text
    assert "data-store-image-bulk-drop" in response.text
    assert "展开所有语言" in response.text
    assert "row.hidden = isMarketingWorkspace && !groupExpanded && !isActiveLocale" in response.text
    assert "row.dataset.expanded = expanded ? 'true' : 'false'" in response.text
    assert "toggle.addEventListener('click'" in response.text
    assert "toggle.dataset.localeToggleBound = 'true'" in response.text
    assert "event.stopPropagation()" in response.text
    assert "syncMetadataEditor(form)" in response.text
    assert "label.textContent = groupExpanded ? '收起多语言' : '展开所有语言'" in response.text
    assert "panel.hidden = isMarketingWorkspace ? false : !isSelected" in response.text
    assert "scrollIntoView({" in response.text
    assert "form.dataset.storeWorkspaceMode === 'marketing'" in response.text
    assert "function toggleLocaleRow(row)" in response.text
    assert "const localeRow = event.target.closest('[data-locale-row]')" in response.text
    assert "row.dataset.rowExpanded = expanded ? 'true' : 'false'" in response.text
    assert "data-locale-detail-input" in response.text
    assert 'data-locale="zh-Hans" data-locale-row' in response.text
    assert 'data-locale="en-US" data-locale-row' in response.text
    assert response.text.index("商店图") < response.text.index("data-store-image-bulk-drop")
    assert "商店版本" in response.text
    assert "内容范围" not in response.text
    assert "文案、链接、商店图" not in response.text


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_store_metadata_shows_backfilled_keywords_readonly(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    db_session.add(
        StoreAppMetadataDraft(
            id="metadata-backfilled-keywords",
            developer_account_id="account-apple-enterprise",
            app_id="app-aurora-ios",
            platform="ios",
            version=CURRENT_METADATA_VERSION,
            locale="en-US",
            content_set_id="default",
            content_set_name="默认上架内容",
            keywords="reader,books,stories",
            promotional_text="Read stories anywhere.",
            description="Internal distribution metadata for testing installs.",
            store_images_json={},
        )
    )
    db_session.commit()

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata?locale=en-US",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert "store-readonly-keywords" in response.text
    assert "reader,books,stories" in response.text
    assert 'name="keywords"' not in response.text


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_store_connection_page_stays_in_store_workspace(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store/connection",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert "商店管理" in response.text
    assert "App Store Connect 商店连接" in response.text
    assert "Connector、语言、版本检查" in response.text
    assert (
        'class="resource-link active" href="/admin/developer-accounts/'
        'account-apple-enterprise/apps/app-aurora-ios/store/connection" aria-current="page"'
        in response.text
    )
    assert (
        'action="/admin/developer-accounts/account-apple-enterprise/apps/'
        'app-aurora-ios/store/connection/check"'
        in response.text
    )
    assert 'href="/admin/developer-accounts/account-apple-enterprise#connector"' in response.text
    assert "Internal Store Connector" in response.text
    assert "商店语言" in response.text


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_store_marketing_page_lists_marketing_pages(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store/marketing-pages",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "marketingPageType": "custom_product_page",
            "marketingPageName": "冷启动投放页",
            "locales": ["en-US", "zh-Hant"],
            "promotionalText": ["Read stories anytime.", "隨時閱讀故事。"],
            "phoneScreenshots": ["", ""],
            "tabletScreenshots": ["", ""],
        },
    )

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store/marketing",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert "商店管理" in response.text
    assert "默认商店页" in response.text
    assert "营销页面" in response.text
    assert "冷启动投放页" in response.text
    assert "自定义产品页面" in response.text
    assert "resource-layout store-management-resource-layout" in response.text
    assert "table-card store-marketing-table-card" in response.text
    assert "新建产品页面优化" not in response.text
    assert 'name="marketingPageType" value="product_page_optimization"' not in response.text
    assert "新建自定义产品页面" in response.text
    assert "data-marketing-page-row" in response.text
    assert 'role="link"' in response.text
    assert "2 语言 / 0 张图" in response.text
    assert "未同步后回填" in response.text
    assert "营销页面控制台" not in response.text
    assert "store-management-nav" not in response.text
    assert "section=history" not in response.text
    assert "同步历史" not in response.text
    assert (
        "/developer-accounts/account-apple-enterprise/apps/app-aurora-ios/store/connection"
        in response.text
    )
    assert "store-marketing-side" not in response.text
    assert "/store/marketing-pages/" in response.text


def test_admin_store_metadata_can_create_marketing_page(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store/marketing-pages",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "marketingPageType": "product_page_optimization",
            "marketingPageName": "新用户转化页",
            "locales": ["en-US", "zh-Hant"],
            "promotionalText": ["Read stories anytime.", ""],
            "phoneScreenshots": ["", ""],
            "tabletScreenshots": ["", ""],
        },
        files=[
            (
                "storeImageFiles__phone_screenshots__en-US",
                ("iphone-69.png", make_png_header_bytes(1290, 2796), "image/png"),
            )
        ],
    )

    page = db_session.query(StoreMarketingPage).one()
    locales = (
        db_session.query(StoreMarketingPageLocale)
        .order_by(StoreMarketingPageLocale.locale)
        .all()
    )
    assert response.status_code == 200
    assert "营销页面已创建" in response.text
    assert "新用户转化页" in response.text
    assert page.page_name == "新用户转化页"
    assert page.page_type == "product_page_optimization"
    assert page.app_id == "app-aurora-ios"
    assert db_session.query(StoreSyncRun).count() == 0
    assert [item.locale for item in locales] == ["en-US", "zh-Hant"]
    assert locales[0].promotional_text == "Read stories anytime."
    assert locales[1].promotional_text == "Read stories anytime."
    phone_assets = locales[0].store_images_json["phone_screenshots"]["assets"]
    assert phone_assets[0]["fileName"] == "iphone-69.png"


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_marketing_page_shows_backfilled_keywords_readonly(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store/marketing-pages",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "marketingPageType": "custom_product_page",
            "marketingPageName": "冷启动投放页",
        },
    )
    page = db_session.query(StoreMarketingPage).one()
    page.keywords = "stories,books"
    db_session.commit()

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        f"/apps/app-aurora-ios/store/marketing-pages/{page.page_id}",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert "stories,books" in response.text
    assert "由 App Store Connect 回填，只读展示" in response.text
    assert 'name="keywords"' not in response.text


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_marketing_page_detail_can_save_locales_and_images(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store/marketing-pages",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "marketingPageType": "custom_product_page",
            "marketingPageName": "冷启动投放页",
        },
    )
    page = db_session.query(StoreMarketingPage).one()

    detail = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        f"/apps/app-aurora-ios/store/marketing-pages/{page.page_id}",
        headers=_admin_headers(),
    )
    assert detail.status_code == 200
    assert "营销页面同步确认" in detail.text
    assert "宣传文本" in detail.text
    assert "手机截图" in detail.text
    assert "未同步" in detail.text
    assert "Apple 页面 ID" in detail.text
    assert "未同步后回填" in detail.text
    assert "由 App Store Connect 回填，只读展示" in detail.text
    assert 'name="applePageId"' not in detail.text
    assert "store-workspace-toolbar" not in detail.text
    assert "metadata-preflight-chip" not in detail.text
    assert "sync-scope-card" not in detail.text
    assert "同步到商店前会打开确认清单" in detail.text
    assert "同步范围只在确认弹窗里选择" in detail.text
    assert '<span class="sync-count"' not in detail.text
    assert "<small data-sync-item-status>" not in detail.text
    assert detail.text.count("保存草稿") == 1
    assert 'name="keywords"' not in detail.text
    assert 'data-sync-item-panel="promotional_text"' in detail.text
    assert 'data-sync-editor-pane="promotional_text" data-locale-group' in detail.text
    assert 'class="locale-detail-input"' in detail.text
    assert 'data-sync-item-panel="phone_screenshots"' in detail.text
    assert 'data-sync-editor-pane="phone_screenshots" data-locale-group' in detail.text
    assert 'data-sync-editor-pane="phone_screenshots" data-locale-group hidden' not in detail.text
    assert "event.target.closest('[data-locale-toggle]')" in detail.text

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        f"/apps/app-aurora-ios/store/marketing-pages/{page.page_id}",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "pageName": "冷启动投放页 v2",
            "pageType": "custom_product_page",
            "keywords": "stories,books",
            "applePageId": "manual-should-not-save",
            "deepLinkUrl": "anystories:///home",
            "locales": ["en-US", "zh-Hans"],
            "promotionalText": ["Read stories anytime.", "随时阅读故事。"],
            "phoneScreenshots": ["", ""],
            "tabletScreenshots": ["", ""],
        },
        files=[
            (
                "storeImageFiles__phone_screenshots__en-US",
                ("iphone-69.png", make_png_header_bytes(1290, 2796), "image/png"),
            )
        ],
    )

    db_session.refresh(page)
    assert page.apple_page_id == ""
    locales = (
        db_session.query(StoreMarketingPageLocale)
        .order_by(StoreMarketingPageLocale.locale)
        .all()
    )
    en_locale = next(item for item in locales if item.locale == "en-US")
    assert response.status_code == 200
    assert "营销页面草稿已保存" in response.text
    assert page.page_name == "冷启动投放页 v2"
    assert page.keywords == ""
    assert page.deep_link_url == "anystories:///home"
    assert [item.locale for item in locales] == ["en-US", "zh-Hans"]
    assert en_locale.promotional_text == "Read stories anytime."
    phone_assets = en_locale.store_images_json["phone_screenshots"]["assets"]
    assert phone_assets[0]["fileName"] == "iphone-69.png"
    assert "iphone-69.png" in response.text
    assert "store/marketing-pages/" in response.text

    delete_response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        f"/apps/app-aurora-ios/store/marketing-pages/{page.page_id}/store-images/delete",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "storeImageDelete": json.dumps(
                {
                    "locale": "en-US",
                    "slot": "phone_screenshots",
                    "storageKey": phone_assets[0]["storageKey"],
                }
            ),
        },
    )

    db_session.refresh(en_locale)
    assert delete_response.status_code == 200
    assert "已删除中心后台的营销页面截图" in delete_response.text
    assert en_locale.store_images_json["phone_screenshots"]["assets"] == []


def test_admin_marketing_page_sync_creates_sync_runs(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store/marketing-pages",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "marketingPageType": "custom_product_page",
            "marketingPageName": "冷启动投放页",
        },
    )
    page = db_session.query(StoreMarketingPage).one()

    preflight = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        f"/apps/app-aurora-ios/store/marketing-pages/{page.page_id}/preflight",
        headers=_admin_headers(),
        data={"locale": "en-US"},
    )
    assert preflight.status_code == 200
    assert "已实时查询营销页面同步状态" in preflight.text

    response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        f"/apps/app-aurora-ios/store/marketing-pages/{page.page_id}/sync",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "pageName": "冷启动投放页",
            "pageType": "custom_product_page",
            "keywords": "stories,books",
            "locales": ["en-US"],
            "promotionalText": ["Read stories anytime."],
            "phoneScreenshots": [""],
            "tabletScreenshots": [""],
            "syncScopes": ["marketing_text", "store_images"],
        },
    )

    run = db_session.query(StoreSyncRun).filter_by(operation="update_marketing_page").one()
    db_session.refresh(page)
    assert response.status_code == 200
    assert "营销页面已同步 1 个语言" in response.text
    assert page.status == "synced"
    assert run.version == page.page_id
    assert run.locale == "en-US"
    assert run.sync_scopes_json == {"scopes": ["marketing_text", "store_images"]}
    assert run.payload_snapshot_json["marketingPage"]["pageName"] == "冷启动投放页"
    assert "keywords" not in run.payload_snapshot_json["marketingPage"]
    assert run.payload_snapshot_json["marketingPage"]["promotionalText"] == "Read stories anytime."


def test_admin_marketing_page_can_copy_and_delete(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store/marketing-pages",
        headers=_admin_headers(),
        data={
            "locale": "en-US",
            "marketingPageType": "custom_product_page",
            "marketingPageName": "冷启动投放页",
        },
    )
    page = db_session.query(StoreMarketingPage).one()
    page_db_id = page.id
    locale = (
        db_session.query(StoreMarketingPageLocale)
        .filter_by(marketing_page_id=page.id, locale="en-US")
        .one()
    )
    locale.promotional_text = "Read stories anytime."
    db_session.commit()

    copy_response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        f"/apps/app-aurora-ios/store/marketing-pages/{page.page_id}/copy",
        headers=_admin_headers(),
    )
    pages = db_session.query(StoreMarketingPage).order_by(StoreMarketingPage.created_at).all()
    copied = next(item for item in pages if item.page_id != page.page_id)
    assert copy_response.status_code == 200
    assert "已复制营销页面" in copy_response.text
    assert len(pages) == 2
    assert copied.page_name == "冷启动投放页 副本"
    assert db_session.query(StoreMarketingPageLocale).count() == 2

    delete_response = client.post(
        "/admin/developer-accounts/account-apple-enterprise"
        f"/apps/app-aurora-ios/store/marketing-pages/{page.page_id}/delete",
        headers=_admin_headers(),
    )

    assert delete_response.status_code == 200
    assert "已删除中心后台的营销页面" in delete_response.text
    db_session.expire_all()
    assert db_session.get(StoreMarketingPage, page_db_id) is None
    assert db_session.query(StoreMarketingPage).count() == 1


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_store_metadata_page_uses_google_play_terms_for_android(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    android_app = db_session.query(App).filter_by(id="app-dataflow-android").one()
    android_app.developer_account_id = "account-apple-enterprise"
    android_app.store_package_name = android_app.bundle_identifier
    db_session.commit()

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-dataflow-android/store-metadata",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert "Google Play Console 默认商店页" in response.text
    assert "完整描述" in response.text
    assert "功能宣传图" in response.text
    assert "Google Play 功能宣传图必须是 1024 x 500" in response.text
    assert "Google Play 截图最小边 320" in response.text
    assert "手机截图" in response.text
    assert "平板截图" in response.text
    assert "Keywords（关键词）" not in response.text
    assert "Promotional Text（宣传文本）" not in response.text
    assert "App Store Connect 同步" not in response.text
    assert "iPhone screenshots" not in response.text
    assert "iPad screenshots" not in response.text


class _LocaleClient:
    def supported_locales(
        self,
        connector: StoreConnector,
        *,
        account_id: str,
        app: App,
        version: str,
    ) -> list[str]:
        return ["en-US", "zh-Hant", "fr-FR"]


def test_supported_locales_use_connector_app_languages_only(db_session: Session) -> None:
    seed_demo_catalog(db_session)

    locales = supported_locales_for_app(
        db_session,
        account_id="account-apple-enterprise",
        app_id="app-aurora-ios",
        version="2.4.0",
        fallback_locale="zh-Hans",
        client=_LocaleClient(),
    )

    assert locales == ["en-US", "zh-Hant", "fr-FR"]
    assert "zh-Hans" not in locales


@pytest.mark.skip(reason=LEGACY_JINJA_PAGE_REASON)
def test_admin_store_metadata_page_uses_local_draft_locales_without_connector(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_demo_catalog(db_session)
    connector = db_session.query(StoreConnector).one()
    connector.base_url = "http://connector.test"
    db_session.add_all(
        [
            StoreAppMetadataDraft(
                id="draft-local-en-us",
                developer_account_id="account-apple-enterprise",
                app_id="app-aurora-ios",
                platform="ios",
                version="2.4.0",
                locale="en-US",
                content_set_id="default",
                content_set_name="默认上架内容",
                description="English draft",
            ),
            StoreAppMetadataDraft(
                id="draft-local-zh-hant",
                developer_account_id="account-apple-enterprise",
                app_id="app-aurora-ios",
                platform="ios",
                version="2.4.0",
                locale="zh-Hant",
                content_set_id="default",
                content_set_name="默认上架内容",
                description="Traditional Chinese draft",
            ),
            StoreAppMetadataDraft(
                id="draft-historical-fr",
                developer_account_id="account-apple-enterprise",
                app_id="app-aurora-ios",
                platform="ios",
                version="2.3.0",
                locale="fr-FR",
                content_set_id="default",
                content_set_name="默认上架内容",
                description="Historical French draft",
            ),
        ]
    )
    db_session.commit()

    def fail_if_connector_locales_are_loaded(*_args: object, **_kwargs: object) -> list[str]:
        raise AssertionError("page render should not block on connector locales")

    monkeypatch.setattr(
        "testflying_api.admin.view_models.supported_locales_for_app",
        fail_if_connector_locales_are_loaded,
    )

    response = client.get(
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata",
        headers=_admin_headers(),
    )

    assert response.status_code == 200
    assert 'name="locales" value="en-US"' in response.text
    assert 'name="locales" value="zh-Hant"' in response.text
    assert 'name="locales" value="fr-FR"' in response.text
    assert "English draft" in response.text
    assert "Traditional Chinese draft" in response.text


def test_supported_locales_falls_back_when_connector_resets(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_demo_catalog(db_session)
    connector = db_session.query(StoreConnector).one()
    connector.base_url = "http://connector.test"
    db_session.commit()

    def reset_connection(*_args: object, **_kwargs: object) -> None:
        raise ConnectionResetError(104, "Connection reset by peer")

    monkeypatch.setattr("testflying_api.store_sync.urlopen", reset_connection)

    locales = supported_locales_for_app(
        db_session,
        account_id="account-apple-enterprise",
        app_id="app-aurora-ios",
        version="2.4.0",
        fallback_locale="en-US",
    )

    assert locales == ["en-US"]


def test_admin_store_metadata_realtime_preflight_is_throttled(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)
    path = (
        "/admin/developer-accounts/account-apple-enterprise"
        "/apps/app-aurora-ios/store-metadata/preflight"
    )
    data = {"version": "2.4.0", "locale": "en-US"}

    first_response = client.post(path, headers=_admin_headers(), data=data)
    second_response = client.post(path, headers=_admin_headers(), data=data)

    checks = db_session.query(StorePreflightCheck).order_by(StorePreflightCheck.checked_at).all()
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert "已实时查询商店状态" in first_response.text
    assert "1 分钟内已查询过，已显示最近一次结果" in second_response.text
    assert len(checks) == 1
    assert checks[0].store_state_json["manualRefresh"] is True
