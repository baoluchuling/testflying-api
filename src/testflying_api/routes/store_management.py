from __future__ import annotations

import json
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from testflying_api.database import get_db_session
from testflying_api.errors import ApiError
from testflying_api.schema import StoreImageSuite, StoreImageSuiteLocale
from testflying_api.store_image_requirements import validate_store_image
from testflying_api.store_sync import (
    CURRENT_METADATA_VERSION,
    DEFAULT_CONTENT_SET_ID,
    DEFAULT_CONTENT_SET_NAME,
    DEFAULT_LOCALE,
    create_marketing_page,
    metadata_draft_for_scope,
    save_current_app_metadata_draft,
    save_release_note_draft,
    scoped_app,
)

router = APIRouter(prefix="/v1/store-management", tags=["store-management"])
SessionDep = Annotated[Session, Depends(get_db_session)]

STORE_IMAGE_SLOT_KEYS = {
    "feature_graphic_url",
    "phone_screenshots",
    "tablet_screenshots",
}
STORE_IMAGE_SLOT_ALIASES = {
    "featureGraphicUrl": "feature_graphic_url",
    "feature_graphic_url": "feature_graphic_url",
    "featureGraphic": "feature_graphic_url",
    "phoneScreenshots": "phone_screenshots",
    "phone_screenshots": "phone_screenshots",
    "tabletScreenshots": "tablet_screenshots",
    "tablet_screenshots": "tablet_screenshots",
}


class CamelModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class ContentSetInput(CamelModel):
    id: str = DEFAULT_CONTENT_SET_ID
    name: str = DEFAULT_CONTENT_SET_NAME


class LocaleMetadataInput(CamelModel):
    locale: str
    keywords: str = ""
    promotional_text: str = Field(default="", alias="promotionalText")
    description: str = ""
    store_images: dict[str, object] = Field(default_factory=dict, alias="storeImages")


class MetadataContentSetImport(CamelModel):
    version: str = CURRENT_METADATA_VERSION
    content_set: ContentSetInput = Field(default_factory=ContentSetInput, alias="contentSet")
    source_locale: str = Field(default=DEFAULT_LOCALE, alias="sourceLocale")
    locales: list[LocaleMetadataInput]
    store_images: dict[str, object] = Field(default_factory=dict, alias="storeImages")


class MetadataContentSetResponse(CamelModel):
    content_set: ContentSetInput = Field(alias="contentSet")
    version: str
    locales: list[str]
    saved_drafts: int = Field(alias="savedDrafts")
    uploaded_assets: int = Field(alias="uploadedAssets")
    warnings: list[str] = Field(default_factory=list)


class VersionLocaleDraftInput(CamelModel):
    locale: str
    keywords: str = ""
    promotional_text: str = Field(default="", alias="promotionalText")
    description: str = ""
    release_notes: str = Field(default="", alias="releaseNotes")


class StoreVersionDraftImport(CamelModel):
    source_locale: str = Field(default=DEFAULT_LOCALE, alias="sourceLocale")
    locales: list[VersionLocaleDraftInput]


class StoreVersionDraftResponse(CamelModel):
    version: str
    locales: list[str]
    saved_metadata_drafts: int = Field(alias="savedMetadataDrafts")
    saved_release_note_drafts: int = Field(alias="savedReleaseNoteDrafts")
    warnings: list[str] = Field(default_factory=list)


class StoreImageSuiteInput(CamelModel):
    id: str = DEFAULT_CONTENT_SET_ID
    name: str = "默认商店图"


class LocaleStoreImagesInput(CamelModel):
    locale: str
    store_images: dict[str, object] = Field(default_factory=dict, alias="storeImages")


class StoreImageSuiteImport(CamelModel):
    image_suite: StoreImageSuiteInput = Field(
        default_factory=StoreImageSuiteInput,
        alias="imageSuite",
    )
    source: str = "api"
    source_locale: str = Field(default=DEFAULT_LOCALE, alias="sourceLocale")
    locales: list[LocaleStoreImagesInput]
    store_images: dict[str, object] = Field(default_factory=dict, alias="storeImages")


class StoreImageSuiteResponse(CamelModel):
    image_suite: StoreImageSuiteInput = Field(alias="imageSuite")
    locales: list[str]
    saved_locales: int = Field(alias="savedLocales")
    uploaded_assets: int = Field(alias="uploadedAssets")
    warnings: list[str] = Field(default_factory=list)


