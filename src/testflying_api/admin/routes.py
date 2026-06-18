from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
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
    platform_label,
    release_notes_context,
    store_metadata_context,
    upload_context,
)
from testflying_api.database import get_db_session
from testflying_api.errors import ApiError
from testflying_api.models import UploadResponse
from testflying_api.schema import App, DeveloperAccount
from testflying_api.store_sync import (
    DEFAULT_CONTENT_SET_ID,
    DEFAULT_CONTENT_SET_NAME,
    DEFAULT_LOCALE,
    account_connector,
    check_connector_health,
    resolve_connector_base_url,
    save_app_metadata_draft,
    save_connector,
    save_release_note_draft,
    scoped_app,
    sync_app_metadata,
    sync_release_notes,
)
from testflying_api.translation import translate_store_metadata_text
from testflying_api.upload_service import create_package_upload

router = APIRouter(prefix="/admin", tags=["admin"])
SessionDep = Annotated[Session, Depends(get_db_session)]
AdminDep = Annotated[None, Depends(require_admin)]
CONNECTOR_AUTO_CHECK_TTL = timedelta(minutes=5)


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
    context = _app_log_connect_context(request)
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

    context = _app_log_connect_context(request, host=host, port=port, name=name)
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
    version = _form_value(form, "version")
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    content_set_id = _form_value(form, "contentSetId", DEFAULT_CONTENT_SET_ID)
    content_set_name = _form_value(form, "contentSetName", DEFAULT_CONTENT_SET_NAME)
    try:
        store_image_assets = await _store_image_assets_from_form(
            form,
            storage=request.app.state.artifact_storage,
            account_id=account_id,
            app_id=app_id,
            version=version,
            content_set_id=content_set_id,
        )
        metadata_rows = _metadata_rows_from_request_form(
            form,
            current_locale=locale,
            store_image_assets_by_locale=store_image_assets,
        )
        for row in metadata_rows:
            save_app_metadata_draft(
                session,
                account_id=account_id,
                app_id=app_id,
                version=version,
                locale=row["locale"],
                content_set_id=content_set_id,
                content_set_name=content_set_name,
                keywords=row["keywords"],
                promotional_text=row["promotional_text"],
                description=row["description"],
                store_images=row["store_images"],
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
    version = _form_value(form, "version")
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    content_set_id = _form_value(form, "contentSetId", f"set-{uuid4().hex[:12]}")
    content_set_name = _form_value(form, "contentSetName", content_set_id)
    try:
        metadata_rows = _metadata_rows_from_request_form(form, current_locale=locale)
        for row in metadata_rows:
            save_app_metadata_draft(
                session,
                account_id=account_id,
                app_id=app_id,
                version=version,
                locale=row["locale"],
                content_set_id=content_set_id,
                content_set_name=content_set_name,
                keywords=row["keywords"],
                promotional_text=row["promotional_text"],
                description=row["description"],
                store_images=row["store_images"],
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
    version = _form_value(form, "version")
    locale = _form_value(form, "locale", DEFAULT_LOCALE)
    content_set_id = _form_value(form, "contentSetId", DEFAULT_CONTENT_SET_ID)
    content_set_name = _form_value(form, "contentSetName", DEFAULT_CONTENT_SET_NAME)
    try:
        store_image_assets = await _store_image_assets_from_form(
            form,
            storage=request.app.state.artifact_storage,
            account_id=account_id,
            app_id=app_id,
            version=version,
            content_set_id=content_set_id,
        )
        metadata_rows = _metadata_rows_from_request_form(
            form,
            current_locale=locale,
            store_image_assets_by_locale=store_image_assets,
        )
        sync_runs = []
        for row in metadata_rows:
            sync_runs.append(
                sync_app_metadata(
                    session,
                    account_id=account_id,
                    app_id=app_id,
                    version=version,
                    locale=row["locale"],
                    content_set_id=content_set_id,
                    content_set_name=content_set_name,
                    keywords=row["keywords"],
                    promotional_text=row["promotional_text"],
                    description=row["description"],
                    actor="admin",
                    store_images=row["store_images"],
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
        message = (
            f"商店元数据已同步 {len(sync_runs)} 个语言"
            if success_count == len(sync_runs)
            else f"同步已完成，成功 {success_count}/{len(sync_runs)} 个语言"
        )
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
        feature_graphic_url=_form_values(form, "featureGraphicUrl"),
        phone_screenshots=_form_values(form, "phoneScreenshots"),
        tablet_screenshots=_form_values(form, "tabletScreenshots"),
        store_image_assets_by_locale=store_image_assets_by_locale,
    )


async def _store_image_assets_from_form(
    form: object,
    *,
    storage: object,
    account_id: str,
    app_id: str,
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


def _app_log_connect_context(
    request: Request,
    *,
    host: str = "",
    port: str = "",
    name: str = "Mac",
) -> dict[str, str]:
    normalized_host = (host or request.url.hostname or "127.0.0.1").strip()
    normalized_port = (port or str(request.url.port or _default_port(request))).strip()
    normalized_name = (name or "Mac").strip()
    query = urlencode(
        {
            "host": normalized_host,
            "port": normalized_port,
            "name": normalized_name,
        }
    )
    return {
        "host": normalized_host,
        "port": normalized_port,
        "name": normalized_name,
        "connect_url": f"applog://connect?{query}",
        "websocket_url": f"ws://{normalized_host}:{normalized_port}/push?token=<设备ID>",
    }


def _default_port(request: Request) -> int:
    return 443 if request.url.scheme == "https" else 80


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
