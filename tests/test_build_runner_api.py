from __future__ import annotations

from base64 import b64encode
from datetime import UTC, datetime, timedelta

import pytest

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from testflying_api.build_platform import hash_runner_token
from testflying_api.schema import App, Artifact, Build, BuildEvent, BuildRunner


def _admin_headers(password: str = "dev-token") -> dict[str, str]:
    token = b64encode(f"admin:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _runner_headers(token: str = "runner-token") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _runner_token_hash(token: str = "runner-token") -> str:
    return hash_runner_token(token, token_pepper="dev-token")


def _provision_runner_record(
    session: Session,
    *,
    runner_id: str = "runner-mac-1",
    current_build_id: str | None = None,
) -> BuildRunner:
    runner = BuildRunner(
        id=runner_id,
        name="Mac mini 1",
        token_hash=_runner_token_hash(),
        labels_json=[],
        capabilities_json={},
        status="busy" if current_build_id else "offline",
        version="",
        package_agent_version="",
        current_build_id=current_build_id,
    )
    session.add(runner)
    session.commit()
    return runner


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


def test_admin_provisions_runner_token_once(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/admin/api/build-runners/provision",
        headers=_admin_headers(),
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
    payload = response.json()
    assert payload["runner"]["id"] == "runner-mac-1"
    assert payload["runner"]["status"] == "offline"
    assert payload["token"]
    runner = db_session.get(BuildRunner, "runner-mac-1")
    assert runner is not None
    assert runner.token_hash.startswith("hmac-sha256:")
    assert runner.token_hash != payload["token"]


def test_runner_register_updates_provisioned_runner_record(
    client: TestClient,
    db_session: Session,
) -> None:
    _provision_runner_record(db_session)

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
    assert runner.token_hash == _runner_token_hash()
    assert runner.labels_json == ["ios-release"]
    assert runner.capabilities_json["capacity"] == 1


def test_runner_heartbeat_rejects_unknown_runner(client: TestClient) -> None:
    response = client.post(
        "/admin/api/build-runners/heartbeat",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-unknown",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unknown_runner"


def test_runner_register_rejects_unknown_runner(client: TestClient) -> None:
    response = client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-unknown",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unknown_runner"


def test_runner_poll_rejects_unknown_runner(client: TestClient) -> None:
    response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-unknown", "timeoutSeconds": 0},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unknown_runner"


def test_runner_heartbeat_updates_provisioned_capabilities(
    client: TestClient,
    db_session: Session,
) -> None:
    _provision_runner_record(db_session)

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


def test_build_runners_state_lists_runner_status_and_capabilities(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, build_id="build-agent-active", app=app)
    db_session.add(
        BuildRunner(
            id="runner-mac-1",
            name="Mac mini 1",
            token_hash=_runner_token_hash(),
            labels_json=["ios-release"],
            capabilities_json={"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
            status="busy",
            version="0.1.0",
            package_agent_version="0.1.2",
            last_seen_at=datetime(2026, 7, 10, 2, 30, tzinfo=UTC),
            current_build_id=build.id,
        )
    )
    db_session.commit()

    response = client.get("/admin/api/build-runners", headers=_admin_headers())

    assert response.status_code == 200
    assert response.json() == {
        "runners": [
            {
                "id": "runner-mac-1",
                "name": "Mac mini 1",
                "status": "busy",
                "labels": ["ios-release"],
                "version": "0.1.0",
                "packageAgentVersion": "0.1.2",
                "lastSeenAtLabel": "2026-07-10 02:30",
                "currentBuildId": "build-agent-active",
                "capabilities": {
                    "platforms": ["ios"],
                    "llmAdapters": ["codex"],
                    "capacity": 1,
                },
            }
        ],
        "total": 1,
    }


def test_build_runners_state_requires_basic_auth(client: TestClient) -> None:
    response = client.get("/admin/api/build-runners")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Basic"


def test_runner_reregister_rejects_token_takeover(client: TestClient, db_session: Session) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    runner = _provision_runner_record(db_session, current_build_id=build.id)
    runner.labels_json = ["ios-release"]
    runner.capabilities_json = {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1}
    runner.status = "busy"
    runner.version = "0.1.0"
    runner.package_agent_version = "0.1.0"
    db_session.add(runner)
    db_session.commit()

    response = client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers("replacement-token"),
        json={
            "runnerId": "runner-mac-1",
            "name": "Hijack attempt",
            "labels": ["android-release"],
            "version": "9.9.9",
            "packageAgentVersion": "9.9.9",
            "capabilities": {"platforms": ["android"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_runner_token",
            "message": "Runner token 不正确",
            "detail": {"retryable": False},
        }
    }
    db_session.refresh(runner)
    assert runner.token_hash == _runner_token_hash()
    assert runner.name == "Mac mini 1"
    assert runner.labels_json == ["ios-release"]
    assert runner.capabilities_json["platforms"] == ["ios"]
    assert runner.current_build_id == build.id


def test_runner_poll_assigns_matching_queued_build_and_enforces_capacity(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    first_build = _create_agent_build(db_session, build_id="build-agent-queued-1", app=app)
    second_build = _create_agent_build(db_session, build_id="build-agent-queued-2", app=app)
    _provision_runner_record(db_session)
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
    assert second_response.json()["build"]["id"] == first_build.id
    db_session.refresh(second_build)
    assert second_build.lifecycle_status == "queued"


def test_runner_poll_requires_explicit_platform_capability(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build_without_platforms = _create_agent_build(
        db_session,
        build_id="build-agent-no-platforms",
        app=app,
    )
    build_with_wrong_platform = _create_agent_build(
        db_session,
        build_id="build-agent-wrong-platform",
        app=app,
    )
    build_matching = _create_agent_build(
        db_session,
        build_id="build-agent-matching-platform",
        app=app,
    )
    _provision_runner_record(db_session)

    client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"llmAdapters": ["codex"], "capacity": 1},
        },
    )

    no_platforms_response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )

    assert no_platforms_response.status_code == 200
    assert no_platforms_response.json() == {"build": None}
    db_session.refresh(build_without_platforms)
    assert build_without_platforms.lifecycle_status == "queued"

    client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "name": "Mac mini 1",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["android"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )

    wrong_platform_response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )

    assert wrong_platform_response.status_code == 200
    assert wrong_platform_response.json() == {"build": None}
    db_session.refresh(build_with_wrong_platform)
    assert build_with_wrong_platform.lifecycle_status == "queued"

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

    matching_response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )

    assert matching_response.status_code == 200
    assert matching_response.json()["build"]["id"] == "build-agent-no-platforms"
    db_session.refresh(build_matching)
    assert build_matching.lifecycle_status == "queued"


def test_runner_poll_terminalizes_queued_builds_at_retry_cap(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    capped_build = _create_agent_build(db_session, build_id="build-agent-capped", app=app)
    capped_build.attempt_count = 5
    eligible_build = _create_agent_build(db_session, build_id="build-agent-eligible", app=app)
    db_session.add_all([capped_build, eligible_build])
    db_session.commit()

    _provision_runner_record(db_session)
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
    assert response.json()["build"]["id"] == "build-agent-eligible"
    db_session.refresh(capped_build)
    db_session.refresh(eligible_build)
    assert capped_build.lifecycle_status == "needs_human"
    assert capped_build.failure_classification == "retry_cap_reached"
    assert capped_build.attempt_count == 5
    assert eligible_build.lifecycle_status == "assigned"
    assert eligible_build.attempt_count == 1


def test_runner_poll_returns_same_assignment_with_valid_lease(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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

    first_response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )

    assert first_response.status_code == 200
    assert first_response.json()["build"]["id"] == build.id
    db_session.refresh(build)
    first_lease = build.assignment_lease_expires_at
    assert build.attempt_count == 1
    assert first_lease is not None

    second_response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "timeoutSeconds": 0},
    )

    assert second_response.status_code == 200
    assert second_response.json()["build"]["id"] == build.id
    db_session.refresh(build)
    assert build.runner_id == "runner-mac-1"
    assert build.attempt_count == 1
    assert build.assignment_lease_expires_at is not None
    assert build.assignment_lease_expires_at >= first_lease