class MarketingPageLocaleInput(CamelModel):
    locale: str
    promotional_text: str = Field(default="", alias="promotionalText")
    store_images: dict[str, object] = Field(default_factory=dict, alias="storeImages")


class MarketingPageImport(CamelModel):
    page_name: str = Field(default="新的自定义产品页面", alias="pageName")
    page_type: str = Field(default="custom_product_page", alias="pageType")
    source_locale: str = Field(default=DEFAULT_LOCALE, alias="sourceLocale")
    deep_link_url: str = Field(default="", alias="deepLinkUrl")
    locales: list[MarketingPageLocaleInput]
    store_images: dict[str, object] = Field(default_factory=dict, alias="storeImages")


class MarketingPageImportResponse(CamelModel):
    page_id: str = Field(alias="pageId")
    page_name: str = Field(alias="pageName")
    page_type: str = Field(alias="pageType")
    status: str
    locales: list[str]
    saved_locales: int = Field(alias="savedLocales")
    uploaded_assets: int = Field(alias="uploadedAssets")
    warnings: list[str] = Field(default_factory=list)


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/metadata-content-sets",
    response_model=MetadataContentSetResponse,
)
async def import_metadata_content_set(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
) -> MetadataContentSetResponse:
    _require_static_token(request)
    form = await request.form()
    payload = _metadata_payload_from_form(form)
    app = scoped_app(session, account_id, app_id)
    if app is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)

    uploaded_assets = await _store_image_assets_from_form(
        form,
        request=request,
        account_id=account_id,
        app_id=app_id,
        platform=app.platform,
        version=CURRENT_METADATA_VERSION,
        content_set_id=DEFAULT_CONTENT_SET_ID,
    )
    rows = _metadata_rows(payload, uploaded_assets)
    for row in rows:
        save_current_app_metadata_draft(
            session,
            account_id=account_id,
            app_id=app_id,
            locale=row["locale"],
            keywords=row["keywords"],
            promotional_text=row["promotional_text"],
            description=row["description"],
            store_images=row["store_images"],
        )
    session.commit()
    return MetadataContentSetResponse(
        contentSet=payload.content_set,
        version=payload.version,
        locales=[row["locale"] for row in rows],
        savedDrafts=len(rows),
        uploadedAssets=sum(
            len(assets)
            for slots in uploaded_assets.values()
            for assets in slots.values()
        ),
        warnings=[],
    )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-versions/{version}/draft",
    response_model=StoreVersionDraftResponse,
)
async def import_store_version_draft(
    account_id: str,
    app_id: str,
    version: str,
    request: Request,
    session: SessionDep,
) -> StoreVersionDraftResponse:
    _require_static_token(request)
    payload = await _store_version_payload_from_request(request)
    app = scoped_app(session, account_id, app_id)
    if app is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)

    rows = _version_draft_rows(payload)
    saved_metadata_drafts = 0
    saved_release_note_drafts = 0
    for row in rows:
        if row["save_metadata"]:
            existing = metadata_draft_for_scope(
                session,
                account_id=account_id,
                app_id=app_id,
                platform=app.platform,
                version=CURRENT_METADATA_VERSION,
                locale=str(row["locale"]),
                content_set_id=DEFAULT_CONTENT_SET_ID,
            )
            save_current_app_metadata_draft(
                session,
                account_id=account_id,
                app_id=app_id,
                locale=str(row["locale"]),
                keywords=str(row["keywords"]),
                promotional_text=str(row["promotional_text"]),
                description=str(row["description"]),
                store_images=existing.store_images_json if existing is not None else {},
            )
            saved_metadata_drafts += 1

        save_release_note_draft(
            session,
            account_id=account_id,
            app_id=app_id,
            version=version,
            locale=str(row["locale"]),
            release_notes=str(row["release_notes"]),
        )
        saved_release_note_drafts += 1

    session.commit()
    return StoreVersionDraftResponse(
        version=version,
        locales=[str(row["locale"]) for row in rows],
        savedMetadataDrafts=saved_metadata_drafts,
        savedReleaseNoteDrafts=saved_release_note_drafts,
        warnings=[],
    )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/store-image-suites",
    response_model=StoreImageSuiteResponse,
)
async def import_store_image_suite(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
) -> StoreImageSuiteResponse:
    _require_static_token(request)
    form = await request.form()
    payload = _store_image_suite_payload_from_form(form)
    app = scoped_app(session, account_id, app_id)
    if app is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)

    suite_id = _normalize_suite_id(payload.image_suite.id)
    suite_name = _normalize_suite_name(payload.image_suite.name, suite_id)
    uploaded_assets = await _store_image_assets_from_form(
        form,
        request=request,
        account_id=account_id,
        app_id=app_id,
        platform=app.platform,
        image_suite_id=suite_id,
    )
    rows = _image_suite_rows(payload, uploaded_assets)
    suite = _save_image_suite(
        session,
        account_id=account_id,
        app_id=app_id,
        platform=app.platform,
        suite_id=suite_id,
        suite_name=suite_name,
        source=payload.source,
    )
    for row in rows:
        _save_image_suite_locale(
            session,
            suite=suite,
            locale=str(row["locale"]),
            store_images=row["store_images"],
        )
    session.commit()
    return StoreImageSuiteResponse(
        imageSuite=StoreImageSuiteInput(id=suite_id, name=suite_name),
        locales=[str(row["locale"]) for row in rows],
        savedLocales=len(rows),
        uploadedAssets=_uploaded_asset_count(uploaded_assets),
        warnings=[],
    )


