from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from testflying_api.schema import (
    App,
    Build,
    DeveloperAccount,
    DeveloperAccountApp,
    Device,
    Notification,
)


@dataclass(frozen=True)
class StatCard:
    label: str
    value: str
    tone: str = "neutral"


def dashboard_context(session: Session) -> dict[str, object]:
    app_count = session.scalar(select(func.count(App.id))) or 0
    build_count = session.scalar(select(func.count(Build.id))) or 0
    ios_count = session.scalar(select(func.count(Build.id)).where(Build.platform == "ios")) or 0
    android_count = (
        session.scalar(select(func.count(Build.id)).where(Build.platform == "android")) or 0
    )
    renewal_count = session.scalar(
        select(func.count(DeveloperAccount.id)).where(DeveloperAccount.status != "ok")
    ) or 0
    return {
        "stats": [
            StatCard("应用", str(app_count), "blue"),
            StatCard("构建", str(build_count), "green"),
            StatCard("iOS / Android", f"{ios_count} / {android_count}", "neutral"),
            StatCard("续费提醒", str(renewal_count), "red" if renewal_count else "neutral"),
        ],
        "recent_builds": list_builds(session, limit=6),
        "recent_notifications": list_notifications(session, limit=8),
    }


def list_apps(session: Session) -> list[App]:
    return list(
        session.scalars(
            select(App)
            .options(selectinload(App.builds))
            .order_by(App.added_at.desc(), App.name.asc())
        )
    )


def list_builds(session: Session, *, limit: int | None = None) -> list[Build]:
    statement = (
        select(Build)
        .options(joinedload(Build.app), joinedload(Build.artifact))
        .order_by(Build.uploaded_at.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement))


def list_devices(session: Session) -> list[Device]:
    return list(session.scalars(select(Device).order_by(Device.registered_at.desc())))


def list_accounts(session: Session) -> list[dict[str, object]]:
    accounts = list(
        session.scalars(select(DeveloperAccount).order_by(DeveloperAccount.expires_at.asc()))
    )
    app_rows = session.execute(select(DeveloperAccountApp.developer_account_id, App.name).join(App))
    names_by_account: dict[str, list[str]] = {}
    for account_id, app_name in app_rows:
        names_by_account.setdefault(account_id, []).append(app_name)
    return [
        {
            "account": account,
            "remaining_days": remaining_days(account.expires_at),
            "apps": names_by_account.get(account.id, []),
        }
        for account in accounts
    ]


def list_notifications(session: Session, *, limit: int | None = None) -> list[Notification]:
    statement = select(Notification).order_by(Notification.created_at.desc())
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement))


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    timestamp = value if value.tzinfo else value.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC).strftime("%Y-%m-%d %H:%M")


def format_size(size_bytes: int | None) -> str:
    if not size_bytes:
        return "0 B"
    units = ["B", "KB", "MB", "GB"]
    value = float(size_bytes)
    unit_index = 0
    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1
    return f"{value:.1f} {units[unit_index]}" if unit_index else f"{int(value)} B"


def environment_label(value: str) -> str:
    return "线上环境" if value == "production" else "开发环境"


def platform_label(value: str) -> str:
    return "iOS" if value == "ios" else "Android"


def remaining_days(expires_at: datetime) -> int:
    now = datetime.now(UTC)
    expires = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=UTC)
    return (expires - now).days
