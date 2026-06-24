from __future__ import annotations

import hashlib
import json
import re
import secrets
import zipfile
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from testflying_api.admin.security import require_admin
from testflying_api.admin.services import (
    ACCOUNT_STATUSES,
    bind_app_to_account,
    parse_admin_datetime,
    save_developer_account,
    unbind_app_from_account,
    update_bound_app_store_settings,
)
from testflying_api.admin.view_models import (
    account_detail_context,
    account_status_label,
    dashboard_context,
    environment_label,
    format_datetime,
    format_size,
    list_accounts,
    list_apps,
    list_builds,
    list_devices,
    list_notifications,
    marketing_page_context,
    platform_label,
    release_notes_context,
    store_metadata_context,
    upload_context,
)
from testflying_api.app_logs import build_app_log_connect_context
from testflying_api.database import get_db_session
from testflying_api.errors import ApiError
from testflying_api.models import UploadResponse
from testflying_api.schema import (
    App,
    DeveloperAccount,
    StoreAppMetadataDraft,
    StoreImageSuite,
    StoreImageSuiteLocale,
    StoreMarketingPageLocale,
)
from testflying_api.store_image_requirements import validate_store_image
from testflying_api.store_sync import (
    CURRENT_METADATA_VERSION,
    DEFAULT_CONTENT_SET_ID,
    DEFAULT_CONTENT_SET_NAME,
    DEFAULT_LOCALE,
    account_connector,
    check_connector_health,
    create_marketing_page,
    delete_marketing_page,
    duplicate_marketing_page,
    marketing_page_for_scope,
    marketing_page_locales,
    metadata_draft_for_scope,
    resolve_connector_base_url,
    save_connector,
    save_current_app_metadata_draft,
    save_marketing_page,
    save_release_note_draft,
    scoped_app,
    sync_current_app_metadata,
    sync_marketing_page,
    sync_release_notes,
)
from testflying_api.translation import translate_store_metadata_text
from testflying_api.upload_service import create_package_upload

router = APIRouter(prefix="/admin", tags=["admin"])
SessionDep = Annotated[Session, Depends(get_db_session)]
AdminDep = Annotated[None, Depends(require_admin)]
CONNECTOR_AUTO_CHECK_TTL = timedelta(minutes=5)
ADMIN_CSS_PATH = Path(__file__).parents[1] / "static" / "admin" / "admin.css"
ADMIN_ASSET_VERSION = hashlib.sha256(ADMIN_CSS_PATH.read_bytes()).hexdigest()[:12]


def preflight_title_label(preflight: object | None) -> str:
    return _preflight_copy(preflight)["title"]


def preflight_summary_label(preflight: object | None) -> str:
    return _preflight_copy(preflight)["summary"]


def preflight_action_label(preflight: object | None, platform: str = "") -> str:
    return _preflight_copy(preflight, platform=platform)["action"]


templates = Jinja2Templates(directory=str(Path(__file__).parents[1] / "templates"))
templates.env.filters["datetime"] = format_datetime
templates.env.filters["size"] = format_size
templates.env.filters["environment"] = environment_label
templates.env.filters["platform"] = platform_label
templates.env.filters["account_status"] = account_status_label
templates.env.filters["preflight_title"] = preflight_title_label
templates.env.filters["preflight_summary"] = preflight_summary_label
templates.env.filters["preflight_action"] = preflight_action_label


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


@router.get("/app-logs", response_class=HTMLResponse)
def app_logs_page(request: Request, _: AdminDep) -> HTMLResponse:
    context = build_app_log_connect_context(request)
    snapshot = request.app.state.app_log_hub.snapshot(limit=200)
    return templates.TemplateResponse(
        request,
        "admin/app_logs.html",
        _context(
            request,
            active="app-logs",
            connect=context,
            devices=snapshot.devices,
            logs=snapshot.logs,
            errors=snapshot.errors,
            cursor=snapshot.cursor,
        ),
    )


@router.get("/app-logs/events")
def app_logs_events(
    request: Request,
    _: AdminDep,
    cursor: int = 0,
    limit: int = 500,
) -> JSONResponse:
    snapshot = request.app.state.app_log_hub.snapshot(cursor=cursor, limit=limit)
    return JSONResponse(
        {
            "cursor": snapshot.cursor,
            "devices": snapshot.devices,
            "logs": snapshot.logs,
            "errors": snapshot.errors,
            "levels": list(("跟踪", "调试", "信息", "警告", "错误", "致命")),
        }
    )


