from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status

from testflying_connector.config import Settings
from testflying_connector.models import (
    PreflightRequest,
    PreflightResponse,
    SupportedLocalesResponse,
    SyncRunRequest,
    SyncRunResponse,
)
from testflying_connector.rate_limit import SlidingWindowRateLimiter, StoreRateLimitPolicy

app = FastAPI(
    title="testflying-connector",
    version="0.1.0",
    description="Account-scoped store sync connector for testflying-server.",
)
settings = Settings.from_environment()
rate_limiter = SlidingWindowRateLimiter()
rate_limit_policy = StoreRateLimitPolicy(settings)


def require_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {settings.connector_token}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid connector token",
        )


def validate_account(developer_account_id: str) -> None:
    if developer_account_id != settings.developer_account_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="developer account does not match this connector",
        )


def enforce_rate_limit(platform: str) -> None:
    decision = rate_limiter.check(rate_limit_policy.rule_for_platform(platform))
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="connector rate limit exceeded",
            headers={"Retry-After": str(decision.retry_after)},
        )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "developerAccountId": settings.developer_account_id,
    }


@app.post("/v1/preflight", response_model=PreflightResponse, dependencies=[Depends(require_token)])
def preflight(payload: PreflightRequest) -> PreflightResponse:
    validate_account(payload.developer_account_id)
    enforce_rate_limit(payload.platform)
    operation_label = _operation_label(payload.operation)
    if not payload.version or "missing" in payload.version.lower():
        return PreflightResponse(
            canSync=False,
            reasonCode="store_version_missing",
            message=(
                f"商店中还没有创建 {payload.version or '目标'} 版本，"
                f"暂不能同步{operation_label}。"
            ),
            storeState={
                "versionExists": False,
                "editable": False,
                "currentStatus": "missing",
            },
        )
    return PreflightResponse(
        canSync=True,
        reasonCode=None,
        message=f"商店中已存在 {payload.version} 版本，当前状态允许修改{operation_label}。",
        storeState={
            "versionExists": True,
            "editable": True,
            "currentStatus": "prepare_for_submission",
        },
    )


@app.get(
    "/v1/apps/{app_id}/supported-locales",
    response_model=SupportedLocalesResponse,
    dependencies=[Depends(require_token)],
)
def supported_locales(
    app_id: str,
    developer_account_id: Annotated[str, Query(alias="developerAccountId")],
    platform: str = "",
    version: str = "",
) -> SupportedLocalesResponse:
    validate_account(developer_account_id)
    enforce_rate_limit(platform)
    locales = ["zh-Hans", "en-US", "ja", "ko"] if platform == "ios" else ["zh-Hans", "en-US"]
    return SupportedLocalesResponse(locales=locales)


@app.post("/v1/sync-runs", response_model=SyncRunResponse, dependencies=[Depends(require_token)])
def create_sync_run(payload: SyncRunRequest) -> SyncRunResponse:
    validate_account(payload.developer_account_id)
    enforce_rate_limit(payload.platform)
    if payload.operation == "update_app_metadata":
        if payload.metadata is None or not payload.metadata.title.strip():
            response = SyncRunResponse(
                status="failed",
                message="商店元数据标题不能为空。",
                errorCode="empty_metadata_title",
                errorSummary="商店元数据标题不能为空。",
            )
        elif not payload.metadata.description.strip():
            response = SyncRunResponse(
                status="failed",
                message="商店元数据描述不能为空。",
                errorCode="empty_metadata_description",
                errorSummary="商店元数据描述不能为空。",
            )
        else:
            response = SyncRunResponse(status="succeeded", message="商店元数据已同步。")
    elif not payload.release_notes.strip():
        response = SyncRunResponse(
            status="failed",
            message="版本说明不能为空。",
            errorCode="empty_release_notes",
            errorSummary="版本说明不能为空。",
        )
    else:
        response = SyncRunResponse(status="succeeded", message="版本说明已同步。")
    return response


def _operation_label(operation: str) -> str:
    return "商店元数据" if operation == "update_app_metadata" else "版本说明"
