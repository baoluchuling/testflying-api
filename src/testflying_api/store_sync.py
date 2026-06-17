from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from testflying_api.errors import ApiError
from testflying_api.schema import (
    App,
    AuditLog,
    Build,
    DeveloperAccount,
    DeveloperAccountApp,
    StoreConnector,
    StorePreflightCheck,
    StoreReleaseNoteDraft,
    StoreSyncRun,
)

PREFLIGHT_TTL = timedelta(minutes=5)
UPDATE_RELEASE_NOTES = "update_release_notes"
DEFAULT_LOCALE = "zh-Hans"


@dataclass(frozen=True)
class PreflightState:
    can_sync: bool
    reason_code: str | None
    message: str
    store_state: dict[str, object]
    checked_at: datetime
    expires_at: datetime
    cached: bool

    @property
    def remaining_seconds(self) -> int:
        return max(int((_as_utc(self.expires_at) - datetime.now(UTC)).total_seconds()), 0)


class StoreConnectorClient:
    def preflight(
        self,
        connector: StoreConnector,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if connector.base_url.startswith("mock://"):
            return _mock_preflight(payload)
        return _post_json(connector, "/v1/preflight", payload)

    def sync_release_notes(
        self,
        connector: StoreConnector,
        payload: dict[str, object],
    ) -> dict[str, object]:
        if connector.base_url.startswith("mock://"):
            return {
                "status": "succeeded",
                "message": "版本说明已同步。",
            }
        return _post_json(connector, "/v1/sync-runs", payload)


def account_apps(session: Session, account_id: str) -> list[App]:
    direct_apps = list(
        session.scalars(
            select(App)
            .where(App.developer_account_id == account_id)
            .order_by(App.added_at.desc(), App.name.asc())
        )
    )
    if direct_apps:
        return direct_apps

    legacy_app_ids = list(
        session.scalars(
            select(DeveloperAccountApp.app_id).where(
                DeveloperAccountApp.developer_account_id == account_id
            )
        )
    )
    if not legacy_app_ids:
        return []
    return list(
        session.scalars(
            select(App).where(App.id.in_(legacy_app_ids)).order_by(App.added_at.desc(), App.name)
        )
    )


def account_connector(session: Session, account_id: str) -> StoreConnector | None:
    return session.scalar(
        select(StoreConnector)
        .where(StoreConnector.developer_account_id == account_id)
        .order_by(StoreConnector.created_at.asc())
        .limit(1)
    )


def save_connector(
    session: Session,
    *,
    account_id: str,
    name: str,
    base_url: str,
    auth_token: str,
) -> StoreConnector:
    account_or_404(session, account_id)
    normalized_name = name.strip() or "Store Connector"
    normalized_base_url = base_url.strip().rstrip("/")
    normalized_token = auth_token.strip()
    if not normalized_base_url:
        raise ApiError("invalid_connector", "connector 地址不能为空", status_code=422)
    connector = account_connector(session, account_id)
    if connector is None:
        if not normalized_token:
            raise ApiError(
                "invalid_connector",
                "首次配置 connector 时必须填写调用 token",
                status_code=422,
            )
        connector = StoreConnector(
            id=f"connector-{uuid4().hex[:12]}",
            developer_account_id=account_id,
            name=normalized_name,
            base_url=normalized_base_url,
            auth_token=normalized_token,
            status="unknown",
        )
        session.add(connector)
    else:
        connector.name = normalized_name
        connector.base_url = normalized_base_url
        if normalized_token:
            connector.auth_token = normalized_token
        connector.status = connector.status or "unknown"
    session.flush()
    return connector


def latest_build_for_app(session: Session, app_id: str) -> Build | None:
    return session.scalar(
        select(Build).where(Build.app_id == app_id).order_by(Build.uploaded_at.desc()).limit(1)
    )


def draft_for_scope(
    session: Session,
    *,
    account_id: str,
    app_id: str,
    platform: str,
    version: str,
    locale: str,
) -> StoreReleaseNoteDraft | None:
    return session.scalar(
        select(StoreReleaseNoteDraft).where(
            StoreReleaseNoteDraft.developer_account_id == account_id,
            StoreReleaseNoteDraft.app_id == app_id,
            StoreReleaseNoteDraft.platform == platform,
            StoreReleaseNoteDraft.version == version,
            StoreReleaseNoteDraft.locale == locale,
        )
    )


def save_release_note_draft(
    session: Session,
    *,
    account_id: str,
    app_id: str,
    version: str,
    locale: str,
    release_notes: str,
) -> StoreReleaseNoteDraft:
    app = scoped_app(session, account_id, app_id)
    if app is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
    normalized_notes = release_notes.strip()
    draft = draft_for_scope(
        session,
        account_id=account_id,
        app_id=app.id,
        platform=app.platform,
        version=version,
        locale=locale,
    )
    if draft is None:
        draft = StoreReleaseNoteDraft(
            id=f"draft-{uuid4().hex[:12]}",
            developer_account_id=account_id,
            app_id=app.id,
            platform=app.platform,
            version=version,
            locale=locale,
            release_notes=normalized_notes,
        )
        session.add(draft)
    else:
        draft.release_notes = normalized_notes
        draft.updated_at = datetime.now(UTC)
    session.flush()
    return draft


def get_or_refresh_preflight(
    session: Session,
    *,
    account_id: str,
    app_id: str,
    version: str,
    locale: str,
    client: StoreConnectorClient | None = None,
) -> PreflightState:
    app = scoped_app(session, account_id, app_id)
    if app is None:
        return _ephemeral_preflight(
            can_sync=False,
            reason_code="app_not_found",
            message="当前开发者账号下没有这个 App。",
        )

    connector = account_connector(session, account_id)
    if connector is None:
        return _ephemeral_preflight(
            can_sync=False,
            reason_code="connector_missing",
            message="当前开发者账号还没有配置 connector。",
        )

    payload = _preflight_payload(
        account_id=account_id,
        app=app,
        connector=connector,
        version=version,
        locale=locale,
    )
    request_hash = _request_hash(payload)
    now = datetime.now(UTC)
    cached = session.scalar(
        select(StorePreflightCheck)
        .where(
            StorePreflightCheck.request_hash == request_hash,
            StorePreflightCheck.expires_at > now,
        )
        .order_by(StorePreflightCheck.checked_at.desc())
        .limit(1)
    )
    if cached is not None:
        return _state_from_check(cached, cached=True)

    connector_client = client or StoreConnectorClient()
    try:
        response = connector_client.preflight(connector, payload)
    except ConnectorCallError as error:
        response = {
            "canSync": False,
            "reasonCode": "connector_error",
            "message": error.message,
            "storeState": {"reachable": False},
        }

    check = StorePreflightCheck(
        id=f"preflight-{uuid4().hex[:12]}",
        developer_account_id=account_id,
        app_id=app.id,
        connector_id=connector.id,
        platform=app.platform,
        operation=UPDATE_RELEASE_NOTES,
        version=version,
        locale=locale,
        request_hash=request_hash,
        can_sync=bool(response.get("canSync")),
        reason_code=_optional_str(response.get("reasonCode")),
        message=str(response.get("message") or "已完成同步条件检查。"),
        store_state_json=dict(response.get("storeState") or {}),
        checked_at=now,
        expires_at=now + PREFLIGHT_TTL,
    )
    session.add(check)
    session.flush()
    return _state_from_check(check, cached=False)


def sync_release_notes(
    session: Session,
    *,
    account_id: str,
    app_id: str,
    version: str,
    locale: str,
    release_notes: str,
    actor: str,
    client: StoreConnectorClient | None = None,
) -> StoreSyncRun:
    app = scoped_app(session, account_id, app_id)
    if app is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
    connector = account_connector(session, account_id)
    if connector is None:
        raise ApiError("connector_missing", "当前开发者账号还没有配置 connector", status_code=422)
    draft = save_release_note_draft(
        session,
        account_id=account_id,
        app_id=app.id,
        version=version,
        locale=locale,
        release_notes=release_notes,
    )
    preflight = get_or_refresh_preflight(
        session,
        account_id=account_id,
        app_id=app.id,
        version=version,
        locale=locale,
        client=client,
    )
    if not preflight.can_sync:
        raise ApiError("preflight_failed", preflight.message, status_code=422)

    run = StoreSyncRun(
        id=f"sync-{uuid4().hex[:12]}",
        developer_account_id=account_id,
        app_id=app.id,
        connector_id=connector.id,
        draft_id=draft.id,
        platform=app.platform,
        operation=UPDATE_RELEASE_NOTES,
        version=version,
        locale=locale,
        status="running",
    )
    session.add(run)
    session.flush()

    payload = _sync_payload(
        run=run,
        account_id=account_id,
        app=app,
        version=version,
        locale=locale,
        release_notes=draft.release_notes,
    )
    connector_client = client or StoreConnectorClient()
    try:
        response = connector_client.sync_release_notes(connector, payload)
    except ConnectorCallError as error:
        run.status = "failed"
        run.error_code = "connector_error"
        run.error_summary = error.message
    else:
        status = str(response.get("status") or "succeeded")
        run.status = "succeeded" if status in {"ok", "success", "succeeded"} else status
        run.error_code = _optional_str(response.get("errorCode"))
        run.error_summary = _optional_str(response.get("errorSummary") or response.get("message"))
        if run.status == "succeeded":
            run.error_code = None
            run.error_summary = None
    run.finished_at = datetime.now(UTC)
    session.add(
        AuditLog(
            id=f"audit-{uuid4().hex[:12]}",
            developer_account_id=account_id,
            actor=actor,
            action="store.release_notes.sync",
            target_type="store_sync_run",
            target_id=run.id,
        )
    )
    session.flush()
    return run


def recent_sync_runs(
    session: Session,
    *,
    account_id: str,
    app_id: str | None = None,
) -> list[StoreSyncRun]:
    statement = (
        select(StoreSyncRun)
        .where(StoreSyncRun.developer_account_id == account_id)
        .order_by(StoreSyncRun.started_at.desc())
        .limit(8)
    )
    if app_id is not None:
        statement = statement.where(StoreSyncRun.app_id == app_id)
    return list(session.scalars(statement))


def scoped_app(session: Session, account_id: str, app_id: str) -> App | None:
    app = session.get(App, app_id)
    if app is None:
        return None
    if app.developer_account_id == account_id:
        return app
    legacy_link = session.scalar(
        select(DeveloperAccountApp).where(
            DeveloperAccountApp.developer_account_id == account_id,
            DeveloperAccountApp.app_id == app_id,
        )
    )
    return app if legacy_link is not None and app.developer_account_id is None else None


def account_or_404(session: Session, account_id: str) -> DeveloperAccount:
    account = session.get(DeveloperAccount, account_id)
    if account is None:
        raise ApiError("account_not_found", "开发者账号不存在", status_code=404)
    return account


class ConnectorCallError(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _preflight_payload(
    *,
    account_id: str,
    app: App,
    connector: StoreConnector,
    version: str,
    locale: str,
) -> dict[str, object]:
    return {
        "developerAccountId": account_id,
        "connectorId": connector.id,
        "operation": UPDATE_RELEASE_NOTES,
        "platform": app.platform,
        "version": version,
        "locale": locale,
        "app": _app_payload(app),
    }


def _sync_payload(
    *,
    run: StoreSyncRun,
    account_id: str,
    app: App,
    version: str,
    locale: str,
    release_notes: str,
) -> dict[str, object]:
    return {
        "runId": run.id,
        "developerAccountId": account_id,
        "operation": UPDATE_RELEASE_NOTES,
        "platform": app.platform,
        "version": version,
        "locale": locale,
        "app": _app_payload(app),
        "releaseNotes": release_notes,
    }


def _app_payload(app: App) -> dict[str, object]:
    return {
        "appId": app.id,
        "bundleIdentifier": app.bundle_identifier,
        "storeAppId": app.store_app_id,
        "packageName": app.store_package_name or app.bundle_identifier,
    }


def _post_json(
    connector: StoreConnector,
    path: str,
    payload: dict[str, object],
) -> dict[str, object]:
    url = connector.base_url.rstrip("/") + path
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {connector.auth_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - connector URL is admin configured.
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise ConnectorCallError(f"connector 返回 HTTP {error.code}: {body[:180]}") from error
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise ConnectorCallError(f"connector 调用失败: {error}") from error


def _mock_preflight(payload: dict[str, object]) -> dict[str, object]:
    version = str(payload.get("version") or "")
    if not version or "missing" in version.lower():
        return {
            "canSync": False,
            "reasonCode": "store_version_missing",
            "message": f"商店中还没有创建 {version or '目标'} 版本，暂不能同步版本说明。",
            "storeState": {
                "versionExists": False,
                "editable": False,
                "currentStatus": "missing",
            },
        }
    return {
        "canSync": True,
        "reasonCode": None,
        "message": f"商店中已存在 {version} 版本，当前状态允许修改版本说明。",
        "storeState": {
            "versionExists": True,
            "editable": True,
            "currentStatus": "prepare_for_submission",
        },
    }


def _request_hash(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _state_from_check(check: StorePreflightCheck, *, cached: bool) -> PreflightState:
    return PreflightState(
        can_sync=check.can_sync,
        reason_code=check.reason_code,
        message=check.message,
        store_state=check.store_state_json,
        checked_at=check.checked_at,
        expires_at=check.expires_at,
        cached=cached,
    )


def _ephemeral_preflight(
    *,
    can_sync: bool,
    reason_code: str,
    message: str,
) -> PreflightState:
    now = datetime.now(UTC)
    return PreflightState(
        can_sync=can_sync,
        reason_code=reason_code,
        message=message,
        store_state={},
        checked_at=now,
        expires_at=now,
        cached=False,
    )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
