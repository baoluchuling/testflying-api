from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from testflying_api.admin.view_models import (
    environment_label,
    format_datetime,
    format_size,
    platform_label,
)
from testflying_api.admin_api.errors import AdminApiError
from testflying_api.admin_api.schemas import (
    AppDetailState,
    BuildAppSummary,
    BuildArtifactItem,
    BuildItem,
    BuildSettingItem,
)
from testflying_api.domain import (
    ArtifactType,
    BuildLifecycleStatus,
    channel_for_environment,
    normalize_environment,
)
from testflying_api.errors import ApiError
from testflying_api.schema import App, AppBuildSetting, Artifact, Build, BuildEvent, BuildRunner
from testflying_api.storage import ArtifactStorage

_CREDENTIAL_REF_MAX_LENGTH = 120
_CREDENTIAL_REF_ID_MAX_LENGTH = 40
_PEM_MARKER_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", re.IGNORECASE)
_JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")
_HEX_SECRET_RE = re.compile(r"^[A-Fa-f0-9]{32,}$")
_TOKEN_PREFIXES = ("ghp_", "gho_", "github_pat_", "glpat-", "sk-", "xoxb-", "xoxp-")
_SECRET_WORD_RE = re.compile(r"(secret|token|apikey|api_key|password|passwd|private[_-]?key)", re.I)
_CREDENTIAL_REF_ID_RE = re.compile(
    r"^(?:git|ios|android|apple|google|keystore|certificate|provisioning|signing|runner|mac)"
    r"-[a-z0-9]+(?:-[a-z0-9]+)*$"
)
_RUNNER_REQUIRED_ARTIFACTS = {
    ArtifactType.PACKAGE.value,
    ArtifactType.SYMBOLS.value,
    ArtifactType.REPORT.value,
    ArtifactType.LOG.value,
}
_TERMINAL_BUILD_LIFECYCLE_STATUSES = {
    BuildLifecycleStatus.SUCCEEDED.value,
    BuildLifecycleStatus.FAILED.value,
    BuildLifecycleStatus.NEEDS_HUMAN.value,
    BuildLifecycleStatus.CANCELLED.value,
}
_RUNNER_EVENT_LIFECYCLE_STATUSES = {
    status.value for status in BuildLifecycleStatus if status.value not in _TERMINAL_BUILD_LIFECYCLE_STATUSES
}


def app_or_404(session: Session, app_id: str) -> App:
    app = session.get(App, app_id)
    if app is None:
        raise ApiError("app_not_found", "应用不存在", status_code=404)
    return app


def list_app_builds(session: Session, app_id: str) -> list[Build]:
    return list(
        session.scalars(
            select(Build)
            .where(Build.app_id == app_id)
            .options(joinedload(Build.app), selectinload(Build.artifacts))
            .order_by(Build.uploaded_at.desc())
        )
    )


def settings_by_environment(session: Session, app_id: str) -> dict[str, AppBuildSetting]:
    settings = session.scalars(select(AppBuildSetting).where(AppBuildSetting.app_id == app_id))
    return {item.environment: item for item in settings}


def app_detail_state(session: Session, app_id: str) -> AppDetailState:
    app = app_or_404(session, app_id)
    settings = settings_by_environment(session, app.id)
    return AppDetailState(
        app=_build_app_summary(app),
        builds=[build_item(build) for build in list_app_builds(session, app.id)],
        settings={
            "development": build_setting_item(settings.get("development")),
            "production": build_setting_item(settings.get("production")),
        },
    )


def _parse_environment(value: str) -> str:
    try:
        return normalize_environment(value).value
    except ValueError as error:
        raise ApiError(
            "invalid_environment",
            "environment 必须是 development 或 production",
            status_code=422,
        ) from error


