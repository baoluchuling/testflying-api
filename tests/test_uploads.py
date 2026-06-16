from __future__ import annotations

import plistlib
from io import BytesIO
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.schema import DeviceBuildVisibility
from testflying_api.seed import seed_demo_catalog


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


def test_upload_android_requires_metadata(client: TestClient) -> None:
    response = client.post(
        "/v1/test-distribution/uploads",
        data={"platform": "android", "environment": "development"},
        files={"file": ("app.apk", b"apk-bytes", "application/vnd.android.package-archive")},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_package"


def make_ipa_bytes() -> bytes:
    plist = plistlib.dumps(
        {
            "CFBundleIdentifier": "com.example.uploaded",
            "CFBundleDisplayName": "Uploaded App",
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "100",
        }
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("Payload/Uploaded.app/Info.plist", plist)
    return buffer.getvalue()
