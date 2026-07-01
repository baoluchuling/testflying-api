from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy.orm import Session

from testflying_api.admin.security import require_admin
from testflying_api.admin.view_models import list_accounts, list_apps, upload_context
from testflying_api.admin_api.errors import AdminApiError
from testflying_api.admin_api.schemas import (
    AdminBootstrapResponse,
    AdminHealthState,
    AdminNavItem,
    AdminUploadResponse,
    AppLogsState,
    ReviewAnalysisIssue,
    ReviewAnalysisRunItem,
    ReviewAppItem,
    ReviewFetchRunItem,
    ReviewItem,
    ReviewScopeRequest,
    ReviewStats,
    StoreAppBuildItem,
    StoreAppItem,
    StoreAppsAccountSummary,
    StoreAppsState,
    StoreAppsStats,
    StoreReviewAnalysisResponse,
    StoreReviewFetchResponse,
    StoreReviewsState,
    UploadAccountOption,
    UploadResult,
    UploadState,
)
from testflying_api.app_logs import LEVELS, build_app_log_connect_context
from testflying_api.database import get_db_session
from testflying_api.errors import ApiError
from testflying_api.schema import (
    App,
    DeveloperAccount,
    StoreReview,
    StoreReviewAnalysisRun,
    StoreReviewFetchRun,
)
from testflying_api.store_reviews import (
    analyze_store_reviews,
    fetch_store_reviews_incremental,
    store_reviews_context,
)
from testflying_api.upload_service import create_package_upload

router = APIRouter(prefix="/admin/api", tags=["admin-api"])
AdminDep = Annotated[None, Depends(require_admin)]
SessionDep = Annotated[Session, Depends(get_db_session)]


@router.get("/bootstrap", response_model=AdminBootstrapResponse, response_model_by_alias=True)
def admin_bootstrap(_: AdminDep) -> AdminBootstrapResponse:
    return AdminBootstrapResponse(
        app_name="testflying",
        nav_items=[
            AdminNavItem(key="dashboard", label="总览", path="/admin-next"),
            AdminNavItem(key="uploads", label="上传", path="/admin-next/uploads"),
            AdminNavItem(key="apps", label="商店管理", path="/admin-next/apps"),
            AdminNavItem(key="store-reviews", label="商店评论", path="/admin-next/store-reviews"),
            AdminNavItem(key="api-docs", label="接口文档", path="/admin-next/api-docs"),
            AdminNavItem(key="builds", label="构建", path="/admin-next/builds"),
            AdminNavItem(key="devices", label="设备", path="/admin-next/devices"),
            AdminNavItem(key="app-logs", label="App 日志", path="/admin-next/app-logs"),
            AdminNavItem(key="notifications", label="通知", path="/admin-next/notifications"),
        ],
        health=AdminHealthState(state="idle", label="未检查"),
    )


@router.get(
    "/store-apps",
    response_model=StoreAppsState,
    response_model_by_alias=True,
)
def store_apps_state(
    session: SessionDep,
    _: AdminDep,
    filter: Annotated[str, Query()] = "all",
    appId: Annotated[str, Query()] = "",
) -> StoreAppsState:
    return _store_apps_state(session, active_filter=filter, app_id=appId)


@router.get(
    "/uploads",
    response_model=UploadState,
    response_model_by_alias=True,
)
def upload_state(
    session: SessionDep,
    _: AdminDep,
) -> UploadState:
    return _upload_state(session)


@router.get(
    "/app-logs",
    response_model=AppLogsState,
    response_model_by_alias=True,
)
def app_logs_state(
    request: Request,
    _: AdminDep,
    cursor: Annotated[int, Query()] = 0,
    limit: Annotated[int, Query()] = 500,
) -> AppLogsState:
    return _app_logs_state(request, cursor=cursor, limit=limit)


@router.get(
    "/app-logs/events",
    response_model=AppLogsState,
    response_model_by_alias=True,
)
def app_logs_events(
    request: Request,
    _: AdminDep,
    cursor: Annotated[int, Query()] = 0,
    limit: Annotated[int, Query()] = 500,
) -> AppLogsState:
    return _app_logs_state(request, cursor=cursor, limit=limit)


