from __future__ import annotations

from base64 import b64encode

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.schema import App, Artifact, Build, BuildEvent


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


def test_admin_app_detail_returns_all_artifacts_and_failure_diagnostics(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = Build(
        id="build-agent-needs-human",
        app_id=app.id,
        version="",
        build_number="",
        channel="dev",
        environment="development",
        requested_environment="development",
        platform="ios",
        source="agent",
        lifecycle_status="needs_human",
        status="pending",
        git_ref="main",
        failure_classification="missing_artifacts",
        failure_summary="Automatic success requires package, symbols, and logs.",
        human_action="Upload missing artifacts.",
    )
    db_session.add(build)
    for artifact_type, file_name in [
        ("package", "app.ipa"),
        ("symbols", "symbols.zip"),
        ("report", "report.json"),
        ("log", "runner.log"),
    ]:
        db_session.add(
            Artifact(
                id=f"artifact-{artifact_type}",
                build_id=build.id,
                artifact_type=artifact_type,
                file_name=file_name,
                content_type="application/octet-stream",
                storage_backend="local",
                storage_key=f"{build.id}/{file_name}",
                download_url=f"https://dist.example.test/{file_name}",
                install_url=(
                    f"https://dist.example.test/{file_name}"
                    if artifact_type == "package"
                    else ""
                ),
                size_bytes=10,
            )
        )
    db_session.add(
        BuildEvent(
            id="event-needs-human",
            build_id=build.id,
            runner_id=None,
            type="runner.build.needs_human",
            message="Upload missing artifacts.",
            payload_json={},
        )
    )
    db_session.commit()

    response = client.get(f"/admin/api/apps/{app.id}", headers=_admin_headers())

    assert response.status_code == 200
    build_payload = response.json()["builds"][0]
    assert build_payload["failureClassification"] == "missing_artifacts"
    assert (
        build_payload["failureSummary"]
        == "Automatic success requires package, symbols, and logs."
    )
    assert build_payload["humanAction"] == "Upload missing artifacts."
    assert [item["artifactType"] for item in build_payload["artifacts"]] == [
        "log",
        "package",
        "report",
        "symbols",
    ]
    assert build_payload["artifact"]["fileName"] == "app.ipa"
    assert build_payload["recentEvents"][0]["type"] == "runner.build.needs_human"


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
    assert (
        payload["state"]["settings"]["development"]["gitUrl"]
        == "git@example.com:mobile/demo.git"
    )
    assert payload["state"]["settings"]["development"]["runnerLabels"] == [
        "ios-release",
        "mac-mini-1",
    ]


@pytest.mark.parametrize("repo_subpath", ["../escape", "/tmp/project", "ios\\Runner"])
def test_admin_save_build_setting_rejects_repo_subpath_traversal(
    client: TestClient,
    db_session: Session,
    repo_subpath: str,
) -> None:
    app = _create_app(db_session)

    response = client.put(
        f"/admin/api/apps/{app.id}/build-settings/development",
        headers=_admin_headers(),
        json={
            "gitUrl": "git@example.com:mobile/demo.git",
            "repoSubpath": repo_subpath,
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa",
            "optionalDefaults": {},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_repo_subpath"


def test_admin_can_save_production_build_settings_with_valid_credential_refs(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)

    response = client.put(
        f"/admin/api/apps/{app.id}/build-settings/production",
        headers=_admin_headers(),
        json={
            "gitUrl": "  git@example.com:mobile/demo.git  ",
            "repoSubpath": " ios/App ",
            "runnerLabels": [" release-runner ", " "],
            "credentialRefs": {"git": "git-main", "iosSigning": "mac-mini-1"},
            "artifactType": " ipa ",
            "optionalDefaults": {},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["state"]["settings"]["production"] == {
        "environment": "production",
        "gitUrl": "git@example.com:mobile/demo.git",
        "repoSubpath": "ios/App",
        "runnerLabels": ["release-runner"],
        "credentialRefs": {"git": "git-main", "iosSigning": "mac-mini-1"},
        "artifactType": "ipa",
        "optionalDefaults": {},
        "updatedAtLabel": payload["state"]["settings"]["production"]["updatedAtLabel"],
    }


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


def test_admin_create_agent_build_rejects_repo_subpath_traversal(
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
            "repoSubpath": "../escape",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_repo_subpath"


@pytest.mark.parametrize("credential_ref", ["git-main", "ios-dev", "mac-mini-1"])
def test_admin_accepts_supported_credential_ref_ids(
    client: TestClient,
    db_session: Session,
    credential_ref: str,
) -> None:
    app = _create_app(db_session)

    response = client.put(
        f"/admin/api/apps/{app.id}/build-settings/development",
        headers=_admin_headers(),
        json={
            "gitUrl": "git@example.com:mobile/demo.git",
            "repoSubpath": "apps/demo",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": credential_ref},
            "artifactType": "ipa",
            "optionalDefaults": {},
        },
    )

    assert response.status_code == 200
    assert response.json()["state"]["settings"]["development"]["credentialRefs"] == {
        "git": credential_ref
    }


def test_admin_save_build_setting_rejects_blank_required_fields_with_admin_error(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)

    response = client.put(
        f"/admin/api/apps/{app.id}/build-settings/development",
        headers=_admin_headers(),
        json={
            "gitUrl": "   ",
            "repoSubpath": "apps/demo",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": " \t ",
            "optionalDefaults": {},
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_build_input",
            "message": "git_url 不能为空",
            "detail": {"field": "git_url", "retryable": False},
        }
    }


def test_admin_create_agent_build_rejects_blank_required_fields_with_admin_error(
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
            "gitRef": "   ",
            "repoSubpath": "",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_build_input",
            "message": "git_ref 不能为空",
            "detail": {"field": "git_ref", "retryable": False},
        }
    }


@pytest.mark.parametrize(
    ("credential_ref", "message"),
    [
        ("   ", "git: credential ref 不能为空"),
        ("-----BEGIN PRIVATE KEY-----", "git: credential ref 不能是私钥内容"),
        ("line1\nline2", "git: credential ref 不能包含换行"),
        ("x" * 121, "git: credential ref 过长"),
        (
            "supersecret",
            "git: credential ref 必须是受支持前缀的小写 kebab-case 标识",
        ),
        (
            "password",
            "git: credential ref 必须是受支持前缀的小写 kebab-case 标识",
        ),
        (
            "token-main",
            "git: credential ref 必须是受支持前缀的小写 kebab-case 标识",
        ),
        (
            "abc123",
            "git: credential ref 必须是受支持前缀的小写 kebab-case 标识",
        ),
        (
            "Git-Main",
            "git: credential ref 必须是受支持前缀的小写 kebab-case 标识",
        ),
        (
            "git.main",
            "git: credential ref 必须是受支持前缀的小写 kebab-case 标识",
        ),
        (
            "mac mini 1",
            "git: credential ref 必须是受支持前缀的小写 kebab-case 标识",
        ),
        (
            "mac-" + ("mini-" * 11) + "1",
            "git: credential ref 过长",
        ),
    ],
)
def test_admin_save_build_setting_rejects_invalid_credential_refs_with_admin_error(
    client: TestClient,
    db_session: Session,
    credential_ref: str,
    message: str,
) -> None:
    app = _create_app(db_session)

    response = client.put(
        f"/admin/api/apps/{app.id}/build-settings/development",
        headers=_admin_headers(),
        json={
            "gitUrl": "git@example.com:mobile/demo.git",
            "repoSubpath": "apps/demo",
            "runnerLabels": ["ios-release"],
            "credentialRefs": {"git": credential_ref},
            "artifactType": "ipa",
            "optionalDefaults": {},
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_credential_ref",
            "message": message,
            "detail": {"field": "credential_refs", "key": "git", "retryable": False},
        }
    }


@pytest.mark.parametrize(
    ("credential_ref", "message"),
    [
        ("ghp_1234567890abcdefghijklmnopqrstuvwxyz", "git: credential ref 不能是 token 或密钥"),
        (
            "supersecret",
            "git: credential ref 必须是受支持前缀的小写 kebab-case 标识",
        ),
        (
            "runner-\nprod",
            "git: credential ref 不能包含换行",
        ),
    ],
)
def test_admin_create_agent_build_rejects_invalid_credential_refs_with_admin_error(
    client: TestClient,
    db_session: Session,
    credential_ref: str,
    message: str,
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
            "credentialRefs": {"git": credential_ref},
            "artifactType": "ipa",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_credential_ref",
            "message": message,
            "detail": {"field": "credential_refs", "key": "git", "retryable": False},
        }
    }


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
