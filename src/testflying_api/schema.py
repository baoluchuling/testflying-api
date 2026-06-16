from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class App(Base):
    __tablename__ = "apps"
    __table_args__ = (UniqueConstraint("platform", "bundle_identifier"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    bundle_identifier: Mapped[str] = mapped_column(String(180), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    default_channel: Mapped[str] = mapped_column(String(20), nullable=False, default="dev")
    icon_key: Mapped[str] = mapped_column(String(40), nullable=False, default="app")
    icon_color: Mapped[str] = mapped_column(String(20), nullable=False, default="#53606E")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    builds: Mapped[list[Build]] = relationship(back_populates="app", cascade="all, delete-orphan")


class Build(Base):
    __tablename__ = "builds"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    build_number: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    environment: Mapped[str] = mapped_column(String(30), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="available")
    min_os_version: Mapped[str | None] = mapped_column(String(80))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    app: Mapped[App] = relationship(back_populates="builds")
    artifact: Mapped[Artifact | None] = relationship(
        back_populates="build",
        cascade="all, delete-orphan",
        uselist=False,
    )


class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    build_id: Mapped[str] = mapped_column(
        ForeignKey("builds.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    file_name: Mapped[str] = mapped_column(String(240), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False)
    storage_backend: Mapped[str] = mapped_column(String(20), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(400), nullable=False)
    download_url: Mapped[str] = mapped_column(String(800), nullable=False)
    manifest_url: Mapped[str | None] = mapped_column(String(800))
    install_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    build: Mapped[Build] = relationship(back_populates="artifact")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    owner: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="registered")
    status_color: Mapped[str] = mapped_column(String(20), nullable=False, default="#20864A")
    detail: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    udid: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    os_version: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    certificate_status: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class DeviceBuildVisibility(Base):
    __tablename__ = "device_build_visibility"

    device_id: Mapped[str] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        primary_key=True,
    )
    build_id: Mapped[str] = mapped_column(
        ForeignKey("builds.id", ondelete="CASCADE"),
        primary_key=True,
    )
    reason: Mapped[str] = mapped_column(String(120), nullable=False, default="assigned")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class DeveloperAccount(Base):
    __tablename__ = "developer_accounts"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    team_name: Mapped[str] = mapped_column(String(160), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="renewal_due")
    renewal_action_label: Mapped[str] = mapped_column(String(40), nullable=False, default="去续费")


class DeveloperAccountApp(Base):
    __tablename__ = "developer_account_apps"

    developer_account_id: Mapped[str] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), primary_key=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    section: Mapped[str] = mapped_column(String(80), nullable=False)
    icon_key: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    subtitle: Mapped[str] = mapped_column(String(280), nullable=False)
    tag: Mapped[str] = mapped_column(String(40), nullable=False)
    tag_color: Mapped[str] = mapped_column(String(20), nullable=False)
    app_id: Mapped[str | None] = mapped_column(ForeignKey("apps.id", ondelete="SET NULL"))
    build_id: Mapped[str | None] = mapped_column(ForeignKey("builds.id", ondelete="SET NULL"))
    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    developer_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="SET NULL"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