@router.post(
    "/uploads",
    response_model=AdminUploadResponse,
    response_model_by_alias=True,
)
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
) -> AdminUploadResponse:
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
        raise _admin_api_error(error) from error

    return AdminUploadResponse(
        message="上传成功，包信息已自动解析",
        result=_upload_result(session, upload.app.id),
        state=_upload_state(session),
    )


def _upload_state(session: Session) -> UploadState:
    context = upload_context(session)
    accounts = context.get("accounts", [])
    return UploadState(
        accounts=[
            UploadAccountOption(
                id=account.id,
                team_name=account.team_name,
                status=account.status,
                platform=None,
            )
            for account in accounts
            if isinstance(account, DeveloperAccount)
        ]
    )


def _upload_result(session: Session, app_id: str) -> UploadResult:
    app = session.get(App, app_id)
    if app is None:
        raise AdminApiError("upload_app_not_found", "上传结果中的 App 不存在", status_code=500)
    latest_build = max(app.builds, key=lambda build: build.uploaded_at, default=None)
    if latest_build is None:
        raise AdminApiError("upload_build_not_found", "上传结果中的构建不存在", status_code=500)
    install_info = latest_build.artifact
    return UploadResult(
        app_id=app.id,
        app_name=app.name,
        bundle_identifier=app.bundle_identifier,
        platform=latest_build.platform,
        environment=latest_build.environment,
        version=latest_build.version,
        build_number=latest_build.build_number,
        developer_account=(
            app.developer_account.team_name if app.developer_account else "未绑定账号"
        ),
        store_identifier=_store_identifier(app) or "未填写",
        install_url=install_info.install_url if install_info else "",
        manifest_url=install_info.manifest_url if install_info else None,
        download_url=install_info.download_url if install_info else None,
    )


def _app_logs_state(request: Request, *, cursor: int = 0, limit: int = 500) -> AppLogsState:
    snapshot = request.app.state.app_log_hub.snapshot(cursor=cursor, limit=limit)
    return AppLogsState(
        connect=build_app_log_connect_context(request),
        cursor=snapshot.cursor,
        devices=snapshot.devices,
        logs=snapshot.logs,
        errors=snapshot.errors,
        levels=list(LEVELS),
    )


@router.get(
    "/store-reviews",
    response_model=StoreReviewsState,
    response_model_by_alias=True,
)
def store_reviews_state(
    session: SessionDep,
    _: AdminDep,
    accountId: Annotated[str, Query()] = "",
    appId: Annotated[str, Query()] = "",
    rating: Annotated[int | None, Query()] = None,
) -> StoreReviewsState:
    return _store_reviews_state(session, account_id=accountId, app_id=appId, rating=rating)


@router.post(
    "/store-reviews/fetch",
    response_model=StoreReviewFetchResponse,
    response_model_by_alias=True,
)
def fetch_store_reviews(
    scope: ReviewScopeRequest,
    session: SessionDep,
    _: AdminDep,
) -> StoreReviewFetchResponse:
    try:
        result = fetch_store_reviews_incremental(
            session,
            account_id=scope.account_id,
            app_id=scope.app_id,
        )
        session.commit()
    except ApiError as error:
        session.rollback()
        raise _admin_api_error(error) from error
    return StoreReviewFetchResponse(
        message="最新评论已拉取",
        result=_fetch_run_item(result.run),
        state=_store_reviews_state(
            session,
            account_id=scope.account_id,
            app_id=scope.app_id,
            rating=None,
        ),
    )


@router.post(
    "/store-reviews/analyze",
    response_model=StoreReviewAnalysisResponse,
    response_model_by_alias=True,
)
def analyze_reviews(
    request: Request,
    scope: ReviewScopeRequest,
    session: SessionDep,
    _: AdminDep,
) -> StoreReviewAnalysisResponse:
    try:
        run = analyze_store_reviews(
            session,
            request.app.state.settings,
            account_id=scope.account_id,
            app_id=scope.app_id,
        )
        session.commit()
        return StoreReviewAnalysisResponse(
            message="评论分析已完成",
            result=_analysis_run_item(run),
            state=_store_reviews_state(
                session,
                account_id=scope.account_id,
                app_id=scope.app_id,
                rating=None,
            ),
        )
    except ApiError as error:
        session.commit()
        return StoreReviewAnalysisResponse(
            message="评论分析失败",
            result=None,
            state=_store_reviews_state(
                session,
                account_id=scope.account_id,
                app_id=scope.app_id,
                rating=None,
            ),
            error={
                "code": error.code,
                "message": error.message,
            },
        )


