from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

from testflying_api.database import get_db_session
from testflying_api.errors import ApiError
from testflying_api.store_image_requirements import validate_store_image
from testflying_api.store_sync import (
    DEFAULT_CONTENT_SET_ID,
    DEFAULT_CONTENT_SET_NAME,
    DEFAULT_LOCALE,
    save_app_metadata_draft,
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
    version: str
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
        version=payload.version,
        content_set_id=payload.content_set.id,
    )
    rows = _metadata_rows(payload, uploaded_assets)
    for row in rows:
        save_app_metadata_draft(
            session,
            account_id=account_id,
            app_id=app_id,
            version=payload.version,
            locale=row["locale"],
            content_set_id=payload.content_set.id,
            content_set_name=payload.content_set.name,
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


async def _store_image_assets_from_form(
    form: object,
    *,
    request: Request,
    account_id: str,
    app_id: str,
    platform: str,
    version: str,
    content_set_id: str,
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
        stored = request.app.state.artifact_storage.save(
            _store_image_storage_folder(
                account_id=account_id,
                app_id=app_id,
                version=version,
                content_set_id=content_set_id,
                locale=locale,
                slot_key=slot_key,
            ),
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


def _safe_storage_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    return normalized.strip("-") or "default"