@router.post(
    "/developer-accounts/{account_id}/apps/{app_id}/marketing-pages",
    response_model=MarketingPageImportResponse,
)
async def import_marketing_page(
    account_id: str,
    app_id: str,
    request: Request,
    session: SessionDep,
) -> MarketingPageImportResponse:
    _require_static_token(request)
    form = await request.form()
    payload = _marketing_page_payload_from_form(form)
    app = scoped_app(session, account_id, app_id)
    if app is None:
        raise ApiError("app_not_found", "当前开发者账号下没有这个 App", status_code=404)
    if app.platform != "ios":
        raise ApiError(
            "unsupported_marketing_page",
            "营销页面控制台当前仅支持 App Store Connect",
            status_code=422,
        )

    page_id = f"page-{uuid4().hex[:8]}"
    uploaded_assets = await _store_image_assets_from_form(
        form,
        request=request,
        account_id=account_id,
        app_id=app_id,
        platform=app.platform,
        version="marketing",
        content_set_id=page_id,
    )
    rows = _marketing_page_rows(payload, uploaded_assets)
    page = create_marketing_page(
        session,
        account_id=account_id,
        app_id=app.id,
        page_id=page_id,
        page_name=payload.page_name,
        page_type=payload.page_type,
        deep_link_url=payload.deep_link_url,
        locale_rows=rows,
    )
    session.commit()
    return MarketingPageImportResponse(
        pageId=page.page_id,
        pageName=page.page_name,
        pageType=page.page_type,
        status=page.status,
        locales=[str(row["locale"]) for row in rows],
        savedLocales=len(rows),
        uploadedAssets=_uploaded_asset_count(uploaded_assets),
        warnings=[],
    )


def _require_static_token(request: Request) -> None:
    expected = f"Bearer {request.app.state.settings.static_token}"
    authorization = request.headers.get("Authorization", "")
    if not secrets.compare_digest(authorization, expected):
        raise ApiError("invalid_static_token", "接口 token 不正确", status_code=401)


def _metadata_payload_from_form(form: object) -> MetadataContentSetImport:
    raw_metadata = str(getattr(form, "get", lambda _key, _default=None: None)("metadata") or "")
    if not raw_metadata.strip():
        raise ApiError("missing_metadata", "metadata 字段不能为空", status_code=422)
    try:
        decoded = json.loads(raw_metadata)
        return MetadataContentSetImport.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError) as error:
        raise ApiError(
            "invalid_metadata",
            f"metadata JSON 格式不正确：{error}",
            status_code=422,
        ) from error


async def _store_version_payload_from_request(request: Request) -> StoreVersionDraftImport:
    try:
        decoded = await request.json()
        return StoreVersionDraftImport.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError) as error:
        raise ApiError(
            "invalid_metadata",
            f"metadata JSON 格式不正确：{error}",
            status_code=422,
        ) from error