def test_runner_poll_reassigns_stale_assignment_to_different_runner(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    first_runner = _provision_runner_record(db_session, runner_id="runner-mac-1")
    _provision_runner_record(db_session, runner_id="runner-mac-2")
    for runner_id in ("runner-mac-1", "runner-mac-2"):
        client.post(
            "/admin/api/build-runners/register",
            headers=_runner_headers(),
            json={
                "runnerId": runner_id,
                "name": runner_id,
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
    db_session.refresh(build)
    build.assignment_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(build)
    db_session.commit()

    response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-2", "timeoutSeconds": 0},
    )

    assert response.status_code == 200
    assert response.json()["build"]["id"] == build.id
    db_session.refresh(build)
    db_session.refresh(first_runner)
    assert build.lifecycle_status == "assigned"
    assert build.runner_id == "runner-mac-2"
    assert build.attempt_count == 2
    assert first_runner.current_build_id is None


def test_runner_poll_terminalizes_stale_assignment_at_retry_cap(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session, runner_id="runner-mac-1", current_build_id=build.id)
    _provision_runner_record(db_session, runner_id="runner-mac-2")
    build.lifecycle_status = "assigned"
    build.runner_id = "runner-mac-1"
    build.attempt_count = 5
    build.assignment_lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(build)
    db_session.commit()

    client.post(
        "/admin/api/build-runners/register",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-2",
            "name": "runner-mac-2",
            "labels": ["ios-release"],
            "version": "0.1.0",
            "packageAgentVersion": "0.1.0",
            "capabilities": {"platforms": ["ios"], "llmAdapters": ["codex"], "capacity": 1},
        },
    )
    response = client.post(
        "/admin/api/build-runners/poll",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-2", "timeoutSeconds": 0},
    )

    assert response.status_code == 200
    assert response.json() == {"build": None}
    db_session.refresh(build)
    assert build.lifecycle_status == "needs_human"
    assert build.failure_classification == "retry_cap_reached"
    assert build.runner_id is None


def test_runner_artifact_event_and_complete_flow_marks_build_succeeded(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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
            "commitSha": "abc123def456",
            "note": "done",
        },
    )

    assert complete_response.status_code == 200
    db_session.refresh(build)
    assert build.lifecycle_status == "succeeded"
    assert build.status == "available"
    assert build.version == "1.2.3"
    assert build.build_number == "42"
    assert build.commit_sha == "abc123def456"
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
    assert events[-1].payload_json["commitSha"] == "abc123def456"


