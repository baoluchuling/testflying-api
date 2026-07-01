from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    words = value.split("_")
    return words[0] + "".join(word[:1].upper() + word[1:] for word in words[1:])


class AdminApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AdminNavItem(AdminApiModel):
    key: str
    label: str
    path: str


class AdminHealthState(AdminApiModel):
    state: str
    label: str


class AdminBootstrapResponse(AdminApiModel):
    app_name: str
    nav_items: list[AdminNavItem]
    health: AdminHealthState


class ReviewAppItem(AdminApiModel):
    account_id: str
    app_id: str
    app_name: str
    bundle_identifier: str
    platform: str
    account_name: str
    icon_color: str
    review_count: int
    selected: bool


class ReviewStats(AdminApiModel):
    total: int
    low: int
    ios: int
    android: int


class ReviewItem(AdminApiModel):
    id: str
    store_review_id: str
    rating: int | None
    title: str
    body: str
    author_name: str
    locale: str
    territory: str
    app_version: str
    created_at: str


class ReviewFetchRunItem(AdminApiModel):
    id: str
    status: str
    page_count: int
    fetched_count: int
    inserted_count: int
    duplicate_count: int
    stopped_reason: str
    finished_at: str | None
    error_summary: str


class ReviewAnalysisRunItem(AdminApiModel):
    id: str
    status: str
    review_count: int
    low_rating_count: int
    issue_count: int
    summary: str
    finished_at: str | None
    error_summary: str


class ReviewAnalysisIssue(AdminApiModel):
    title: str
    severity: str
    count: int | None = None
    focus: str
    representative_review_ids: list[str] = Field(default_factory=list)


class StoreReviewsState(AdminApiModel):
    apps: list[ReviewAppItem]
    selected_account_id: str | None
    selected_app_id: str | None
    rating: int | None
    stats: ReviewStats
    reviews: list[ReviewItem]
    latest_fetch: ReviewFetchRunItem | None
    latest_analysis: ReviewAnalysisRunItem | None
    analysis_issues: list[ReviewAnalysisIssue]
    analysis_boundaries: list[str]


class ReviewScopeRequest(AdminApiModel):
    account_id: str
    app_id: str


class StoreReviewFetchResponse(AdminApiModel):
    message: str
    result: ReviewFetchRunItem
    state: StoreReviewsState


class StoreReviewAnalysisResponse(AdminApiModel):
    message: str
    result: ReviewAnalysisRunItem | None
    state: StoreReviewsState
    error: dict[str, Any] | None = None


class StoreAppBuildItem(AdminApiModel):
    version: str
    build_number: str
    environment: str
    uploaded_at: str


class StoreAppItem(AdminApiModel):
    id: str
    name: str
    bundle_identifier: str
    platform: str
    developer_account_id: str | None
    developer_account_name: str
    icon_color: str
    icon_text: str
    store_identifier: str
    status: str
    status_label: str
    latest_build: StoreAppBuildItem | None
    selected: bool
    store_management_path: str
    reviews_path: str


class StoreAppsStats(AdminApiModel):
    total: int
    ios: int
    android: int
    ready: int
    needs: int


class StoreAppsAccountSummary(AdminApiModel):
    total_accounts: int
    bound_apps: int
    connector_ok: int
    connector_needs: int
    renewal_reminders: int


class StoreAppsState(AdminApiModel):
    apps: list[StoreAppItem]
    selected_app: StoreAppItem | None
    filter: str
    stats: StoreAppsStats
    account_summary: StoreAppsAccountSummary


class UploadAccountOption(AdminApiModel):
    id: str
    team_name: str
    status: str
    platform: str | None = None


class UploadState(AdminApiModel):
    accounts: list[UploadAccountOption]


class UploadResult(AdminApiModel):
    app_id: str
    app_name: str
    bundle_identifier: str
    platform: str
    environment: str
    version: str
    build_number: str
    developer_account: str
    store_identifier: str
    install_url: str
    manifest_url: str | None = None
    download_url: str | None = None


class AdminUploadResponse(AdminApiModel):
    message: str
    result: UploadResult
    state: UploadState