def save_build_setting(
    session: Session,
    *,
    app_id: str,
    environment: str,
    git_url: str,
    repo_subpath: str,
    runner_labels: list[str],
    credential_refs: dict[str, str],
    artifact_type: str,
    optional_defaults: dict[str, object],
) -> AppBuildSetting:
    app_or_404(session, app_id)
    normalized_environment = _parse_environment(environment)
    normalized_git_url = _require_non_blank(git_url, field="git_url", label="git_url")
    normalized_artifact_type = _require_non_blank(
        artifact_type,
        field="artifact_type",
        label="artifact_type",
    )
    normalized_credential_refs = _normalize_credential_refs(credential_refs)
    existing = session.scalar(
        select(AppBuildSetting).where(
            AppBuildSetting.app_id == app_id,
            AppBuildSetting.environment == normalized_environment,
        )
    )
    setting = existing or AppBuildSetting(
        id=f"build-setting-{app_id}-{normalized_environment}-{uuid4().hex[:8]}",
        app_id=app_id,
        environment=normalized_environment,
    )
    setting.git_url = normalized_git_url
    setting.repo_subpath = repo_subpath.strip()
    setting.runner_labels_json = [label.strip() for label in runner_labels if label.strip()]
    setting.credential_refs_json = normalized_credential_refs
    setting.artifact_type = normalized_artifact_type
    setting.optional_defaults_json = dict(optional_defaults)
    setting.updated_at = datetime.now(UTC)
    session.add(setting)
    session.commit()
    return setting


def create_agent_build(
    session: Session,
    *,
    app_id: str,
    environment: str,
    git_url: str,
    git_ref: str,
    repo_subpath: str,
    runner_labels: list[str],
    credential_refs: dict[str, str],
    artifact_type: str,
) -> Build:
    app = app_or_404(session, app_id)
    normalized_environment = _parse_environment(environment)
    normalized_git_url = _require_non_blank(git_url, field="git_url", label="git_url")
    normalized_git_ref = _require_non_blank(git_ref, field="git_ref", label="git_ref")
    normalized_artifact_type = _require_non_blank(
        artifact_type,
        field="artifact_type",
        label="artifact_type",
    )
    normalized_credential_refs = _normalize_credential_refs(credential_refs)
    build = Build(
        id=f"build-agent-{uuid4().hex[:12]}",
        app_id=app.id,
        version=None,
        build_number=None,
        channel=channel_for_environment(normalized_environment),
        environment=normalized_environment,
        requested_environment=normalized_environment,
        platform=app.platform,
        source="agent",
        lifecycle_status="queued",
        git_url=normalized_git_url,
        git_ref=normalized_git_ref,
        runner_labels_json={
            "required": [label.strip() for label in runner_labels if label.strip()],
            "repoSubpath": repo_subpath.strip(),
            "credentialRefs": normalized_credential_refs,
            "artifactType": normalized_artifact_type,
        },
        attempt_count=0,
        note="",
        status="pending",
        uploaded_at=datetime.now(UTC),
    )
    session.add(build)
    session.commit()
    return session.scalars(
        select(Build)
        .where(Build.id == build.id)
        .options(joinedload(Build.app), selectinload(Build.artifacts))
    ).one()


def register_runner(
    session: Session,
    *,
    runner_id: str,
    name: str,
    token: str,
    labels: list[str],
    version: str,
    package_agent_version: str,
    capabilities: dict[str, object],
) -> BuildRunner:
    runner = session.get(BuildRunner, runner_id)
    normalized_token = _require_non_blank(token, field="token", label="token")
    if runner is not None and runner.token_hash != normalized_token:
        raise ApiError("invalid_runner_token", "Runner token 不正确", status_code=401)
    runner = runner or BuildRunner(id=runner_id)
    runner.name = _require_non_blank(name, field="name", label="name")
    runner.token_hash = normalized_token
    runner.labels_json = [label.strip() for label in labels if label.strip()]
    runner.capabilities_json = dict(capabilities)
    runner.status = "busy" if runner.current_build_id else "online"
    runner.version = version.strip()
    runner.package_agent_version = package_agent_version.strip()
    runner.last_seen_at = datetime.now(UTC)
    session.add(runner)
    session.commit()
    return runner


def heartbeat_runner(
    session: Session,
    *,
    runner_id: str,
    name: str,
    token: str,
    labels: list[str],
    version: str,
    package_agent_version: str,
    capabilities: dict[str, object],
) -> BuildRunner:
    return register_runner(
        session,
        runner_id=runner_id,
        name=name,
        token=token,
        labels=labels,
        version=version,
        package_agent_version=package_agent_version,
        capabilities=capabilities,
    )


