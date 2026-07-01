from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from testflying_api.admin.security import require_admin

AdminDep = Annotated[None, Depends(require_admin)]

router = APIRouter(prefix="/admin-next", tags=["admin-next"])
ADMIN_APP_DIR = Path(__file__).parent / "static" / "admin-app"


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
@router.get("/{path:path}", response_class=HTMLResponse)
def admin_next_app(request: Request, _: AdminDep, path: str = "") -> HTMLResponse:
    return HTMLResponse(_admin_app_index())


def _admin_app_index() -> str:
    index_path = ADMIN_APP_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return """<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>testflying 管理后台</title>
  </head>
  <body>
    <div id="root" data-admin-app-root data-admin-app-build="missing">
      <h1>testflying 新后台</h1>
      <p>Admin App 还没有构建。请运行 npm --prefix admin-web run build。</p>
    </div>
  </body>
</html>"""