@router.get("/app-logs/qr.svg")
def app_logs_qr(
    request: Request,
    _: AdminDep,
    host: str = "",
    port: str = "",
    name: str = "Mac",
) -> Response:
    import qrcode
    import qrcode.image.svg

    context = build_app_log_connect_context(request, host=host, port=port, name=name)
    image = qrcode.make(context["connect_url"], image_factory=qrcode.image.svg.SvgPathImage)
    stream = BytesIO()
    image.save(stream)
    return Response(
        content=stream.getvalue(),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/builds", response_class=HTMLResponse)
def builds_page(request: Request, session: SessionDep, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/builds.html",
        _context(request, active="builds", builds=list_builds(session)),
    )


@router.get("/uploads", response_class=HTMLResponse)
def upload_page(request: Request, session: SessionDep, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/upload.html",
        _context(request, active="uploads", **upload_context(session)),
    )


@router.get("/artifacts/{storage_key:path}")
def admin_artifact(
    storage_key: str,
    request: Request,
    _: AdminDep,
) -> Response:
    artifact = request.app.state.artifact_storage.read(storage_key)
    return Response(
        content=artifact.content,
        media_type=artifact.content_type,
        headers={"Cache-Control": "private, max-age=300"},
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
    developer_account_id: Annotated[str | None, Form(alias="developerAccountId")] = None,
    store_app_id: Annotated[str | None, Form(alias="storeAppId")] = None,
    store_package_name: Annotated[str | None, Form(alias="storePackageName")] = None,
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
            developer_account_id=developer_account_id,
            store_app_id=store_app_id,
            store_package_name=store_package_name,
        )
    except ApiError as error:
        session.rollback()
        return templates.TemplateResponse(
            request,
            "admin/upload.html",
            _context(request, active="uploads", error=error.message, **upload_context(session)),
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
            **upload_context(session),
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


@router.get("/developer-accounts/new", response_class=HTMLResponse)
def new_developer_account_page(request: Request, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/account_form.html",
        _context(
            request,
            active="developer-accounts",
            mode="create",
            account=None,
            statuses=ACCOUNT_STATUSES,
        ),
    )


@router.post("/developer-accounts", response_class=HTMLResponse)
def create_developer_account_page(
    request: Request,
    session: SessionDep,
    _: AdminDep,
    account_id: Annotated[str, Form(alias="accountId")],
    team_name: Annotated[str, Form(alias="teamName")],
    expires_at: Annotated[str, Form(alias="expiresAt")],
    status: Annotated[str, Form()],
    renewal_action_label: Annotated[str, Form(alias="renewalActionLabel")] = "去续费",
) -> HTMLResponse:
    try:
        account = save_developer_account(
            session,
            account_id=account_id,
            team_name=team_name,
            expires_at=parse_admin_datetime(expires_at),
            status=status,
            renewal_action_label=renewal_action_label,
        )
        session.commit()
        context = _account_detail_context(request, session, account.id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", success="开发者账号已保存", **context),
        )
    except ApiError as error:
        session.rollback()
        return templates.TemplateResponse(
            request,
            "admin/account_form.html",
            _context(
                request,
                active="developer-accounts",
                mode="create",
                account={
                    "id": account_id,
                    "team_name": team_name,
                    "expires_at": expires_at,
                    "status": status,
                    "renewal_action_label": renewal_action_label,
                },
                statuses=ACCOUNT_STATUSES,
                error=error.message,
            ),
            status_code=error.status_code,
        )


@router.get("/developer-accounts/{account_id}", response_class=HTMLResponse)
def developer_account_detail_page(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    _auto_check_connector(session, account_id)
    session.commit()
    context = _account_detail_context(request, session, account_id)
    if context["account"] is None:
        raise ApiError("account_not_found", "开发者账号不存在", status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/account_detail.html",
        _context(request, active="developer-accounts", **context),
    )


@router.get("/developer-accounts/{account_id}/edit", response_class=HTMLResponse)
def edit_developer_account_page(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    account = session.get(DeveloperAccount, account_id)
    if account is None:
        context = _account_detail_context(request, session, account_id)
        if context["account"] is None:
            raise ApiError("account_not_found", "开发者账号不存在", status_code=404)
        account = context["account"]
    return templates.TemplateResponse(
        request,
        "admin/account_form.html",
        _context(
            request,
            active="developer-accounts",
            mode="edit",
            account=account,
            statuses=ACCOUNT_STATUSES,
        ),
    )


@router.post("/developer-accounts/{account_id}", response_class=HTMLResponse)
def update_developer_account_page(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    team_name: Annotated[str, Form(alias="teamName")],
    expires_at: Annotated[str, Form(alias="expiresAt")],
    status: Annotated[str, Form()],
    renewal_action_label: Annotated[str, Form(alias="renewalActionLabel")] = "去续费",
) -> HTMLResponse:
    if session.get(DeveloperAccount, account_id) is None:
        raise ApiError("account_not_found", "开发者账号不存在", status_code=404)
    try:
        account = save_developer_account(
            session,
            account_id=account_id,
            team_name=team_name,
            expires_at=parse_admin_datetime(expires_at),
            status=status,
            renewal_action_label=renewal_action_label,
        )
        session.commit()
        context = _account_detail_context(request, session, account.id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", success="开发者账号已更新", **context),
        )
    except ApiError as error:
        session.rollback()
        account = {
            "id": account_id,
            "team_name": team_name,
            "expires_at": expires_at,
            "status": status,
            "renewal_action_label": renewal_action_label,
        }
        return templates.TemplateResponse(
            request,
            "admin/account_form.html",
            _context(
                request,
                active="developer-accounts",
                mode="edit",
                account=account,
                statuses=ACCOUNT_STATUSES,
                error=error.message,
            ),
            status_code=error.status_code,
        )


@router.post("/developer-accounts/{account_id}/connector", response_class=HTMLResponse)
def save_connector_page(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    name: Annotated[str, Form()],
    base_url: Annotated[str, Form(alias="baseUrl")] = "",
    auth_token: Annotated[str, Form(alias="authToken")] = "",
) -> HTMLResponse:
    try:
        save_connector(
            session,
            account_id=account_id,
            name=name,
            base_url=base_url,
            auth_token=auth_token,
            base_url_template=request.app.state.settings.connector_base_url_template,
        )
        session.commit()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", success="Connector 已保存", **context),
        )
    except ApiError as error:
        session.rollback()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.post("/developer-accounts/{account_id}/connector/windows-package")
async def generate_connector_windows_package(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    apple_issuer_id: Annotated[str, Form(alias="appleIssuerId")] = "",
    apple_key_id: Annotated[str, Form(alias="appleKeyId")] = "",
    apple_private_key: Annotated[UploadFile | None, File(alias="applePrivateKey")] = None,
    google_service_account: Annotated[UploadFile | None, File(alias="googleServiceAccount")] = None,
) -> Response:
    context = _account_detail_context(request, session, account_id)
    if context["account"] is None:
        raise ApiError("account_not_found", "开发者账号不存在", status_code=404)
    try:
        apple_file = await _read_optional_upload(apple_private_key)
        google_file = await _read_optional_upload(google_service_account)
        package = _build_windows_connector_package(
            account_id=account_id,
            platform=str(context["account_store_platform"]),
            center_url=_connector_center_url(request),
            apple_issuer_id=apple_issuer_id,
            apple_key_id=apple_key_id,
            apple_file=apple_file,
            google_file=google_file,
        )
        save_connector(
            session,
            account_id=account_id,
            name="Windows Active Connector",
            base_url=f"active://{account_id}",
            auth_token=package["token"],
        )
        session.commit()
    except ApiError as error:
        session.rollback()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )

    filename = f"testflying-connector-{_safe_filename(account_id)}-windows.zip"
    return Response(
        content=package["content"],
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/developer-accounts/{account_id}/connector/check", response_class=HTMLResponse)
def check_connector_page(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    try:
        result = check_connector_health(session, account_id=account_id)
        session.commit()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(
                request,
                active="developer-accounts",
                connector_check_result=result,
                **context,
            ),
            status_code=200 if result.ok else 502,
        )
    except ApiError as error:
        session.rollback()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(
                request,
                active="developer-accounts",
                connector_check_result={
                    "ok": False,
                    "message": error.message,
                },
                **context,
            ),
            status_code=error.status_code,
        )


@router.post("/developer-accounts/{account_id}/apps", response_class=HTMLResponse)
def bind_account_app_page(
    account_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    app_id: Annotated[str, Form(alias="appId")],
    store_app_id: Annotated[str, Form(alias="storeAppId")] = "",
    store_package_name: Annotated[str, Form(alias="storePackageName")] = "",
) -> HTMLResponse:
    try:
        bind_app_to_account(
            session,
            account_id=account_id,
            app_id=app_id,
            store_app_id=store_app_id,
            store_package_name=store_package_name,
        )
        session.commit()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", success="App 已绑定到账号", **context),
        )
    except ApiError as error:
        session.rollback()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.post("/developer-accounts/{account_id}/apps/{app_id}/settings", response_class=HTMLResponse)
def update_account_app_settings_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    store_app_id: Annotated[str, Form(alias="storeAppId")] = "",
    store_package_name: Annotated[str, Form(alias="storePackageName")] = "",
) -> HTMLResponse:
    try:
        update_bound_app_store_settings(
            session,
            account_id=account_id,
            app_id=app_id,
            store_app_id=store_app_id,
            store_package_name=store_package_name,
        )
        session.commit()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", success="商店标识已保存", **context),
        )
    except ApiError as error:
        session.rollback()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.post("/developer-accounts/{account_id}/apps/{app_id}/unbind", response_class=HTMLResponse)
def unbind_account_app_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    try:
        unbind_app_from_account(session, account_id=account_id, app_id=app_id)
        session.commit()
        context = _account_detail_context(request, session, account_id)
        return templates.TemplateResponse(
            request,
            "admin/account_detail.html",
            _context(request, active="developer-accounts", success="App 已解绑", **context),
        )
    except ApiError as error:
        session.rollback()
        context = _account_detail_context(request, session, account_id)
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