def poll_runner_build(session: Session, *, runner_id: str, token: str) -> Build | None:
    runner = _runner_or_401(session, runner_id=runner_id, token=token)
    runner.last_seen_at = datetime.now(UTC)
    if runner.current_build_id:
        runner.status = "busy"
        session.add(runner)
        session.commit()
        return None

    runner_platforms = {
        str(item).strip()
        for item in (runner.capabilities_json or {}).get("platforms", [])
        if str(item).strip()
    }
    queued_builds = session.scalars(
        select(Build)
        .where(
            Build.source == "agent",
            Build.lifecycle_status == BuildLifecycleStatus.QUEUED.value,
            Build.attempt_count < 5,
        )
        .order_by(Build.uploaded_at.asc())
    )
    runner_labels = set(runner.labels_json or [])
    for build in queued_builds:
        required_labels = set((build.runner_labels_json or {}).get("required", []))
        if required_labels and not required_labels.issubset(runner_labels):
            continue
        if build.platform not in runner_platforms:
            continue
        build.lifecycle_status = BuildLifecycleStatus.ASSIGNED.value
        build.runner_id = runner.id
        build.attempt_count += 1
        build.started_at = build.started_at or datetime.now(UTC)
        runner.current_build_id = build.id
        runner.status = "busy"
        session.add_all([build, runner])
        session.commit()
        return _build_with_relations(session, build.id)

    runner.status = "online"
    session.add(runner)
    session.commit()
    return None


def append_build_event(
    session: Session,
    *,
    build_id: str,
    runner_id: str,
    token: str,
    event_type: str,
    message: str,
    lifecycle_status: str | None = None,
    payload: dict[str, object] | None = None,
) -> BuildEvent:
    build, runner = _runner_build_pair(session, build_id=build_id, runner_id=runner_id, token=token)
    normalized_type = _require_non_blank(event_type, field="type", label="type")
    normalized_message = _require_non_blank(message, field="message", label="message")
    normalized_lifecycle_status = _normalize_runner_event_lifecycle_status(lifecycle_status)
    event = BuildEvent(
        id=f"build-event-{uuid4().hex[:12]}",
        build_id=build.id,
        runner_id=runner.id,
        type=normalized_type,
        message=normalized_message,
        payload_json=dict(payload or {}),
    )
    if normalized_lifecycle_status is not None:
        build.lifecycle_status = normalized_lifecycle_status
    build.started_at = build.started_at or datetime.now(UTC)
    runner.last_seen_at = datetime.now(UTC)
    session.add_all([event, build, runner])
    session.commit()
    return event


def upload_build_artifact(
    session: Session,
    *,
    storage: ArtifactStorage,
    build_id: str,
    runner_id: str,
    token: str,
    artifact_type: str,
    file_name: str,
    content: bytes,
    content_type: str,
) -> Artifact:
    build, runner = _runner_build_pair(session, build_id=build_id, runner_id=runner_id, token=token)
    normalized_type = _require_non_blank(
        artifact_type,
        field="artifact_type",
        label="artifact_type",
    ).lower()
    stored = storage.save(
        build.id,
        file_name=file_name,
        content=content,
        content_type=content_type or "application/octet-stream",
    )
    artifact = session.scalar(
        select(Artifact).where(
            Artifact.build_id == build.id,
            Artifact.artifact_type == normalized_type,
        )
    )
    if artifact is None:
        artifact = Artifact(
            id=f"artifact-{build.id}-{normalized_type}",
            build_id=build.id,
            artifact_type=normalized_type,
            file_name=file_name,
            content_type=content_type or "application/octet-stream",
            storage_backend=storage.backend,
            storage_key=stored.storage_key,
            download_url=stored.download_url,
            manifest_url=None,
            install_url=(
                stored.download_url if normalized_type == ArtifactType.PACKAGE.value else ""
            ),
            size_bytes=len(content),
            metadata_json={"source": "runner", "runnerId": runner.id},
        )
    else:
        if artifact.storage_key != stored.storage_key:
            storage.delete(artifact.storage_key)
        artifact.file_name = file_name
        artifact.content_type = content_type or "application/octet-stream"
        artifact.storage_backend = storage.backend
        artifact.storage_key = stored.storage_key
        artifact.download_url = stored.download_url
        artifact.manifest_url = None
        artifact.install_url = (
            stored.download_url if normalized_type == ArtifactType.PACKAGE.value else ""
        )
        artifact.size_bytes = len(content)
        artifact.metadata_json = {"source": "runner", "runnerId": runner.id}
    build.lifecycle_status = BuildLifecycleStatus.UPLOADING_ARTIFACTS.value
    runner.last_seen_at = datetime.now(UTC)
    event = BuildEvent(
        id=f"build-event-{uuid4().hex[:12]}",
        build_id=build.id,
        runner_id=runner.id,
        type="artifact_uploaded",
        message=f"{normalized_type} uploaded",
        payload_json={"artifactType": normalized_type, "fileName": file_name},
    )
    session.add_all([artifact, build, runner, event])
    session.commit()
    return artifact


