from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from testflying_api.admin.security import require_admin
from testflying_api.admin.view_models import (
    account_detail_context,
    dashboard_context,
    environment_label,
    format_datetime,
    format_size,
    list_accounts,
    list_apps,
    list_builds,
    list_devices,
    list_notifications,
    platform_label,
    release_notes_context,
)
from testflying_api.database import get_db_session
from testflying_api.errors import ApiError
from testflying_api.models import UploadResponse
from testflying_api.schema import App
from testflying_api.store_sync import (
    DEFAULT_LOCALE,
    save_connector,
    save_release_note_draft,
    sync_release_notes,
)
from testflying_api.upload_service import create_package_upload

router = APIRouter(prefix="/admin", tags=["admin"])
SessionDep = Annotated[Session, Depends(get_db_session)]
AdminDep = Annotated[None, Depends(require_admin)]

templates = Jinja2Templates(directory=str(Path(__file__).parents[1] / "templates"))
templates.env.filters["datetime"] = format_datetime
templates.env.filters["size"] = format_size
templates.env.filters["environment"] = environment_label
templates.env.filters["platform"] = platform_label


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: SessionDep, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        _context(request, active="dashboard", **dashboard_context(session)),
    )


@router.get("/apps", response_class=HTMLResponse)
def apps_page(request: Request, session: SessionDep, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/apps.html",
        _context(request, active="apps", apps=list_apps(session)),
    )


@router.get("/builds", response_class=HTMLResponse)
def builds_page(request: Request, session: SessionDep, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/builds.html",
        _context(request, active="builds", builds=list_builds(session)),
    )


@router.get("/uploads", response_class=HTMLResponse)
def upload_page(request: Request, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/upload.html",
        _context(request, active="uploads"),
    )


@router.post("/uploads", response_class=HTMLResponse)
async def upload_package(
    request: Request,
    session: SessionDep,
    _: AdminDep,
    file: Annotated[UploadFile, File()],
    platform: Annotated[str, Form()],
    environment: Annotated[str, Form()],
    changelog: Annotated[str, Form()] = "",
    app_name: Annotated[str | None, Form(alias="appName")] = None,
) -> HTMLResponse:
    try:
        upload = create_package_upload(
            session=session,
            storage=request.app.state.artifact_storage,
            content=await file.read(),
            file_name=file.filename or "",
            content_type=file.content_type or "",
            platform=platform,
            environment=environment,
            changelog=changelog,
            app_name=app_name,
        )
    except ApiError as error:
        session.rollback()
        return templates.TemplateResponse(
            request,
            "admin/upload.html",
            _context(request, active="uploads", error=error.message),
            status_code=error.status_code,
        )

    return templates.TemplateResponse(
        request,
        "admin/upload.html",
        _context(
            request,
            active="uploads",
            upload=upload,
            upload_details=_upload_details(session, upload),
        ),
    )


@router.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request, session: SessionDep, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/devices.html",
        _context(request, active="devices", devices=list_devices(session)),
    )


@router.get("/developer-accounts", response_class=HTMLResponse)
def developer_accounts_page(
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/accounts.html",
        _context(request, active="developer-accounts", accounts=list_accounts(session)),
    )


@router.get("/developer-accounts/{account_id}", response_class=HTMLResponse)
def developer_account_detail_page(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    context = account_detail_context(session, account_id)
    if context["account"] is None:
        raise ApiError("account_not_found", "开发者账号不存在", status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/account_detail.html",
        _context(request, active="developer-accounts", **context),
    )


@router.post("/developer-accounts/{account_id}/connector", response_class=HTMLResponse)
def save_connector_page(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    name: Annotated[str, Form()],
    base_url: Annotated[str, Form(alias="baseUrl")],
    auth_token: Annotated[str, Form(alias="authToken")] = "",
) -> HTMLResponse:
    try:
        save_connector(
            session,
            account_id=account_id,
            name=name,
            base_url=base_url,
            auth_token=auth_token,
        )
        session.commit()
        context = account_detail_context(session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", success="Connector 已保存", **context),
        )
    except ApiError as error:
        session.rollback()
        context = account_detail_context(session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.get(
    "/developer-accounts/{account_id}/apps/{app_id}/release-notes",
    response_class=HTMLResponse,
)
def release_notes_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    version: str | None = None,
    locale: str = DEFAULT_LOCALE,
) -> HTMLResponse:
    context = release_notes_context(
        session,
        account_id=account_id,
        app_id=app_id,
        version=version,
        locale=locale,
    )
    if context["account"] is None or context["app"] is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
    session.commit()
    return templates.TemplateResponse(
        request,
        "admin/release_notes.html",
        _context(request, active="developer-accounts", **context),
    )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/release-notes",
    response_class=HTMLResponse,
)
def save_release_notes_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    version: Annotated[str, Form()],
    locale: Annotated[str, Form()] = DEFAULT_LOCALE,
    release_notes: Annotated[str, Form(alias="releaseNotes")] = "",
) -> HTMLResponse:
    try:
        save_release_note_draft(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
            release_notes=release_notes,
        )
        session.commit()
        context = release_notes_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/release_notes.html",
            _context(request, active="developer-accounts", success="草稿已保存", **context),
        )
    except ApiError as error:
        session.rollback()
        context = release_notes_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
        )
        return templates.TemplateResponse(
            request,
            "admin/release_notes.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/release-notes/sync",
    response_class=HTMLResponse,
)
def sync_release_notes_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    version: Annotated[str, Form()],
    locale: Annotated[str, Form()] = DEFAULT_LOCALE,
    release_notes: Annotated[str, Form(alias="releaseNotes")] = "",
) -> HTMLResponse:
    try:
        sync_run = sync_release_notes(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
            release_notes=release_notes,
            actor="admin",
        )
        session.commit()
        context = release_notes_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
        )
        session.commit()
        message = "版本说明已同步" if sync_run.status == "succeeded" else "同步已完成"
        return templates.TemplateResponse(
            request,
            "admin/release_notes.html",
            _context(request, active="developer-accounts", success=message, **context),
        )
    except ApiError as error:
        session.rollback()
        context = release_notes_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/release_notes.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, session: SessionDep, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/notifications.html",
        _context(request, active="notifications", notifications=list_notifications(session)),
    )


def _context(request: Request, *, active: str, **values: object) -> dict[str, object]:
    return {
        "request": request,
        "active": active,
        "nav_items": [
            ("dashboard", "/admin", "总览"),
            ("uploads", "/admin/uploads", "上传"),
            ("apps", "/admin/apps", "应用"),
            ("builds", "/admin/builds", "构建"),
            ("devices", "/admin/devices", "设备"),
            ("developer-accounts", "/admin/developer-accounts", "开发者账号"),
            ("notifications", "/admin/notifications", "通知"),
        ],
        **values,
    }


def _upload_details(session: Session, upload: UploadResponse) -> dict[str, str]:
    app = session.get(App, upload.app.id)
    return {
        "app_name": upload.app.name,
        "bundle_identifier": app.bundle_identifier if app else "-",
        "platform": upload.install_info.platform,
        "environment": upload.build.environment,
        "version": upload.build.version,
        "build_number": upload.build.build_number,
    }