def test_runner_artifact_upload_keeps_multiple_rows_for_same_type(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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

    for artifact_type, file_name in [
        ("package", "app.ipa"),
        ("symbols", "symbols.zip"),
        ("report", "report.json"),
        ("log", "runner.log"),
        ("log", "xcode.log"),
    ]:
        upload_response = client.post(
            f"/admin/api/build-runners/builds/{build.id}/artifacts",
            headers=_runner_headers(),
            data={"runnerId": "runner-mac-1", "artifactType": artifact_type},
            files={"file": (file_name, b"content", "application/octet-stream")},
        )
        assert upload_response.status_code == 200

    complete_response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/complete",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "status": "succeeded"},
    )

    assert complete_response.status_code == 200
    artifacts = db_session.query(Artifact).filter_by(build_id=build.id).all()
    log_artifacts = [artifact for artifact in artifacts if artifact.artifact_type == "log"]
    assert len(log_artifacts) == 2
    assert {artifact.file_name for artifact in log_artifacts} == {"runner.log", "xcode.log"}


def test_runner_artifact_upload_rejects_unknown_type(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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

    response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/artifacts",
        headers=_runner_headers(),
        data={"runnerId": "runner-mac-1", "artifactType": "other"},
        files={"file": ("other.bin", b"content", "application/octet-stream")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_artifact_type"
    assert db_session.query(Artifact).filter_by(build_id=build.id).count() == 0


def test_runner_event_rejects_terminal_lifecycle_status(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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

    response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/events",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "type": "build_finished",
            "message": "done",
            "lifecycleStatus": "succeeded",
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_runner_event_lifecycle_status",
            "message": "Runner event lifecycle_status 只支持非终态构建状态",
            "detail": {"field": "lifecycle_status", "retryable": False},
        }
    }
    db_session.refresh(build)
    assert build.lifecycle_status == "assigned"
    assert db_session.query(BuildEvent).filter_by(build_id=build.id).count() == 0


def test_runner_event_redacts_message_and_payload_before_persisting(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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

    response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/events",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "type": "building",
            "message": "token=super-secret",
            "payload": {
                "nested": "password=hunter2",
                "key": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----",
            },
        },
    )

    assert response.status_code == 200
    event = db_session.query(BuildEvent).filter_by(build_id=build.id).one()
    persisted = f"{event.message} {event.payload_json}"
    assert "super-secret" not in persisted
    assert "hunter2" not in persisted
    assert "PRIVATE KEY" not in persisted
    assert "[REDACTED]" in persisted