@router.get(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata",
    response_class=HTMLResponse,
)
def store_metadata_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    version: str | None = None,
    locale: str = DEFAULT_LOCALE,
    content_set_id: str = DEFAULT_CONTENT_SET_ID,
) -> HTMLResponse:
    context = store_metadata_context(
        session,
        account_id=account_id,
        app_id=app_id,
        version=version,
        locale=locale,
        content_set_id=content_set_id,
    )
    if context["account"] is None or context["app"] is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
    session.commit()
    return templates.TemplateResponse(
        request,
        "admin/store_metadata.html",
        _context(request, active="developer-accounts", **context),
    )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata",
    response_class=HTMLResponse,
)
async def save_store_metadata_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    form = await request.form()
    version = _form_value(form, "syncVersion", _form_value(form, "version"))
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    content_set_id = DEFAULT_CONTENT_SET_ID
    try:
        app = scoped_app(session, account_id, app_id)
        if app is None:
            raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
        store_image_assets = await _store_image_assets_from_form(
            form,
            storage=request.app.state.artifact_storage,
            account_id=account_id,
            app_id=app_id,
            platform=app.platform,
            version=CURRENT_METADATA_VERSION,
            content_set_id=content_set_id,
        )
        metadata_rows = _metadata_rows_from_request_form(
            form,
            current_locale=locale,
            store_image_assets_by_locale=store_image_assets,
        )
        _preserve_readonly_keywords(
            session,
            account_id=account_id,
            app=app,
            metadata_rows=metadata_rows,
        )
        for row in metadata_rows:
            save_current_app_metadata_draft(
                session,
                account_id=account_id,
                app_id=app_id,
                locale=row["locale"],
                keywords=row["keywords"],
                promotional_text=row["promotional_text"],
                description=row["description"],
                store_images=row["store_images"],
            )
            if version:
                save_release_note_draft(
                    session,
                    account_id=account_id,
                    app_id=app_id,
                    version=version,
                    locale=row["locale"],
                    release_notes=row["release_notes"],
                )
        session.commit()
        context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
            content_set_id=content_set_id,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(
                request,
                active="developer-accounts",
                success=f"商店元数据草稿已保存 {len(metadata_rows)} 个语言",
                **context,
            ),
        )
    except ApiError as error:
        session.rollback()
        context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
            content_set_id=content_set_id,
        )
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.post("/developer-accounts/{account_id}/apps/{app_id}/store-metadata/content-sets")
async def create_store_metadata_content_set(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> JSONResponse:
    form = await request.form()
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    content_set_id = _form_value(form, "contentSetId", f"set-{uuid4().hex[:12]}")
    content_set_name = _form_value(form, "contentSetName", content_set_id)
    try:
        metadata_rows = _metadata_rows_from_request_form(form, current_locale=locale)
        app = scoped_app(session, account_id, app_id)
        if app is None:
            raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
        _save_store_image_suite_rows(
            session,
            account_id=account_id,
            app=app,
            suite_id=content_set_id,
            suite_name=content_set_name,
            metadata_rows=metadata_rows,
        )
        session.commit()
    except ApiError as error:
        session.rollback()
        return JSONResponse(
            {"code": error.code, "error": error.message},
            status_code=error.status_code,
        )
    return JSONResponse(
        {
            "id": content_set_id,
            "name": content_set_name,
            "locales": [row["locale"] for row in metadata_rows],
        }
    )


@router.post("/developer-accounts/{account_id}/apps/{app_id}/store-metadata/translations")
async def translate_store_metadata_field(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> JSONResponse:
    if scoped_app(session, account_id, app_id) is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
    payload = await _json_payload(request)
    try:
        translations = translate_store_metadata_text(
            request.app.state.settings,
            source_locale=str(payload.get("sourceLocale") or DEFAULT_LOCALE),
            target_locales=[
                str(locale or "")
                for locale in payload.get("targetLocales", [])
                if isinstance(locale, str)
            ],
            field=str(payload.get("field") or ""),
            text=str(payload.get("text") or ""),
        )
    except ApiError as error:
        return JSONResponse(
            {"code": error.code, "message": error.message, "retryable": error.retryable},
            status_code=error.status_code,
        )
    return JSONResponse({"translations": translations})


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/marketing-pages",
    response_class=HTMLResponse,
)
async def create_store_marketing_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    form = await request.form()
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    page_name = _form_value(form, "marketingPageName", "新的自定义产品页面")
    page_type = _form_value(form, "marketingPageType", "custom_product_page")
    try:
        app = scoped_app(session, account_id, app_id)
        if app is None:
            raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
        if app.platform != "ios":
            raise ApiError(
                "unsupported_marketing_page",
                "营销页面控制台当前仅支持 App Store Connect",
                status_code=422,
            )
        page_id = f"page-{uuid4().hex[:8]}"
        store_image_assets = await _store_image_assets_from_form(
            form,
            storage=request.app.state.artifact_storage,
            account_id=account_id,
            app_id=app.id,
            platform=app.platform,
            version="marketing",
            content_set_id=page_id,
        )
        rows = _marketing_rows_from_request_form(
            form,
            current_locale=locale,
            existing_locales={},
            store_image_assets_by_locale=store_image_assets,
        )
        page = create_marketing_page(
            session,
            account_id=account_id,
            app_id=app.id,
            page_id=page_id,
            page_name=page_name,
            page_type=page_type,
            deep_link_url=_form_value(form, "deepLinkUrl", ""),
            locale_rows=rows,
        )
        session.commit()
        context = marketing_page_context(
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page.page_id,
            locale=locale,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/marketing_page.html",
            _context(
                request,
                active="developer-accounts",
                success="营销页面已创建",
                **context,
            ),
        )
    except ApiError as error:
        session.rollback()
        context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            locale=locale,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.get(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/marketing-pages/{page_id}",
    response_class=HTMLResponse,
)
def marketing_page_detail(
    account_id: str,
    app_id: str,
    page_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    locale: str = DEFAULT_LOCALE,
) -> HTMLResponse:
    context = marketing_page_context(
        session,
        account_id=account_id,
        app_id=app_id,
        page_id=page_id,
        locale=locale,
    )
    if context["account"] is None or context["app"] is None or context["page"] is None:
        raise ApiError("marketing_page_not_found", "营销页面不存在", status_code=404)
    return templates.TemplateResponse(
        request,
        "admin/marketing_page.html",
        _context(request, active="developer-accounts", **context),
    )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/marketing-pages/{page_id}",
    response_class=HTMLResponse,
)
async def save_marketing_page_detail(
    account_id: str,
    app_id: str,
    page_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    form = await request.form()
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    try:
        app = scoped_app(session, account_id, app_id)
        if app is None:
            raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
        store_image_assets = await _store_image_assets_from_form(
            form,
            storage=request.app.state.artifact_storage,
            account_id=account_id,
            app_id=app.id,
            platform=app.platform,
            version="marketing",
            content_set_id=page_id,
        )
        page = marketing_page_for_scope(
            session,
            account_id=account_id,
            app_id=app.id,
            page_id=page_id,
        )
        if page is None:
            raise ApiError("marketing_page_not_found", "营销页面不存在", status_code=404)
        rows = _marketing_rows_from_request_form(
            form,
            current_locale=locale,
            existing_locales=marketing_page_locales(session, page.id),
            store_image_assets_by_locale=store_image_assets,
        )
        save_marketing_page(
            session,
            account_id=account_id,
            app_id=app.id,
            page_id=page_id,
            page_name=_form_value(form, "pageName", page.page_name),
            page_type=_form_value(form, "pageType", page.page_type),
            keywords=page.keywords,
            apple_page_id=page.apple_page_id,
            deep_link_url=_form_value(form, "deepLinkUrl", page.deep_link_url),
            locale_rows=rows,
        )
        session.commit()
        context = marketing_page_context(
            session,
            account_id=account_id,
            app_id=app.id,
            page_id=page_id,
            locale=locale,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/marketing_page.html",
            _context(request, active="developer-accounts", success="营销页面草稿已保存", **context),
        )
    except ApiError as error:
        session.rollback()
        return _marketing_page_error_response(
            request,
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            locale=locale,
            error=error,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/marketing-pages/{page_id}/copy",
    response_class=HTMLResponse,
)
def copy_marketing_page_detail(
    account_id: str,
    app_id: str,
    page_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    try:
        copied = duplicate_marketing_page(
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
        )
        session.commit()
        context = marketing_page_context(
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=copied.page_id,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/marketing_page.html",
            _context(request, active="developer-accounts", success="已复制营销页面", **context),
        )
    except ApiError as error:
        session.rollback()
        return _marketing_page_error_response(
            request,
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            locale=DEFAULT_LOCALE,
            error=error,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/marketing-pages/{page_id}/delete",
    response_class=HTMLResponse,
)
def delete_marketing_page_detail(
    account_id: str,
    app_id: str,
    page_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    try:
        delete_marketing_page(
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
        )
        session.commit()
        context = store_metadata_context(session, account_id=account_id, app_id=app_id)
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(
                request,
                active="developer-accounts",
                success="已删除中心后台的营销页面",
                **context,
            ),
        )
    except ApiError as error:
        session.rollback()
        return _marketing_page_error_response(
            request,
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            locale=DEFAULT_LOCALE,
            error=error,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/marketing-pages/{page_id}/preflight",
    response_class=HTMLResponse,
)
def refresh_marketing_page_preflight(
    account_id: str,
    app_id: str,
    page_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    locale: Annotated[str, Form()] = DEFAULT_LOCALE,
) -> HTMLResponse:
    context = marketing_page_context(
        session,
        account_id=account_id,
        app_id=app_id,
        page_id=page_id,
        locale=locale,
        force_preflight_refresh=True,
    )
    if context["account"] is None or context["app"] is None or context["page"] is None:
        raise ApiError("marketing_page_not_found", "营销页面不存在", status_code=404)
    session.commit()
    preflight = context.get("preflight")
    success = (
        "1 分钟内已查询过，已显示最近一次结果"
        if getattr(preflight, "throttled", False)
        else "已实时查询营销页面同步状态"
    )
    return templates.TemplateResponse(
        request,
        "admin/marketing_page.html",
        _context(request, active="developer-accounts", success=success, **context),
    )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/marketing-pages/{page_id}/sync",
    response_class=HTMLResponse,
)
async def sync_marketing_page_detail(
    account_id: str,
    app_id: str,
    page_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    form = await request.form()
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    try:
        await _save_marketing_page_from_form(
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            request=request,
            session=session,
            form=form,
            locale=locale,
        )
        requested_sync_scopes = _form_values(form, "syncScopes") or []
        locales = _unique_non_empty(_form_values(form, "locales")) or [locale]
        sync_runs = [
            sync_marketing_page(
                session,
                account_id=account_id,
                app_id=app_id,
                page_id=page_id,
                locale=item_locale,
                sync_scopes=requested_sync_scopes,
                actor="admin",
            )
            for item_locale in locales
        ]
        session.commit()
        context = marketing_page_context(
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            locale=locale,
        )
        session.commit()
        success_count = sum(1 for run in sync_runs if run.status == "succeeded")
        message = (
            f"营销页面已同步 {len(sync_runs)} 个语言"
            if success_count == len(sync_runs)
            else f"营销页面同步完成，成功 {success_count}/{len(sync_runs)} 个语言"
        )
        return templates.TemplateResponse(
            request,
            "admin/marketing_page.html",
            _context(request, active="developer-accounts", success=message, **context),
        )
    except ApiError as error:
        session.rollback()
        return _marketing_page_error_response(
            request,
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            locale=locale,
            error=error,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/marketing-pages/{page_id}/store-images/delete",
    response_class=HTMLResponse,
)
def delete_marketing_page_image(
    account_id: str,
    app_id: str,
    page_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    locale: Annotated[str, Form()] = DEFAULT_LOCALE,
    target_locale: Annotated[str, Form(alias="storeImageLocale")] = DEFAULT_LOCALE,
    slot_key: Annotated[str, Form(alias="storeImageSlot")] = "",
    storage_key: Annotated[str, Form(alias="storageKey")] = "",
    store_image_delete: Annotated[str, Form(alias="storeImageDelete")] = "",
) -> HTMLResponse:
    try:
        delete_payload = _store_image_delete_payload(store_image_delete)
        target_locale = delete_payload.get("locale") or target_locale
        slot_key = delete_payload.get("slot") or slot_key
        storage_key = delete_payload.get("storageKey") or storage_key
        _delete_marketing_store_image_asset(
            session,
            storage=request.app.state.artifact_storage,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            locale=target_locale,
            slot_key=slot_key,
            storage_key=storage_key,
        )
        session.commit()
        context = marketing_page_context(
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            locale=locale,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/marketing_page.html",
            _context(
                request,
                active="developer-accounts",
                success="已删除中心后台的营销页面截图",
                **context,
            ),
        )
    except ApiError as error:
        session.rollback()
        return _marketing_page_error_response(
            request,
            session,
            account_id=account_id,
            app_id=app_id,
            page_id=page_id,
            locale=locale,
            error=error,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/sync",
    response_class=HTMLResponse,
)
async def sync_store_metadata_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
) -> HTMLResponse:
    form = await request.form()
    version = _form_value(form, "syncVersion", _form_value(form, "version"))
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    content_set_id = DEFAULT_CONTENT_SET_ID
    try:
        if not version:
            raise ApiError("missing_version", "同步到商店前需要填写目标商店版本", status_code=422)
        app = scoped_app(session, account_id, app_id)
        if app is None:
            raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
        store_image_assets = await _store_image_assets_from_form(
            form,
            storage=request.app.state.artifact_storage,
            account_id=account_id,
            app_id=app_id,
            platform=app.platform,
            version=CURRENT_METADATA_VERSION,
            content_set_id=content_set_id,
        )
        metadata_rows = _metadata_rows_from_request_form(
            form,
            current_locale=locale,
            store_image_assets_by_locale=store_image_assets,
        )
        _preserve_readonly_keywords(
            session,
            account_id=account_id,
            app=app,
            metadata_rows=metadata_rows,
        )
        requested_sync_scopes = _form_values(form, "syncScopes")
        sync_scopes = set(requested_sync_scopes or [])
        if not sync_scopes:
            raise ApiError("missing_sync_scope", "请至少勾选一个要同步的内容", status_code=422)
        include_store_images = "store_images" in sync_scopes
        sync_runs = []
        for row in metadata_rows:
            if "metadata" in sync_scopes:
                sync_runs.append(
                    sync_current_app_metadata(
                        session,
                        account_id=account_id,
                        app_id=app_id,
                        version=version,
                        locale=row["locale"],
                        keywords=row["keywords"],
                        promotional_text=row["promotional_text"],
                        description=row["description"],
                        actor="admin",
                        store_images=row["store_images"],
                        include_store_images_in_payload=include_store_images,
                        sync_scopes=sorted(sync_scopes & {"metadata", "store_images"}),
                    )
                )
            elif "store_images" in sync_scopes:
                sync_runs.append(
                    sync_current_app_metadata(
                        session,
                        account_id=account_id,
                        app_id=app_id,
                        version=version,
                        locale=row["locale"],
                        keywords=row["keywords"],
                        promotional_text=row["promotional_text"],
                        description=row["description"],
                        actor="admin",
                        store_images=row["store_images"],
                        include_store_images_in_payload=True,
                        sync_scopes=["store_images"],
                    )
                )
            if "release_notes" in sync_scopes:
                sync_runs.append(
                    sync_release_notes(
                        session,
                        account_id=account_id,
                        app_id=app_id,
                        version=version,
                        locale=row["locale"],
                        release_notes=row["release_notes"],
                        actor="admin",
                    )
                )
        session.commit()
        context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
            content_set_id=content_set_id,
        )
        session.commit()
        success_count = sum(1 for run in sync_runs if run.status == "succeeded")
        if sync_runs:
            if sync_scopes == {"metadata"}:
                message = (
                    f"商店元数据已同步 {len(sync_runs)} 个语言"
                    if success_count == len(sync_runs)
                    else f"同步已完成，成功 {success_count}/{len(sync_runs)} 个语言"
                )
            else:
                message = (
                    f"已同步 {len(sync_runs)} 个任务"
                    if success_count == len(sync_runs)
                    else f"同步已完成，成功 {success_count}/{len(sync_runs)} 个任务"
                )
        else:
            message = "商店图草稿已保存；当前 connector 暂未实现商店图单独同步"
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(request, active="developer-accounts", success=message, **context),
        )
    except ApiError as error:
        session.rollback()
        context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
            content_set_id=content_set_id,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/store-images/delete",
    response_class=HTMLResponse,
)
def delete_store_metadata_image_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    version: Annotated[str, Form()],
    locale: Annotated[str, Form()] = DEFAULT_LOCALE,
    content_set_id: Annotated[str, Form(alias="contentSetId")] = DEFAULT_CONTENT_SET_ID,
    target_locale: Annotated[str, Form(alias="storeImageLocale")] = DEFAULT_LOCALE,
    slot_key: Annotated[str, Form(alias="storeImageSlot")] = "",
    storage_key: Annotated[str, Form(alias="storageKey")] = "",
    store_image_delete: Annotated[str, Form(alias="storeImageDelete")] = "",
) -> HTMLResponse:
    try:
        delete_payload = _store_image_delete_payload(store_image_delete)
        target_locale = delete_payload.get("locale") or target_locale
        slot_key = delete_payload.get("slot") or slot_key
        storage_key = delete_payload.get("storageKey") or storage_key
        app = scoped_app(session, account_id, app_id)
        if app is None:
            raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
        _delete_store_image_asset(
            session,
            storage=request.app.state.artifact_storage,
            account_id=account_id,
            app=app,
            version=version,
            content_set_id=content_set_id,
            locale=target_locale,
            slot_key=slot_key,
            storage_key=storage_key,
        )
        session.commit()
        context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
            content_set_id=content_set_id,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(
                request,
                active="developer-accounts",
                success="已删除中心后台的商店图",
                **context,
            ),
        )
    except ApiError as error:
        session.rollback()
        context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
            content_set_id=content_set_id,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/preflight",
    response_class=HTMLResponse,
)
def refresh_store_metadata_preflight_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    version: Annotated[str, Form()],
    locale: Annotated[str, Form()] = DEFAULT_LOCALE,
    content_set_id: Annotated[str, Form(alias="contentSetId")] = DEFAULT_CONTENT_SET_ID,
) -> HTMLResponse:
    context = store_metadata_context(
        session,
        account_id=account_id,
        app_id=app_id,
        version=version,
        locale=locale,
        content_set_id=content_set_id,
        force_preflight_refresh=True,
    )
    if context["account"] is None or context["app"] is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
    session.commit()
    preflight = context.get("preflight")
    success = (
        "1 分钟内已查询过，已显示最近一次结果"
        if getattr(preflight, "throttled", False)
        else "已实时查询商店状态"
    )
    return templates.TemplateResponse(
        request,
        "admin/store_metadata.html",
        _context(request, active="developer-accounts", success=success, **context),
    )


