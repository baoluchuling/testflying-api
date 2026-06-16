from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from testflying_api.catalog_repository import CatalogRepository
from testflying_api.catalog_service import CatalogService
from testflying_api.database import get_db_session
from testflying_api.domain import channel_for_environment, normalize_environment, normalize_platform
from testflying_api.errors import ApiError
from testflying_api.manifest import generate_ios_manifest, itms_services_url
from testflying_api.models import UploadResponse
from testflying_api.package_parser import (
    PackageMetadata,
    PackageParseError,
    android_metadata_from_upload,
    parse_ipa_metadata,
)
from testflying_api.schema import App, Artifact, Build, Device, DeviceBuildVisibility, Notification

router = APIRouter(prefix="/v1/test-distribution", tags=["uploads"])
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.post("/uploads", response_model=UploadResponse)
async def upload_package(
    request: Request,
    session: SessionDep,
    file: Annotated[UploadFile, File()],
    platform: Annotated[str, Form()],
    environment: Annotated[str, Form()],
    changelog: Annotated[str, Form()] = "",
    package_name: Annotated[str | None, Form(alias="packageName")] = None,
    app_name: Annotated[str | None, Form(alias="appName")] = None,
    version: Annotated[str | None, Form()] = None,
    build_number: Annotated[str | None, Form(alias="buildNumber")] = None,
) -> UploadResponse:
    normalized_platform = _parse_platform(platform)
    normalized_environment = _parse_environment(environment)
    content = await file.read()
    if not content:
        raise ApiError("empty_package", "上传包不能为空", status_code=422)

    metadata = _metadata_for_upload(
        platform=normalized_platform,
        content=content,
        package_name=package_name,
        app_name=app_name,
        version=version,
        build_number=build_number,
    )
    app = _upsert_app(session, metadata, environment=normalized_environment)
    build = _create_build(
        session,
        app,
        metadata,
        environment=normalized_environment,
        changelog=changelog,
    )
    storage = request.app.state.artifact_storage
    package_file_name = file.filename or _default_file_name(metadata)
    content_type = file.content_type or _content_type_for_platform(normalized_platform)
    saved_package = storage.save(
        build.id,
        package_file_name,
        content,
        content_type=content_type,
    )

    manifest_url = None
    install_url = saved_package.download_url
    if normalized_platform == "ios":
        manifest_bytes = generate_ios_manifest(
            download_url=saved_package.download_url,
            bundle_identifier=metadata.bundle_identifier,
            version=metadata.version,
            title=metadata.app_name,
        )
        saved_manifest = storage.save(
            build.id,
            "manifest.plist",
            manifest_bytes,
            content_type="application/xml",
        )
        manifest_url = saved_manifest.download_url
        install_url = itms_services_url(manifest_url)

    session.add(
        Artifact(
            id=f"artifact-{build.id}",
            build_id=build.id,
            file_name=package_file_name,
            content_type=content_type,
            storage_backend=storage.backend,
            storage_key=saved_package.storage_key,
            download_url=saved_package.download_url,
            manifest_url=manifest_url,
            install_url=install_url,
            size_bytes=len(content),
        )
    )
    _grant_build_to_registered_devices(session, build)
    session.add(
        Notification(
            id=f"notice-{build.id}",
            type="build",
            section="新构建",
            icon_key="rocket",
            title=f"{metadata.app_name} {metadata.version} 已上传",
            subtitle=(
                f"{_environment_label(normalized_environment)} build "
                f"{metadata.build_number} 可以安装验证。"
            ),
            tag=_environment_label(normalized_environment),
            tag_color="#2478FF" if normalized_environment == "development" else "#20864A",
            app_id=app.id,
            build_id=build.id,
            created_at=datetime.now(UTC),
        )
    )
    session.commit()

    created_build = session.scalars(
        select(Build)
        .options(joinedload(Build.app), joinedload(Build.artifact))
        .where(Build.id == build.id)
    ).one()
    service = CatalogService(CatalogRepository(session))
    build_response = service.build_response(created_build)
    return UploadResponse(
        app=service.app_response(app),
        build=build_response,
        install_info=build_response.install_info,
    )


def _parse_platform(value: str) -> str:
    try:
        return normalize_platform(value).value
    except ValueError as error:
        raise ApiError(
            "invalid_platform",
            "platform 必须是 ios 或 android",
            status_code=422,
        ) from error


def _parse_environment(value: str) -> str:
    try:
        return normalize_environment(value).value
    except ValueError as error:
        raise ApiError(
            "invalid_environment",
            "environment 必须是 development 或 production",
            status_code=422,
        ) from error


def _metadata_for_upload(
    *,
    platform: str,
    content: bytes,
    package_name: str | None,
    app_name: str | None,
    version: str | None,
    build_number: str | None,
) -> PackageMetadata:
    try:
        if platform == "ios":
            return parse_ipa_metadata(content)
        return android_metadata_from_upload(
            package_name=package_name,
            app_name=app_name,
            version=version,
            build_number=build_number,
        )
    except PackageParseError as error:
        raise ApiError("invalid_package", str(error), status_code=422) from error


def _upsert_app(session: Session, metadata: PackageMetadata, *, environment: str) -> App:
    app = session.scalar(
        select(App).where(
            App.platform == metadata.platform,
            App.bundle_identifier == metadata.bundle_identifier,
        )
    )
    if app is not None:
        app.name = metadata.app_name
        app.default_channel = channel_for_environment(environment)
        return app

    app = App(
        id=f"app-{metadata.platform}-{_slug(metadata.bundle_identifier)}",
        name=metadata.app_name,
        bundle_identifier=metadata.bundle_identifier,
        platform=metadata.platform,
        default_channel=channel_for_environment(environment),
        icon_key="rocket" if metadata.platform == "ios" else "layers",
        icon_color="#2478FF" if metadata.platform == "ios" else "#B45309",
    )
    session.add(app)
    session.flush()
    return app


def _create_build(
    session: Session,
    app: App,
    metadata: PackageMetadata,
    *,
    environment: str,
    changelog: str,
) -> Build:
    build = Build(
        id=f"build-{_slug(metadata.bundle_identifier)}-{metadata.build_number}-{uuid4().hex[:8]}",
        app_id=app.id,
        version=metadata.version,
        build_number=metadata.build_number,
        channel=channel_for_environment(environment),
        environment=environment,
        platform=metadata.platform,
        uploaded_at=datetime.now(UTC),
        note=changelog,
        status="available",
    )
    session.add(build)
    session.flush()
    return build


def _grant_build_to_registered_devices(session: Session, build: Build) -> None:
    devices = session.scalars(select(Device).where(Device.platform == build.platform)).all()
    for device in devices:
        session.merge(DeviceBuildVisibility(device_id=device.id, build_id=build.id))


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or uuid4().hex[:8]


def _default_file_name(metadata: PackageMetadata) -> str:
    extension = "ipa" if metadata.platform == "ios" else "apk"
    return f"{_slug(metadata.app_name)}.{extension}"


def _content_type_for_platform(platform: str) -> str:
    if platform == "android":
        return "application/vnd.android.package-archive"
    return "application/octet-stream"


def _environment_label(environment: str) -> str:
    return "线上环境" if environment == "production" else "开发环境"
