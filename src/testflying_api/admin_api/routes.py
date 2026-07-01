from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from testflying_api.admin.security import require_admin
from testflying_api.admin_api.errors import AdminApiError
from testflying_api.admin_api.schemas import (
    AdminBootstrapResponse,
    AdminHealthState,
    AdminNavItem,
    ReviewAnalysisIssue,
    ReviewAnalysisRunItem,
    ReviewAppItem,
    ReviewFetchRunItem,
    ReviewItem,
    ReviewScopeRequest,
    ReviewStats,
    StoreReviewAnalysisResponse,
    StoreReviewFetchResponse,
    StoreReviewsState,
)
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