@router.get("/notifications", response_class=HTMLResponse)
def notifications_page(request: Request, session: SessionDep, _: AdminDep) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "admin/notifications.html",
        _context(request, active="notifications", notifications=list_notifications(session)),
    )


async def _read_optional_upload(upload: UploadFile | None) -> tuple[str, bytes] | None:
    if upload is None or not upload.filename:
        return None
    content = await upload.read()
    if not content:
        return None
    return _safe_filename(upload.filename), content


def _build_windows_connector_package(
    *,
    account_id: str,
    platform: str,
    center_url: str,
    apple_issuer_id: str,
    apple_key_id: str,
    apple_file: tuple[str, bytes] | None,
    google_file: tuple[str, bytes] | None,
) -> dict[str, object]:
    token = secrets.token_urlsafe(32)
    root = f"C:\\ProgramData\\TestFlying\\connectors\\{_safe_filename(account_id)}"
    config: dict[str, object] = {
        "accountId": account_id,
        "connectorToken": token,
        "storeMode": "live",
        "centerUrl": center_url,
    }
    secrets_to_write: list[tuple[str, bytes]] = []

    if apple_file is not None:
        apple_filename, apple_content = apple_file
        if not apple_filename.lower().endswith(".p8"):
            raise ApiError(
                "invalid_apple_key",
                "App Store Connect API Key 必须是 .p8 文件",
                status_code=422,
            )
        key_id = apple_key_id.strip() or _apple_key_id_from_filename(apple_filename)
        issuer_id = apple_issuer_id.strip()
        if not issuer_id or not key_id:
            raise ApiError(
                "invalid_apple_key",
                "Apple 凭据需要填写 Issuer ID 和 Key ID",
                status_code=422,
            )
        apple_path = f"{root}\\secrets\\apple\\{apple_filename}"
        config["apple"] = {
            "issuerId": issuer_id,
            "keyId": key_id,
            "privateKeyPath": apple_path,
        }
        secrets_to_write.append((f"secrets/apple/{apple_filename}", apple_content))

    if google_file is not None:
        google_filename, google_content = google_file
        try:
            json.loads(google_content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ApiError(
                "invalid_google_key",
                "Google Play service account 必须是合法 JSON 文件",
                status_code=422,
            ) from error
        google_path = f"{root}\\secrets\\google\\{google_filename}"
        config["google"] = {"serviceAccountJsonPath": google_path}
        secrets_to_write.append((f"secrets/google/{google_filename}", google_content))

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("config.json", json.dumps(config, ensure_ascii=False, indent=2))
        archive.writestr("install.ps1", _windows_install_script(account_id=account_id, root=root))
        archive.writestr("README.txt", _windows_package_readme(account_id=account_id, root=root))
        for path, content in secrets_to_write:
            archive.writestr(path, content)
    return {"token": token, "content": buffer.getvalue()}


def _connector_center_url(request: Request) -> str:
    configured = request.app.state.settings.public_base_url.strip().rstrip("/")
    return configured or str(request.base_url).rstrip("/")


def _apple_key_id_from_filename(filename: str) -> str:
    match = re.match(r"AuthKey_([A-Za-z0-9]+)\.p8$", filename)
    return match.group(1) if match else ""


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-") or "connector"


def _marketing_page_error_response(
    request: Request,
    session: Session,
    *,
    account_id: str,
    app_id: str,
    page_id: str,
    locale: str,
    error: ApiError,
) -> HTMLResponse:
    context = marketing_page_context(
        session,
        account_id=account_id,
        app_id=app_id,
        page_id=page_id,
        locale=locale,
    )
    session.commit()
    if context.get("page") is None or context.get("app") is None:
        fallback_context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            locale=locale,
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(
                request,
                active="developer-accounts",
                error=error.message,
                **fallback_context,
            ),
            status_code=error.status_code,
        )
    return templates.TemplateResponse(
        request,
        "admin/marketing_page.html",
        _context(request, active="developer-accounts", error=error.message, **context),
        status_code=error.status_code,
    )