def test_runner_complete_redacts_runner_supplied_fields_before_persisting(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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

    response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/complete",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "status": "needs_human",
            "note": "token=note-secret",
            "failureClassification": "missing_artifacts",
            "failureSummary": "password=summary-secret",
            "humanAction": "private_key=action-secret",
        },
    )

    assert response.status_code == 200
    db_session.refresh(build)
    persisted = f"{build.note} {build.failure_summary} {build.human_action}"
    assert "note-secret" not in persisted
    assert "summary-secret" not in persisted
    assert "action-secret" not in persisted
    assert persisted.count("[REDACTED]") == 3


@pytest.mark.parametrize(
    ("failure_classification", "expected"),
    [
        ("token=secret", "runner_reported_failure"),
        ("-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----", "runner_reported_failure"),
    ],
)
def test_runner_complete_sanitizes_failure_classification_before_persisting(
    client: TestClient,
    db_session: Session,
    failure_classification: str,
    expected: str,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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

    response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/complete",
        headers=_runner_headers(),
        json={
            "runnerId": "runner-mac-1",
            "status": "needs_human",
            "failureClassification": failure_classification,
        },
    )

    assert response.status_code == 200
    db_session.refresh(build)
    assert build.failure_classification == expected
    assert "secret" not in (build.failure_classification or "")
    assert "PRIVATE KEY" not in (build.failure_classification or "")


def test_runner_complete_rejects_success_without_required_artifacts(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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


def test_runner_complete_rejects_invalid_terminal_status(
    client: TestClient,
    db_session: Session,
) -> None:
    app = _create_app(db_session)
    build = _create_agent_build(db_session, app=app)
    _provision_runner_record(db_session)
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

    response = client.post(
        f"/admin/api/build-runners/builds/{build.id}/complete",
        headers=_runner_headers(),
        json={"runnerId": "runner-mac-1", "status": "done"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_runner_complete_status",
            "message": "status 必须是受支持的终态构建状态",
            "detail": {"field": "status", "retryable": False},
        }
    }
    db_session.refresh(build)
    assert build.lifecycle_status == "assigned"
    assert build.finished_at is None
    runner = db_session.get(BuildRunner, "runner-mac-1")
    assert runner is not None
    assert runner.current_build_id == build.id
