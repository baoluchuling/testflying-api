from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.schema import App, DeviceBuildVisibility
from testflying_api.seed import seed_demo_catalog
from tests.fixtures import make_android_apk_bytes, make_ipa_bytes


def test_upload_ipa_creates_build_without_install_task(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_demo_catalog(db_session)

    response = client.post(
        "/v1/test-distribution/uploads",
        data={
            "platform": "ios",
            "environment": "development",
            "changelog": "验证新上传链路",
        },
        files={"file": ("AuroraNew.ipa", make_ipa_bytes(), "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["build"]["installInfo"]["installUrl"].startswith("itms-services://")
    assert body["build"]["installInfo"]["manifestUrl"].endswith("/manifest.plist")
    assert body["build"]["environment"] == "development"

    workspace_response = client.get(
        "/v1/test-distribution/workspace",
        headers={"X-Device-ID": "device-001", "X-Client-Platform": "ios"},
    )
    workspace = workspace_response.json()
    assert body["build"]["id"] in {build["id"] for build in workspace["builds"]}
    assert workspace["installTasks"] == []
    assert (
        db_session.query(DeviceBuildVisibility).filter_by(build_id=body["build"]["id"]).count() >= 1
    )


def test_upload_android_parses_metadata_from_apk(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        "/v1/test-distribution/uploads",
        data={
            "platform": "android",
            "environment": "development",
            "changelog": "自动解析 Android metadata",
        },
        files={
            "file": (
                "app.apk",
                make_android_apk_bytes(),
                "application/vnd.android.package-archive",
            )
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["app"]["name"] == "Auto Parsed"
    assert body["build"]["version"] == "4.5.6"
    assert body["build"]["buildNumber"] == "321"
    assert body["build"]["installInfo"]["installUrl"].endswith("/app.apk")

    app = db_session.get(App, body["app"]["id"])
    assert app is not None
    assert app.bundle_identifier == "com.example.autoparse"