def _store_apps_state(
    session: Session,
    *,
    active_filter: str,
    app_id: str,
) -> StoreAppsState:
    all_apps = list_apps(session)
    normalized_filter = (
        active_filter if active_filter in {"all", "ios", "android", "needs", "ok"} else "all"
    )
    app_items = [_store_app_item(app, selected_app_id=app_id) for app in all_apps]
    filtered_apps = [
        item for item in app_items if _store_app_matches_filter(item, normalized_filter)
    ]
    selected_app = next((item for item in filtered_apps if item.id == app_id), None)
    if selected_app is None:
        selected_app = filtered_apps[0] if filtered_apps else None
    if selected_app is not None:
        filtered_apps = [
            item.model_copy(update={"selected": item.id == selected_app.id})
            for item in filtered_apps
        ]
        selected_app = next((item for item in filtered_apps if item.selected), selected_app)
    return StoreAppsState(
        apps=filtered_apps,
        selected_app=selected_app,
        filter=normalized_filter,
        stats=StoreAppsStats(
            total=len(app_items),
            ios=sum(1 for item in app_items if item.platform == "ios"),
            android=sum(1 for item in app_items if item.platform == "android"),
            ready=sum(1 for item in app_items if item.status == "ready"),
            needs=sum(1 for item in app_items if item.status != "ready"),
        ),
        account_summary=_store_apps_account_summary(session, app_items),
    )


def _store_app_item(app: App, *, selected_app_id: str) -> StoreAppItem:
    latest_build = max(app.builds, key=lambda build: build.uploaded_at, default=None)
    account = app.developer_account
    store_identifier = _store_identifier(app)
    status = _store_app_status(app, store_identifier)
    return StoreAppItem(
        id=app.id,
        name=app.name,
        bundle_identifier=app.bundle_identifier,
        platform=app.platform,
        developer_account_id=account.id if account else None,
        developer_account_name=account.team_name if account else "",
        icon_color=app.icon_color,
        icon_text=app.name[:2].upper(),
        store_identifier=store_identifier,
        status=status,
        status_label=_store_app_status_label(status),
        latest_build=(
            StoreAppBuildItem(
                version=latest_build.version,
                build_number=latest_build.build_number,
                environment=latest_build.environment,
                uploaded_at=_iso_datetime(latest_build.uploaded_at),
            )
            if latest_build
            else None
        ),
        selected=app.id == selected_app_id,
        store_management_path=(
            f"/admin/developer-accounts/{account.id}/apps/{app.id}/store" if account else ""
        ),
        reviews_path=(
            f"/admin-next/store-reviews?accountId={account.id}&appId={app.id}" if account else ""
        ),
    )


def _store_app_matches_filter(app: StoreAppItem, active_filter: str) -> bool:
    if active_filter == "all":
        return True
    if active_filter in {"ios", "android"}:
        return app.platform == active_filter
    if active_filter == "ok":
        return app.status == "ready"
    if active_filter == "needs":
        return app.status != "ready"
    return True


def _store_apps_account_summary(
    session: Session,
    app_items: list[StoreAppItem],
) -> StoreAppsAccountSummary:
    accounts = list_accounts(session)
    return StoreAppsAccountSummary(
        total_accounts=len(accounts),
        bound_apps=sum(1 for item in app_items if item.developer_account_id),
        connector_ok=sum(
            1 for item in accounts if getattr(item.get("connector"), "status", "") == "ok"
        ),
        connector_needs=sum(
            1 for item in accounts if getattr(item.get("connector"), "status", "") != "ok"
        ),
        renewal_reminders=sum(
            1 for item in accounts if getattr(item.get("account"), "status", "") != "ok"
        ),
    )


def _store_identifier(app: App) -> str:
    if app.platform == "ios":
        return app.store_app_id or ""
    if app.platform == "android":
        return app.store_package_name or app.bundle_identifier
    return app.store_app_id or app.store_package_name or ""


def _store_app_status(app: App, store_identifier: str) -> str:
    if app.developer_account is None:
        return "needs_account"
    if not store_identifier:
        return "needs_identifier"
    return "ready"


def _store_app_status_label(status: str) -> str:
    if status == "ready":
        return "可同步"
    if status == "needs_identifier":
        return "待填写商店标识"
    return "未绑定账号"