def _windows_install_script(*, account_id: str, root: str) -> str:
    task_name = f"testflying-connector-{_safe_filename(account_id)}"
    template = r'''$ErrorActionPreference = "Stop"
$Root = "__ROOT__"
$TaskName = "__TASK_NAME__"
$Repo = "baoluchuling/testflying-api"

New-Item -ItemType Directory -Force $Root, "$Root\logs", "$Root\secrets" | Out-Null
Copy-Item -Force "$PSScriptRoot\config.json" "$Root\config.json"
if (Test-Path "$PSScriptRoot\secrets") {
  Copy-Item -Force -Recurse "$PSScriptRoot\secrets\*" "$Root\secrets"
}

if (Test-Path "$PSScriptRoot\testflying-connector.exe") {
  Copy-Item -Force "$PSScriptRoot\testflying-connector.exe" "$Root\testflying-connector.exe"
}

if (!(Test-Path "$Root\testflying-connector.exe")) {
  $Release = Invoke-RestMethod `
    -Headers @{"User-Agent" = "testflying-connector-installer"} `
    -Uri "https://api.github.com/repos/$Repo/releases/latest"
  $Asset = $Release.assets |
    Where-Object { $_.name -like "testflying-connector-windows-amd64-*.zip" } |
    Select-Object -First 1
  if ($null -eq $Asset) {
    throw "GitHub Release 中没有找到 Windows connector 构建产物"
  }
  $ZipPath = "$Root\connector-windows.zip"
  $ExtractPath = "$Root\download"
  Invoke-WebRequest `
    -Headers @{"User-Agent" = "testflying-connector-installer"} `
    -Uri $Asset.browser_download_url `
    -OutFile $ZipPath
  if (Test-Path $ExtractPath) {
    Remove-Item -Recurse -Force $ExtractPath
  }
  Expand-Archive -Force $ZipPath $ExtractPath
  $Exe = Get-ChildItem -Path $ExtractPath -Filter "*.exe" -Recurse | Select-Object -First 1
  if ($null -eq $Exe) {
    throw "Windows connector 构建包中没有 exe"
  }
  Copy-Item -Force $Exe.FullName "$Root\testflying-connector.exe"
}

$RunScript = @"
`$ErrorActionPreference = "Stop"
`$env:TESTFLYING_CONNECTOR_CONFIG_PATH = "$Root\config.json"
& "$Root\testflying-connector.exe" *>> "$Root\logs\connector.log"
"@
Set-Content -Encoding UTF8 "$Root\run-connector.ps1" $RunScript

schtasks /End /TN $TaskName | Out-Null
schtasks /Delete /TN $TaskName /F | Out-Null
schtasks /Create `
  /TN $TaskName `
  /SC ONSTART `
  /RL HIGHEST `
  /RU SYSTEM `
  /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$Root\run-connector.ps1`"" `
  /F | Out-Null
schtasks /Run /TN $TaskName | Out-Null

Write-Host "testflying connector installed."
Write-Host "Task: $TaskName"
Write-Host "Root: $Root"
Write-Host "Log:  $Root\logs\connector.log"
'''
    return template.replace("__ROOT__", root).replace("__TASK_NAME__", task_name)


def _windows_package_readme(*, account_id: str, root: str) -> str:
    task_name = f"testflying-connector-{_safe_filename(account_id)}"
    return f"""testflying Windows Connector 安装包

账号: {account_id}
安装目录: {root}
计划任务: {task_name}

安装:
1. 在 Windows 上解压这个 zip。
2. 右键 PowerShell，选择“以管理员身份运行”。
3. 进入解压目录，执行:
   powershell.exe -ExecutionPolicy Bypass -File .\\install.ps1

手动重启:
   schtasks /Run /TN {task_name}

查看日志:
   {root}\\logs\\connector.log

注意:
- Apple/Google 凭据只在这个安装包和 Windows 本机安装目录中保存。
- 如果同目录下没有 testflying-connector.exe，
  install.ps1 会自动从 GitHub Release 下载最新 Windows 构建产物。
"""


def _account_detail_context(
    request: Request,
    session: Session,
    account_id: str,
) -> dict[str, object]:
    context = account_detail_context(session, account_id)
    context["default_connector_base_url"] = resolve_connector_base_url(
        account_id=account_id,
        base_url="",
        base_url_template=request.app.state.settings.connector_base_url_template,
    )
    return context


def _auto_check_connector(session: Session, account_id: str) -> None:
    connector = account_connector(session, account_id)
    if connector and _recently_checked(connector.last_checked_at):
        return
    try:
        check_connector_health(session, account_id=account_id)
    except ApiError as error:
        if error.code not in {"connector_missing", "account_not_found"}:
            raise


def _recently_checked(value: datetime | None) -> bool:
    if value is None:
        return False
    checked_at = value if value.tzinfo else value.replace(tzinfo=UTC)
    return datetime.now(UTC) - checked_at.astimezone(UTC) < CONNECTOR_AUTO_CHECK_TTL