def complete_runner_build(
    session: Session,
    *,
    build_id: str,
    runner_id: str,
    token: str,
    status: str,
    version: str | None = None,
    build_number: str | None = None,
    note: str | None = None,
    failure_classification: str | None = None,
    failure_summary: str | None = None,
    human_action: str | None = None,
) -> Build:
    build, runner = _runner_build_pair(session, build_id=build_id, runner_id=runner_id, token=token)
    normalized_status = _normalize_complete_status(status)
    artifacts = session.scalars(select(Artifact).where(Artifact.build_id == build.id)).all()
    if normalized_status == BuildLifecycleStatus.SUCCEEDED.value:
        existing_types = {artifact.artifact_type for artifact in artifacts}
        missing = sorted(_RUNNER_REQUIRED_ARTIFACTS - existing_types)
        if missing:
            raise ApiError(
                "missing_required_artifacts",
                f"自动构建缺少必需制品: {', '.join(missing)}",
                status_code=422,
            )
        build.status = "available"
    elif normalized_status == BuildLifecycleStatus.NEEDS_HUMAN.value:
        build.status = "pending"
    else:
        build.status = "failed"
    if version is not None and version.strip():
        build.version = version.strip()
    if build_number is not None and build_number.strip():
        build.build_number = build_number.strip()
    if note is not None and note.strip():
        build.note = note.strip()
    build.lifecycle_status = normalized_status
    build.failure_classification = (
        failure_classification.strip() if failure_classification else None
    )
    build.failure_summary = failure_summary.strip() if failure_summary else None
    build.human_action = human_action.strip() if human_action else None
    build.started_at = _ensure_utc_datetime(build.started_at) or datetime.now(UTC)
    build.finished_at = datetime.now(UTC)
    build.duration_seconds = int((build.finished_at - build.started_at).total_seconds())
    runner.current_build_id = None
    runner.status = "online"
    runner.last_seen_at = datetime.now(UTC)
    event = BuildEvent(
        id=f"build-event-{uuid4().hex[:12]}",
        build_id=build.id,
        runner_id=runner.id,
        type="complete",
        message=f"build {normalized_status}",
        payload_json={
            "status": normalized_status,
            "version": build.version or "",
            "buildNumber": build.build_number or "",
        },
    )
    session.add_all([build, runner, event])
    session.commit()
    return _build_with_relations(session, build.id)


def build_item(build: Build) -> BuildItem:
    artifact = build.package_artifact()
    app = build.app
    if app is None:
        raise AdminApiError("build_app_not_found", "构建关联的应用不存在", status_code=500)
    return BuildItem(
        id=build.id,
        app=_build_app_summary(app),
        version=build.version or "",
        build_number=build.build_number or "",
        source=build.source,
        lifecycle_status=build.lifecycle_status,
        git_ref=build.git_ref or "",
        platform=build.platform,
        platform_label=platform_label(build.platform),
        environment=build.environment,
        environment_label=environment_label(build.environment),
        status=build.status,
        note=build.note or "",
        min_os_version=build.min_os_version or "",
        uploaded_at=_iso_datetime(build.uploaded_at),
        uploaded_at_label=format_datetime(build.uploaded_at),
        expires_at=_optional_iso_datetime(build.expires_at),
        expires_at_label=format_datetime(build.expires_at),
        artifact=(
            BuildArtifactItem(
                file_name=artifact.file_name,
                size_label=format_size(artifact.size_bytes),
                install_url=artifact.install_url,
                download_url=artifact.download_url,
                manifest_url=artifact.manifest_url,
            )
            if artifact
            else None
        ),
    )


def build_setting_item(setting: AppBuildSetting | None) -> BuildSettingItem | None:
    if setting is None:
        return None
    return BuildSettingItem(
        environment=setting.environment,
        git_url=setting.git_url,
        repo_subpath=setting.repo_subpath,
        runner_labels=list(setting.runner_labels_json or []),
        credential_refs=dict(setting.credential_refs_json or {}),
        artifact_type=setting.artifact_type,
        optional_defaults=dict(setting.optional_defaults_json or {}),
        updated_at_label=format_datetime(setting.updated_at),
    )