def _store_image_suite_payload_from_form(form: object) -> StoreImageSuiteImport:
    raw_metadata = str(getattr(form, "get", lambda _key, _default=None: None)("metadata") or "")
    if not raw_metadata.strip():
        raise ApiError("missing_metadata", "metadata 字段不能为空", status_code=422)
    try:
        decoded = json.loads(raw_metadata)
        return StoreImageSuiteImport.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError) as error:
        raise ApiError(
            "invalid_metadata",
            f"metadata JSON 格式不正确：{error}",
            status_code=422,
        ) from error


def _marketing_page_payload_from_form(form: object) -> MarketingPageImport:
    raw_metadata = str(getattr(form, "get", lambda _key, _default=None: None)("metadata") or "")
    if not raw_metadata.strip():
        raise ApiError("missing_metadata", "metadata 字段不能为空", status_code=422)
    try:
        decoded = json.loads(raw_metadata)
        return MarketingPageImport.model_validate(decoded)
    except (json.JSONDecodeError, ValidationError) as error:
        raise ApiError(
            "invalid_metadata",
            f"metadata JSON 格式不正确：{error}",
            status_code=422,
        ) from error


async def _store_image_assets_from_form(
    form: object,
    *,
    request: Request,
    account_id: str,
    app_id: str,
    platform: str,
    version: str | None = None,
    content_set_id: str | None = None,
    image_suite_id: str | None = None,
) -> dict[str, dict[str, list[dict[str, object]]]]:
    assets_by_locale: dict[str, dict[str, list[dict[str, object]]]] = {}
    if not hasattr(form, "multi_items"):
        return assets_by_locale

    for field_name, value in form.multi_items():
        if not isinstance(field_name, str) or not field_name.startswith("storeImageFiles__"):
            continue
        parts = field_name.split("__", 2)
        if len(parts) != 3:
            continue
        slot_key = _normalize_slot_key(parts[1])
        locale = parts[2].strip()
        if slot_key is None or not locale:
            continue
        filename = str(getattr(value, "filename", "") or "").strip()
        if not filename or not hasattr(value, "read"):
            continue
        content = await value.read()
        if not content:
            continue
        content_type = str(getattr(value, "content_type", "") or "application/octet-stream")
        validation = validate_store_image(
            platform=platform,
            slot_key=slot_key,
            filename=filename,
            content_type=content_type,
            content=content,
        )
        if not validation.valid:
            raise ApiError(
                "store_image_invalid",
                f"{locale} {Path(filename).name}: {validation.message}",
                status_code=422,
            )
        folder = (
            _store_image_suite_storage_folder(
                account_id=account_id,
                app_id=app_id,
                image_suite_id=image_suite_id,
                locale=locale,
                slot_key=slot_key,
            )
            if image_suite_id is not None
            else _store_image_storage_folder(
                account_id=account_id,
                app_id=app_id,
                version=str(version or ""),
                content_set_id=str(content_set_id or DEFAULT_CONTENT_SET_ID),
                locale=locale,
                slot_key=slot_key,
            )
        )
        stored = request.app.state.artifact_storage.save(
            folder,
            filename,
            content,
            content_type=content_type,
        )
        assets_by_locale.setdefault(locale, {}).setdefault(slot_key, []).append(
            {
                "fileName": Path(filename).name,
                "contentType": content_type,
                "sizeBytes": len(content),
                "storageKey": stored.storage_key,
                "downloadUrl": stored.download_url,
                "width": validation.image.width if validation.image else None,
                "height": validation.image.height if validation.image else None,
                "format": validation.image.format if validation.image else None,
                "validationMessage": validation.message,
                "matchedLabel": validation.matched_label,
            }
        )
    return assets_by_locale


def _version_draft_rows(payload: StoreVersionDraftImport) -> list[dict[str, object]]:
    locale_inputs = [item for item in payload.locales if item.locale.strip()]
    if not locale_inputs:
        raise ApiError("invalid_metadata", "locales 至少需要包含一个语言", status_code=422)
    source_locale = payload.source_locale.strip() or locale_inputs[0].locale.strip()
    source = next(
        (item for item in locale_inputs if item.locale.strip() == source_locale),
        locale_inputs[0],
    )
    source_has_metadata = bool(
        source.keywords.strip()
        or source.promotional_text.strip()
        or source.description.strip()
    )
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in locale_inputs:
        locale = item.locale.strip()
        if locale in seen:
            continue
        seen.add(locale)
        description = item.description.strip() or source.description.strip()
        save_metadata = bool(
            source_has_metadata
            or item.keywords.strip()
            or item.promotional_text.strip()
            or item.description.strip()
        )
        if save_metadata and not description:
            raise ApiError(
                "invalid_metadata",
                f"{locale} 的 description 不能为空",
                status_code=422,
            )
        rows.append(
            {
                "locale": locale,
                "save_metadata": save_metadata,
                "keywords": item.keywords.strip() or source.keywords.strip(),
                "promotional_text": (
                    item.promotional_text.strip() or source.promotional_text.strip()
                ),
                "description": description,
                "release_notes": item.release_notes.strip() or source.release_notes.strip(),
            }
        )
    return rows


