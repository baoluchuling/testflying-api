from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
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
    DEFAULT_LOCALE,
    check_connector_health,
    resolve_connector_base_url,
    save_app_metadata_draft,
    save_connector,
    save_release_note_draft,
    sync_app_metadata,
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
templates.env.filters["account_status"] = account_status_label


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
                success=result.message if result.ok else None,
                error=None if result.ok else result.message,
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
            _context(request, active="developer-accounts", error=error.message, **context),
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
) -> HTMLResponse:
    context = store_metadata_context(
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
        "admin/store_metadata.html",
        _context(request, active="developer-accounts", **context),
    )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata",
    response_class=HTMLResponse,
)
def save_store_metadata_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    version: Annotated[str, Form()],
    locale: Annotated[str, Form()] = DEFAULT_LOCALE,
    title: Annotated[str, Form()] = "",
    subtitle: Annotated[str, Form()] = "",
    locales: Annotated[list[str] | None, Form()] = None,
    keywords: Annotated[list[str] | None, Form()] = None,
    promotional_text: Annotated[list[str] | None, Form(alias="promotionalText")] = None,
    description: Annotated[list[str] | None, Form()] = None,
    privacy_policy_url: Annotated[str, Form(alias="privacyPolicyUrl")] = "",
    support_url: Annotated[str, Form(alias="supportUrl")] = "",
    marketing_url: Annotated[str, Form(alias="marketingUrl")] = "",
) -> HTMLResponse:
    try:
        metadata_rows = _metadata_rows_from_form(
            current_locale=locale,
            locales=locales,
            keywords=keywords,
            promotional_text=promotional_text,
            description=description,
        )
        for row in metadata_rows:
            save_app_metadata_draft(
                session,
                account_id=account_id,
                app_id=app_id,
                version=version,
                locale=row["locale"],
                title=title,
                subtitle=subtitle,
                keywords=row["keywords"],
                promotional_text=row["promotional_text"],
                description=row["description"],
                privacy_policy_url=privacy_policy_url,
                support_url=support_url,
                marketing_url=marketing_url,
            )
        session.commit()
        context = store_metadata_context(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=locale,
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
        )
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
            _context(request, active="developer-accounts", error=error.message, **context),
            status_code=error.status_code,
        )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-metadata/sync",
    response_class=HTMLResponse,
)
def sync_store_metadata_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
    _: AdminDep,
    version: Annotated[str, Form()],
    locale: Annotated[str, Form()] = DEFAULT_LOCALE,
    title: Annotated[str, Form()] = "",
    subtitle: Annotated[str, Form()] = "",
    locales: Annotated[list[str] | None, Form()] = None,
    keywords: Annotated[list[str] | None, Form()] = None,
    promotional_text: Annotated[list[str] | None, Form(alias="promotionalText")] = None,
    description: Annotated[list[str] | None, Form()] = None,
    privacy_policy_url: Annotated[str, Form(alias="privacyPolicyUrl")] = "",
    support_url: Annotated[str, Form(alias="supportUrl")] = "",
    marketing_url: Annotated[str, Form(alias="marketingUrl")] = "",
) -> HTMLResponse:
    try:
        metadata_rows = _metadata_rows_from_form(
            current_locale=locale,
            locales=locales,
            keywords=keywords,
            promotional_text=promotional_text,
            description=description,
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
                    title=title,
                    subtitle=subtitle,
                    keywords=row["keywords"],
                    promotional_text=row["promotional_text"],
                    description=row["description"],
                    privacy_policy_url=privacy_policy_url,
                    support_url=support_url,
                    marketing_url=marketing_url,
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
        )
        session.commit()
        return templates.TemplateResponse(
            request,
            "admin/store_metadata.html",
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
    try:
        check_connector_health(session, account_id=account_id)
    except ApiError as error:
        if error.code not in {"connector_missing", "account_not_found"}:
            raise


def _metadata_rows_from_form(
    *,
    current_locale: str,
    locales: list[str] | None,
    keywords: list[str] | None,
    promotional_text: list[str] | None,
    description: list[str] | None,
) -> list[dict[str, str]]:
    normalized_locales = _unique_non_empty(locales) or [current_locale.strip() or DEFAULT_LOCALE]
    rows = [
        {
            "locale": locale,
            "keywords": _form_list_value(keywords, index),
            "promotional_text": _form_list_value(promotional_text, index),
            "description": _form_list_value(description, index),
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
    return rows


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
    }