def _form_value(form: object, name: str, default: str = "") -> str:
    value = form.get(name) if hasattr(form, "get") else None
    return value.strip() if isinstance(value, str) and value.strip() else default


def _form_values(form: object, name: str) -> list[str] | None:
    if not hasattr(form, "getlist"):
        return None
    values = [value for value in form.getlist(name) if isinstance(value, str)]
    return values or None


async def _json_payload(request: Request) -> dict[str, Any]:
    try:
        payload = await request.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _metadata_rows_from_request_form(
    form: object,
    *,
    current_locale: str,
    store_image_assets_by_locale: dict[str, dict[str, list[dict[str, object]]]] | None = None,
) -> list[dict[str, object]]:
    return _metadata_rows_from_form(
        current_locale=current_locale,
        locales=_form_values(form, "locales"),
        keywords=_form_values(form, "keywords"),
        promotional_text=_form_values(form, "promotionalText"),
        description=_form_values(form, "description"),
        release_notes=_form_values(form, "releaseNotes"),
        feature_graphic_url=_form_values(form, "featureGraphicUrl"),
        phone_screenshots=_form_values(form, "phoneScreenshots"),
        tablet_screenshots=_form_values(form, "tabletScreenshots"),
        store_image_assets_by_locale=store_image_assets_by_locale,
    )


def _preserve_readonly_keywords(
    session: Session,
    *,
    account_id: str,
    app: App,
    metadata_rows: list[dict[str, object]],
) -> None:
    keywords_by_locale = {
        draft.locale: draft.keywords
        for draft in session.scalars(
            select(StoreAppMetadataDraft).where(
                StoreAppMetadataDraft.developer_account_id == account_id,
                StoreAppMetadataDraft.app_id == app.id,
                StoreAppMetadataDraft.platform == app.platform,
                StoreAppMetadataDraft.version == CURRENT_METADATA_VERSION,
                StoreAppMetadataDraft.content_set_id == DEFAULT_CONTENT_SET_ID,
            )
        )
    }
    for row in metadata_rows:
        locale = str(row.get("locale") or "").strip()
        row["keywords"] = keywords_by_locale.get(locale, "")


async def _save_marketing_page_from_form(
    *,
    account_id: str,
    app_id: str,
    page_id: str,
    request: Request,
    session: Session,
    form: object,
    locale: str,
) -> None:
    app = scoped_app(session, account_id, app_id)
    if app is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
    page = marketing_page_for_scope(
        session,
        account_id=account_id,
        app_id=app.id,
        page_id=page_id,
    )
    if page is None:
        raise ApiError("marketing_page_not_found", "营销页面不存在", status_code=404)
    store_image_assets = await _store_image_assets_from_form(
        form,
        storage=request.app.state.artifact_storage,
        account_id=account_id,
        app_id=app.id,
        platform=app.platform,
        version="marketing",
        content_set_id=page_id,
    )
    rows = _marketing_rows_from_request_form(
        form,
        current_locale=locale,
        existing_locales=marketing_page_locales(session, page.id),
        store_image_assets_by_locale=store_image_assets,
    )
    save_marketing_page(
        session,
        account_id=account_id,
        app_id=app.id,
        page_id=page_id,
        page_name=_form_value(form, "pageName", page.page_name),
        page_type=_form_value(form, "pageType", page.page_type),
        keywords=page.keywords,
        apple_page_id=page.apple_page_id,
        deep_link_url=_form_value(form, "deepLinkUrl", page.deep_link_url),
        locale_rows=rows,
    )


def _marketing_rows_from_request_form(
    form: object,
    *,
    current_locale: str,
    existing_locales: dict[str, StoreMarketingPageLocale],
    store_image_assets_by_locale: dict[str, dict[str, list[dict[str, object]]]] | None = None,
) -> list[dict[str, object]]:
    locales = _unique_non_empty(
        [
            *(_form_values(form, "locales") or []),
            *((store_image_assets_by_locale or {}).keys()),
        ]
    ) or [current_locale.strip() or DEFAULT_LOCALE]
    promotional_text = _form_values(form, "promotionalText")
    phone_screenshots = _form_values(form, "phoneScreenshots")
    tablet_screenshots = _form_values(form, "tabletScreenshots")
    rows: list[dict[str, object]] = []
    for index, locale in enumerate(locales):
        current_images = {
            "feature_graphic_url": {"urls": [], "assets": []},
            "phone_screenshots": _store_image_form_value(
                phone_screenshots,
                index,
                locale,
                "phone_screenshots",
                store_image_assets_by_locale,
            ),
            "tablet_screenshots": _store_image_form_value(
                tablet_screenshots,
                index,
                locale,
                "tablet_screenshots",
                store_image_assets_by_locale,
            ),
        }
        rows.append(
            {
                "locale": locale,
                "promotional_text": _form_list_value(promotional_text, index),
                "store_images": _merge_marketing_store_images(
                    existing_locales.get(locale),
                    current_images,
                ),
            }
        )
    base_row = next(
        (row for row in rows if row["locale"] == (current_locale.strip() or DEFAULT_LOCALE)),
        rows[0],
    )
    for row in rows:
        if not row["promotional_text"]:
            row["promotional_text"] = base_row["promotional_text"]
    return rows


def _merge_marketing_store_images(
    existing_locale: StoreMarketingPageLocale | None,
    current_images: dict[str, object],
) -> dict[str, object]:
    existing = existing_locale.store_images_json if existing_locale else {}
    merged: dict[str, object] = {}
    for slot_key in _store_image_file_slot_keys():
        current_slot = current_images.get(slot_key) if isinstance(current_images, dict) else None
        existing_slot = existing.get(slot_key) if isinstance(existing, dict) else None
        current_urls = _slot_urls(current_slot)
        current_assets = _slot_assets(current_slot)
        existing_urls = _slot_urls(existing_slot)
        existing_assets = _slot_assets(existing_slot)
        merged[slot_key] = {
            "urls": current_urls or existing_urls,
            "assets": _dedupe_store_image_assets([*existing_assets, *current_assets]),
        }
    return merged


async def _store_image_assets_from_form(
    form: object,
    *,
    storage: object,
    account_id: str,
    app_id: str,
    platform: str,
    version: str,
    content_set_id: str,
) -> dict[str, dict[str, list[dict[str, object]]]]:
    assets_by_locale: dict[str, dict[str, list[dict[str, object]]]] = {}
    if not hasattr(form, "multi_items"):
        return assets_by_locale

    for field_name, value in form.multi_items():
        if not isinstance(field_name, str) or not field_name.startswith("storeImageFiles__"):
            continue
        parts = field_name.split("__", 2)
        if len(parts) != 3:
            continue
        slot_key, locale = parts[1], parts[2]
        if slot_key not in _store_image_file_slot_keys():
            continue
        filename = str(getattr(value, "filename", "") or "").strip()
        if not filename or not hasattr(value, "read"):
            continue
        content = await value.read()
        if not content:
            continue
        validation = validate_store_image(
            platform=platform,
            slot_key=slot_key,
            filename=filename,
            content_type=str(getattr(value, "content_type", "") or ""),
            content=content,
        )
        if not validation.valid:
            raise ApiError(
                "store_image_invalid",
                f"{locale} {Path(filename).name}: {validation.message}",
                status_code=422,
            )
        stored = storage.save(
            _store_image_storage_folder(
                account_id=account_id,
                app_id=app_id,
                version=version,
                content_set_id=content_set_id,
                locale=locale,
                slot_key=slot_key,
            ),
            filename,
            content,
            content_type=str(getattr(value, "content_type", "") or "application/octet-stream"),
        )
        assets_by_locale.setdefault(locale, {}).setdefault(slot_key, []).append(
            {
                "fileName": Path(filename).name,
                "contentType": str(
                    getattr(value, "content_type", "") or "application/octet-stream"
                ),
                "sizeBytes": len(content),
                "storageKey": stored.storage_key,
                "downloadUrl": stored.download_url,
                "width": validation.image.width if validation.image else None,
                "height": validation.image.height if validation.image else None,
                "format": validation.image.format if validation.image else None,
                "validationMessage": validation.message,
                "matchedLabel": validation.matched_label,
            }
        )

    return assets_by_locale


def _store_image_storage_folder(
    *,
    account_id: str,
    app_id: str,
    version: str,
    content_set_id: str,
    locale: str,
    slot_key: str,
) -> str:
    return "/".join(
        [
            "store-assets",
            _safe_storage_part(account_id),
            _safe_storage_part(app_id),
            _safe_storage_part(content_set_id),
            _safe_storage_part(version),
            _safe_storage_part(locale),
            _safe_storage_part(slot_key),
        ]
    )