def _image_suite_rows(
    payload: StoreImageSuiteImport,
    uploaded_assets: dict[str, dict[str, list[dict[str, object]]]],
) -> list[dict[str, object]]:
    locale_inputs = [item for item in payload.locales if item.locale.strip()]
    if not locale_inputs:
        raise ApiError("invalid_metadata", "locales 至少需要包含一个语言", status_code=422)
    source_locale = payload.source_locale.strip() or locale_inputs[0].locale.strip()
    source = next(
        (item for item in locale_inputs if item.locale.strip() == source_locale),
        locale_inputs[0],
    )
    source_images = _suite_images_for_locale(payload, source, uploaded_assets)
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in locale_inputs:
        locale = item.locale.strip()
        if locale in seen:
            continue
        seen.add(locale)
        rows.append(
            {
                "locale": locale,
                "store_images": _merge_store_images(
                    _suite_images_for_locale(payload, item, uploaded_assets),
                    source_images,
                ),
            }
        )
    return rows


def _marketing_page_rows(
    payload: MarketingPageImport,
    uploaded_assets: dict[str, dict[str, list[dict[str, object]]]],
) -> list[dict[str, object]]:
    locale_inputs = {
        item.locale.strip(): item for item in payload.locales if item.locale.strip()
    }
    locales = _unique_non_empty(
        [
            *locale_inputs.keys(),
            *uploaded_assets.keys(),
            payload.source_locale,
        ]
    )
    if not locales:
        raise ApiError("invalid_metadata", "locales 至少需要包含一个语言", status_code=422)
    source_locale = payload.source_locale.strip() or locales[0]
    source = locale_inputs.get(source_locale) or locale_inputs.get(locales[0])
    source_text = source.promotional_text.strip() if source is not None else ""
    source_images = _marketing_images_for_locale(payload, source_locale, source, uploaded_assets)
    rows: list[dict[str, object]] = []
    for locale in locales:
        item = locale_inputs.get(locale)
        promotional_text = (
            item.promotional_text.strip() if item is not None else ""
        ) or source_text
        rows.append(
            {
                "locale": locale,
                "promotional_text": promotional_text,
                "store_images": _merge_store_images(
                    _marketing_images_for_locale(payload, locale, item, uploaded_assets),
                    source_images,
                ),
            }
        )
    return rows


def _save_image_suite(
    session: Session,
    *,
    account_id: str,
    app_id: str,
    platform: str,
    suite_id: str,
    suite_name: str,
    source: str,
) -> StoreImageSuite:
    suite = session.scalar(
        select(StoreImageSuite).where(
            StoreImageSuite.developer_account_id == account_id,
            StoreImageSuite.app_id == app_id,
            StoreImageSuite.platform == platform,
            StoreImageSuite.suite_id == suite_id,
        )
    )
    now = datetime.now(UTC)
    if suite is None:
        suite = StoreImageSuite(
            id=f"image-suite-{uuid4().hex[:12]}",
            developer_account_id=account_id,
            app_id=app_id,
            platform=platform,
            suite_id=suite_id,
            suite_name=suite_name,
            source=_normalize_source(source),
            created_at=now,
            updated_at=now,
        )
        session.add(suite)
    else:
        suite.suite_name = suite_name
        suite.source = _normalize_source(source)
        suite.updated_at = now
    session.flush()
    return suite


