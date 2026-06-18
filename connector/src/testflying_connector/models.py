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


class StoreMetadata(BaseModel):
    title: str
    subtitle: str = ""
    keywords: str = ""
    promotional_text: str = Field(default="", alias="promotionalText")
    description: str
    privacy_policy_url: str = Field(default="", alias="privacyPolicyUrl")
    support_url: str = Field(default="", alias="supportUrl")
    marketing_url: str = Field(default="", alias="marketingUrl")


class SyncRunRequest(PreflightRequest):
    run_id: str = Field(alias="runId")
    release_notes: str = Field(default="", alias="releaseNotes")
    metadata: StoreMetadata | None = None


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
