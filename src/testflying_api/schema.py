from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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
    developer_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="SET NULL"),
    )
    store_app_id: Mapped[str | None] = mapped_column(String(120))
    store_package_name: Mapped[str | None] = mapped_column(String(180))
    default_channel: Mapped[str] = mapped_column(String(20), nullable=False, default="dev")
    icon_key: Mapped[str] = mapped_column(String(40), nullable=False, default="app")
    icon_color: Mapped[str] = mapped_column(String(20), nullable=False, default="#53606E")
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    builds: Mapped[list[Build]] = relationship(back_populates="app", cascade="all, delete-orphan")
    developer_account: Mapped[DeveloperAccount | None] = relationship(back_populates="apps")


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

    apps: Mapped[list[App]] = relationship(back_populates="developer_account")


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


class StoreConnector(Base):
    __tablename__ = "store_connectors"
    __table_args__ = (UniqueConstraint("developer_account_id"),)

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    developer_account_id: Mapped[str] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(String(400), nullable=False)
    auth_token: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class StoreReleaseNoteDraft(Base):
    __tablename__ = "store_release_note_drafts"
    __table_args__ = (
        UniqueConstraint("developer_account_id", "app_id", "platform", "version", "locale"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    developer_account_id: Mapped[str] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    locale: Mapped[str] = mapped_column(String(40), nullable=False)
    release_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class StoreAppMetadataDraft(Base):
    __tablename__ = "store_app_metadata_drafts"
    __table_args__ = (
        UniqueConstraint(
            "developer_account_id",
            "app_id",
            "platform",
            "version",
            "locale",
            "content_set_id",
            name="uq_store_app_metadata_drafts_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    developer_account_id: Mapped[str] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    locale: Mapped[str] = mapped_column(String(40), nullable=False)
    content_set_id: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    content_set_name: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        default="默认上架内容",
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    subtitle: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    keywords: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    promotional_text: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    privacy_policy_url: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    support_url: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    marketing_url: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    store_images_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )


class StoreImageSuite(Base):
    __tablename__ = "store_image_suites"
    __table_args__ = (
        UniqueConstraint(
            "developer_account_id",
            "app_id",
            "platform",
            "suite_id",
            name="uq_store_image_suites_scope",
        ),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    developer_account_id: Mapped[str] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    suite_id: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    suite_name: Mapped[str] = mapped_column(String(120), nullable=False, default="默认商店图")
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="api")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    locales: Mapped[list[StoreImageSuiteLocale]] = relationship(
        back_populates="image_suite",
        cascade="all, delete-orphan",
    )


class StoreImageSuiteLocale(Base):
    __tablename__ = "store_image_suite_locales"
    __table_args__ = (
        UniqueConstraint("image_suite_id", "locale", name="uq_store_image_suite_locales_scope"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    image_suite_id: Mapped[str] = mapped_column(
        ForeignKey("store_image_suites.id", ondelete="CASCADE"),
        nullable=False,
    )
    locale: Mapped[str] = mapped_column(String(40), nullable=False)
    store_images_json: Mapped[dict[str, object]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )

    image_suite: Mapped[StoreImageSuite] = relationship(back_populates="locales")


class StorePreflightCheck(Base):
    __tablename__ = "store_preflight_checks"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    developer_account_id: Mapped[str] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("store_connectors.id", ondelete="CASCADE"),
        nullable=False,
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    locale: Mapped[str] = mapped_column(String(40), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    can_sync: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(80))
    message: Mapped[str] = mapped_column(String(280), nullable=False)
    store_state_json: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StoreSyncRun(Base):
    __tablename__ = "store_sync_runs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    developer_account_id: Mapped[str] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    app_id: Mapped[str] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), nullable=False)
    connector_id: Mapped[str] = mapped_column(
        ForeignKey("store_connectors.id", ondelete="CASCADE"),
        nullable=False,
    )
    draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("store_release_note_drafts.id", ondelete="SET NULL"),
    )
    metadata_draft_id: Mapped[str | None] = mapped_column(
        ForeignKey("store_app_metadata_drafts.id", ondelete="SET NULL"),
    )
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    operation: Mapped[str] = mapped_column(String(60), nullable=False)
    version: Mapped[str] = mapped_column(String(60), nullable=False)
    locale: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_summary: Mapped[str | None] = mapped_column(String(280))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    developer_account_id: Mapped[str | None] = mapped_column(
        ForeignKey("developer_accounts.id", ondelete="SET NULL"),
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