def _save_image_suite_locale(
    session: Session,
    *,
    suite: StoreImageSuite,
    locale: str,
    store_images: object,
) -> StoreImageSuiteLocale:
    suite_locale = session.scalar(
        select(StoreImageSuiteLocale).where(
            StoreImageSuiteLocale.image_suite_id == suite.id,
            StoreImageSuiteLocale.locale == locale,
        )
    )
    now = datetime.now(UTC)
    if suite_locale is None:
        suite_locale = StoreImageSuiteLocale(
            id=f"image-suite-locale-{uuid4().hex[:12]}",
            image_suite_id=suite.id,
            locale=locale,
            store_images_json=dict(store_images) if isinstance(store_images, dict) else {},
            updated_at=now,
        )
        session.add(suite_locale)
    else:
        suite_locale.store_images_json = (
            dict(store_images) if isinstance(store_images, dict) else {}
        )
        suite_locale.updated_at = now
    session.flush()
    return suite_locale


def _metadata_rows(
    payload: MetadataContentSetImport,
    uploaded_assets: dict[str, dict[str, list[dict[str, object]]]],
) -> list[dict[str, object]]:
    locale_inputs = [item for item in payload.locales if item.locale.strip()]
    if not locale_inputs:
        raise ApiError("invalid_metadata", "locales 至少需要包含一个语言", status_code=422)
    source_locale = payload.source_locale.strip() or locale_inputs[0].locale.strip()
    source = next(
        (item for item in locale_inputs if item.locale.strip() == source_locale),
        locale_inputs[0],
    )
    source_images = _images_for_locale(payload, source, uploaded_assets)
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in locale_inputs:
        locale = item.locale.strip()
        if locale in seen:
            continue
        seen.add(locale)
        description = item.description.strip() or source.description.strip()
        if not description:
            raise ApiError(
                "invalid_metadata",
                f"{locale} 的 description 不能为空",
                status_code=422,
            )
        rows.append(
            {
                "locale": locale,
                "keywords": item.keywords.strip() or source.keywords.strip(),
                "promotional_text": (
                    item.promotional_text.strip() or source.promotional_text.strip()
                ),
                "description": description,
                "store_images": _merge_store_images(
                    _images_for_locale(payload, item, uploaded_assets),
                    source_images,
                ),
            }
        )
    return rows


def _images_for_locale(
    payload: MetadataContentSetImport,
    item: LocaleMetadataInput,
    uploaded_assets: dict[str, dict[str, list[dict[str, object]]]],
) -> dict[str, object]:
    locale = item.locale.strip()
    merged = _normalize_store_image_payload(_top_level_images_for_locale(payload, locale))
    merged.update(_normalize_store_image_payload(item.store_images))
    for slot_key, assets in uploaded_assets.get(locale, {}).items():
        slot = dict(merged.get(slot_key) if isinstance(merged.get(slot_key), dict) else {})
        slot["urls"] = _string_list(slot.get("urls"))
        slot["assets"] = _asset_list(slot.get("assets")) + assets
        merged[slot_key] = slot
    return merged


def _top_level_images_for_locale(
    payload: MetadataContentSetImport,
    locale: str,
) -> dict[str, object]:
    raw_images = payload.store_images
    locale_images = raw_images.get(locale)
    if isinstance(locale_images, dict):
        return locale_images
    if any(_normalize_slot_key(key) for key in raw_images):
        return raw_images
    return {}


def _suite_images_for_locale(
    payload: StoreImageSuiteImport,
    item: LocaleStoreImagesInput,
    uploaded_assets: dict[str, dict[str, list[dict[str, object]]]],
) -> dict[str, object]:
    locale = item.locale.strip()
    merged = _normalize_store_image_payload(_suite_top_level_images_for_locale(payload, locale))
    merged.update(_normalize_store_image_payload(item.store_images))
    for slot_key, assets in uploaded_assets.get(locale, {}).items():
        slot = dict(merged.get(slot_key) if isinstance(merged.get(slot_key), dict) else {})
        slot["urls"] = _string_list(slot.get("urls"))
        slot["assets"] = _asset_list(slot.get("assets")) + assets
        merged[slot_key] = slot
    return merged


def _suite_top_level_images_for_locale(
    payload: StoreImageSuiteImport,
    locale: str,
) -> dict[str, object]:
    raw_images = payload.store_images
    locale_images = raw_images.get(locale)
    if isinstance(locale_images, dict):
        return locale_images
    if any(_normalize_slot_key(key) for key in raw_images):
        return raw_images
    return {}


