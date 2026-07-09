from __future__ import annotations

from base64 import b64encode

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.schema import App, Artifact, Build, BuildEvent, BuildRunner


def _admin_headers(password: str = "dev-token") -> dict[str, str]:
    token = b64encode(f"admin:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _runner_headers(token: str = "runner-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_app(session: Session, *, app_id: str = "app-ios-demo", platform: str = "ios") -> App:
    app = App(
        id=app_id,
        name="Demo",
        bundle_identifier=f"com.example.{app_id}",
        platform=platform,
        default_channel="dev",
    )
    session.add(app)
    session.commit()
    return app


def _create_agent_build(
    session: Session,
    *,
    build_id: str = "build-agent-queued",
    app: App,
    required_labels: list[str] | None = None,
) -> Build:
    build = Build(
        id=build_id,
        app_id=app.id,
        channel="dev",
        environment="development",
        requested_environment="development",
        platform=app.platform,
        source="agent",
        lifecycle_status="queued",
        git_url="git@example.com:demo.git",
        git_ref="main",
        runner_labels_json={
            "required": required_labels or ["ios-release"],
            "repoSubpath": "apps/demo",
            "credentialRefs": {"git": "git-main"},
            "artifactType": "ipa" if app.platform == "ios" else "apk",
        },
        note="",
        status="pending",
    )
    session.add(build)
    session.commit()
    return build


def test_runner_register_creates_runner_record(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    runner = db_session.get(BuildRunner, "runner-mac-1")
    assert runner is not None
    assert runner.status == "online"
    assert runner.token_hash == "runner-token"
    assert runner.labels_json == ["ios-release"]
    assert runner.capabilities_json["capacity"] == 1


def test_runner_heartbeat_registers_capabilities(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/admin/api/build-runners/heartbeat",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )

    assert response.status_code == 200
    runner = db_session.get(BuildRunner, "runner-mac-1")
    assert runner is not None
    assert runner.status == "online"
    assert runner.labels_json == ["ios-release"]


def test_runner_poll_assigns_matching_queued_build_and_enforces_capacity(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    first_build = _create_agent_build(db_session, build_id="build-agent-queued-1", app=app)
    second_build = _create_agent_build(db_session, build_id="build-agent-queued-2", app=app)
    client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )

    response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["build"] == {
        "id": "build-agent-queued-1",
        "appId": app.id,
        "platform": "ios",
        "environment": "development",
        "gitUrl": "git@example.com:demo.git",
        "gitRef": "main",
        "repoSubpath": "apps/demo",
        "artifactType": "ipa",
        "credentialRefs": {"git": "git-main"},
    }
    db_session.refresh(first_build)
    assert first_build.lifecycle_status == "assigned"
    assert first_build.runner_id == "runner-mac-1"

    second_response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )

    assert second_response.status_code == 200
    assert second_response.json() == {"build": None}
    db_session.refresh(second_build)
    assert second_build.lifecycle_status == "queued"


def test_runner_artifact_event_and_complete_flow_marks_build_succeeded(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )
    client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )

    event_response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/events",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "type": "building",
            "message": "archive started",
            "lifecycleStatus": "building",
            "payload": {"step": "archive"},
        },
    )

    assert event_response.status_code == 200

    for artifact_type, file_name in [
        ("package", "app.ipa"),
        ("symbols", "symbols.zip"),
        ("report", "report.json"),
        ("log", "runner.log"),
    ]:
        upload_response = client.post(
            f"/admin/api/build-runners/builds/{build.id}/artifacts",
            headers=_runner_headers(),
            data={"runnerId": "runner-mac-1", "artifactType": artifact_type},
            files={"file": (file_name, b"content", "application/octet-stream")},
        )
        assert upload_response.status_code == 200
        assert upload_response.json()["ok"] is True

    complete_response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/complete",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "status": "succeeded",
            "version": "1.2.3",
            "buildNumber": "42",
            "note": "done",
        },
    )

    assert complete_response.status_code == 200
    db_session.refresh(build)
    assert build.lifecycle_status == "succeeded"
    assert build.status == "available"
    assert build.version == "1.2.3"
    assert build.build_number == "42"
    assert build.finished_at is not None
    assert build.started_at is not None
    assert build.runner_id == "runner-mac-1"
    assert {
        artifact.artifact_type
        for artifact in db_session.query(Artifact).filter_by(build_id=build.id)
    } == {
        "package",
        "symbols",
        "report",
        "log",
    }
    events = db_session.query(BuildEvent).filter_by(build_id=build.id).all()
    assert [item.type for item in events] == [
        "building",
        "artifact_uploaded",
        "artifact_uploaded",
        "artifact_uploaded",
        "artifact_uploaded",
        "complete",
    ]


def test_runner_complete_rejects_success_without_required_artifacts(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )
    client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )
    db_session.add(
        Artifact(
            id="artifact-package",
            build_id=build.id,
            artifact_type="package",
            file_name="app.ipa",
            content_type="application/octet-stream",
            storage_backend="local",
            storage_key=f"{build.id}/app.ipa",
            download_url=f"https://dist.example.test/artifacts/{build.id}/app.ipa",
            install_url=f"https://dist.example.test/artifacts/{build.id}/app.ipa",
            size_bytes=7,
        )
    )
    db_session.commit()

    response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/complete",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "status": "succeeded"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "missing_required_artifacts",
            "message": "自动构建缺少必需制品: log, report, symbols",
            "detail": {"retryable": False},
        }
    }
