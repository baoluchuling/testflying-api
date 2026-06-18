from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

from testflying_connector.config import Settings
from testflying_connector.models import (
    PreflightRequest,
    PreflightResponse,
    SyncRunRecord,
    SyncRunRequest,
    SyncRunResponse,
)

app = FastAPI(
    title="testflying-connector",
    version="0.1.0",
    description="Account-scoped store sync connector for testflying-server.",
)
settings = Settings.from_environment()
sync_runs: dict[str, SyncRunRecord] = {}


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


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "developerAccountId": settings.developer_account_id,
    }


@app.post("/v1/preflight", response_model=PreflightResponse, dependencies=[Depends(require_token)])
def preflight(payload: PreflightRequest) -> PreflightResponse:
    validate_account(payload.developer_account_id)
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


@app.post("/v1/sync-runs", response_model=SyncRunResponse, dependencies=[Depends(require_token)])
def create_sync_run(payload: SyncRunRequest) -> SyncRunResponse:
    validate_account(payload.developer_account_id)
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
    sync_runs[payload.run_id] = SyncRunRecord(
        runId=payload.run_id,
        developerAccountId=payload.developer_account_id,
        status=response.status,
        message=response.message,
    )
    return response


def _operation_label(operation: str) -> str:
    return "商店元数据" if operation == "update_app_metadata" else "版本说明"


@app.get(
    "/v1/sync-runs/{run_id}",
    response_model=SyncRunRecord,
    dependencies=[Depends(require_token)],
)
def sync_run(run_id: str, request: Request) -> SyncRunRecord:
    record = sync_runs.get(run_id)
    if record is None:
        raise HTTPException(status_code=404, detail="sync run not found")
    validate_account(record.developer_account_id)
    return record