def _marketing_images_for_locale(
    payload: MarketingPageImport,
    locale: str,
    item: MarketingPageLocaleInput | None,
    uploaded_assets: dict[str, dict[str, list[dict[str, object]]]],
) -> dict[str, object]:
    merged = _normalize_store_image_payload(
        _marketing_top_level_images_for_locale(payload, locale)
    )
    if item is not None:
        merged.update(_normalize_store_image_payload(item.store_images))
    for slot_key, assets in uploaded_assets.get(locale, {}).items():
        slot = dict(merged.get(slot_key) if isinstance(merged.get(slot_key), dict) else {})
        slot["urls"] = _string_list(slot.get("urls"))
        slot["assets"] = _asset_list(slot.get("assets")) + assets
        merged[slot_key] = slot
    return merged


def _marketing_top_level_images_for_locale(
    payload: MarketingPageImport,
    locale: str,
) -> dict[str, object]:
    raw_images = payload.store_images
    locale_images = raw_images.get(locale)
    if isinstance(locale_images, dict):
        return locale_images
    if any(_normalize_slot_key(key) for key in raw_images):
        return raw_images
    return {}


def _normalize_store_image_payload(raw_images: dict[str, object] | None) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for raw_key, raw_value in (raw_images or {}).items():
        slot_key = _normalize_slot_key(raw_key)
        if slot_key is None:
            continue
        urls = raw_value.get("urls") if isinstance(raw_value, dict) else raw_value
        assets = raw_value.get("assets") if isinstance(raw_value, dict) else None
        normalized[slot_key] = {
            "urls": _string_list(urls),
            "assets": _asset_list(assets),
        }
    return normalized


def _merge_store_images(
    images: dict[str, object],
    fallback: dict[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = {}
    for slot_key in STORE_IMAGE_SLOT_KEYS:
        current = images.get(slot_key)
        merged[slot_key] = (
            current if _has_store_image_value(current) else fallback.get(slot_key, {})
        )
    return merged


def _has_store_image_value(value: object) -> bool:
    if not isinstance(value, dict):
        return bool(_string_list(value))
    return bool(_string_list(value.get("urls")) or _asset_list(value.get("assets")))


def _normalize_slot_key(raw_key: object) -> str | None:
    return STORE_IMAGE_SLOT_ALIASES.get(str(raw_key or "").strip())


def _unique_non_empty(values: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _string_list(value: object) -> list[str]:
    if isinstance(value, list | tuple):
        raw_values = [str(item or "") for item in value]
    else:
        raw_values = str(value or "").splitlines()
    return [item.strip() for item in raw_values if item.strip()]


def _asset_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list | tuple):
        return []
    return [item for item in value if isinstance(item, dict)]


def _store_image_storage_folder(
    *,
    account_id: str,
    app_id: str,
    version: str,
    content_set_id: str,
    locale: str,
    slot_key: str,
) -> str:
    return "/".join(
        [
            "store-assets",
            _safe_storage_part(account_id),
            _safe_storage_part(app_id),
            _safe_storage_part(content_set_id),
            _safe_storage_part(version),
            _safe_storage_part(locale),
            _safe_storage_part(slot_key),
        ]
    )


def _store_image_suite_storage_folder(
    *,
    account_id: str,
    app_id: str,
    image_suite_id: str,
    locale: str,
    slot_key: str,
) -> str:
    return "/".join(
        [
            "store-assets",
            _safe_storage_part(account_id),
            _safe_storage_part(app_id),
            "image-suites",
            _safe_storage_part(image_suite_id),
            _safe_storage_part(locale),
            _safe_storage_part(slot_key),
        ]
    )


def _normalize_suite_id(value: str | None) -> str:
    normalized = str(value or "").strip()
    return normalized or DEFAULT_CONTENT_SET_ID


def _normalize_suite_name(value: str | None, suite_id: str) -> str:
    normalized = str(value or "").strip()
    if normalized:
        return normalized
    return "默认商店图" if suite_id == DEFAULT_CONTENT_SET_ID else suite_id


def _normalize_source(value: str | None) -> str:
    normalized = str(value or "").strip()
    return normalized or "api"


def _uploaded_asset_count(
    uploaded_assets: dict[str, dict[str, list[dict[str, object]]]],
) -> int:
    return sum(len(assets) for slots in uploaded_assets.values() for assets in slots.values())


def _safe_storage_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return normalized.strip("-") or "default"
