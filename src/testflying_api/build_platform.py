from __future__ import annotations

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
from testflying_api.domain import channel_for_environment, normalize_environment
from testflying_api.errors import ApiError
from testflying_api.schema import App, AppBuildSetting, Build


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
    setting.git_url = git_url.strip()
    setting.repo_subpath = repo_subpath.strip()
    setting.runner_labels_json = [label.strip() for label in runner_labels if label.strip()]
    setting.credential_refs_json = dict(credential_refs)
    setting.artifact_type = artifact_type.strip()
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
        git_url=git_url.strip(),
        git_ref=git_ref.strip(),
        runner_labels_json={
            "required": [label.strip() for label in runner_labels if label.strip()],
            "repoSubpath": repo_subpath.strip(),
            "credentialRefs": dict(credential_refs),
            "artifactType": artifact_type.strip(),
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