def _build_app_summary(app: App) -> BuildAppSummary:
    return BuildAppSummary(
        id=app.id,
        name=app.name,
        bundle_identifier=app.bundle_identifier,
        platform=app.platform,
        icon_color=app.icon_color,
        icon_text=app.name[:2].upper(),
    )


def _iso_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _optional_iso_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _iso_datetime(value)


def _require_non_blank(value: str, *, field: str, label: str) -> str:
    normalized = value.strip()
    if normalized:
        return normalized
    raise ApiError(
        "invalid_build_input",
        f"{label} 不能为空",
        status_code=422,
        extra={"field": field},
    )


def _normalize_credential_refs(credential_refs: dict[str, str]) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key, raw_value in credential_refs.items():
        normalized[key] = _validate_credential_ref(key=key, value=raw_value)
    return normalized


def _validate_credential_ref(*, key: str, value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise _invalid_credential_ref(key, "credential ref 不能为空")
    if "\n" in value or "\r" in value:
        raise _invalid_credential_ref(key, "credential ref 不能包含换行")
    if len(normalized) > _CREDENTIAL_REF_MAX_LENGTH:
        raise _invalid_credential_ref(key, "credential ref 过长")
    lowered = normalized.lower()
    if _PEM_MARKER_RE.search(value):
        raise _invalid_credential_ref(key, "credential ref 不能是私钥内容")
    if normalized.startswith(_TOKEN_PREFIXES) or _JWT_RE.fullmatch(normalized):
        raise _invalid_credential_ref(key, "credential ref 不能是 token 或密钥")
    if _HEX_SECRET_RE.fullmatch(normalized) and any(char.isalpha() for char in normalized):
        raise _invalid_credential_ref(key, "credential ref 不能是 token 或密钥")
    if _SECRET_WORD_RE.search(lowered) and len(normalized) >= 16:
        raise _invalid_credential_ref(key, "credential ref 不能是 secret 文本")
    if len(normalized) > _CREDENTIAL_REF_ID_MAX_LENGTH:
        raise _invalid_credential_ref(key, "credential ref 过长")
    if not _CREDENTIAL_REF_ID_RE.fullmatch(normalized):
        raise _invalid_credential_ref(
            key,
            "credential ref 必须是受支持前缀的小写 kebab-case 标识",
        )
    return normalized


def _invalid_credential_ref(key: str, message: str) -> ApiError:
    return ApiError(
        "invalid_credential_ref",
        f"{key}: {message}",
        status_code=422,
        extra={"field": "credential_refs", "key": key},
    )


def _build_with_relations(session: Session, build_id: str) -> Build:
    return session.scalars(
        select(Build)
        .where(Build.id == build_id)
        .options(joinedload(Build.app), selectinload(Build.artifacts))
    ).one()


def _normalize_runner_event_lifecycle_status(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = _require_non_blank(
        value,
        field="lifecycle_status",
        label="lifecycle_status",
    ).lower()
    if normalized not in _RUNNER_EVENT_LIFECYCLE_STATUSES:
        raise ApiError(
            "invalid_runner_event_lifecycle_status",
            "Runner event lifecycle_status 只支持非终态构建状态",
            status_code=422,
            extra={"field": "lifecycle_status"},
        )
    return normalized


def _normalize_complete_status(value: str) -> str:
    normalized = _require_non_blank(value, field="status", label="status").lower()
    if normalized not in _TERMINAL_BUILD_LIFECYCLE_STATUSES:
        raise ApiError(
            "invalid_runner_complete_status",
            "status 必须是受支持的终态构建状态",
            status_code=422,
            extra={"field": "status"},
        )
    return normalized


def _runner_or_401(session: Session, *, runner_id: str, token: str) -> BuildRunner:
    runner = session.get(BuildRunner, runner_id)
    if runner is None or runner.token_hash != token:
        raise ApiError("invalid_runner_token", "Runner token 不正确", status_code=401)
    return runner


def _runner_build_pair(
    session: Session,
    *,
    build_id: str,
    runner_id: str,
    token: str,
) -> tuple[Build, BuildRunner]:
    runner = _runner_or_401(session, runner_id=runner_id, token=token)
    build = session.get(Build, build_id)
    if build is None:
        raise ApiError("build_not_found", "构建不存在", status_code=404)
    if build.runner_id != runner.id or runner.current_build_id != build.id:
        raise ApiError("runner_build_mismatch", "Runner 未持有该构建", status_code=409)
    return build, runner


def _ensure_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
