from __future__ import annotations

from base64 import b64encode

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.schema import App, Build


def _admin_headers(password: str = "dev-token") -> dict[str, str]:
    token = b64encode(f"admin:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _create_app(session: Session) -> App:
    app = App(
        id="app-ios-com-example-demo",
        name="Demo",
        bundle_identifier="com.example.demo",
        platform="ios",
        default_channel="dev",
    )
    session.add(app)
    session.commit()
    return app


def test_admin_app_detail_returns_build_history_and_empty_settings(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    db_session.add(
        Build(
            id="build-1",
            app_id=app.id,
            version="1.0",
            build_number="10",
            channel="dev",
            environment="development",
            requested_environment="development",
            platform="ios",
            source="upload",
            lifecycle_status="succeeded",
        )
    )
    db_session.commit()

    response = client.get(f"/admin/api/apps/{app.id}", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["app"]["id"] == app.id
    assert payload["app"]["bundleIdentifier"] == "com.example.demo"
    assert payload["builds"][0]["id"] == "build-1"
    assert payload["settings"]["development"] is None
    assert payload["settings"]["production"] is None


def test_admin_app_detail_returns_admin_error_for_missing_app(
    client: TestClient,
) -> None:
    response = client.get(
        "/admin/api/apps/app-ios-com-example-missing",
        headers=_admin_headers(),
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "app_not_found",
            "message": "应用不存在",
            "detail": {"retryable": False},
        }
    }


def test_admin_can_save_development_build_settings(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)

    response = client.put(
        f"/admin/api/apps/{app.id}/build-settings/development",
        headers=_admin_headers(),
        json={
            "gitUrl": "git@example.com:mobile/demo.git",
            "repoSubpath": "apps/demo",
            "runnerLabels": ["ios-release", "mac-mini-1"],
            "credentialRefs": {"git": "git-main", "iosSigning": "ios-dev"},
            "artifactType": "ipa",
            "optionalDefaults": {"flutterVersion": "3.22.3"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["build"] is None
    assert payload["state"]["settings"]["development"]["gitUrl"] == "git@example.com:mobile/demo.git"
    assert payload["state"]["settings"]["development"]["runnerLabels"] == [
        "ios-release",
        "mac-mini-1",
    ]


def test_admin_can_create_queued_agent_build_from_app_detail(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)

    response = client.post(
        f"/admin/api/apps/{app.id}/builds",
        headers=_admin_headers(),
        json={
            "environment": "development",
            "gitUrl": "git@example.com:mobile/demo.git",
            "gitRef": "main",
            "repoSubpath": "",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    created = payload["build"]
    assert created["source"] == "agent"
    assert created["lifecycleStatus"] == "queued"
    assert created["gitRef"] == "main"
    assert created["version"] == ""
    assert created["buildNumber"] == ""


def test_admin_save_build_setting_rejects_invalid_environment_with_admin_error(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)

    response = client.put(
        f"/admin/api/apps/{app.id}/build-settings/staging",
        headers=_admin_headers(),
        json={
            "gitUrl": "git@example.com:mobile/demo.git",
            "repoSubpath": "apps/demo",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa",
            "optionalDefaults": {},
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_environment",
            "message": "environment 必须是 development 或 production",
            "detail": {"retryable": False},
        }
    }


def test_admin_save_build_setting_returns_admin_error_for_missing_app(
    client: TestClient,
) -> None:
    response = client.put(
        "/admin/api/apps/app-ios-com-example-missing/build-settings/development",
        headers=_admin_headers(),
        json={
            "gitUrl": "git@example.com:mobile/demo.git",
            "repoSubpath": "apps/demo",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa",
            "optionalDefaults": {},
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "app_not_found",
            "message": "应用不存在",
            "detail": {"retryable": False},
        }
    }


def test_admin_create_agent_build_rejects_invalid_environment_with_admin_error(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)

    response = client.post(
        f"/admin/api/apps/{app.id}/builds",
        headers=_admin_headers(),
        json={
            "environment": "staging",
            "gitUrl": "git@example.com:mobile/demo.git",
            "gitRef": "main",
            "repoSubpath": "",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_environment",
            "message": "environment 必须是 development 或 production",
            "detail": {"retryable": False},
        }
    }


def test_admin_create_agent_build_returns_admin_error_for_missing_app(
    client: TestClient,
) -> None:
    response = client.post(
        "/admin/api/apps/app-ios-com-example-missing/builds",
        headers=_admin_headers(),
        json={
            "environment": "development",
            "gitUrl": "git@example.com:mobile/demo.git",
            "gitRef": "main",
            "repoSubpath": "",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa",
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "app_not_found",
            "message": "应用不存在",
            "detail": {"retryable": False},
        }
    }
