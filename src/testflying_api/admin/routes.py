from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from testflying_api.admin.security import require_admin
from testflying_api.admin.view_models import (
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
)
from testflying_api.database import get_db_session
from testflying_api.errors import ApiError
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
        _context(request, active="uploads", upload=upload),
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