def _store_reviews_state(
    session: Session,
    *,
    account_id: str = "",
    app_id: str = "",
    rating: int | None = None,
) -> StoreReviewsState:
    context = store_reviews_context(session, account_id=account_id, app_id=app_id, rating=rating)
    selected_account = context["selected_review_account"]
    selected_app = context["selected_review_app"]
    return StoreReviewsState(
        apps=[
            _review_app_item(
                item,
                selected_account=selected_account,
                selected_app=selected_app,
            )
            for item in context["review_apps"]
        ],
        selected_account_id=(
            selected_account.id if isinstance(selected_account, DeveloperAccount) else None
        ),
        selected_app_id=selected_app.id if isinstance(selected_app, App) else None,
        rating=rating,
        stats=ReviewStats(**context["review_stats"]),
        reviews=[_review_item(review) for review in context["reviews"]],
        latest_fetch=_fetch_run_item(context["latest_review_fetch"]),
        latest_analysis=_analysis_run_item(context["latest_review_analysis"]),
        analysis_issues=[_analysis_issue_item(issue) for issue in context["analysis_issues"]],
        analysis_boundaries=list(context["analysis_boundaries"]),
    )


def _review_app_item(
    item: dict[str, object],
    *,
    selected_account: object,
    selected_app: object,
) -> ReviewAppItem:
    app = item["app"]
    account = item["account"]
    if not isinstance(app, App) or not isinstance(account, DeveloperAccount):
        raise AdminApiError("invalid_review_app", "评论应用数据格式异常", status_code=500)
    return ReviewAppItem(
        account_id=account.id,
        app_id=app.id,
        app_name=app.name,
        bundle_identifier=app.bundle_identifier,
        platform=app.platform,
        account_name=account.team_name,
        icon_color=app.icon_color,
        review_count=int(item.get("review_count") or 0),
        selected=(
            isinstance(selected_account, DeveloperAccount)
            and isinstance(selected_app, App)
            and selected_account.id == account.id
            and selected_app.id == app.id
        ),
    )


def _review_item(review: StoreReview) -> ReviewItem:
    return ReviewItem(
        id=review.id,
        store_review_id=review.store_review_id,
        rating=review.rating,
        title=review.title or "",
        body=review.body or "",
        author_name=review.author_name or "",
        locale=review.locale or "",
        territory=review.territory or "",
        app_version=review.app_version or "",
        created_at=_iso_datetime(review.created_at),
    )


def _fetch_run_item(run: StoreReviewFetchRun | None) -> ReviewFetchRunItem | None:
    if run is None:
        return None
    return ReviewFetchRunItem(
        id=run.id,
        status=run.status,
        page_count=run.page_count,
        fetched_count=run.fetched_count,
        inserted_count=run.inserted_count,
        duplicate_count=run.duplicate_count,
        stopped_reason=run.stopped_reason,
        finished_at=_optional_iso_datetime(run.finished_at),
        error_summary=run.error_summary or "",
    )


def _analysis_run_item(run: StoreReviewAnalysisRun | None) -> ReviewAnalysisRunItem | None:
    if run is None:
        return None
    return ReviewAnalysisRunItem(
        id=run.id,
        status=run.status,
        review_count=run.review_count,
        low_rating_count=run.low_rating_count,
        issue_count=run.issue_count,
        summary=run.summary or "",
        finished_at=_optional_iso_datetime(run.finished_at),
        error_summary=run.error_summary or "",
    )


def _analysis_issue_item(issue: dict[str, object]) -> ReviewAnalysisIssue:
    representative = issue.get("representativeReviewIds") or issue.get("representative_review_ids")
    representative_ids = representative if isinstance(representative, list) else []
    return ReviewAnalysisIssue(
        title=str(issue.get("title") or "未命名关注点"),
        severity=str(issue.get("severity") or "medium"),
        count=_optional_int(issue.get("count")),
        focus=str(issue.get("focus") or "需要人工确认影响范围。"),
        representative_review_ids=[str(item) for item in representative_ids],
    )


def _iso_datetime(value: datetime) -> str:
    return value.isoformat()


def _optional_iso_datetime(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _admin_api_error(error: ApiError) -> AdminApiError:
    return AdminApiError(
        error.code,
        error.message,
        status_code=error.status_code,
        detail={"retryable": error.retryable, **error.extra},
    )
