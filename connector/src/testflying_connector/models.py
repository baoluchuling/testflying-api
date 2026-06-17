from __future__ import annotations

from pydantic import BaseModel, Field


class StoreApp(BaseModel):
    app_id: str = Field(alias="appId")
    bundle_identifier: str = Field(alias="bundleIdentifier")
    store_app_id: str | None = Field(default=None, alias="storeAppId")
    package_name: str | None = Field(default=None, alias="packageName")


class PreflightRequest(BaseModel):
    developer_account_id: str = Field(alias="developerAccountId")
    operation: str
    platform: str
    version: str
    locale: str
    app: StoreApp


class PreflightResponse(BaseModel):
    can_sync: bool = Field(alias="canSync")
    reason_code: str | None = Field(default=None, alias="reasonCode")
    message: str
    store_state: dict[str, object] = Field(default_factory=dict, alias="storeState")


class SyncRunRequest(PreflightRequest):
    run_id: str = Field(alias="runId")
    release_notes: str = Field(alias="releaseNotes")


class SyncRunResponse(BaseModel):
    status: str
    message: str
    error_code: str | None = Field(default=None, alias="errorCode")
    error_summary: str | None = Field(default=None, alias="errorSummary")


class SyncRunRecord(BaseModel):
    run_id: str = Field(alias="runId")
    developer_account_id: str = Field(alias="developerAccountId")
    status: str
    message: str