def _safe_storage_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return normalized.strip("-") or "default"


def _store_image_file_slot_keys() -> set[str]:
    return {
        "feature_graphic_url",
        "phone_screenshots",
        "tablet_screenshots",
    }


def _metadata_rows_from_form(
    *,
    current_locale: str,
    locales: list[str] | None,
    keywords: list[str] | None,
    promotional_text: list[str] | None,
    description: list[str] | None,
    release_notes: list[str] | None,
    feature_graphic_url: list[str] | None,
    phone_screenshots: list[str] | None,
    tablet_screenshots: list[str] | None,
    store_image_assets_by_locale: dict[str, dict[str, list[dict[str, object]]]] | None = None,
) -> list[dict[str, object]]:
    normalized_locales = _unique_non_empty(locales) or [current_locale.strip() or DEFAULT_LOCALE]
    rows = [
        {
            "locale": locale,
            "keywords": _form_list_value(keywords, index),
            "promotional_text": _form_list_value(promotional_text, index),
            "description": _form_list_value(description, index),
            "release_notes": _form_list_value(release_notes, index),
            "store_images": {
                "feature_graphic_url": _store_image_form_value(
                    feature_graphic_url,
                    index,
                    locale,
                    "feature_graphic_url",
                    store_image_assets_by_locale,
                ),
                "phone_screenshots": _store_image_form_value(
                    phone_screenshots,
                    index,
                    locale,
                    "phone_screenshots",
                    store_image_assets_by_locale,
                ),
                "tablet_screenshots": _store_image_form_value(
                    tablet_screenshots,
                    index,
                    locale,
                    "tablet_screenshots",
                    store_image_assets_by_locale,
                ),
            },
        }
        for index, locale in enumerate(normalized_locales)
    ]
    base_row = next(
        (row for row in rows if row["locale"] == (current_locale.strip() or DEFAULT_LOCALE)),
        rows[0],
    )
    for row in rows:
        row["keywords"] = row["keywords"] or base_row["keywords"]
        row["promotional_text"] = row["promotional_text"] or base_row["promotional_text"]
        row["description"] = row["description"] or base_row["description"]
        row["release_notes"] = row["release_notes"] or base_row["release_notes"]
        row["store_images"] = _merge_store_images(row["store_images"], base_row["store_images"])
    return rows


