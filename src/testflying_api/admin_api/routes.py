from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from testflying_api.admin.security import require_admin
from testflying_api.admin_api.schemas import (
    AdminBootstrapResponse,
    AdminHealthState,
    AdminNavItem,
)

router = APIRouter(prefix="/admin/api", tags=["admin-api"])
AdminDep = Annotated[None, Depends(require_admin)]


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