def _merge_store_images(
    store_images: dict[str, object],
    base_store_images: dict[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = {}
    for key in _store_image_file_slot_keys():
        current = store_images.get(key)
        base = base_store_images.get(key)
        merged[key] = current if _has_store_image_value(current) else base
    return merged


def _metadata_store_images_for_sync(
    session: Session,
    *,
    account_id: str,
    app: App,
    version: str,
    locale: str,
    content_set_id: str,
    row_store_images: dict[str, object],
    include_store_images: bool,
) -> dict[str, object]:
    if include_store_images:
        return row_store_images
    existing = metadata_draft_for_scope(
        session,
        account_id=account_id,
        app_id=app.id,
        platform=app.platform,
        version=version,
        locale=locale,
        content_set_id=content_set_id,
    )
    if existing is not None and isinstance(existing.store_images_json, dict):
        return dict(existing.store_images_json)
    return row_store_images


def _save_store_image_suite_rows(
    session: Session,
    *,
    account_id: str,
    app: App,
    suite_id: str,
    suite_name: str,
    metadata_rows: list[dict[str, object]],
) -> StoreImageSuite:
    normalized_suite_id = (suite_id or DEFAULT_CONTENT_SET_ID).strip() or DEFAULT_CONTENT_SET_ID
    normalized_suite_name = (
        (suite_name or DEFAULT_CONTENT_SET_NAME).strip()
        or (
            DEFAULT_CONTENT_SET_NAME
            if normalized_suite_id == DEFAULT_CONTENT_SET_ID
            else normalized_suite_id
        )
    )
    suite = session.scalar(
        select(StoreImageSuite).where(
            StoreImageSuite.developer_account_id == account_id,
            StoreImageSuite.app_id == app.id,
            StoreImageSuite.platform == app.platform,
            StoreImageSuite.suite_id == normalized_suite_id,
        )
    )
    now = datetime.now(UTC)
    if suite is None:
        suite = StoreImageSuite(
            id=f"image-suite-{uuid4().hex[:12]}",
            developer_account_id=account_id,
            app_id=app.id,
            platform=app.platform,
            suite_id=normalized_suite_id,
            suite_name=normalized_suite_name,
            source="admin",
            created_at=now,
            updated_at=now,
        )
        session.add(suite)
    else:
        suite.suite_name = normalized_suite_name
        suite.source = "admin"
        suite.updated_at = now
    session.flush()
    for row in metadata_rows:
        _save_store_image_suite_locale_row(
            session,
            suite=suite,
            locale=str(row["locale"]),
            store_images=row["store_images"],
        )
    return suite


def _save_store_image_suite_locale_row(
    session: Session,
    *,
    suite: StoreImageSuite,
    locale: str,
    store_images: object,
) -> StoreImageSuiteLocale:
    suite_locale = session.scalar(
        select(StoreImageSuiteLocale).where(
            StoreImageSuiteLocale.image_suite_id == suite.id,
            StoreImageSuiteLocale.locale == locale,
        )
    )
    now = datetime.now(UTC)
    store_images_json = dict(store_images) if isinstance(store_images, dict) else {}
    if suite_locale is None:
        suite_locale = StoreImageSuiteLocale(
            id=f"image-suite-locale-{uuid4().hex[:12]}",
            image_suite_id=suite.id,
            locale=locale,
            store_images_json=store_images_json,
            updated_at=now,
        )
        session.add(suite_locale)
    else:
        suite_locale.store_images_json = store_images_json
        suite_locale.updated_at = now
    session.flush()
    return suite_locale


def _delete_store_image_asset(
    session: Session,
    *,
    storage: object,
    account_id: str,
    app: App,
    version: str,
    content_set_id: str,
    locale: str,
    slot_key: str,
    storage_key: str,
) -> None:
    normalized_slot = slot_key.strip()
    normalized_storage_key = storage_key.strip()
    normalized_content_set_id = (
        (content_set_id or DEFAULT_CONTENT_SET_ID).strip() or DEFAULT_CONTENT_SET_ID
    )
    normalized_locale = locale.strip() or DEFAULT_LOCALE
    if normalized_slot not in _store_image_file_slot_keys():
        raise ApiError("invalid_store_image_slot", "商店图类型不合法", status_code=422)
    if not normalized_storage_key:
        raise ApiError("invalid_store_image", "缺少要删除的商店图", status_code=422)

    now = datetime.now(UTC)
    draft = session.scalar(
        select(StoreAppMetadataDraft).where(
            StoreAppMetadataDraft.developer_account_id == account_id,
            StoreAppMetadataDraft.app_id == app.id,
            StoreAppMetadataDraft.platform == app.platform,
            StoreAppMetadataDraft.version == CURRENT_METADATA_VERSION,
            StoreAppMetadataDraft.locale == normalized_locale,
            StoreAppMetadataDraft.content_set_id == DEFAULT_CONTENT_SET_ID,
        )
    )
    if draft is None:
        raise ApiError("store_image_not_found", "这个语言下还没有商店图", status_code=404)
    draft_images, removed = _remove_store_image_asset_from_json(
        draft.store_images_json,
        slot_key=normalized_slot,
        storage_key=normalized_storage_key,
    )
    if not removed:
        raise ApiError("store_image_not_found", "这张商店图已经不存在或已被删除", status_code=404)
    draft.store_images_json = draft_images
    draft.updated_at = now

    suite = session.scalar(
        select(StoreImageSuite).where(
            StoreImageSuite.developer_account_id == account_id,
            StoreImageSuite.app_id == app.id,
            StoreImageSuite.platform == app.platform,
            StoreImageSuite.suite_id == normalized_content_set_id,
        )
    )
    if suite is not None:
        suite_locale = session.scalar(
            select(StoreImageSuiteLocale).where(
                StoreImageSuiteLocale.image_suite_id == suite.id,
                StoreImageSuiteLocale.locale == normalized_locale,
            )
        )
        if suite_locale is not None:
            suite_images, suite_removed = _remove_store_image_asset_from_json(
                suite_locale.store_images_json,
                slot_key=normalized_slot,
                storage_key=normalized_storage_key,
            )
            if suite_removed:
                suite_locale.store_images_json = suite_images
                suite_locale.updated_at = now
                suite.updated_at = now

    if hasattr(storage, "delete"):
        try:
            storage.delete(normalized_storage_key)
        except Exception:
            pass


def _delete_marketing_store_image_asset(
    session: Session,
    *,
    storage: object,
    account_id: str,
    app_id: str,
    page_id: str,
    locale: str,
    slot_key: str,
    storage_key: str,
) -> None:
    normalized_slot = slot_key.strip()
    normalized_storage_key = storage_key.strip()
    normalized_locale = locale.strip() or DEFAULT_LOCALE
    if normalized_slot not in _store_image_file_slot_keys():
        raise ApiError("invalid_store_image_slot", "商店图类型不合法", status_code=422)
    if not normalized_storage_key:
        raise ApiError("invalid_store_image", "缺少要删除的商店图", status_code=422)
    page = marketing_page_for_scope(
        session,
        account_id=account_id,
        app_id=app_id,
        page_id=page_id,
    )
    if page is None:
        raise ApiError("marketing_page_not_found", "营销页面不存在", status_code=404)
    locale_row = session.scalar(
        select(StoreMarketingPageLocale).where(
            StoreMarketingPageLocale.marketing_page_id == page.id,
            StoreMarketingPageLocale.locale == normalized_locale,
        )
    )
    if locale_row is None:
        raise ApiError("store_image_not_found", "这个语言下还没有营销页面截图", status_code=404)
    updated_images, removed = _remove_store_image_asset_from_json(
        locale_row.store_images_json,
        slot_key=normalized_slot,
        storage_key=normalized_storage_key,
    )
    if not removed:
        raise ApiError("store_image_not_found", "这张截图已经不存在或已被删除", status_code=404)
    now = datetime.now(UTC)
    locale_row.store_images_json = updated_images
    locale_row.updated_at = now
    page.status = "draft"
    page.updated_at = now
    if hasattr(storage, "delete"):
        try:
            storage.delete(normalized_storage_key)
        except Exception:
            pass


def _store_image_delete_payload(value: str) -> dict[str, str]:
    if not value.strip():
        return {}
    try:
        raw_payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise ApiError("invalid_store_image_delete", "删除参数不合法", status_code=422) from error
    if not isinstance(raw_payload, dict):
        raise ApiError("invalid_store_image_delete", "删除参数不合法", status_code=422)
    return {
        "locale": str(raw_payload.get("locale") or "").strip(),
        "slot": str(raw_payload.get("slot") or "").strip(),
        "storageKey": str(raw_payload.get("storageKey") or "").strip(),
    }


def _remove_store_image_asset_from_json(
    store_images: object,
    *,
    slot_key: str,
    storage_key: str,
) -> tuple[dict[str, object], bool]:
    if not isinstance(store_images, dict):
        return {}, False
    images = dict(store_images)
    slot = images.get(slot_key)
    if not isinstance(slot, dict):
        return images, False
    assets = slot.get("assets")
    if not isinstance(assets, list | tuple):
        return images, False

    kept_assets: list[dict[str, object]] = []
    removed = False
    for item in assets:
        if not isinstance(item, dict):
            continue
        asset = dict(item)
        if str(asset.get("storageKey") or "").strip() == storage_key:
            removed = True
            continue
        kept_assets.append(asset)
    if not removed:
        return images, False

    updated_slot = dict(slot)
    updated_slot["assets"] = kept_assets
    images[slot_key] = updated_slot
    return images, True


def _slot_urls(value: object) -> list[str]:
    if isinstance(value, dict):
        return _split_lines("\n".join(str(item or "") for item in value.get("urls", [])))
    return _split_lines(str(value or ""))


def _slot_assets(value: object) -> list[dict[str, object]]:
    if not isinstance(value, dict):
        return []
    raw_assets = value.get("assets")
    if not isinstance(raw_assets, list | tuple):
        return []
    return [dict(item) for item in raw_assets if isinstance(item, dict)]


def _dedupe_store_image_assets(assets: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for asset in assets:
        key = str(
            asset.get("storageKey")
            or asset.get("downloadUrl")
            or asset.get("fileName")
            or ""
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(asset)
    return deduped


def _store_image_form_value(
    values: list[str] | None,
    index: int,
    locale: str,
    slot_key: str,
    assets_by_locale: dict[str, dict[str, list[dict[str, object]]]] | None,
) -> dict[str, object]:
    assets = (assets_by_locale or {}).get(locale, {}).get(slot_key, [])
    return {
        "urls": _split_lines(_form_list_value(values, index)),
        "assets": assets,
    }


def _has_store_image_value(value: object) -> bool:
    if not isinstance(value, dict):
        return bool(value)
    return bool(value.get("urls") or value.get("assets"))


def _split_lines(value: str) -> list[str]:
    return [item.strip() for item in value.splitlines() if item.strip()]


def _unique_non_empty(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in values or []:
        value = raw_value.strip()
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result


def _form_list_value(values: list[str] | None, index: int) -> str:
    if values is None or index >= len(values):
        return ""
    return values[index].strip()


def _context(request: Request, *, active: str, **values: object) -> dict[str, object]:
    return {
        "request": request,
        "active": active,
        "admin_asset_version": ADMIN_ASSET_VERSION,
        "nav_items": [
            ("dashboard", "/admin", "总览"),
            ("uploads", "/admin/uploads", "上传"),
            ("apps", "/admin/apps", "应用"),
            ("builds", "/admin/builds", "构建"),
            ("devices", "/admin/devices", "设备"),
            ("app-logs", "/admin/app-logs", "App 日志"),
            ("developer-accounts", "/admin/developer-accounts", "开发者账号"),
            ("notifications", "/admin/notifications", "通知"),
        ],
        **values,
    }


def _upload_details(session: Session, upload: UploadResponse) -> dict[str, str]:
    app = session.get(App, upload.app.id)
    account = (
        session.get(DeveloperAccount, app.developer_account_id)
        if app and app.developer_account_id
        else None
    )
    return {
        "app_name": upload.app.name,
        "bundle_identifier": app.bundle_identifier if app else "-",
        "platform": upload.install_info.platform,
        "environment": upload.build.environment,
        "version": upload.build.version,
        "build_number": upload.build.build_number,
        "developer_account": account.team_name if account else "未绑定",
        "store_identifier": _store_identifier_label(app),
    }


def _store_identifier_label(app: App | None) -> str:
    if app is None:
        return "-"
    if app.platform == "android":
        return app.store_package_name or app.bundle_identifier
    return app.store_app_id or "需手动填写 App Store Connect App ID"


def _preflight_copy(preflight: object | None, *, platform: str = "") -> dict[str, str]:
    if preflight is None:
        return {
            "title": "等待检查",
            "summary": "请先确认 App 和目标版本信息完整。",
            "action": "填写目标版本后，系统会自动检查商店状态。",
        }
    if bool(getattr(preflight, "can_sync", False)):
        return {
            "title": "商店状态正常",
            "summary": "商店版本已创建且允许修改，可以同步到商店。",
            "action": "确认草稿内容后即可提交同步。",
        }

    reason_code = str(getattr(preflight, "reason_code", "") or "")
    blocked_copy = {
        "store_version_missing": {
            "title": "商店版本还没有创建",
            "summary": "testflying 后台构建可以存在，但商店后台还没有对应版本，所以暂时不能同步。",
            "action": f"请先在{_store_console_name(platform)}创建这个商店版本，再回到这里同步。",
        },
        "connector_missing": {
            "title": "Connector 还未配置",
            "summary": "当前开发者账号还没有可用的商店连接配置。",
            "action": "请先回到账号详情配置 Connector。",
        },
        "connector_error": {
            "title": "暂时无法连接商店",
            "summary": "系统没有拿到可靠的商店状态，暂时不会提交同步。",
            "action": "请检查 Connector 服务、账号凭据和网络后重试。",
        },
        "app_not_found": {
            "title": "App 未关联到当前账号",
            "summary": "当前账号下没有找到这个 App，不能执行商店同步。",
            "action": "请先把 App 绑定到这个开发者账号。",
        },
    }
    return blocked_copy.get(
        reason_code,
        {
            "title": "当前状态暂不能同步",
            "summary": "系统检查到商店状态还不满足同步条件。",
            "action": "请确认商店版本状态、账号配置和 Connector 状态后重试。",
        },
    )


def _store_console_name(platform: str) -> str:
    if platform == "ios":
        return " App Store Connect "
    if platform == "android":
        return " Google Play Console "
    return "对应商店后台"
